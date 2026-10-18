/* ============================================================
 * three.js 认证舞台 —— 中央区的 3D 接管方(报告 §6.1/§8.5)
 *
 * 定位:它**不是**页面的一部分,而是一个**独立分包**。console.html 只预留了
 * 一个空 div(#stage-3d),本模块被动态 import 之后才去认领它。这条边界是刻意的:
 *   · three 加压缩后仍有数百 KB,不该压在首屏主包的路径上;
 *   · 弱网/离线/WebGL 被禁时它会静默失败,此时 2D 保底(stages/stage2d.ts)
 *     必须在场 —— 故本模块只做「尽量接管」,任何环节失败都只 emit stage.error,
 *     绝不抛异常打断页面。
 *
 * 握手顺序(§8.5):拿到挂载点 → 建渲染器 → **渲染出第一帧** → 才 emit stage.taken。
 * 不能反:先 taken 后渲染的话,2D 保底会在一段空白之后才被撤下。
 * 反过来,若初始化耗时超过 2D 侧的超时窗口(保底已闩锁为降级),本模块**主动
 * 放弃挂载**并释放渲染器,让页面继续用 2D —— 而不是把「HUD 写着未接管、
 * 画面上却是 3D」这种自相矛盾的状态留在屏上。
 * ============================================================ */
import {
  ACESFilmicToneMapping, Clock, HalfFloatType, PerspectiveCamera, PMREMGenerator,
  Vector2, Vector3, WebGLRenderer, WebGLRenderTarget,
} from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';

import {
  STAGE_CAMERA, STAGE_ERROR, STAGE_READY, STAGE_SHOT, STAGE_TAKEN,
  emit, onPuf, stageReady,
} from '../core/bus';
import type { PufEventName, PufPayload } from '../core/bus';
import { resultOfFrame } from '../core/format';
import { store } from '../core/store';
import { api } from '../core/api';
import { MSG } from '../core/types';
import type { FrameEvent, Verdict } from '../core/types';
import { ANCHOR, CAM_PRESETS, World } from './three/scene';
import { ParticleField } from './three/particles';
import { Fx } from './three/fx';
import { pal } from './three/palette';

/* 走廊两端的收发点。两端等高(ANCHOR.corridorY),光束才是水平飞行的
 * 「通信」而不是斜着砸过去的「攻击」。
 * 无人机侧不跟随悬停浮动:13 单位长的光束上 ±0.09 的抖动肉眼不可见,
 * 却要每帧重算终点,得不偿失。 */
const STATION_TX = new Vector3(ANCHOR.station.x + 0.78, ANCHOR.corridorY, 0);
const DRONE_RX = new Vector3(ANCHOR.drone.x, ANCHOR.corridorY, 0);
const DRONE_HIT = new Vector3(ANCHOR.drone.x, ANCHOR.drone.y + 0.35, 0);
const MID = new Vector3(0, ANCHOR.corridorY, 0);

/** 三档画质。降档顺序即「先牺牲什么」的优先级:辉光最贵、也最容易被看出代价,
 *  故最后才降它;像素比最便宜,先降。 */
const QUALITY = [
  { bloom: false, dpr: 1.0, label: '最低(关辉光 · 像素比 1.0)' },
  { bloom: false, dpr: 1.5, label: '中(关辉光)' },
  { bloom: true, dpr: 2.0, label: '全(辉光 + 2× 像素比)' },
] as const;

interface CamTween {
  t: number; dur: number;
  fromPos: Vector3; toPos: Vector3;
  fromTgt: Vector3; toTgt: Vector3;
}

export function startStage3d(): void {
  const mount = document.getElementById('stage-3d');
  if (mount) { boot(mount); return; }

  /* 挂载点还不在 DOM:等 stage.ready(Stage2d 构造时广播)。
   * 若 ready 早就广播过而元素仍不存在,说明页面结构与预期不符 —— 直接报错,
   * 让 2D 保底顶住,而不是无限期地等。 */
  if (stageReady()) {
    emit(STAGE_ERROR, { reason: '#stage-3d 不存在(console.html 结构变更?)' });
    return;
  }
  const off = onPuf(STAGE_READY, () => {
    off();
    const again = document.getElementById('stage-3d');
    if (again) boot(again);
    else emit(STAGE_ERROR, { reason: '#stage-3d 在 stage.ready 之后仍不可见' });
  });
}

function boot(mount: HTMLElement): void {
  /* 保底已闩锁为降级:说明 2D 侧的超时窗口已经用掉,此时再挂上去会让
   * HUD 文案与画面互相矛盾。主动放弃,把决定权交回页面。 */
  if (store.snapshot.ui.stage3dFailed) {
    store.log({
      tone: 'replay', sev: 'warn', terminalId: null, runId: null, type: 'server.log',
      text: '3D 舞台初始化晚于降级窗口,已主动放弃挂载,页面继续使用 2D 保底时序。',
    });
    return;
  }

  let renderer: WebGLRenderer;
  try {
    renderer = new WebGLRenderer({
      antialias: false,                 // 抗锯齿交给 composer 的 MSAA 渲染目标
      powerPreference: 'high-performance',
      alpha: false,
      stencil: false,
    });
  } catch (e) {
    emit(STAGE_ERROR, { reason: `WebGL 上下文创建失败:${errText(e)}` });
    return;
  }
  const cv = renderer.domElement;
  cv.style.width = '100%';
  cv.style.height = '100%';
  cv.style.display = 'block';
  renderer.toneMapping = ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  mount.appendChild(cv);

  let stage: Stage3d | null = null;
  try {
    stage = new Stage3d(renderer, mount);
    stage.init();
    // 第一帧真的画出来了,才宣告接管
    stage.renderOnce();
  } catch (e) {
    try { stage?.dispose(); } catch { /* 初始化半途失败,清理也可能失败,忽略 */ }
    cv.remove();
    renderer.dispose();
    emit(STAGE_ERROR, { reason: `3D 场景初始化失败:${errText(e)}` });
    return;
  }
  /* 修复(按钮审计 P1-2):初始化(WebGL 上下文 + 场景 + 首帧)可能耗时超过 2D
   * 的等待窗口——期间 stage2d 已闩锁降级。emit 前复检一次,已降级则主动拆除
   * 自己,避免「3D 画面叠加渲染、HUD 却写 2D 保底、相机组隐藏」的矛盾。 */
  if (store.snapshot.ui.stage3dFailed) {
    try { stage.dispose(); } catch { /* 清理失败亦不再挂载 */ }
    cv.remove();
    renderer.dispose();
    store.log({
      tone: 'replay', sev: 'warn', terminalId: null, runId: null, type: 'server.log',
      text: '3D 初始化完成时 2D 保底已接管(超出等待窗口),已拆除并放弃挂载。',
    });
    return;
  }
  emit(STAGE_TAKEN, { by: 'three' });
  stage.start();
  stage.exposeDebug();
}

class Stage3d {
  private world: World;
  private fx: Fx;
  private particles: ParticleField;
  private camera: PerspectiveCamera;
  private controls: OrbitControls;
  private composer: EffectComposer;
  private bloom: UnrealBloomPass;
  private rt: WebGLRenderTarget;
  private envTex: { dispose(): void } | null = null;
  private clock = new Clock();
  private raf = 0;
  private running = false;
  private overlay: HTMLElement | null = null;

  private quality = QUALITY.length - 1;
  private frames = 0;
  private fpsAcc = 0;
  private badStreak = 0;
  private goodStreak = 0;
  private upgrades = 0;

  private tween: CamTween | null = null;
  private pendingShot = false;

  private offs: (() => void)[] = [];
  private ro: ResizeObserver | null = null;
  private reduced = window.matchMedia('(prefers-reduced-motion: reduce)');

  /** 最近一次认证帧的路径 —— REPLAY 判定要把它重演一遍 */
  private lastPath: { from: Vector3; to: Vector3 } | null = null;
  /** 指纹数据的刷新代次:异步取数期间若切了终端,靠它丢弃过期结果 */
  private fpGen = 0;
  private lastTermKey = '';
  private lastPoolKey = '';
  private lastLinkOk: boolean | null = null;
  private lastPreset = 1;

  constructor(private renderer: WebGLRenderer, private mount: HTMLElement) {
    this.world = new World();
    this.particles = new ParticleField(2400);
    this.fx = new Fx(this.particles);
    this.world.root.add(this.particles.points, this.fx.group);

    this.camera = new PerspectiveCamera(42, 1, 0.1, 400);
    this.controls = new OrbitControls(this.camera, renderer.domElement);
    this.controls.enableDamping = !this.reduced.matches;
    this.controls.dampingFactor = 0.07;
    this.controls.minDistance = 5;
    this.controls.maxDistance = 72;
    // 严禁钻到地面之下:从下方看会露出地面网格的背面,像穿模
    this.controls.maxPolarAngle = Math.PI * 0.495;

    this.rt = new WebGLRenderTarget(1, 1, { type: HalfFloatType, samples: 4 });
    this.composer = new EffectComposer(renderer, this.rt);
    this.composer.addPass(new RenderPass(this.world.scene, this.camera));
    this.bloom = new UnrealBloomPass(new Vector2(1, 1), 0.9, 0.55, 0.26);
    this.composer.addPass(this.bloom);
    this.composer.addPass(new OutputPass());
  }

  /* ---------- 初始化 ---------- */
  init(): void {
    /* IBL:金属材质没有环境贴图会渲染成近黑色(「塔身像被挖空」的典型成因)。
     * RoomEnvironment 是纯程序化生成的,零资源文件,符合「产物全离线」硬约束。 */
    const pmrem = new PMREMGenerator(this.renderer);
    const env = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    this.world.setEnvironment(env, 0.2);
    this.envTex = env;
    pmrem.dispose();

    const p = CAM_PRESETS[0];
    this.camera.position.copy(p.pos);
    this.controls.target.copy(p.target);
    this.resize();

    this.wireEvents();
    /* 尺寸观察:中央区是栅格项,窗口缩放与右栏抽屉开合都会改它的尺寸。
     * 必须用 ResizeObserver —— 抽屉开合不触发 window.resize。 */
    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(this.mount);

    this.syncStore(true);
  }

  /* ---------- 事件接线 ---------- */
  private on<E extends PufEventName>(name: E, fn: (p: PufPayload<E>, ev: Event) => void): void {
    this.offs.push(onPuf(name, fn));
  }

  private wireEvents(): void {
    const accepts = (tid: number): boolean => {
      const sel = store.snapshot.selectedTerminal;
      return sel == null || sel === tid;      // 多终端并发下防串台(§6.4)
    };

    this.on('puf:frame', (f: FrameEvent) => {
      if (!accepts(f.terminal_id)) return;
      const forward = f.dir === 'server->term';
      const from = forward ? STATION_TX : DRONE_RX;
      const to = forward ? DRONE_RX : STATION_TX;
      this.fx.beam(from, to, this.colorOf(f), { travel: this.travelOf() });
      this.lastPath = { from: from.clone(), to: to.clone() };
    });

    this.on('puf:gray', (g) => {
      if (!accepts(g.terminal_id)) return;
      this.fx.grayFork(STATION_TX, DRONE_RX, 3);
    });

    this.on('puf:verdict', (v: Verdict) => {
      if (!accepts(v.terminal_id)) return;
      this.fx.verdict(v.result, DRONE_HIT, ANCHOR.pool);
    });

    this.on('puf:confirm', (c) => {
      if (!accepts(c.terminal_id)) return;
      // S7:status!=0 表示终端侧 BLOCKED(桥接代发的信号,见 store.ts 注释),
      // 视觉上表现为终端处放电拒绝,而不是闭环
      if (c.status === 0) this.fx.confirmClose(MID);
      else this.fx.arcBurst(DRONE_HIT, pal().red);
    });

    this.on('puf:replay', (p) => {
      if (!accepts(p.terminal_id)) return;
      this.fx.replayGhost(this.lastPath);
    });

    this.on('puf:pool', (w) => { this.world.setPool(w.pct, true, w.remaining, null); });

    this.on('puf:enroll', (e) => {
      // 注册完成 → 该终端有了新模板,指纹阵必须重取(否则画面停在上一次)
      this.particles.burst(
        new Vector3(ANCHOR.drone.x, ANCHOR.fingerY + 1.1, 0),
        { color: pal().green, count: 60, speed: 2.4, size: 0.06, life: .9, intensity: 1.8, drag: .93, jitter: .3 },
      );
      this.fx.bloomBoost = 1;
      if (e.terminal_id === store.snapshot.selectedTerminal) void this.loadFingerprint(true);
    });

    this.on('puf:runerror', (e) => {
      this.fx.arcBurst(DRONE_HIT, pal().auth);
      store.log({
        tone: 'error', sev: 'error', terminalId: null, runId: e.run_id,
        type: 'server.log', text: `3D 舞台:${e.stage} 阶段异常,已作电弧告警`,
      });
    });

    this.offs.push(
      onPuf(STAGE_CAMERA, (d) => this.gotoPreset(d.preset)),
      onPuf(STAGE_SHOT, () => { this.pendingShot = true; this.wake(); }),
    );

    this.offs.push(store.subscribe(() => this.syncStore(false)));

    /* 上下文丢失不静默变黑幕:暂停循环 + 盖一层说明,恢复后自动继续。
     * 这里不做「回退 2D」—— Stage2d 的降级是单向闩锁,接管成功后就无法
     * 干净地退回(它的 2D 时序在 taken 之后已停止更新)。刷新页面是唯一
     * 可靠的恢复手段,故提示语直接这么说。 */
    const onLost = (e: Event) => {
      e.preventDefault();               // 不阻止默认行为则浏览器不会触发 restored
      this.pause();
      this.showOverlay('WebGL 上下文丢失 —— 等待浏览器恢复…若未自动恢复请刷新页面');
      store.log({
        tone: 'error', sev: 'error', terminalId: null, runId: null, type: 'server.log',
        text: '3D 舞台:WebGL 上下文丢失,已暂停渲染;若未自动恢复请刷新页面。',
      });
    };
    const onRestored = () => {
      this.hideOverlay();
      store.log({
        tone: 'info', sev: 'info', terminalId: null, runId: null, type: 'server.log',
        text: '3D 舞台:WebGL 上下文已恢复,继续渲染。',
      });
      this.start();
      this.wake();
    };
    this.renderer.domElement.addEventListener('webglcontextlost', onLost);
    this.renderer.domElement.addEventListener('webglcontextrestored', onRestored);
    const cv = this.renderer.domElement;
    this.offs.push(() => {
      cv.removeEventListener('webglcontextlost', onLost);
      cv.removeEventListener('webglcontextrestored', onRestored);
    });

    this.reduced.addEventListener('change', () => {
      this.controls.enableDamping = !this.reduced.matches;
      this.wake();
    });
  }

  private showOverlay(text: string): void {
    if (!this.overlay) {
      this.overlay = document.createElement('div');
      this.overlay.className = 'stage3d-overlay';
      this.mount.appendChild(this.overlay);
    }
    this.overlay.textContent = text;
    this.overlay.hidden = false;
  }
  private hideOverlay(): void { if (this.overlay) this.overlay.hidden = true; }

  /* ---------- 帧色与节奏 ---------- */
  /** 一帧一个色,语义与左栏/审计日志同源:
   *  blue=接入请求 · purple=挑战(问) · cyan=响应(答) · green/red=结果 · amber=加测 */
  private colorOf(f: FrameEvent): ReturnType<typeof pal>['cyan'] {
    const c = pal();
    switch (f.msg_id) {
      case MSG.ACCESS_REQUEST: return c.blue;
      case MSG.CHALLENGE: return c.purple;
      case MSG.RESPONSE_R1: return c.cyan;
      case MSG.CONFIRM: return c.green;
      case MSG.EXTRA_CHALLENGE: return c.auth;
      case MSG.RESULT: {
        // RESULT 帧自带 result 字节:在 verdict 事件到达之前就定色,
        // 否则判定光束会先绿后红闪一下(实测过,像 bug)
        const r = resultOfFrame(f.hex);
        return r && r.result === 0 ? c.green : c.red;
      }
      default: return c.muted;
    }
  }

  /** 光束飞行时长。跟随顶栏帧速滑杆(ui.speedFollow),但钳在 [0.22, 0.55]s ——
   *  跟着滑杆线性放大的话,2000ms 档的光束会慢到像在飘,反而看不出「一帧一次往返」。 */
  private travelOf(): number {
    const ui = store.snapshot.ui;
    if (!ui.speedFollow) return 0.42;
    return Math.max(0.22, Math.min(0.55, (ui.frameMs / 1000) * 0.7));
  }

  /* ---------- 相机 ---------- */
  private gotoPreset(n: number): void {
    const idx = Math.max(0, Math.min(CAM_PRESETS.length - 1, n - 1));
    const p = CAM_PRESETS[idx];
    this.lastPreset = idx + 1;
    this.tween = {
      t: 0, dur: this.reduced.matches ? 0.001 : 0.95,
      fromPos: this.camera.position.clone(), toPos: p.pos.clone(),
      fromTgt: this.controls.target.clone(), toTgt: p.target.clone(),
    };
    store.log({
      tone: 'info', sev: 'info', terminalId: null, runId: null, type: 'server.log',
      text: `3D 相机预设 ${n} · ${p.label}`,
    });
    this.wake();
  }

  /* ---------- 尺寸与画质 ---------- */
  private resize(): void {
    // 隐藏时(抽屉里/切到别的页签)客户区为 0:直接返回,别让 aspect 变成 NaN
    if (this.mount.clientWidth === 0 || this.mount.clientHeight === 0) return;
    const w = this.mount.clientWidth;
    const h = this.mount.clientHeight;
    const dpr = Math.min(window.devicePixelRatio || 1, QUALITY[this.quality].dpr);
    this.renderer.setPixelRatio(dpr);
    this.renderer.setSize(w, h, false);
    this.composer.setPixelRatio(dpr);
    this.composer.setSize(w, h);
    this.bloom.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.particles.setScale(this.camera.fov, h);
    this.wake();
  }

  private applyQuality(): void {
    this.resize();
    store.log({
      tone: 'info', sev: 'info', terminalId: null, runId: null, type: 'server.log',
      text: `3D 画质档 → ${QUALITY[this.quality].label}`,
    });
  }

  /* ---------- 主循环 ---------- */
  start(): void {
    if (this.running) return;
    this.running = true;
    this.clock.getDelta();      // 丢掉暂停期间累积的时间差
    this.loop();
  }

  pause(): void {
    this.running = false;
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = 0;
  }

  /** 外部要求立刻出一帧(尺寸变化/截图/reduced-motion 下的状态更新) */
  private wake(): void { if (this.running) this.loop(); }

  private loop = (): void => {
    if (!this.running) return;
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = requestAnimationFrame(this.loop);

    // dt 钳制:切页签回来时 clock 会给出好几秒的间隔,不钳会让粒子瞬移、补间一步跳完
    const dt = Math.min(0.1, Math.max(0.0001, this.clock.getDelta()));
    const t = this.clock.elapsedTime;
    const frozen = this.reduced.matches;

    this.stepCameraTween(dt);
    /* 静止渲染(prefers-reduced-motion)下不推进环境动画:固定时间参数,
     * 场景保持一个静止姿态;只有事件驱动的特效继续演完 —— 完全冻结特效
     * 会让 PASS/REJECT 在画面上毫无区别,那等于把信息也一起关掉了。 */
    this.world.update(frozen ? 0 : dt, frozen ? 0 : t);
    this.fx.update(dt);
    if (!frozen) {
      const [rx, rz] = this.fx.shakeOffset(t);
      this.world.root.rotation.x = rx;
      this.world.root.rotation.z = rz;
    }
    this.stepQuality(dt);

    this.controls.update();
    this.renderOnce();
  };

  private stepCameraTween(dt: number): void {
    const tw = this.tween;
    if (!tw) return;
    tw.t = Math.min(tw.dur, tw.t + dt);
    const u = easeInOut(tw.t / tw.dur);
    this.camera.position.lerpVectors(tw.fromPos, tw.toPos, u);
    this.controls.target.lerpVectors(tw.fromTgt, tw.toTgt, u);
    if (tw.t >= tw.dur) this.tween = null;
  }

  /** 渲染一帧。pendingShot 的截图必须**紧接**在 render 之后同步取 ——
   *  否则绘制缓冲已被交换,拿到的是空白帧。不设 preserveDrawingBuffer 是
   *  为了性能:那面旗子会让每帧都多一次拷贝。 */
  renderOnce(): void {
    this.bloom.strength = 0.9 + this.fx.bloomBoost * 0.9;
    if (QUALITY[this.quality].bloom) this.composer.render();
    else this.renderer.render(this.world.scene, this.camera);

    if (this.pendingShot) {
      this.pendingShot = false;
      this.saveShot();
    }
  }

  private saveShot(): void {
    this.renderer.domElement.toBlob((blob) => {
      if (!blob) return;
      const stamp = new Date().toISOString().replace(/[:.]/g, '-');
      const name = `puf-stage3d-${stamp}.png`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = name;
      a.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 4000);
      store.log({
        tone: 'info', sev: 'info', terminalId: null, runId: null, type: 'server.log',
        text: `3D 舞台截图已保存 → ${name}`,
      });
    }, 'image/png');
  }

  /* ---------- FPS 看门狗 ----------
   * 低帧持续 3 秒才降档,恢复连续 8 秒才升档,且最多升 3 次。
   * 双侧滞回 + 升档上限是为了防抖:S4 分叉、S5 抽干这类瞬时爆发会让单秒帧率
   * 掉一下,若无滞回就会「降档→升档→降档」来回跳,观感比一直低画质更差。 */
  private stepQuality(dt: number): void {
    this.frames++;
    this.fpsAcc += dt;
    if (this.fpsAcc < 1) return;
    const fps = this.frames / this.fpsAcc;
    this.frames = 0;
    this.fpsAcc = 0;

    if (fps < 25) { this.badStreak++; this.goodStreak = 0; }
    else if (fps > 52) { this.goodStreak++; this.badStreak = 0; }
    else { this.badStreak = 0; this.goodStreak = 0; }

    if (this.badStreak >= 3 && this.quality > 0) {
      this.quality--; this.badStreak = 0;
      this.applyQuality();
    } else if (this.goodStreak >= 8 && this.quality < QUALITY.length - 1 && this.upgrades < 3) {
      this.quality++; this.goodStreak = 0; this.upgrades++;
      this.applyQuality();
    }
  }

  /* ---------- store 同步 ---------- */
  private syncStore(force: boolean): void {
    const s = store.snapshot;
    const tid = s.selectedTerminal;

    const termKey = tid == null ? 'none' : String(tid);
    if (force || termKey !== this.lastTermKey) {
      this.lastTermKey = termKey;
      this.world.setTerminalLabel(tid);
      void this.loadFingerprint(true);
    }

    const t = tid == null ? null : s.terminals.get(tid) ?? null;
    // 低水位也算告警:pool.warning 是后端在阈值处发的,前端不该等到那时才变琥珀
    const warn = !!(t && (t.poolWarn || t.pool_pct < 25));
    const poolKey = t
      ? `${Math.round(t.pool_pct)}|${t.pool_remaining}|${t.pool_size}|${warn}`
      : 'none';
    if (force || poolKey !== this.lastPoolKey) {
      this.lastPoolKey = poolKey;
      if (t) this.world.setPool(t.pool_pct, warn, t.pool_remaining, t.pool_size);
      else this.world.setPool(0, false, null, null);
    }

    const ok = s.link?.connected ?? false;
    if (force || ok !== this.lastLinkOk) {
      this.lastLinkOk = ok;
      this.world.setLinkOk(ok);
    }
  }

  /* ---------- 指纹数据 ----------
   * 3D 里那 64 根柱子必须是**真数据**。可达的公开数据源只有 §8.2 的
   * /api/viz/templates(与 viz 页 V3 同一份)。取该终端注册模板里的一份 CRP
   * 响应 + 稳定掩码;取不到就显示「未注册」,绝不合成图案凑数(§4.4)。 */
  private async loadFingerprint(refresh: boolean): Promise<void> {
    const gen = refresh ? ++this.fpGen : this.fpGen;
    const tid = store.snapshot.selectedTerminal;
    if (tid == null) { this.world.applyFingerprint(null, null); return; }
    try {
      const vt = await api.getVizTemplates();
      if (gen !== this.fpGen) return;          // 取数期间切了终端,丢弃本次结果
      const dev = vt.terminals?.[String(tid)];
      const seeds = dev?.responses ? Object.keys(dev.responses).sort() : [];
      if (seeds.length === 0) { this.world.applyFingerprint(null, null); return; }
      /* 取 seed 字典序最小的一条,保证同一终端每次渲染的都是同一份 CRP ——
       * 否则每次刷新柱子都在跳,会被当成「这个指纹不稳定」。 */
      this.world.applyFingerprint(dev.responses[seeds[0]], dev.stability_mask ?? null);
    } catch {
      /* 桥接不可达 / 该终端未注册 —— 都属于「没有数据」,显示未注册即可。
       * 不刷错误日志:viz 端点取不到不该在认证现场的日志里制造噪声。 */
      this.world.applyFingerprint(null, null);
    }
  }

  /* ---------- 排查出口 ----------
   * 与 viz 页的 __viz 同套路:只读快照 + 一个等价于按「1/2/3/4」的相机预设入口。
   * 存在的理由是**答辩现场**:上台前要确认当前画质档没被看门狗降到「关辉光」,
   * 事后要能证明「那轮认证确实发了光束」,光靠肉眼盯着一闪而过的画面不可靠。
   * 不开任何写入口 —— 能改场景状态的开关不该挂在 window 上。 */
  exposeDebug(): void {
    (window as unknown as Record<string, unknown>).__stage3d = {
      state: () => ({
        quality: this.quality,
        qualityLabel: QUALITY[this.quality].label,
        camera: { x: +this.camera.position.x.toFixed(2), y: +this.camera.position.y.toFixed(2), z: +this.camera.position.z.toFixed(2) },
        preset: this.lastPreset,
        ...this.fx.stats,
        particles: this.particles.aliveCount,
        fingerprint: this.world.fingerprintInfo(),
        reducedMotion: this.reduced.matches,
        linkOk: this.lastLinkOk,
      }),
      preset: (n: number) => this.gotoPreset(n),
    };
  }

  dispose(): void {
    this.pause();
    this.offs.forEach(f => f());
    this.offs = [];
    this.ro?.disconnect();
    this.ro = null;
    this.controls.dispose();
    this.fx.dispose();
    this.particles.dispose();
    this.world.dispose();
    this.composer.dispose();
    this.rt.dispose();
    this.envTex?.dispose();
    this.renderer.dispose();
    this.overlay?.remove();
    this.overlay = null;
  }
}

function errText(e: unknown): string { return e instanceof Error ? e.message : String(e); }

function easeInOut(u: number): number {
  const x = Math.min(1, Math.max(0, u));
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
}
