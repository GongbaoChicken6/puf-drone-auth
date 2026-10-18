/* ============================================================
 * 认证舞台的世界本体 —— 基站 ⇄ 无人机 ⇄ PUF 指纹场 ⇄ CRP 池
 *
 * 场景叙事的落位(为什么是这个布局):
 *   基站(x−7)在左、无人机(x+7)在右,二者之间留一条 14 单位宽的走廊;
 *   全部认证帧都沿这条走廊飞,于是「左右」天然表达「谁发给谁」——
 *   不需要额外图例解释方向。
 *   PUF 指纹场悬在无人机正上方:它是**这台终端自己的**硬件属性,
 *   挂在终端头顶比放在场景中央更不容易被误解成公共资源。
 *   CRP 池在基站脚下偏外侧:池是基站侧的资源,正下方会被塔身挡住。
 *
 * 全部颜色经 palette 取自 tokens.css,本文件不写死任何色值(§4.1)。
 * ============================================================ */
import {
  AdditiveBlending, AmbientLight, BoxGeometry, BufferAttribute, BufferGeometry, Color,
  CylinderGeometry, DirectionalLight, DoubleSide, DynamicDrawUsage, Fog, GridHelper, Group,
  IcosahedronGeometry, InstancedMesh, Matrix4, Mesh, MeshBasicMaterial, MeshStandardMaterial,
  Object3D, PlaneGeometry, PointLight, Points, PointsMaterial, RingGeometry, Scene,
  Texture, TorusGeometry, Vector3,
} from 'three';
import { Label, pal } from './palette';

/* ---------- 场景锚点(单位:1 ≈ 1m) ---------- */
export const ANCHOR = {
  station: new Vector3(-7, 0, 0),
  drone: new Vector3(7, 1.85, 0),
  /** PUF 指纹底板的世界高度(柱体自该处向上生长) */
  fingerY: 3.62,
  /** 认证走廊的轴线高度 —— 全部光束沿此高度飞行 */
  corridorY: 2.35,
  pool: new Vector3(-9.35, 0, 1.9),
};

export const BITS = 64;
const FP_DIM = 8;                    // 8×8 = 64 位
const FP_PITCH = 0.30;               // 柱间距
const FP_TALL = 0.92;                // 稳定位柱高
const FP_STUB = 0.26;                // 不稳定位残桩高
const POOL_H = 1.7;                  // 池体高度(水位按 pct 缩放到此高度)

export interface CamPreset {
  key: string;
  label: string;
  pos: Vector3;
  target: Vector3;
}

/* 相机预设 —— 快捷键 1–4(与顶栏提示一致)。
 * 每个预设对应答辩时的一种叙事:全貌 / 看终端 / 看指纹 / 看数据流全局。 */
export const CAM_PRESETS: CamPreset[] = [
  { key: '1', label: '全景', pos: new Vector3(0.5, 9.5, 20.5), target: new Vector3(0, 2.5, 0) },
  { key: '2', label: '跟踪终端', pos: new Vector3(13.2, 4.4, 7.2), target: new Vector3(6.9, 2.4, 0) },
  { key: '3', label: '指纹特写', pos: new Vector3(7.4, 4.35, 5.2), target: new Vector3(7, 4.0, 0) },
  { key: '4', label: '俯瞰', pos: new Vector3(0.6, 20.5, 4.2), target: new Vector3(0, 0.4, 0) },
];

export class World {
  readonly root = new Group();
  readonly scene = new Scene();

  private pillarMesh!: InstancedMesh;
  private plate!: Mesh;
  private fpLabel: Label;
  private droneGroup = new Group();
  private droneLabel: Label;
  private beacon!: Mesh;
  private rings: Mesh[] = [];
  private rotors: Mesh[] = [];
  private droneHalo!: Mesh;
  private droneLight!: PointLight;
  private poolFill!: Mesh;
  private poolRing!: Mesh;
  private poolLabel: Label;
  private poolPts!: Points;
  private poolPos!: Float32Array;
  private poolCol!: Float32Array;
  private poolPct = 0;                 // 显示值(向 poolTarget 缓动)
  private poolTarget = 0;
  private poolWarn = false;
  private stars!: Points;

  /** 每颗指纹柱的状态,update 里做闪烁配色 */
  private fpBit = new Uint8Array(BITS);
  private fpStable = new Uint8Array(BITS);
  private fpHasData = false;
  private matrix = new Matrix4();
  private dummy = new Object3D();
  private flickerAcc = 0;
  private labels: Label[] = [];
  private disposables: { dispose(): void }[] = [];

  constructor() {
    const c = pal();
    this.scene.background = new Color(c.bg);
    /* 雾:近端必须大于「全景相机到场景中心的距离」(≈22.2),
     * 否则默认视角下整个场景被雾吃掉;34 是让中心清晰、只把远处地面网格
     * 边缘淡出的取值。 */
    this.scene.fog = new Fog(c.bg.getHex(), 34, 100);
    this.root.name = 'world';
    this.scene.add(this.root);

    this.buildStars();
    this.buildGround();
    this.buildStation();
    this.droneGroup = this.buildDrone();
    this.buildFingerprint();
    this.buildPool();

    this.fpLabel = this.mkLabel('PUF 指纹 · 未注册', 'puf', 0.42,
      new Vector3(ANCHOR.drone.x, ANCHOR.fingerY + FP_TALL + 0.68, 0));
    this.droneLabel = this.mkLabel('无人机 · 未选中', 'comm', 0.34,
      new Vector3(ANCHOR.drone.x, 1.02, 0));
    this.poolLabel = this.mkLabel('CRP 池 —', 'green', 0.32,
      new Vector3(ANCHOR.pool.x, 2.3, ANCHOR.pool.z));
    this.mkLabel('基站 · 认证服务', 'server', 0.34, new Vector3(ANCHOR.station.x, 4.35, 0));

    this.buildLights();
    this.applyFingerprint(null, null);
    this.setPool(0, false, null, null);
  }

  private mkLabel(text: string, color: Parameters<Label['set']>[1], size: number, at: Vector3): Label {
    const l = new Label(text, { size, color });
    l.object.position.copy(at);
    this.root.add(l.object);
    this.labels.push(l);
    return l;
  }

  /** IBL 环境贴图(由 stage3d 用 PMREMGenerator 生成后注入)。
   *  金属材质没有环境贴图会渲染成近黑色,这是「塔身像被挖空」的常见成因。 */
  setEnvironment(tex: Texture, intensity: number): void {
    this.scene.environment = tex;
    this.scene.environmentIntensity = intensity;
  }

  /* ---------- 星空 ---------- */
  private buildStars(): void {
    const n = 1100;
    const pos = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      // 只在上半球壳撒星:星星出现在地平线以下是穿帮
      const z = Math.random();
      const a = Math.random() * Math.PI * 2;
      const r = Math.sqrt(Math.max(0, 1 - z * z));
      const R = 90 + Math.random() * 70;
      pos[i * 3] = r * Math.cos(a) * R;
      pos[i * 3 + 1] = z * R * 0.85 + 4;
      pos[i * 3 + 2] = r * Math.sin(a) * R;
    }
    const g = new BufferGeometry();
    g.setAttribute('position', new BufferAttribute(pos, 3));
    const m = new PointsMaterial({
      color: pal().muted, size: 0.55, sizeAttenuation: true,
      transparent: true, opacity: 0.5, depthWrite: false,
      blending: AdditiveBlending, fog: false,
    });
    this.stars = new Points(g, m);
    this.stars.frustumCulled = false;
    this.root.add(this.stars);
    this.disposables.push(g, m);
  }

  /* ---------- 地面 ---------- */
  private buildGround(): void {
    const c = pal();
    const floor = new Mesh(
      new PlaneGeometry(260, 260),
      new MeshStandardMaterial({ color: c.bg2, roughness: .97, metalness: .06 }),
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -0.02;
    this.root.add(floor);
    this.disposables.push(floor.geometry, floor.material as MeshStandardMaterial);

    /* 网格线用 dim 派生而非 border:border/border2 自 R1 起是带 alpha 的发丝线
     * (rgba),THREE.Color 解析会丢掉 alpha 只剩亮长春花色,网格就从「退后的
     * 空间参照」变成「发光的亮网」。dim 是实色灰蓝,乘 0.55 当普通格线,
     * 整体不透明度也压到 0.32 —— 网格的任务是给尺度感,不是被看见。 */
    const grid = new GridHelper(64, 64, c.dim.getHex(), c.dim.clone().multiplyScalar(0.55).getHex());
    grid.position.y = 0.002;
    grid.material.transparent = true;
    grid.material.opacity = 0.32;
    this.root.add(grid);
    this.disposables.push(grid.geometry, grid.material);

    // 两个地标环:暗示「这两点才是舞台主角」,其余网格只是空间参照
    const pad = (x: number, color: Color, r: number) => {
      const m = new Mesh(
        new RingGeometry(r, r + 0.06, 64),
        new MeshBasicMaterial({
          color, transparent: true, opacity: .5,
          blending: AdditiveBlending, depthWrite: false,
        }),
      );
      m.rotation.x = -Math.PI / 2;
      m.position.set(x, 0.012, 0);
      this.root.add(m);
      this.disposables.push(m.geometry, m.material as MeshBasicMaterial);
    };
    pad(ANCHOR.station.x, c.server, 1.6);
    pad(ANCHOR.drone.x, c.comm, 1.25);
  }

  /* ---------- 基站 ---------- */
  private buildStation(): Group {
    const c = pal();
    const g = new Group();
    g.position.copy(ANCHOR.station);

    const body = new MeshStandardMaterial({
      color: c.bg3, roughness: .32, metalness: .85,
      emissive: c.server, emissiveIntensity: .05,
    });
    const trim = new MeshStandardMaterial({
      color: c.server, roughness: .3, metalness: .25,
      emissive: c.server, emissiveIntensity: .8,
    });
    this.disposables.push(body, trim);

    const add = (geo: BufferGeometry, mat: MeshStandardMaterial, y: number): Mesh => {
      const m = new Mesh(geo, mat);
      m.position.y = y;
      g.add(m);
      this.disposables.push(geo);
      return m;
    };

    add(new CylinderGeometry(1.35, 1.55, 0.24, 6), body, 0.12);
    add(new CylinderGeometry(0.5, 0.66, 3.0, 6), body, 1.7);
    add(new CylinderGeometry(0.66, 0.5, 0.34, 6), trim, 3.37);
    add(new CylinderGeometry(0.05, 0.05, 1.0, 8), trim, 4.05);
    this.beacon = add(new IcosahedronGeometry(0.19, 1), trim, 4.6);

    // 三道环绕环:静止塔身 + 转动环 = 「系统在运转」的最低成本表达
    for (let i = 0; i < 3; i++) {
      const m = new Mesh(
        new TorusGeometry(0.95 + i * 0.22, 0.022, 8, 72),
        new MeshBasicMaterial({
          color: c.server, transparent: true, opacity: .55,
          blending: AdditiveBlending, depthWrite: false,
        }),
      );
      m.position.y = 1.05 + i * 0.95;
      m.rotation.set(Math.PI / 2 + (i - 1) * 0.22, i * 0.4, 0);
      g.add(m);
      this.rings.push(m);
      this.disposables.push(m.geometry, m.material as MeshBasicMaterial);
    }

    // 朝向走廊的收发环:认证帧从这里进出,给光束一个「发射口」
    const xc = new Mesh(
      new TorusGeometry(0.34, 0.05, 10, 40),
      new MeshBasicMaterial({
        color: c.cyan, transparent: true, opacity: .8,
        blending: AdditiveBlending, depthWrite: false,
      }),
    );
    xc.position.set(0.78, ANCHOR.corridorY, 0);
    xc.rotation.y = Math.PI / 2;
    g.add(xc);
    this.disposables.push(xc.geometry, xc.material as MeshBasicMaterial);

    this.root.add(g);
    return g;
  }

  /* ---------- 无人机 ---------- */
  private buildDrone(): Group {
    const c = pal();
    const g = new Group();
    g.position.copy(ANCHOR.drone);

    const shell = new MeshStandardMaterial({
      color: c.bg3, roughness: .3, metalness: .88,
      emissive: c.comm, emissiveIntensity: .07,
    });
    const glow = new MeshStandardMaterial({
      color: c.comm, roughness: .25, metalness: .3,
      emissive: c.comm, emissiveIntensity: .95,
    });
    this.disposables.push(shell, glow);

    const core = new Mesh(new BoxGeometry(0.62, 0.2, 0.62), shell);
    const cap = new Mesh(new BoxGeometry(0.42, 0.1, 0.42), glow);
    cap.position.y = 0.13;
    g.add(core, cap);
    this.disposables.push(core.geometry, cap.geometry);

    // 四条支臂 + 旋翼(旋翼盘半透明,只有转起来才像在转)
    for (let i = 0; i < 4; i++) {
      const a = Math.PI / 4 + (i * Math.PI) / 2;
      const dx = Math.cos(a), dz = Math.sin(a);
      const arm = new Mesh(new BoxGeometry(0.62, 0.05, 0.09), shell);
      arm.position.set(dx * 0.4, 0, dz * 0.4);
      arm.rotation.y = -a;
      g.add(arm);
      this.disposables.push(arm.geometry);

      const rotor = new Mesh(
        new CylinderGeometry(0.36, 0.36, 0.012, 24),
        new MeshBasicMaterial({
          color: c.comm, transparent: true, opacity: .3,
          blending: AdditiveBlending, depthWrite: false,
        }),
      );
      rotor.position.set(dx * 0.72, 0.09, dz * 0.72);
      g.add(rotor);
      this.rotors.push(rotor);
      this.disposables.push(rotor.geometry, rotor.material as MeshBasicMaterial);
    }

    // 桅杆把收发点抬到走廊高度,使光束两端等高(斜射看起来像打歪了)
    const mast = new Mesh(new CylinderGeometry(0.028, 0.028, 0.62, 8), glow);
    mast.position.y = 0.35;
    const tip = new Mesh(new IcosahedronGeometry(0.09, 1), glow);
    tip.position.y = 0.5;
    g.add(mast, tip);
    this.disposables.push(mast.geometry, tip.geometry);

    // 机身下投光斑:消除「悬空方块」感
    const halo = new Mesh(
      new RingGeometry(0.7, 1.05, 48),
      new MeshBasicMaterial({
        color: c.comm, transparent: true, opacity: .22,
        blending: AdditiveBlending, depthWrite: false,
      }),
    );
    halo.rotation.x = -Math.PI / 2;
    halo.position.y = -ANCHOR.drone.y + 0.02;
    g.add(halo);
    this.droneHalo = halo;
    this.disposables.push(halo.geometry, halo.material as MeshBasicMaterial);

    const pl = new PointLight(c.comm, 26, 14, 2);
    pl.position.y = 0.2;
    g.add(pl);
    this.droneLight = pl;

    this.root.add(g);
    return g;
  }

  /* ---------- PUF 指纹场(8×8 全息柱阵) ---------- */
  private buildFingerprint(): void {
    const c = pal();
    const span = (FP_DIM - 1) * FP_PITCH;
    const plateSize = span + 0.72;

    this.plate = new Mesh(
      new BoxGeometry(plateSize, 0.06, plateSize),
      new MeshStandardMaterial({
        color: c.bg3, roughness: .45, metalness: .65,
        emissive: c.puf, emissiveIntensity: .04,
      }),
    );
    this.plate.position.set(ANCHOR.drone.x, ANCHOR.fingerY - 0.05, 0);
    this.root.add(this.plate);
    this.disposables.push(this.plate.geometry, this.plate.material as MeshStandardMaterial);

    /* 柱体用**不受光材质**:它们是全息投影,不是实体。另有一个实际好处 ——
     * 64 根柱子若走 PBR 就要各自参与光照,而这里观感几乎全靠 Bloom 的辉光;
     * Basic 材质在 HDR 下直接输出高亮色,辉光更干净、也更省。 */
    const geo = new BoxGeometry(0.2, 1, 0.2);
    // 几何体原点移到底面:实例矩阵只需按高度缩放,不必再补半高偏移
    geo.translate(0, 0.5, 0);
    this.pillarMesh = new InstancedMesh(
      geo, new MeshBasicMaterial({ transparent: true, opacity: .92 }), FP_DIM * FP_DIM,
    );
    this.pillarMesh.instanceMatrix.setUsage(DynamicDrawUsage);
    this.pillarMesh.position.set(ANCHOR.drone.x, ANCHOR.fingerY, 0);
    this.root.add(this.pillarMesh);
    this.disposables.push(geo, this.pillarMesh.material as MeshBasicMaterial);

    const edge = new Mesh(
      new BoxGeometry(plateSize, 0.001, plateSize),
      new MeshBasicMaterial({
        color: c.puf, transparent: true, opacity: .16,
        blending: AdditiveBlending, depthWrite: false,
      }),
    );
    edge.position.copy(this.plate.position);
    edge.position.y += 0.035;
    this.root.add(edge);
    this.disposables.push(edge.geometry, edge.material as MeshBasicMaterial);
  }

  /** 更新指纹柱阵。传 null 表示**没有数据**(未注册 / 未取到模板)——
   *  此时 64 根柱子一律等高暗桩并显式标注「未注册」,
   *  绝不用合成图案冒充硬件指纹(§4.4)。 */
  applyFingerprint(respHex: string | null, mask: string | null): void {
    const c = pal();
    const bitStr = respHex ? hexBits(respHex) : '';
    const has = bitStr.length >= BITS;
    this.fpHasData = has;
    const realMask = mask && mask.length >= BITS;
    for (let i = 0; i < BITS; i++) {
      this.fpBit[i] = has && bitStr[i] === '1' ? 1 : 0;
      this.fpStable[i] = realMask ? (mask[i] === '1' ? 1 : 0) : 0;
    }

    for (let i = 0; i < BITS; i++) {
      const row = Math.floor(i / FP_DIM), col = i % FP_DIM;
      this.dummy.position.set(
        -((FP_DIM - 1) * FP_PITCH) / 2 + col * FP_PITCH, 0,
        -((FP_DIM - 1) * FP_PITCH) / 2 + row * FP_PITCH,
      );
      this.dummy.scale.set(1, !has ? 0.3 : (this.fpStable[i] ? FP_TALL : FP_STUB), 1);
      this.dummy.rotation.set(0, 0, 0);
      this.dummy.updateMatrix();
      this.matrix.copy(this.dummy.matrix);
      this.pillarMesh.setMatrixAt(i, this.matrix);
      this.pillarMesh.setColorAt(i, this.pillarColor(i, c));
    }
    this.pillarMesh.instanceMatrix.needsUpdate = true;
    if (this.pillarMesh.instanceColor) this.pillarMesh.instanceColor.needsUpdate = true;

    const stable = has ? this.fpStable.reduce((a, b) => a + b, 0) : 0;
    this.fpLabel.set(has ? `PUF 指纹 · ${stable}/64 稳定` : 'PUF 指纹 · 未注册', 'puf');
  }

  private pillarColor(i: number, c: ReturnType<typeof pal>): Color {
    const base = this.fpHasData ? (this.fpStable[i] ? c.green : c.red) : c.muted;
    // 亮度编码位值(1 亮 / 0 暗),色相与柱高编码可靠性 —— 两个维度各自独立,不互相冒充
    const dim = this.fpBit[i] ? 1 : 0.3;
    const k = this.fpHasData ? (this.fpStable[i] ? 1.5 : 0.85) : 0.42;
    return base.clone().multiplyScalar(dim * k);
  }

  /* ---------- CRP 池 ---------- */
  private buildPool(): Group {
    const c = pal();
    const g = new Group();
    g.position.copy(ANCHOR.pool);

    const shell = new Mesh(
      new CylinderGeometry(1.0, 1.0, POOL_H, 40, 1, true),
      new MeshBasicMaterial({
        color: c.auth, transparent: true, opacity: .2,
        side: DoubleSide, blending: AdditiveBlending, depthWrite: false,
      }),
    );
    shell.position.y = POOL_H / 2;
    g.add(shell);
    this.disposables.push(shell.geometry, shell.material as MeshBasicMaterial);

    // 填充体:高度即水位。不受光 + 加色,读数比实体柱清晰
    this.poolFill = new Mesh(
      new CylinderGeometry(0.94, 0.94, 1, 32, 1, true),
      new MeshBasicMaterial({
        color: c.auth, transparent: true, opacity: .3,
        side: DoubleSide, blending: AdditiveBlending, depthWrite: false,
      }),
    );
    g.add(this.poolFill);
    this.disposables.push(this.poolFill.geometry, this.poolFill.material as MeshBasicMaterial);

    this.poolRing = new Mesh(
      new RingGeometry(0.94, 1.02, 40),
      new MeshBasicMaterial({
        color: c.auth, transparent: true, opacity: .9,
        blending: AdditiveBlending, depthWrite: false, side: DoubleSide,
      }),
    );
    this.poolRing.rotation.x = -Math.PI / 2;
    g.add(this.poolRing);
    this.disposables.push(this.poolRing.geometry, this.poolRing.material as MeshBasicMaterial);

    const base = new Mesh(
      new CylinderGeometry(1.12, 1.2, 0.12, 40),
      new MeshStandardMaterial({ color: c.bg3, roughness: .5, metalness: .6 }),
    );
    base.position.y = 0.06;
    g.add(base);
    this.disposables.push(base.geometry, base.material as MeshStandardMaterial);

    /* 池内悬浮粒子。给每颗粒子一个固定相位,让它们缓慢涡旋 ——
     * 纯静态分布看起来就是「一坨点」,涡旋才读得出是流体。 */
    const n = 360;
    this.poolPos = new Float32Array(n * 3);
    this.poolCol = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const a = Math.random() * Math.PI * 2;
      const r = Math.sqrt(Math.random()) * 0.88;
      this.poolPos[i * 3] = Math.cos(a) * r;
      this.poolPos[i * 3 + 1] = Math.random() * POOL_H;
      this.poolPos[i * 3 + 2] = Math.sin(a) * r;
    }
    const pg = new BufferGeometry();
    pg.setAttribute('position', new BufferAttribute(this.poolPos, 3));
    pg.setAttribute('color', new BufferAttribute(this.poolCol, 3));
    const pm = new PointsMaterial({
      size: 0.06, sizeAttenuation: true, vertexColors: true,
      transparent: true, opacity: .95, depthWrite: false, blending: AdditiveBlending,
    });
    this.poolPts = new Points(pg, pm);
    this.poolPts.frustumCulled = false;
    g.add(this.poolPts);
    this.disposables.push(pg, pm);

    this.root.add(g);
    return g;
  }

  /** 更新池水位。pct 为 0–100;warn 由 pool.warning / 低水位触发,只影响配色。 */
  setPool(pct: number, warn: boolean, remaining: number | null, size: number | null): void {
    this.poolTarget = Math.max(0, Math.min(100, pct)) / 100;
    const warnChanged = this.poolWarn !== warn;
    this.poolWarn = warn;
    this.poolLabel.set(
      (remaining != null && size != null ? `CRP 池 ${remaining}/${size}` : 'CRP 池 —') + (warn ? ' ⚠' : ''),
      warn ? 'auth' : 'green',
    );
    // 标签重绘很贵,但配色只在告警态翻转时才需要重算粒子色
    if (warnChanged) this.recolorPool();
  }

  private recolorPool(): void {
    const c = pal();
    const col = this.poolWarn ? c.auth : c.green;
    (this.poolFill.material as MeshBasicMaterial).color.copy(col);
    (this.poolRing.material as MeshBasicMaterial).color.copy(col);
    const k = this.poolWarn ? 1.8 : 1.2;
    for (let i = 0; i < this.poolCol.length; i += 3) {
      this.poolCol[i] = col.r * k;
      this.poolCol[i + 1] = col.g * k;
      this.poolCol[i + 2] = col.b * k;
    }
    (this.poolPts.geometry.getAttribute('color') as BufferAttribute).needsUpdate = true;
  }

  /** 链路连通性。「终端失联」只压暗机身光效,不做额外提示 ——
   *  链路状态的第一读数在顶栏徽章上,3D 这里只是让画面不撒谎:
   *  联系不上了,终端就不该还亮着。 */
  setLinkOk(ok: boolean): void {
    this.droneHalo.visible = ok;
    this.droneLight.intensity = ok ? 26 : 6;
  }

  /** 指纹阵读数(排查用) */
  fingerprintInfo(): { hasData: boolean; stable: number } {
    let s = 0;
    for (let i = 0; i < BITS; i++) if (this.fpStable[i]) s++;
    return { hasData: this.fpHasData, stable: this.fpHasData ? s : 0 };
  }

  setTerminalLabel(tid: number | null): void {
    this.droneLabel.set(tid == null ? '无人机 · 未选中' : `无人机 · tid ${tid}`, 'comm');
  }

  /* ---------- 灯光 ----------
   * three r155+ 一律用物理光照单位(PointLight 的 intensity 是坎德拉,
   * 衰减为 1/d²)。故这几个值看着偏大是正常的:在 5 单位距离上,
   * intensity 50 大约等效于旧照度模型的 2。 */
  private buildLights(): void {
    const c = pal();
    this.root.add(new AmbientLight(c.bg3, 0.55));

    const key = new DirectionalLight(c.text, 1.5);
    key.position.set(5, 16, 11);
    this.root.add(key);

    const st = new PointLight(c.server, 58, 30, 2);
    st.position.set(ANCHOR.station.x, 4.6, 0);
    this.root.add(st);

    const poolLight = new PointLight(c.auth, 15, 12, 2);
    poolLight.position.set(ANCHOR.pool.x, 1.2, ANCHOR.pool.z);
    this.root.add(poolLight);
  }

  /* ---------- 每帧 ---------- */
  /** 返回「本帧是否有变化」——静止渲染模式据此决定要不要重绘 */
  update(dt: number, t: number): boolean {
    // 无人机悬停:正弦上下 + 极缓俯仰摆动
    this.droneGroup.position.y = ANCHOR.drone.y + Math.sin(t * 1.15) * 0.09;
    this.droneGroup.rotation.z = Math.sin(t * 0.7) * 0.035;
    this.droneGroup.rotation.x = Math.cos(t * 0.55) * 0.03;
    for (const r of this.rotors) r.rotation.y = t * 26;

    // 指纹阵缓慢自转:静止画面里也能读出 8×8 的立体感
    this.pillarMesh.rotation.y = Math.sin(t * 0.22) * 0.28;
    this.plate.rotation.y = this.pillarMesh.rotation.y;

    // 不稳定柱闪烁。12Hz 更新一次即可 —— 每帧改实例色会把整块
    // instanceColor 重传,而闪烁本身在人眼里也不到 12Hz
    this.flickerAcc += dt;
    if (this.fpHasData && this.flickerAcc > 1 / 12) {
      this.flickerAcc = 0;
      const c = pal();
      for (let i = 0; i < BITS; i++) {
        if (this.fpStable[i]) continue;
        this.pillarMesh.setColorAt(i, this.pillarColor(i, c).multiplyScalar(0.55 + Math.random() * 0.75));
      }
      if (this.pillarMesh.instanceColor) this.pillarMesh.instanceColor.needsUpdate = true;
    }

    for (let i = 0; i < this.rings.length; i++) this.rings[i].rotation.z += dt * (0.28 + i * 0.16);
    (this.beacon.material as MeshStandardMaterial).emissiveIntensity =
      0.5 + (0.55 + 0.45 * Math.sin(t * 2.1)) * 1.6;

    // 池水位缓动:突降会让 S5「抽干」失去过程感
    const d = this.poolTarget - this.poolPct;
    if (Math.abs(d) > 0.0015) this.poolPct += d * Math.min(1, dt * 3.2);
    else this.poolPct = this.poolTarget;
    this.poolFill.scale.set(1, Math.max(0.001, this.poolPct), 1);
    this.poolFill.position.y = (POOL_H * this.poolPct) / 2;
    this.poolRing.position.y = POOL_H * this.poolPct + 0.01;

    // 池内粒子只在液面以下:越过液面就折回去,「装了多少」才看得出来
    const n = this.poolPos.length / 3;
    const top = Math.max(0.02, POOL_H * this.poolPct);
    for (let i = 0; i < n; i++) {
      const k = i * 3;
      this.poolPos[k + 1] += dt * 0.12 * (0.5 + ((i * 37) % 10) / 10);
      if (this.poolPos[k + 1] > top) this.poolPos[k + 1] -= top;
      if (this.poolPos[k + 1] < 0) this.poolPos[k + 1] += top;
      // 涡旋:切线推进 + 半径呼吸,看起来是翻滚而非整体平移
      const x = this.poolPos[k], z = this.poolPos[k + 2];
      const r = Math.hypot(x, z);
      const a = Math.atan2(z, x) + dt * 0.3;
      const rr = r + Math.sin(t * 0.8 + i) * dt * 0.05;
      this.poolPos[k] = Math.cos(a) * rr;
      this.poolPos[k + 2] = Math.sin(a) * rr;
    }
    (this.poolPts.geometry.getAttribute('position') as BufferAttribute).needsUpdate = true;

    this.stars.rotation.y = t * 0.006;
    return true;   // 悬停/旋翼/星空始终在动,故本方法恒返回 true
  }

  dispose(): void {
    for (const l of this.labels) l.dispose();
    this.labels = [];
    for (const d of this.disposables) d.dispose();
    this.disposables = [];
    this.scene.clear();
    this.root.clear();
  }
}

/** 64bit 响应 hex → 64 字符位串(MSB first,与 core/format.hexToBits 同口径)。
 *  此处不复用那个函数,是为了不让 three 分包反向依赖 core 的模块图 ——
 *  three chunk 要能被独立加载/独立失败,不该牵出 core 的半张图。 */
function hexBits(hex: string): string {
  const clean = hex.replace(/[^0-9a-fA-F]/g, '');
  let out = '';
  for (let i = 0; i + 2 <= clean.length; i += 2) {
    out += parseInt(clean.slice(i, i + 2), 16).toString(2).padStart(8, '0');
  }
  return out;
}
