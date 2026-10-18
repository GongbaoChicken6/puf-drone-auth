/* ============================================================
 * 池化粒子场 —— 光束粒子流、判定爆散两类动画共用
 *
 * 为什么不用「每条光束建一个 Points」:演示时会连打 S1–S7,每帧事件都触发
 * 新光束。按需 new Points 会把 GPU 缓冲区的创建/销毁摊到动画帧上,表现为
 * 规律性掉帧(最明显是 EXTRA_CHALLENGE 分叉三束同时出现时)。故改为
 * **一次性分配、永久复用**:固定容量 + 游标覆盖最旧粒子。演示场景里
 * 「最旧的粒子被新粒子顶掉」视觉上不可察觉,代价却为零。
 *
 * 着色器自己写(而非 PointsMaterial),只为一件事:逐粒子尺寸与逐粒子透明度。
 * PointsMaterial 的 size 是全局的,做不出「头部亮、边缘淡出」的梯度,
 * 而辉光后处理的观感几乎全靠这个梯度。
 * 属性名带 a 前缀并在着色器里显式声明 —— three 只自动注入 position/normal/uv,
 * 自己声明 aColor 可避免和内置注入重名。
 * ============================================================ */
import {
  AdditiveBlending, BufferAttribute, BufferGeometry, Color, Points, ShaderMaterial,
  Vector3,
} from 'three';

const VERT = /* glsl */`
attribute vec3 aColor;
attribute float aSize;
attribute float aAlpha;
uniform float uScale;          // 世界单位 → 像素: h / (2*tan(fov/2))
varying vec3 vColor;
varying float vAlpha;
void main(){
  vColor = aColor;
  vAlpha = aAlpha;
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  // 近处钳制:粒子贴脸时若不限制点尺寸,填充率会被单个粒子打满(实测掉帧主因)
  gl_PointSize = min(aSize * uScale / max(-mv.z, 0.2), 72.0);
  gl_Position = projectionMatrix * mv;
}`;

const FRAG = /* glsl */`
varying vec3 vColor;
varying float vAlpha;
void main(){
  if (vAlpha < 0.01) discard;
  vec2 d = gl_PointCoord - vec2(0.5);
  float r = dot(d, d);                     // 已是距离平方,省一次 sqrt
  if (r > 0.25) discard;
  float a = smoothstep(0.25, 0.0, r);
  gl_FragColor = vec4(vColor, a * vAlpha);
}`;

export interface SpawnOpts {
  color: Color;
  /** 世界单位的粒子直径(着色器按 uScale 换算成像素) */
  size?: number;
  life?: number;          // 秒
  intensity?: number;     // HDR 倍率,>1 才会被 Bloom 拾取
  /** 每帧速度衰减(0.9 急停 / 0.999 近乎匀速) */
  drag?: number;
  /** 消亡高度(默认 0,即落到地面网格上熄灭) */
  floor?: number;
  /** 亮度抖动幅度(0..1)。只抖亮度不抖色相 —— 色相是「一个消息一个色」的语义载体 */
  jitter?: number;
}

interface Particle {
  vx: number; vy: number; vz: number;
  life: number; maxLife: number;
  drag: number; floor: number;
  active: boolean;
}

export class ParticleField {
  readonly points: Points;
  private cap: number;
  private cursor = 0;
  private p: Particle[] = [];
  private pos: Float32Array;
  private col: Float32Array;
  private siz: Float32Array;
  private alp: Float32Array;
  private geo: BufferGeometry;
  private mat: ShaderMaterial;
  private tmp = new Color();

  constructor(cap = 2400) {
    this.cap = cap;
    this.pos = new Float32Array(cap * 3);
    this.col = new Float32Array(cap * 3);
    this.siz = new Float32Array(cap);
    this.alp = new Float32Array(cap);
    for (let i = 0; i < cap; i++) {
      this.p.push({ vx: 0, vy: 0, vz: 0, life: 0, maxLife: 1, drag: .96, floor: 0, active: false });
    }

    this.geo = new BufferGeometry();
    this.geo.setAttribute('position', new BufferAttribute(this.pos, 3));
    this.geo.setAttribute('aColor', new BufferAttribute(this.col, 3));
    this.geo.setAttribute('aSize', new BufferAttribute(this.siz, 1));
    this.geo.setAttribute('aAlpha', new BufferAttribute(this.alp, 1));

    this.mat = new ShaderMaterial({
      uniforms: { uScale: { value: 400 } },
      vertexShader: VERT,
      fragmentShader: FRAG,
      transparent: true,
      depthWrite: false,          // 加色混合下写深度会让后画粒子切掉先画粒子
      blending: AdditiveBlending,
    });

    this.points = new Points(this.geo, this.mat);
    // 粒子会飞出几何体初始包围盒;不关剔除的话,相机一转整场粒子集体消失
    this.points.frustumCulled = false;
    this.points.renderOrder = 4;
  }

  /** 视口/相机变化时更新点尺寸换算系数 */
  setScale(fovDeg: number, viewportH: number): void {
    this.mat.uniforms.uScale.value = viewportH / (2 * Math.tan((fovDeg * Math.PI) / 360));
  }

  private emit(at: Vector3, vel: Vector3, o: SpawnOpts): void {
    const i = this.cursor;
    this.cursor = (this.cursor + 1) % this.cap;
    const st = this.p[i];
    const k = i * 3;
    this.pos[k] = at.x; this.pos[k + 1] = at.y; this.pos[k + 2] = at.z;
    st.vx = vel.x; st.vy = vel.y; st.vz = vel.z;
    st.maxLife = o.life ?? 1;
    st.life = st.maxLife;
    st.drag = o.drag ?? 0.96;
    st.floor = o.floor ?? 0;
    st.active = true;

    const it = o.intensity ?? 1;
    this.tmp.copy(o.color);
    if ((o.jitter ?? 0) > 0) this.tmp.multiplyScalar(1 + (Math.random() - 0.5) * 2 * (o.jitter ?? 0));
    this.col[k] = this.tmp.r * it;
    this.col[k + 1] = this.tmp.g * it;
    this.col[k + 2] = this.tmp.b * it;
    this.siz[i] = o.size ?? 0.05;
    this.alp[i] = 1;
  }

  /** 沿 from→to 的粒子流:轴向速度 + 少量横向弥散,成「束」而非「柱」 */
  spawnStream(from: Vector3, to: Vector3, o: SpawnOpts & {
    count?: number; speed?: number; spread?: number;
  }): void {
    const dir = new Vector3().subVectors(to, from);
    const len = dir.length();
    if (len < 1e-4) return;
    dir.divideScalar(len);
    const n = o.count ?? 26;
    const speed = o.speed ?? len * 1.6;
    const sp = o.spread ?? 0.12;
    const at = new Vector3();
    const vel = new Vector3();
    for (let i = 0; i < n; i++) {
      // 起点沿轴铺开一小段,让粒子流有「已成形」的体感,而不是从一个点炸开
      const t0 = Math.random() * 0.18;
      at.copy(from).addScaledVector(dir, t0 * len);
      at.x += (Math.random() - 0.5) * sp;
      at.y += (Math.random() - 0.5) * sp;
      at.z += (Math.random() - 0.5) * sp;
      vel.copy(dir).multiplyScalar(speed * (0.75 + Math.random() * 0.5));
      vel.x += (Math.random() - 0.5) * sp * 6;
      vel.y += (Math.random() - 0.5) * sp * 6;
      vel.z += (Math.random() - 0.5) * sp * 6;
      this.emit(at, vel, { ...o, life: (o.life ?? 1) * (0.7 + Math.random() * 0.6) });
    }
  }

  /** 球状爆散(判定冲击波、池干涸碎屑) */
  burst(at: Vector3, o: SpawnOpts & { count?: number; speed?: number }): void {
    const n = o.count ?? 40;
    const speed = o.speed ?? 3;
    const vel = new Vector3();
    for (let i = 0; i < n; i++) {
      // 球面均匀采样(z 均匀 + 方位角均匀),避免「两极聚集」的假爆散
      const z = Math.random() * 2 - 1;
      const a = Math.random() * Math.PI * 2;
      const r = Math.sqrt(Math.max(0, 1 - z * z));
      vel.set(r * Math.cos(a), z, r * Math.sin(a)).multiplyScalar(speed * (0.5 + Math.random()));
      this.emit(at, vel, o);
    }
  }

  update(dt: number): void {
    const { pos, alp } = this;
    for (let i = 0; i < this.cap; i++) {
      const st = this.p[i];
      if (!st.active) continue;
      st.life -= dt;
      if (st.life <= 0) { st.active = false; alp[i] = 0; continue; }
      const k = i * 3;
      // 帧率无关阻尼:每帧乘一次 drag 会让 30fps 与 120fps 的衰减差 4 倍
      const d = Math.pow(st.drag, dt * 60);
      st.vx *= d; st.vy *= d; st.vz *= d;
      st.vy -= 1.6 * dt;                       // 轻微重力,火花才会下落
      pos[k] += st.vx * dt; pos[k + 1] += st.vy * dt; pos[k + 2] += st.vz * dt;
      if (pos[k + 1] < st.floor) { st.active = false; alp[i] = 0; continue; }
      const u = st.life / st.maxLife;
      alp[i] = u * u;                          // 尾部二次淡出;出生瞬间最亮
    }
    /* 四个属性无条件重传。容量 2400 时约 48KB/帧(60fps ≈ 2.9MB/s),
     * 相对「按活动粒子数条件上传」省下的那点带宽,换来的确定性更值:
     * 条件上传最容易漏掉「最后一颗粒子本帧熄灭」那一次写,表现为地面上
     * 永久留一颗不灭的亮点,而且只在特定帧率下复现,极难查。 */
    this.geo.getAttribute('position').needsUpdate = true;
    this.geo.getAttribute('aColor').needsUpdate = true;
    this.geo.getAttribute('aSize').needsUpdate = true;
    this.geo.getAttribute('aAlpha').needsUpdate = true;
  }

  /** 全部熄灭(换 run / 复位时调用,避免上一轮粒子串到新场景) */
  clear(): void {
    for (let i = 0; i < this.cap; i++) { this.p[i].active = false; this.alp[i] = 0; }
    this.geo.getAttribute('aAlpha').needsUpdate = true;
  }

  /** 活动粒子数(排查用读数;0 表示场上没有粒子在飞) */
  get aliveCount(): number {
    let n = 0;
    for (let i = 0; i < this.cap; i++) if (this.p[i].active) n++;
    return n;
  }

  dispose(): void {
    this.geo.dispose();
    this.mat.dispose();
  }
}
