/* ============================================================
 * 舞台演出效果 —— 光束飞行、判定冲击、CONFIRM 闭环、重放残影、震屏
 *
 * 全部效果走**对象池**:演示时 S1–S7 连播会在几秒内抛出几十个光束/冲击波,
 * 若每次都 new Mesh + new Geometry,几何体与材质的创建销毁会直接吃掉帧时间,
 * 而且 GPU 侧还来不及回收(表现为跑完整场后内存曲线只涨不落)。
 * 故每类效果预分配固定数量,用完归还,永不 new。
 *
 * 与「粒子」的分工:本文件管**实体网格**(光束柱、冲击环、电弧线),
 * 细微的飞散颗粒交给 ParticleField —— 网格画轮廓,粒子画质感。
 * ============================================================ */
import {
  AdditiveBlending, BufferAttribute, BufferGeometry, Color, CylinderGeometry, Group,
  IcosahedronGeometry, LineBasicMaterial, LineSegments, Mesh, MeshBasicMaterial,
  Quaternion, RingGeometry, TorusGeometry, Vector3,
} from 'three';
import type { ParticleField } from './particles';
import { pal } from './palette';

const BEAM_POOL = 16;
const RING_POOL = 6;
const ARC_POOL = 4;
const UP = new Vector3(0, 1, 0);

type BeamPhase = 'free' | 'grow' | 'fade';

interface Beam {
  mesh: Mesh;
  head: Mesh;
  phase: BeamPhase;
  t: number;
  /** 飞完全程所需秒数 */
  travel: number;
  fade: number;
  from: Vector3;
  to: Vector3;
  base: Color;
  radius: number;
}

interface Ring {
  mesh: Mesh;
  t: number;
  dur: number;
  from: number;
  to: number;
  y: number;
}

interface Arc {
  lines: LineSegments;
  t: number;
  dur: number;
  origin: Vector3;
}

export interface BeamOpts {
  /** 飞行时长(秒);越短越「急」,长帧用 0.5,加测帧用 0.3 */
  travel?: number;
  intensity?: number;
  /** HDR 倍率作用于粒子 */
  particleCount?: number;
  radius?: number;
}

export class Fx {
  readonly group = new Group();

  private beams: Beam[] = [];
  private rings: Ring[] = [];
  private arcs: Arc[] = [];
  /* CONFIRM 闭环用一对**独立**的环,不复用 rings 池:rings 是水平躺着的
   * (rotation.x=-90°),而闭环必须垂直于走廊、正对光束轴线才读得出「收束」。
   * 用 Group 承载朝向、子网格在本地 XY 平面内自旋 —— 直接改 Mesh 的 rotation
   * 会撞上欧拉角顺序(three 的 'XYZ' 是先绕 X 再绕 Y),两个轴同时设会互相
   * 污染,表现为环面歪着转。 */
  private confirmGroups: Group[] = [];
  private confirmMeshes: Mesh[] = [];
  /* 与光束/环/电弧池同一约定:t === dur 表示「已过期」。
   * 初值曾写成 confirmT = 1 而 confirmDur = 1.7,于是 1 < 1.7 被 stats 判成
   * 「正在播放」—— 刚进页面、一次认证都还没跑,排查快照里的 confirm 就先亮了
   * true。环本身是 visible=false 的,所以画面上看不见;但这份快照存在的意义
   * 就是答辩现场拿它当证据,而它当时在**反向作证**(声称的场景里空无一物)。
   * 故声明顺序也有意让 dur 在前:T 的初值直接引用它,而不是抄一份字面量。 */
  private confirmDur = 1.7;
  private confirmT = this.confirmDur;
  private confirmAt = new Vector3();
  private tmpA = new Vector3();
  private tmpB = new Vector3();
  private q = new Quaternion();

  /** 震屏幅度(世界单位弧度),由 update 指数衰减 */
  private shakeAmp = 0;
  private shakeFreq = 34;
  /** 判定后的「全场呼吸」强度,stage3d 读它去推 Bloom 的强度 */
  bloomBoost = 0;

  private disposables: { dispose(): void }[] = [];

  constructor(private particles: ParticleField) {
    for (let i = 0; i < BEAM_POOL; i++) this.beams.push(this.mkBeam());
    for (let i = 0; i < RING_POOL; i++) this.rings.push(this.mkRing());
    for (let i = 0; i < ARC_POOL; i++) this.arcs.push(this.mkArc());

    const cc = pal();
    const colors = [cc.cyan, cc.green];
    for (let i = 0; i < 2; i++) {
      const g = new Group();
      g.rotation.y = Math.PI / 2;              // 环面法线指向走廊轴(X)
      const geo = new TorusGeometry(1, 0.03, 10, 96);
      const mat = new MeshBasicMaterial({
        color: colors[i].clone().multiplyScalar(2.6),
        transparent: true, opacity: 0, blending: AdditiveBlending, depthWrite: false,
      });
      const m = new Mesh(geo, mat);
      g.add(m);
      g.visible = false;
      this.group.add(g);
      this.confirmGroups.push(g);
      this.confirmMeshes.push(m);
      this.disposables.push(geo, mat);
    }
  }

  /* ---------- 池体构造 ---------- */
  private mkBeam(): Beam {
    // 单位圆柱:半径 1、高 1、轴 +Y,原点居中;用时靠 scale 与四元数摆到任意两点之间
    const geo = new CylinderGeometry(1, 1, 1, 12, 1, true);
    const mat = new MeshBasicMaterial({
      transparent: true, opacity: 0, blending: AdditiveBlending,
      depthWrite: false, side: 2 /* DoubleSide:光束从任何角度都不该消失 */,
    });
    const mesh = new Mesh(geo, mat);
    mesh.visible = false;
    const hgeo = new IcosahedronGeometry(1, 1);
    const hmat = new MeshBasicMaterial({
      transparent: true, opacity: 0, blending: AdditiveBlending, depthWrite: false,
    });
    const head = new Mesh(hgeo, hmat);
    head.visible = false;
    this.group.add(mesh, head);
    this.disposables.push(geo, mat, hgeo, hmat);
    return {
      mesh, head, phase: 'free', t: 0, travel: .45, fade: 0,
      from: new Vector3(), to: new Vector3(), base: new Color(1, 1, 1), radius: .045,
    };
  }

  private mkRing(): Ring {
    const geo = new RingGeometry(0.86, 1, 72);
    const mat = new MeshBasicMaterial({
      transparent: true, opacity: 0, blending: AdditiveBlending,
      depthWrite: false, side: 2,
    });
    const mesh = new Mesh(geo, mat);
    mesh.rotation.x = -Math.PI / 2;
    mesh.visible = false;
    this.group.add(mesh);
    this.disposables.push(geo, mat);
    // 初始 t=dur 即「已过期」:ring() 靠 t>=dur 判空闲,若给 0 则池子里
    // 没有一个可用槽位,第一道冲击环只能抢占 rings[0]
    return { mesh, t: 1, dur: 1, from: 1, to: 10, y: 0 };
  }

  private mkArc(): Arc {
    // 每道电弧 = 5 段折线;顶点位置在触发时随机重排,故容量一次性开好
    const SEG = 5;
    const pos = new Float32Array(SEG * 2 * 3);
    const geo = new BufferGeometry();
    geo.setAttribute('position', new BufferAttribute(pos, 3));
    const mat = new LineBasicMaterial({
      transparent: true, opacity: 0, blending: AdditiveBlending, depthWrite: false,
    });
    const lines = new LineSegments(geo, mat);
    lines.frustumCulled = false;
    lines.visible = false;
    this.group.add(lines);
    this.disposables.push(geo, mat);
    return { lines, t: .6, dur: .6, origin: new Vector3() };
  }

  /* ---------- 光束 ---------- */
  private claimBeam(): Beam {
    let oldest = this.beams[0];
    for (const b of this.beams) {
      if (b.phase === 'free') return b;
      // 全忙时顶掉「最接近结束」的那条(而非固定第一条),避免总是掐掉新光束
      if (b.t / Math.max(0.001, b.travel) > oldest.t / Math.max(0.001, oldest.travel)) oldest = b;
    }
    return oldest;
  }

  /** 发一道定向光束(认证帧)。返回实际使用的飞行时长,供调用方排节奏。 */
  beam(from: Vector3, to: Vector3, color: Color, o: BeamOpts = {}): void {
    const b = this.claimBeam();
    b.from.copy(from);
    b.to.copy(to);
    b.base.copy(color);
    b.travel = o.travel ?? .45;
    b.t = 0;
    b.fade = 0;
    b.phase = 'grow';
    b.mesh.visible = true;
    b.head.visible = true;
    const it = o.intensity ?? 1.9;
    (b.mesh.material as MeshBasicMaterial).color.copy(color).multiplyScalar(it);
    (b.head.material as MeshBasicMaterial).color.copy(color).multiplyScalar(it * 1.6);
    b.head.scale.setScalar(o.radius ?? 0.1);
    b.radius = o.radius ?? .045;

    this.particles.spawnStream(from, to, {
      color, count: o.particleCount ?? 26, size: 0.05,
      life: Math.max(0.35, b.travel * 0.95), intensity: it * 1.2,
      drag: .985, jitter: .35,
    });
  }

  /** EXTRA_CHALLENGE:同一条走廊上分叉三束琥珀光束(§6.3 灰区分叉) */
  grayFork(from: Vector3, to: Vector3, count = 3): void {
    const c = pal();
    const off = [[0, 0], [.34, .22], [-.34, -.22]].slice(0, count);
    for (const [dy, dz] of off) {
      this.tmpA.copy(from);
      this.tmpB.copy(to).add(new Vector3(0, dy, dz));
      this.beam(this.tmpA, this.tmpB, c.auth, {
        travel: .38, intensity: 2.2, particleCount: 18, radius: .085,
      });
    }
  }

  /** 重放嫌疑:把刚才那一帧的路径用琥珀色重演一遍,并留残影 */
  replayGhost(path: { from: Vector3; to: Vector3 } | null): void {
    const c = pal();
    const from = path?.from ?? this.tmpA.set(-6.6, 2.35, 0).clone();
    const to = path?.to ?? this.tmpB.set(6.6, 2.35, 0).clone();
    for (let i = 0; i < 3; i++) {
      const g = new Vector3(0, (i - 1) * 0.16, (i - 1) * 0.1);
      this.beam(
        new Vector3().copy(from).add(g),
        new Vector3().copy(to).add(g),
        c.auth,
        { travel: .35 + i * 0.14, intensity: 1.4 - i * 0.35, particleCount: 12, radius: .075 },
      );
    }
  }

  /* ---------- 判定 ---------- */
  /** 判定时刻的主视觉。at = 无人机位置(判定归属终端) */
  verdict(result: number, at: Vector3, poolAt: Vector3): void {
    const c = pal();
    switch (result) {
      case 0:   // PASS
        this.ring(at, c.green, 0.9, 13, 1.05, at.y + 0.02);
        this.ring(at, c.green, 0.5, 8, 0.75, at.y + 1.5);
        this.particles.burst(at, {
          color: c.green, count: 90, speed: 4.2, size: 0.07,
          life: 1.1, intensity: 1.9, drag: .955, jitter: .3,
        });
        this.shake(0.004);
        this.bloomBoost = 1;
        break;
      case 1:   // REJECT
        this.ring(at, c.red, 0.7, 9, 0.65, at.y + 0.02);
        this.particles.burst(at, {
          color: c.red, count: 70, speed: 3.4, size: 0.065,
          life: .8, intensity: 1.8, drag: .93, jitter: .3,
        });
        this.arcBurst(at, c.red);
        this.shake(0.05);
        this.bloomBoost = 1;
        break;
      case 2:   // ERROR
        this.particles.burst(at, {
          color: c.amber, count: 40, speed: 2.6, size: 0.06,
          life: .7, intensity: 1.5, drag: .92, jitter: .5,
        });
        this.arcBurst(at, c.amber);
        this.shake(0.022);
        break;
      case 3:   // POOL_EMPTY —— 视觉落点在池上,而不是终端上
        this.ring(poolAt, c.auth, 0.8, 7, 0.9, 0.05);
        this.particles.burst(poolAt, {
          color: c.auth, count: 55, speed: 2.2, size: 0.055,
          life: .9, intensity: 1.5, drag: .9, jitter: .4,
        });
        this.shake(0.012);
        break;
      default:  // REPLAY(4)
        this.bloomBoost = 1;
        break;
    }
  }

  /** CONFIRM 双向闭环:一对反向自旋的环自远处收束到走廊中点并保持一拍 */
  confirmClose(at: Vector3): void {
    const c = pal();
    this.confirmAt.copy(at);
    this.confirmT = 0;
    for (const g of this.confirmGroups) g.visible = true;
    this.particles.burst(at, {
      color: c.cyan, count: 46, speed: 1.6, size: 0.055,
      life: .8, intensity: 1.7, drag: .9, jitter: .3,
    });
    this.particles.spawnStream(
      new Vector3(at.x - 1.6, at.y, at.z), new Vector3(at.x + 1.6, at.y, at.z),
      { color: c.green, count: 34, size: 0.05, life: .8, intensity: 1.8, drag: .97, jitter: .25 },
    );
    this.bloomBoost = Math.max(this.bloomBoost, 0.85);
  }

  /** 电弧干扰 */
  arcBurst(origin: Vector3, color: Color): void {
    let used = 0;
    for (const a of this.arcs) {
      if (a.t < a.dur) continue;
      a.origin.copy(origin);
      a.t = 0;
      // 逐段随机:前半段从 origin 出发向外,后半段乱窜 —— 纯随机会像一团线球
      const attr = a.lines.geometry.getAttribute('position') as BufferAttribute;
      const arr = attr.array as Float32Array;
      for (let s = 0; s < 5; s++) {
        const k = s * 6;
        if (s === 0) {
          arr[k] = origin.x; arr[k + 1] = origin.y; arr[k + 2] = origin.z;
        } else {
          arr[k] = arr[k - 6]; arr[k + 1] = arr[k - 5]; arr[k + 2] = arr[k - 4];
        }
        arr[k + 3] = arr[k] + (Math.random() - 0.5) * 2.6;
        arr[k + 4] = arr[k + 1] + (Math.random() - 0.5) * 2.2;
        arr[k + 5] = arr[k + 2] + (Math.random() - 0.5) * 2.6;
      }
      attr.needsUpdate = true;
      (a.lines.material as LineBasicMaterial).color.copy(color).multiplyScalar(2.1);
      a.dur = .35 + Math.random() * .45;
      a.lines.visible = true;
      if (++used >= 2) break;         // 一次最多两道,多了就成噪点
    }
  }

  /** 冲击环 */
  ring(at: Vector3, color: Color, from: number, to: number, dur: number, y: number): void {
    let r: Ring | null = null;
    for (const c of this.rings) if (c.t >= c.dur) { r = c; break; }
    if (!r) r = this.rings[0];
    r.t = 0; r.dur = dur; r.from = from; r.to = to; r.y = y;
    r.mesh.position.set(at.x, y, at.z);
    r.mesh.scale.setScalar(from);
    r.mesh.visible = true;
    (r.mesh.material as MeshBasicMaterial).color.copy(color).multiplyScalar(2.4);
  }

  shake(amp: number): void {
    this.shakeAmp = Math.max(this.shakeAmp, amp);
  }

  /** 把震屏偏移写进传入的四元数/欧拉量的形式:返回 [rotX, rotZ] */
  shakeOffset(t: number): [number, number] {
    if (this.shakeAmp < 1e-5) return [0, 0];
    const a = this.shakeAmp;
    return [
      Math.sin(t * this.shakeFreq) * a,
      Math.cos(t * this.shakeFreq * 1.37) * a,
    ];
  }

  update(dt: number): void {
    // 光束:飞行 → 命中 → 衰减
    for (const b of this.beams) {
      if (b.phase === 'free') continue;
      if (b.phase === 'grow') {
        b.t += dt / b.travel;
        if (b.t >= 1) {
          b.t = 1;
          b.phase = 'fade';
          b.fade = 1;
          // 命中闪光:把终点处粒子重炸一次,「打上了」才有实感
          this.particles.burst(b.to, {
            color: b.base, count: 22, speed: 1.9, size: 0.06,
            life: .5, intensity: 2.0, drag: .9, jitter: .3,
          });
        }
        const p = easeOut(b.t);
        this.tmpA.copy(b.from).lerp(b.to, p);
        this.placeBeam(b, b.from, this.tmpA, b.t < 1);
      } else {
        b.fade -= dt / 0.42;
        if (b.fade <= 0) {
          b.phase = 'free';
          b.mesh.visible = false;
          b.head.visible = false;
          continue;
        }
        this.placeBeam(b, b.from, b.to, false);
        const f = b.fade * b.fade;
        (b.mesh.material as MeshBasicMaterial).opacity = f * .85;
        (b.head.material as MeshBasicMaterial).opacity = f;
      }
    }

    // 冲击环
    for (const r of this.rings) {
      if (r.t >= r.dur) { if (r.mesh.visible) r.mesh.visible = false; continue; }
      r.t += dt;
      const u = Math.min(1, r.t / r.dur);
      r.mesh.scale.setScalar(r.from + (r.to - r.from) * easeOut(u));
      (r.mesh.material as MeshBasicMaterial).opacity = (1 - u) * (1 - u) * .95;
    }

    // 电弧
    for (const a of this.arcs) {
      if (a.t >= a.dur) { if (a.lines.visible) a.lines.visible = false; continue; }
      a.t += dt;
      (a.lines.material as LineBasicMaterial).opacity = (1 - a.t / a.dur) * .9;
    }

    // CONFIRM 闭环:收束(0–45%)→ 保持并自旋(45–72%)→ 淡出(72–100%)
    if (this.confirmT < this.confirmDur) {
      this.confirmT += dt;
      const u = Math.min(1, this.confirmT / this.confirmDur);
      const scale = u < .45 ? 3.2 + (0.62 - 3.2) * easeOut(u / .45) : 0.62;
      const alpha = u < .72 ? Math.min(1, u / .16) : 1 - (u - .72) / .28;
      for (let i = 0; i < this.confirmGroups.length; i++) {
        const g = this.confirmGroups[i];
        g.position.set(this.confirmAt.x + (i === 0 ? -0.45 : 0.45), this.confirmAt.y, this.confirmAt.z);
        g.scale.setScalar(scale);
        // 两环反向自旋 —— 同向转会像一枚环在晃,反向才读得出「双向」
        this.confirmMeshes[i].rotation.z = (i === 0 ? 1 : -1) * this.confirmT * 1.9;
        (this.confirmMeshes[i].material as MeshBasicMaterial).opacity = Math.max(0, alpha) * .95;
      }
      if (u >= 1) for (const g of this.confirmGroups) g.visible = false;
    }

    // 震屏与呼吸脉冲的衰减
    this.shakeAmp *= Math.pow(0.02, dt);
    this.bloomBoost = Math.max(0, this.bloomBoost - dt * 0.85);
  }

  /** 把单位圆柱摆到 a→b 之间:位置取中点、朝向取轴向、Y 向缩放取长度。
   *  keepHead=true 时同时把头部球推到 b。 */
  private placeBeam(b: Beam, a: Vector3, to: Vector3, keepHead: boolean): void {
    const dir = this.tmpB.subVectors(to, a);
    const len = dir.length();
    if (len < 1e-5) { b.mesh.visible = false; return; }
    dir.divideScalar(len);
    b.mesh.position.copy(a).addScaledVector(dir, len / 2);
    this.q.setFromUnitVectors(UP, dir);
    b.mesh.quaternion.copy(this.q);
    b.mesh.scale.set(b.radius, len, b.radius);
    b.mesh.visible = true;
    (b.mesh.material as MeshBasicMaterial).opacity = .9;
    if (keepHead) b.head.position.copy(to);
  }

  /** 池内占用读数(排查用:演示现场可据此确认「光束真的发出了」) */
  get stats(): { beams: number; rings: number; arcs: number; confirm: boolean } {
    let beams = 0, rings = 0, arcs = 0;
    for (const b of this.beams) if (b.phase !== 'free') beams++;
    for (const r of this.rings) if (r.t < r.dur) rings++;
    for (const a of this.arcs) if (a.t < a.dur) arcs++;
    return { beams, rings, arcs, confirm: this.confirmT < this.confirmDur };
  }

  reset(): void {
    for (const b of this.beams) {
      b.phase = 'free'; b.t = 0; b.fade = 0;
      b.mesh.visible = false; b.head.visible = false;
    }
    for (const r of this.rings) { r.t = r.dur; r.mesh.visible = false; }
    for (const a of this.arcs) { a.t = a.dur; a.lines.visible = false; }
    this.confirmT = this.confirmDur;
    for (const g of this.confirmGroups) g.visible = false;
    this.particles.clear();
    this.shakeAmp = 0;
    this.bloomBoost = 0;
  }

  dispose(): void {
    for (const d of this.disposables) d.dispose();
    this.disposables = [];
    this.group.clear();
  }
}

/** easeOutCubic:光束头部出膛快、到位慢,比匀速更有「被推进」的力感 */
function easeOut(u: number): number {
  const x = 1 - Math.min(1, Math.max(0, u));
  return 1 - x * x * x;
}
