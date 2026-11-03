/* ============================================================
 * 最小 observable 状态 —— 报告 §8.4 store.ts
 * terminals / currentRun / verdict / link / log[](封顶 2000)
 * UI 模块 subscribe()→ 渲染;事件先经 bus → store 汇聚
 *
 * 相对报告 §8.4 的两处扩展(均为 §6.4 明确要求的语义,非另造状态):
 *  · run 取代裸 currentRun:§6.4「事件按 run_id 隔离,动画锁定当前选中终端」
 *    要求舞台能拿到**一个 run 的完整帧序列**(时序图/hex 查看器/耗时都依赖它),
 *    故按 run_id 聚合成 RunState,只保留最近 RUN_CAP 个。
 *  · ui:帧速滑杆/顶栏隐藏/右栏抽屉/3D 接管结果等纯前端偏好,不上报后端。
 * ============================================================ */
import type {
  ConfirmDone, EnrollDone, FrameEvent, GrayExtra, LinkStatus, PoolWarning,
  ResultCode, RunError, ServerLog, SessionUpdate, SourceBadge, Verdict,
} from './types';
import { tidNum } from './format';

export interface TerminalState {
  id: number;
  n_pairs: number;
  /* 沿 /api/status 的 templates[] 原生口径:掩码未算出时为 null(见 types.ts) */
  stable_bits: number | null;
  stability_pct: number | null;
  pool_remaining: number;
  pool_size: number;
  pool_pct: number;
  lastDecision: ResultCode | null;
  sessionState: string | null;    // session.update 的 state(IDLE/SESSION/…)
  /* §6.2 右栏「会话计数」要显示 challenges_issued / responses_scored / hd_sum,
   * 而 state 只是这三个之外的一个字段 —— 故整条 session.update 原样留存。 */
  lastSession: SessionUpdate | null;
  c2Cleared: boolean;             // 本会话内是否执行过 /api/c2reset
  keyInstalled: boolean;          // 本会话内是否装入过演示密钥(setkey)
  authCount: number;              // 本会话完成的认证轮次数(R2 金角标节拍用)
  enrolling: boolean;             // 注册进度态
  poolWarn: boolean;              // pool.warning → 水位条琥珀闪
}

/* 一个 run 的全部舞台素材(§6.4 按 run_id 隔离) */
export interface RunState {
  run_id: string;
  terminal_id: number;
  startedAt: number;              // performance.now(),用于场景标题条耗时
  frames: FrameEvent[];           // 时序图/hex 查看器的数据源
  extra: GrayExtra | null;        // gray.extra(S4 分叉)
  verdict: Verdict | null;
  confirm: ConfirmDone | null;
  errors: RunError[];
  /* S7:终端侧 BLOCKED。桥接层在 evilbase 下会**主动**发一条
   * confirm.done(status=1),其注释明言这是给 UI 的「终端侧 BLOCKED」信号而非
   * 终端真发了 CONFIRM_FAIL 帧(web_bridge.py:601-613)。因此这里直接由
   * confirm.status !== 0 得出,不做推断 —— 推断会在 verdict→confirm 的间隙
   * 让 S1 误闪一次 BLOCKED。 */
  terminalBlocked: boolean;
  endedAt: number | null;         // 首个终态事件到达时刻(耗时用)
}

/* 审计日志行。配色(tone)与严重级(sev)分开:§6.2 的过滤器按严重级,
 * 而配色要区分 verdict 的绿/红与 gray/replay 的琥珀 —— 同一严重级下颜色不同,
 * 故不能用一个字段兼表两件事。 */
export type LogTone = 'info' | 'frame' | 'ok' | 'bad' | 'gray' | 'replay' | 'error';
export type LogSev = 'info' | 'warn' | 'error';

export interface LogEntry {
  seq: number;
  ts: string;
  tone: LogTone;
  sev: LogSev;
  terminalId: number | null;
  runId: string | null;
  type: string;                   // 原始 SSE type(类型过滤器)
  text: string;
}

export interface UiState {
  frameMs: number;                // 帧速滑杆 200–2000,默认 600(仅动画节奏)
  topbarHidden: boolean;          // H 键
  rightDrawerOpen: boolean;       // <1280px 右栏折叠为抽屉
  stage3d: boolean;               // 3D 是否已接管(§8.5 握手结果)
  stage3dFailed: boolean;         // 已降级 2D(此后 3D 不得再挂载)
  goldenMode: boolean;            // 黄金帧回放模式(启用逐字节 diff,§6.2)
  speedFollow: boolean;           // 是否把滑杆值同步给 3D(scene 节奏)
}

export interface AppState {
  link: LinkStatus | null;
  terminals: Map<number, TerminalState>;
  selectedTerminal: number | null;
  run: RunState | null;           // 舞台锁定的当前 run
  logs: LogEntry[];
  ui: UiState;
  runCount: number;               // 顶栏 run 计数(剪辑对轴,§6.4)
  /* 数据源徽章三态(§4.4)。桥接 --mock 时 link.version 以 "-mock" 结尾
   * (web_bridge.py:1039),据此判定,不靠猜。 */
  source: SourceBadge;
}

type Listener = (s: AppState) => void;

const LOG_CAP = 2000;
const RUN_CAP = 40;
export const DEFAULT_FRAME_MS = 600;

function blankTerminal(id: number): TerminalState {
  return {
    id, n_pairs: 0, stable_bits: null, stability_pct: null,
    pool_remaining: 0, pool_size: 0, pool_pct: 0,
    lastDecision: null, sessionState: null, lastSession: null, c2Cleared: false,
    keyInstalled: false, authCount: 0, enrolling: false, poolWarn: false,
  };
}

class Store {
  private state: AppState = {
    link: null,
    terminals: new Map(),
    selectedTerminal: null,
    run: null,
    logs: [],
    ui: {
      frameMs: DEFAULT_FRAME_MS, topbarHidden: false, rightDrawerOpen: false,
      stage3d: false, stage3dFailed: false, goldenMode: false, speedFollow: true,
    },
    runCount: 0,
    source: 'REAL-LIVE',
  };
  private runOrder: string[] = [];
  private listeners = new Set<Listener>();

  get snapshot(): AppState { return this.state; }

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private emit(): void { this.listeners.forEach(fn => fn(this.state)); }

  /* ---------- 终端 ---------- */
  upsertTerminal(id: number, patch: Partial<TerminalState>): void {
    const cur = this.state.terminals.get(id) ?? blankTerminal(id);
    this.state.terminals.set(id, { ...cur, ...patch });
    this.emit();
  }

  terminal(id: number): TerminalState {
    let t = this.state.terminals.get(id);
    if (!t) { t = blankTerminal(id); this.state.terminals.set(id, t); }
    return t;
  }

  /* /api/status 全量灌入(首屏 + 每次重同步)。templates[] 的 tid 是字符串、
   * pools[] 的是数字,故两侧都过 tidNum() 归一到同一 key。 */
  hydrateFromStatus(st: {
    link: LinkStatus;
    templates: { terminal_id: string; n_pairs: number; stable_bits: number | null }[];
    pools: { terminal_id: number; remaining: number; pool_size: number; pct: number }[];
  }): void {
    this.setLink(st.link, /* quiet */ true);
    for (const row of st.templates) {
      const id = tidNum(row.terminal_id);
      const t = this.terminal(id);
      // 稳定位占比由展示层现算(服务端不提供该字段,见 types.ts)
      t.stable_bits = row.stable_bits;
      t.stability_pct = row.stable_bits == null ? null : Math.round(1000 * row.stable_bits / 64) / 10;
      t.n_pairs = row.n_pairs;
    }
    for (const p of st.pools) {
      const t = this.terminal(tidNum(p.terminal_id));
      t.pool_remaining = p.remaining;
      t.pool_size = p.pool_size;
      t.pool_pct = p.pct;
    }
    if (this.state.selectedTerminal == null && this.state.terminals.size > 0) {
      /* 默认选中演示终端(优先 tid7):tid1/2 是真板终端,loopback 仿真无法复现
       * 其指纹(桥侧守卫会拦截并报 ERROR),若默认落在真板上,用户第一次点
       * 剧本就会吃到「错误」而非预期的 PASS/REJECT 叙事。 */
      const demo = [7, 9, 55, 99].find(id => this.state.terminals.has(id));
      this.state.selectedTerminal = demo ?? Math.min(...this.state.terminals.keys());
    }
    this.emit();
  }

  setLink(link: LinkStatus, quiet = false): void {
    /* P3(按钮审计 N7):桥接重启(uptime 回退)时,未见终态的旧 run 会残留成
     * 「进行中」秒表走字 —— 按中断收尾并留痕(quiet 时也发,日志不入 emit 节流)。 */
    const restarted = this.state.link != null && link.uptime_s < this.state.link.uptime_s;
    if (restarted) {
      const r = this.state.run;
      if (r && r.endedAt == null) {
        r.endedAt = performance.now();
        this.log({
          tone: 'replay', sev: 'warn', terminalId: r.terminal_id, runId: r.run_id,
          type: 'server.log',
          text: '桥接已重启:该运行未见终态,已按中断收尾(计时停止)。',
        });
      }
    }
    this.state.link = link;
    this.state.source = link.version?.endsWith('-mock') ? 'MOCK' : 'REAL-LIVE';
    if (!quiet) this.emit();
  }

  select(id: number): void {
    if (this.state.selectedTerminal === id) return;
    this.state.selectedTerminal = id;
    this.state.run = null;        // 切换选中即清舞台(§6.4 动画锁定当前终端)
    this.emit();
  }

  /* ---------- run ---------- */
  /* 事件是否属于「舞台当前锁定的终端」。非选中终端的事件只喂卡片与日志,
   * 不动舞台动画 —— 多终端并发下防串台(§6.4)。 */
  private stageAccepts(terminalId: number): boolean {
    const sel = this.state.selectedTerminal;
    return sel == null || sel === terminalId;
  }

  private runFor(runId: string, terminalId: number): RunState {
    const cur = this.state.run;
    if (cur && cur.run_id === runId) return cur;
    const fresh: RunState = {
      run_id: runId, terminal_id: terminalId, startedAt: performance.now(),
      frames: [], extra: null, verdict: null, confirm: null,
      errors: [], terminalBlocked: false, endedAt: null,
    };
    this.state.run = fresh;
    this.state.runCount++;
    this.runOrder.push(runId);
    while (this.runOrder.length > RUN_CAP) this.runOrder.shift();
    return fresh;
  }

  /* 提交 REST 后由调用方先行注册 run_id,使标题条在首帧到达前就有内容 */
  beginRun(runId: string, terminalId: number): void {
    this.runFor(runId, terminalId);
    this.emit();
  }

  onFrame(f: FrameEvent): void {
    if (this.stageAccepts(f.terminal_id)) this.runFor(f.run_id, f.terminal_id).frames.push(f);
    this.log({
      tone: 'frame', sev: 'info', terminalId: f.terminal_id, runId: f.run_id,
      type: f.dir === 'server->term' ? 'frame.tx' : 'frame.rx',
      text: `${f.name} ${f.len}B ${f.dir === 'server->term' ? '基站→终端' : '终端→基站'}`
        + ` [${f.source === 'simulated-terminal' ? '代演' : '真机'}]`,
    });
  }

  onGrayExtra(g: GrayExtra): void {
    if (this.stageAccepts(g.terminal_id)) {
      const r = this.runFor(g.run_id, g.terminal_id);
      r.extra = g;
    }
    this.log({
      tone: 'gray', sev: 'warn', terminalId: g.terminal_id, runId: g.run_id,
      type: 'gray.extra',
      text: `灰区加测 +${g.n} 挑战(本轮共 ${4 + g.n} 个响应参与判定)`,
    });
  }

  onSession(u: SessionUpdate): void {
    this.upsertTerminal(u.terminal_id, { sessionState: u.state, lastSession: u });
  }

  onVerdict(v: Verdict): void {
    if (this.stageAccepts(v.terminal_id)) {
      const r = this.runFor(v.run_id, v.terminal_id);
      r.verdict = v;
      // REJECT/ERROR/池耗尽/重放都不会有 CONFIRM(桥接仅在 result=0 时代演握手),
      // 故除 PASS 外,判定事件即本轮终态。
      if (v.result !== 0) r.endedAt = performance.now();
    }
    const t = this.terminal(v.terminal_id);
    t.lastDecision = v.result;
    t.pool_remaining = v.pool.remaining;
    t.pool_size = v.pool.pool_size;
    t.pool_pct = v.pool.pct;
    t.authCount++;
    this.log({
      tone: v.result === 0 ? 'ok' : 'bad',
      sev: v.result === 0 ? 'info' : v.result === 3 ? 'warn' : 'error',
      terminalId: v.terminal_id, runId: v.run_id, type: 'verdict',
      text: `判定 ${v.result_name} HD=${v.hd}/${64 * v.n_responses}`
        + (v.r2 ? ` R2=${v.r2}` : '')
        + `(绿区 <${v.thresholds.scaled_pass} / 红区 ≥${v.thresholds.scaled_reject})`,
    });
  }

  onConfirm(c: ConfirmDone): void {
    if (this.stageAccepts(c.terminal_id)) {
      const r = this.runFor(c.run_id, c.terminal_id);
      r.confirm = c;
      r.terminalBlocked = c.status !== 0;    // status=1 即 S7 终端侧 BLOCKED(见 RunState)
      r.endedAt = performance.now();
    }
    this.log({
      tone: c.status === 0 ? 'ok' : 'error',
      sev: c.status === 0 ? 'info' : 'error',
      terminalId: c.terminal_id, runId: c.run_id, type: 'confirm.done',
      text: c.status === 0
        ? `CONFIRM OK 双向闭环${c.verified_r2 ? '(终端侧 R2 复算一致)' : '(终端侧 R2 不一致)'}`
        : '终端侧 BLOCKED —— 检出 R2 被篡改(假基站),拒绝发 CONFIRM',
    });
  }

  onEnroll(e: EnrollDone): void {
    this.upsertTerminal(e.terminal_id, {
      n_pairs: e.n_pairs, stable_bits: e.stable_bits, stability_pct: e.stability_pct,
      pool_remaining: e.pool.remaining, pool_size: e.pool.pool_size,
      pool_pct: e.pool.pct, enrolling: false,
    });
    this.log({
      tone: 'ok', sev: 'info', terminalId: e.terminal_id, runId: null,
      type: 'enroll.done',
      text: `注册完成 n_pairs=${e.n_pairs} (本次新增 ${e.added})`
        + ` stable=${e.stable_bits}/64 (${e.stability_pct}%)`,
    });
  }

  onPool(w: PoolWarning): void {
    this.upsertTerminal(w.terminal_id, { poolWarn: true, pool_remaining: w.remaining, pool_pct: w.pct });
    this.log({
      tone: 'replay', sev: 'warn', terminalId: w.terminal_id, runId: null,
      type: 'pool.warning',
      text: `CRP 池告警 remaining=${w.remaining} (${w.pct}%) —— 抽干后需重注册补池`,
    });
  }

  onReplay(r: { run_id: string; terminal_id: number; result: 4 }): void {
    this.log({
      tone: 'replay', sev: 'warn', terminalId: r.terminal_id, runId: r.run_id,
      type: 'replay.reject',
      text: '重放嫌疑:该 C2 已在回放窗内(执行「清 C2 窗」可恢复)',
    });
  }

  onServerLog(l: ServerLog): void {
    this.log({
      tone: l.level === 'error' ? 'error' : l.level === 'warn' ? 'replay' : 'info',
      sev: l.level === 'error' ? 'error' : l.level === 'warn' ? 'warn' : 'info',
      terminalId: null, runId: null, type: 'server.log', text: l.msg,
    });
  }

  onRunError(e: RunError): void {
    const r = this.state.run;
    if (r && r.run_id === e.run_id) {
      r.errors.push(e);
      r.endedAt = performance.now();
    }
    // job 失败时复位该终端的忙标志,否则注册失败卡片永远"注册中…"
    // (HTTP 层失败的复位在 main-console.ts 的 catch;这里兜 SSE 异步失败)
    if (e.terminal_id != null && e.stage === 'enroll') {
      this.upsertTerminal(e.terminal_id, { enrolling: false });
    }
    this.log({
      tone: 'error', sev: 'error', terminalId: e.terminal_id ?? null, runId: e.run_id,
      type: 'run.error', text: `[${e.stage}] ${e.error}`,
    });
  }

  onAck(terminalId: number, kind: 'c2reset' | 'setkey' | 'enroll-start'): void {
    if (kind === 'c2reset') this.upsertTerminal(terminalId, { c2Cleared: true });
    else if (kind === 'setkey') this.upsertTerminal(terminalId, { keyInstalled: true });
    else this.upsertTerminal(terminalId, { enrolling: true });
  }

  /* ---------- 日志 ---------- */
  log(e: Omit<LogEntry, 'seq' | 'ts'> & { ts?: string }): void {
    const row: LogEntry = {
      seq: this.state.logs.length,
      ts: e.ts ?? new Date().toISOString(),
      tone: e.tone, sev: e.sev, terminalId: e.terminalId,
      runId: e.runId, type: e.type, text: e.text,
    };
    this.state.logs.push(row);
    if (this.state.logs.length > LOG_CAP) {
      this.state.logs.splice(0, this.state.logs.length - LOG_CAP);
      // splice 后 seq 不再等于下标,重新编号以保持"seq 单调 + 即窗口内序号"
      this.state.logs.forEach((r, i) => { r.seq = i; });
    }
    this.emit();
  }

  /* ---------- UI 偏好 ---------- */
  patchUi(patch: Partial<UiState>): void {
    this.state.ui = { ...this.state.ui, ...patch };
    this.emit();
  }

  /* ---------- 舞台握手 ---------- */
  onStageTaken(): void { this.patchUi({ stage3d: true, stage3dFailed: false }); }
  onStageError(): void { this.patchUi({ stage3d: false, stage3dFailed: true }); }
}

export const store = new Store();
