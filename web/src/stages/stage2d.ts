/* ============================================================
 * 认证舞台(中央区)与 2D 保底 —— 报告 §6.1 / §6.2 / §8.5
 *
 * 本模块是中央区的**所有者**,也是 3D 挂载握手的主持方:
 *   1. 渲染 2D 保底(场景标题条 + 五帧时序 SVG + hex 结构查看器)并挂进 #center-stage;
 *   2. DOM 就绪后广播 puf:stage.ready {mount:'#stage-3d'}(§8.5);
 *   3. 600ms 内收到 puf:stage.taken → 判定 3D 接管成功,隐去 2D 时序(hex 保留,
 *      它不属于舞台动画);收到 puf:stage.error 或超时 → 保留 2D,并记录降级。
 *
 * 为什么超时也算失败:3D chunk 是独立分包,弱网/离线/WebGL 被禁时会**静默**
 * 不返回。不给超时兜底,演示时舞台会是一片空白 —— 2D 保底是 §13 的硬性兜底项。
 * 一旦降级,后到的 taken 不再翻案(store.stage3dFailed 为单向闩锁)。
 * ============================================================ */
import { HexViewer } from '../components/hex-viewer';
import { FrameTimeline } from '../components/frame-timeline';
import { STAGE_CAMERA, STAGE_ERROR, STAGE_READY, STAGE_SHOT, STAGE_TAKEN, emit, onPuf } from '../core/bus';
import { store, type AppState, type RunState } from '../core/store';
import { MSG, RESULT_CN, type FrameEvent } from '../core/types';

/* 判定码 → 舞台大字配色类(与右栏同一套视觉语义) */
const STAMP_CLS: Record<number, string> = {
  0: 'pass', 1: 'reject', 2: 'error', 3: 'drain', 4: 'replay',
};

/* 3D 模块的应答窗口。chunk 已缓存时 taken 通常在 1–2 帧内到达,但**冷启动**
 * 要算上:分包下载 + WebGL 上下文创建 + 着色器编译(Bloom 的那几个 pass 在
 * 弱机上首次编译可达数百毫秒)+ PMREM 环境贴图生成。600ms 会在真实机器上
 * 误杀 —— 这不是推测,是实测出来的。
 *
 * 放宽到 1500ms 的代价几乎为零:超时期间屏上并不是空白,而是**完整的 2D 时序
 * 保底**在正常渲染。故这里唯一的取舍是「2D→3D 的切换晚一点发生」,
 * 而不给窗口就会退化成「永远只有 2D」。 */
const TAKEN_TIMEOUT_MS = 1500;

export class Stage2d {
  readonly el: HTMLElement;
  private timeline = new FrameTimeline();
  private hex = new HexViewer();
  private titleRun!: HTMLElement;
  private titleDur!: HTMLElement;
  private fallback!: HTMLElement;
  private hud!: HTMLElement;
  private pipe!: HTMLElement;
  private stamp!: HTMLElement;
  private stampMain!: HTMLElement;
  private stampSub!: HTMLElement;
  private pipeSteps = new Map<string, { el: HTMLElement; st: HTMLElement }>();
  private pipeSig = '';
  private stampKey = '';
  private stampPrimed = false;
  private stampTimer = 0;
  private taken = false;
  private settled = false;
  private unbind: (() => void)[] = [];

  constructor() {
    this.el = document.createElement('div');
    this.el.className = 'stage';
    this.el.innerHTML = `
      <div class="stage-title">
        <span class="st-name" id="st-name">认证舞台</span>
        <span class="st-run mono" id="st-run">run —</span>
        <span class="st-dur mono" id="st-dur">—</span>
        <span class="st-cams" id="st-cams" title="相机预设(快捷键 1–4);F 截图">
          <button class="btn ghost st-cam" data-cam="1">全景</button>
          <button class="btn ghost st-cam" data-cam="2">跟踪</button>
          <button class="btn ghost st-cam" data-cam="3">特写</button>
          <button class="btn ghost st-cam" data-cam="4">俯瞰</button>
          <button class="btn ghost st-cam" data-cam="shot" title="导出当前舞台画面(F)">⤓</button>
        </span>
        <span class="tb-spacer"></span>
        <span class="st-hud" id="st-hud"></span>
      </div>
      <div class="stage-view">
        <!-- three.js 挂载点(#stage-3d 由 console.html 预留,§8.5 契约) -->
        <div class="stage-fallback" id="stage-fallback"></div>
        <div class="stage-hint" id="stage-hint" hidden>按住拖拽旋转 · 滚轮缩放</div>
        <!-- 常驻协议流水线:五帧走到哪一步,舞台上直接读(仅 3D 接管后显示) -->
        <div class="stage-pipe" id="stage-pipe" hidden></div>
        <!-- 判定压屏大字(1.6s 自动淡出,pointer-events:none) -->
        <div class="stage-stamp" id="stage-stamp" hidden>
          <b class="stamp-main"></b><span class="stamp-sub"></span>
        </div>
      </div>
      <div class="stage-hex" id="stage-hex"></div>`;

    this.titleRun = this.q('#st-run');
    this.titleDur = this.q('#st-dur');
    this.fallback = this.q('#stage-fallback');
    this.hud = this.q('#st-hud');
    this.pipe = this.q('#stage-pipe');
    this.stamp = this.q('#stage-stamp');
    this.stampMain = this.q('.stamp-main');
    this.stampSub = this.q('.stamp-sub');
    this.buildPipe();

    this.fallback.append(this.timeline.el);
    this.q('#stage-hex').append(this.hex.el);

    /* R7:相机预设从「只有键盘 1–4 才能触发」补上可见按钮 —— 交互入口不能
     * 只活在快捷键里,答辩观众和演示者第一眼都看不见快捷键。emit 的是同一条
     * STAGE_CAMERA 总线事件,3D 未接管时没人应答,故按钮组随接管态显隐。 */
    const cams = this.q('#st-cams');
    cams.hidden = true;
    /* R8 D19:当前预设常亮(.st-cam.active)。按钮点击与键盘 1–4(也走
     * STAGE_CAMERA 总线)两条通道同源刷新,不会出现「按钮亮 A、实际是 B」。 */
    const setCam = (n: number): void => {
      cams.querySelectorAll<HTMLButtonElement>('.st-cam[data-cam]').forEach(b => {
        b.classList.toggle('active', Number(b.dataset.cam) === n);
      });
    };
    cams.addEventListener('click', (e) => {
      const b = (e.target as HTMLElement).closest<HTMLButtonElement>('.st-cam');
      if (!b) return;
      if (b.dataset.cam === 'shot') emit(STAGE_SHOT, { name: 'stage' });
      else emit(STAGE_CAMERA, { preset: Number(b.dataset.cam) });
    });
    this.unbind.push(onPuf(STAGE_CAMERA, (p) => setCam(p.preset)));

    /* R7:拖拽暗示条。接管成功即浮现;第一次在舞台上按下指针就淡出 ——
     * 它的使命是「告诉你能拖」,你已经拖了,它就完成了。 */
    const hint = this.q('#stage-hint');
    const dismiss = (): void => {
      hint.classList.add('off');
      window.setTimeout(() => { hint.hidden = true; }, 700);
      this.q('.stage-view').removeEventListener('pointerdown', dismiss);
    };
    this.q('.stage-view').addEventListener('pointerdown', dismiss);

    /* 把 console.html 预置的 #stage-3d 认领进舞台视图:它是一个绝对定位的
     * 覆盖层,必须叠在 2D 时序之上。这一步必须在入口 replaceWith 掉
     * #center-stage 之前完成 —— 故放在构造函数里,而非 mount 之后。 */
    const mount = document.getElementById('stage-3d');
    if (mount) this.q('.stage-view').append(mount);

    this.handshake();
  }

  private q<T extends HTMLElement>(sel: string): T { return this.el.querySelector<T>(sel)!; }

  /* 五节点流水线骨架:标签写死,状态由 update() 逐帧回填 */
  private buildPipe(): void {
    const defs = [
      { k: 'ar', label: '接入请求' },
      { k: 'ch', label: '挑战' },
      { k: 'r1', label: '指纹响应' },
      { k: 'res', label: '判决结果' },
      { k: 'cf', label: '确认' },
    ];
    defs.forEach((d, i) => {
      if (i > 0) {
        const a = document.createElement('span');
        a.className = 'sp-arrow';
        a.textContent = '›';
        this.pipe.append(a);
      }
      const el = document.createElement('div');
      el.className = 'sp-step st-pending';
      el.innerHTML = `<i></i><b>${d.label}</b><small>—</small>`;
      this.pipe.append(el);
      this.pipeSteps.set(d.k, { el, st: el.querySelector('small')! });
    });
  }

  /* ---------- 3D 握手(§8.5) ---------- */
  private handshake(): void {
    this.unbind.push(
      onPuf(STAGE_TAKEN, () => this.onTaken()),
      onPuf(STAGE_ERROR, (p) => this.onError(p.reason)),
      /* finals-demo-drone:2D 保底下无人机状态徽章(3D 已接管时由舞台右下
       * 的无人机状态卡负责,这里不再重复) */
      onPuf('puf:drone-state', (p) => {
        if (this.taken) return;
        const sel = store.snapshot.selectedTerminal;
        if (sel != null && sel !== p.terminal_id) return;
        this.hud.textContent = `无人机 · ${p.unlocked ? p.state : '🔒未解锁'} · 高度 ${p.pos[2].toFixed(1)}m`;
        this.hud.hidden = false;
      }),
    );
    // 先广播 ready,再排超时:3D 模块可能在本行之前就已加载完成(它自己查询
    // bus.stageReady()),故 taken 有可能同步到达 —— 那种情况下定时器会看到
    // settled=true 而直接退出,不会误判为超时。
    emit(STAGE_READY, { mount: '#stage-3d' });
    window.setTimeout(() => {
      if (this.settled) return;
      this.onError(`${TAKEN_TIMEOUT_MS}ms 内未收到 puf:stage.taken`);
    }, TAKEN_TIMEOUT_MS);
  }

  private onTaken(): void {
    // 已降级则单向闩锁,不被后到的 taken 翻案(降级后 3D 不得再挂载)
    if (this.settled && !this.taken) return;
    this.settled = true;
    this.taken = true;
    this.fallback.classList.add('hidden');
    this.q('#st-cams').hidden = false;
    this.q('#stage-hint').hidden = false;
    this.pipe.hidden = false;
    this.pipeSig = '';                       // 强制下一帧重画流水线
    this.renderPipe(store.snapshot.run);
    /* 3D 已接管:标题条右侧不再挂状态说明文字,保持干净 */
    this.hud.textContent = '';
    this.hud.hidden = true;
    store.onStageTaken();
    store.log({
      tone: 'info', sev: 'info', terminalId: null, runId: null,
      type: 'server.log', text: '3D 认证舞台接管成功,已隐藏 2D 时序保底。',
    });
  }

  private onError(reason: string): void {
    if (this.settled) return;
    this.settled = true;
    this.taken = false;
    this.fallback.classList.remove('hidden');
    this.pipe.hidden = true;
    this.hud.textContent = '2D 保底时序(3D 舞台未接管)';
    this.hud.hidden = false;
    store.onStageError();
    // 记 server.log 而非 run.error:这是**页面自身**的降级通告,不是协议运行错误。
    // 用 run.error 会让类型过滤器把它和真正的认证失败混在一起(实测踩过)。
    store.log({
      tone: 'replay', sev: 'warn', terminalId: null, runId: null,
      type: 'server.log', text: `3D 舞台未接管,已切 2D 保底时序:${reason}`,
    });
  }

  /* ---------- 渲染 ---------- */
  private lastRunId = '';
  private renderSig = '';

  update(s: AppState): void {
    const run = s.run;
    const term = s.selectedTerminal != null
      ? s.terminals.get(s.selectedTerminal) ?? null : null;

    // 标题条
    this.titleRun.textContent = run ? `认证轮次 ${run.run_id}` : '认证轮次 —';
    if (run) {
      const ended = run.endedAt ?? performance.now();   // 未终结则走实时秒表
      const ms = ended - run.startedAt;
      this.titleDur.textContent = run.endedAt == null
        ? `${(ms / 1000).toFixed(1)} s (进行中)`
        : `${(ms / 1000).toFixed(2)} s`;
      const name = run.extra ? '待定区加测认证' : (run.verdict?.result_name ?? '认证中');
      this.q('#st-name').textContent = `${name} · 终端 ${run.terminal_id}`;
    } else {
      this.q('#st-name').textContent = term ? `认证舞台 · 终端 ${term.id}` : '认证舞台';
      this.titleDur.textContent = '—';
    }

    // 2D 保底只在未接管时更新(接管后其 DOM 隐藏,继续绘制纯属浪费帧)
    if (!this.taken) this.timeline.update(run, term);

    // 3D 接管后:舞台常驻协议流水线 + 判定压屏大字
    if (this.taken) this.renderPipe(run);
    this.maybeStamp(run);

    // hex 查看器与 3D 无关,始终跟随(run 变了才重绘,内部有签名守卫)
    const sig = run ? `${run.run_id}:${run.frames.length}` : '';
    if (sig !== this.renderSig) {
      this.renderSig = sig;
      this.hex.update(run);
    }
    if (this.lastRunId !== (run?.run_id ?? '')) {
      this.lastRunId = run?.run_id ?? '';
      // 换 run 时若舞台上还有上一次的残留态(未终结),显式复位一次,
      // 避免新 run 的第一帧到来前标题条显示旧耗时
      if (run == null) this.timeline.reset();
    }
  }

  /* ---------- 协议流水线 ----------
   * 只读 run.frames / verdict / confirm,不推断桥接没发出的帧。
   * 状态:st-pending 未到达 / st-live 在途 / st-ok 通过 / st-fail 失败 /
   * st-skip 本轮不会发生(如 REJECT 后没有 CONFIRM)。 */
  private renderPipe(run: RunState | null): void {
    if (this.pipe.hidden) return;
    const v = run?.verdict ?? null;
    const sig = run
      ? `${run.run_id}:${run.frames.length}:${v?.result ?? -1}:${run.confirm?.status ?? -1}`
      : '';
    if (sig === this.pipeSig) return;
    this.pipeSig = sig;

    const frames = run?.frames ?? [];
    const firstOf = (msg: number): FrameEvent | null =>
      frames.find(f => f.msg_id === msg) ?? null;
    const nResp = frames.filter(f => f.msg_id === MSG.RESPONSE_R1).length;
    const extra = frames.some(f => f.msg_id === MSG.EXTRA_CHALLENGE);

    const paint = (k: string, cls: string, small: string): void => {
      const s = this.pipeSteps.get(k);
      if (!s) return;
      s.el.className = `sp-step ${cls}`;
      s.st.textContent = small;
    };

    const ar = firstOf(MSG.ACCESS_REQUEST);
    const ch = firstOf(MSG.CHALLENGE);
    const r1 = firstOf(MSG.RESPONSE_R1);
    const res = firstOf(MSG.RESULT);
    const cf = firstOf(MSG.CONFIRM);

    /* 判定一下来,已参与判定的四个节点统一回填通过/失败色 */
    const doneCls = v ? (v.result === 0 ? 'st-ok' : 'st-fail') : '';
    const clsOf = (f: FrameEvent | null): string =>
      f ? (doneCls || 'st-live') : 'st-pending';
    const sizeOf = (f: FrameEvent | null): string => (f ? `${f.len}B` : '—');

    paint('ar', clsOf(ar), sizeOf(ar));
    paint('ch', clsOf(ch), ch ? `${ch.len}B${extra ? ' +加测' : ''}` : '—');
    paint('r1', clsOf(r1), r1 ? `${r1.len}B${nResp > 1 ? ` ×${nResp}` : ''}` : '—');
    paint('res', clsOf(res), v ? (RESULT_CN[v.result] ?? v.result_name) : sizeOf(res));

    const cfOk = run?.confirm != null && run.confirm.status === 0;
    const cfBlocked = run?.confirm != null && run.confirm.status !== 0;
    const cfCls = cfBlocked ? 'st-fail'
      : cfOk ? 'st-ok'
        : v && v.result !== 0 ? 'st-skip'
          : cf ? 'st-live' : 'st-pending';
    paint('cf', cfCls,
      cfBlocked ? 'BLOCKED' : cfOk ? '闭环' : v && v.result !== 0 ? '未闭环' : '—');
  }

  /* ---------- 判定压屏大字 ----------
   * 首次 update 只记基线,不补放历史判定 —— 刷新页面不该再闪一次旧结果。 */
  private maybeStamp(run: RunState | null): void {
    const v = run?.verdict ?? null;
    if (!this.stampPrimed) {
      this.stampPrimed = true;
      if (run && v) this.stampKey = `${run.run_id}:${v.result}`;
      return;
    }
    if (!this.taken || !run || !v) return;
    const key = `${run.run_id}:${v.result}`;
    if (key === this.stampKey) return;
    this.stampKey = key;
    this.stampMain.textContent = RESULT_CN[v.result] ?? v.result_name;
    this.stampSub.textContent = '';
    this.stamp.className = `stage-stamp show ${STAMP_CLS[v.result] ?? ''}`;
    this.stamp.hidden = false;
    window.clearTimeout(this.stampTimer);
    this.stampTimer = window.setTimeout(() => {
      this.stamp.hidden = true;
      this.stamp.className = 'stage-stamp';
    }, 1600);
  }

  dispose(): void {
    this.unbind.forEach(f => f());
    this.unbind = [];
    window.clearTimeout(this.stampTimer);
  }
}
