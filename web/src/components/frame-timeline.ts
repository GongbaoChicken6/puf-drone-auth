/* ============================================================
 * 五帧时序(2D) —— 报告 §6.2「中央·认证舞台 / 2D 保底帧时序」
 *
 * 帧序取自桥接编排实读(web_bridge.py _open_round/_auth_round):
 *   常规: ACCESS_REQUEST → CHALLENGE → RESPONSE_R1 → RESULT → CONFIRM
 *   灰区: …RESPONSE_R1 → **EXTRA_CHALLENGE → RESPONSE_R1** → RESULT → CONFIRM
 * 故 EXTRA_CHALLENGE 连同它的第二个响应**成对分叉下挂**在 RESULT 之前,
 * 而不是插进主线 —— 这是 §6.2「从判定前分叉下挂」的确切含义。
 *
 * 方向由 frame.dir 决定(term->server 为上行、server->term 为下行),
 * 不按节点名猜:CONFIRM 只在 PASS 后才出现,REJECT 路线根本没有它。
 * ============================================================ */
import type { RunState, TerminalState } from '../core/store';
import { MSG, MSG_NAMES } from '../core/types';

type NodeState = 'idle' | 'tx' | 'rx' | 'ok' | 'fail';

interface Slot {
  key: string;
  label: string;
  node: HTMLElement;
  state: NodeState;
}

const MAIN: { key: string; label: string; msg: number }[] = [
  { key: 'ar', label: 'ACCESS_REQUEST', msg: MSG.ACCESS_REQUEST },
  { key: 'ch', label: 'CHALLENGE', msg: MSG.CHALLENGE },
  { key: 'r1', label: 'RESPONSE_R1', msg: MSG.RESPONSE_R1 },
];
const TAIL: { key: string; label: string; msg: number }[] = [
  { key: 'res', label: 'RESULT', msg: MSG.RESULT },
  { key: 'cf', label: 'CONFIRM', msg: MSG.CONFIRM },
];
const FORK: { key: string; label: string; msg: number }[] = [
  { key: 'xc', label: 'EXTRA_CHALLENGE', msg: MSG.EXTRA_CHALLENGE },
  { key: 'xr1', label: 'RESPONSE_R1', msg: MSG.RESPONSE_R1 },
];

export class FrameTimeline {
  readonly el: HTMLElement;
  private slots = new Map<string, Slot>();
  private forkWrap!: HTMLElement;
  private forkLink!: HTMLElement;
  private note!: HTMLElement;
  private prevKey = '';
  private drawnRunId = '';

  constructor() {
    this.el = document.createElement('div');
    this.el.className = 'frame-timeline';

    this.el.innerHTML = `
      <div class="ft-main" id="ft-main"></div>
      <div class="ft-fork" id="ft-fork"><span class="ft-fork-label">灰区分叉</span></div>
      <div class="ft-note" id="ft-note"></div>`;
    this.forkWrap = this.el.querySelector<HTMLElement>('#ft-fork')!;
    this.forkLink = document.createElement('div');
    this.forkLink.className = 'ft-fork-link';
    this.note = this.el.querySelector<HTMLElement>('#ft-note')!;

    const main = this.el.querySelector<HTMLElement>('#ft-main')!;
    this.buildRow(main, MAIN, 'ft-node');
    main.append(this.mkArrow('ft-arrow'));
    this.buildRow(main, TAIL, 'ft-node');

    const fork = this.el.querySelector<HTMLElement>('#ft-fork')!;
    fork.prepend(this.forkLink);
    this.buildRow(fork, FORK, 'ft-node ft-node-fork');

    this.reset();
  }

  private buildRow(parent: HTMLElement, defs: typeof MAIN, cls: string): void {
    defs.forEach((d, i) => {
      if (i > 0) parent.append(this.mkArrow('ft-arrow'));
      const node = document.createElement('div');
      node.className = cls;
      node.innerHTML = `<span class="ft-name">${d.label}</span>
        <span class="ft-dir"></span><span class="ft-st"></span>`;
      parent.append(node);
      this.slots.set(d.key, { key: d.key, label: d.label, node, state: 'idle' });
    });
  }

  private mkArrow(cls: string): HTMLElement {
    const a = document.createElement('div');
    a.className = cls;
    a.textContent = '⇄';
    return a;
  }

  private set(key: string, state: NodeState, dir?: 'up' | 'down', hint?: string): void {
    const s = this.slots.get(key);
    if (!s) return;
    s.state = state;
    s.node.className = s.node.className.replace(/\bft-(idle|tx|rx|ok|fail)\b/g, '').trim();
    s.node.classList.add(`ft-${state}`, 'ft-node');
    const dirEl = s.node.querySelector('.ft-dir')!;
    dirEl.textContent = dir === 'up' ? '终端→基站' : dir === 'down' ? '基站→终端' : '';
    dirEl.className = 'ft-dir' + (dir ? ` ft-dir-${dir}` : '');
    const st = s.node.querySelector('.ft-st')!;
    st.textContent = state === 'idle' ? '未到达'
      : state === 'tx' || state === 'rx' ? '在途'
      : state === 'ok' ? '通过' : '失败';
    if (hint) s.node.title = hint;
  }

  reset(): void {
    this.slots.forEach((_, k) => this.set(k, 'idle'));
    this.forkWrap.classList.remove('open');
    this.el.classList.remove('has-run');
    this.note.textContent = '等待指令 —— 五个帧节点:接入请求 / 挑战 / 响应 / 判定 / 确认';
    this.prevKey = '';
    this.drawnRunId = '';
  }

  /* 把 run 的帧序列归位到槽位。灰区分叉由 EXTRA_CHALLENGE 的实际出现驱动,
   * 不靠 mode 字段推断 —— 展示的是"桥接真的发了什么"。 */
  update(run: RunState | null, term: TerminalState | null): void {
    if (!run || run.frames.length === 0) { this.reset(); return; }
    /* 换 run 必须先复位再画。update() 只设置「本轮见过的帧」对应的节点,不碰
     * 本轮没出现的节点 —— 而 doAuth(main-console.ts:144)是**先 POST 后
     * beginRun**:桥接在响应返回前就把整轮 SSE 发完了,于是「新 run 的
     * frames.length===0」这一时刻根本不存在,靠它触发的 reset() 永远等不到。
     * 后果实测:S1(PASS)之后跑 S2(4 帧、无 CONFIRM),主线四个节点都被判定
     * 回填成 fail,而 CONFIRM 节点还留着 S1 的绿色「通过·双向闭环」—— 同一屏
     * 里 note 写着「4 帧」,节点却在报一次根本没发生的闭环。3D 接管后本时序被
     * 隐藏,故 §13 的 3D 探针一直没照到;是 2D 保底探针把它量出来的。 */
    if (run.run_id !== this.drawnRunId) { this.reset(); this.drawnRunId = run.run_id; }
    this.el.classList.add('has-run');

    let seenExtra = false;
    let r1Done = false;
    const last = run.frames[run.frames.length - 1];

    for (const f of run.frames) {
      const dir: 'up' | 'down' = f.dir === 'term->server' ? 'up' : 'down';
      const st: NodeState = f.dir === 'term->server' ? 'rx' : 'tx';
      switch (f.msg_id) {
        case MSG.ACCESS_REQUEST: this.set('ar', st, dir); break;
        case MSG.CHALLENGE: this.set('ch', st, dir); break;
        case MSG.EXTRA_CHALLENGE:
          seenExtra = true;
          this.set('xc', st, dir);
          break;
        case MSG.RESPONSE_R1:
          if (seenExtra) this.set('xr1', st, dir);
          else if (!r1Done) { this.set('r1', st, dir); r1Done = true; }
          else this.set('xr1', st, dir);      // 防御:意外多帧时不覆盖首响应
          break;
        case MSG.RESULT: this.set('res', st, dir); break;
        case MSG.CONFIRM: this.set('cf', st, dir); break;
        default: break;
      }
    }

    if (seenExtra) {
      this.forkWrap.classList.add('open');
      this.forkLink.textContent = `判定前分叉 · 加测 ${run.extra?.n ?? 3} 挑战,总轮次 `
        + `${run.frames.filter(f => f.msg_id === MSG.RESPONSE_R1).length} 段响应`;
    } else {
      this.forkWrap.classList.remove('open');
      this.forkLink.textContent = '';
    }

    // 判定下来后回填主线各节点的"通过/失败"(它们都参与了这次判定)
    const v = run.verdict;
    if (v) {
      const cls: NodeState = v.result === 0 ? 'ok' : 'fail';
      for (const k of ['ar', 'ch', 'r1', 'res']) {
        const s = this.slots.get(k)!;
        if (s.state !== 'idle') this.set(k, cls, undefined, s.node.title);
      }
      const res = this.slots.get('res')!;
      res.node.querySelector('.ft-st')!.textContent = `通过 · ${v.result_name}`;
      if (v.result !== 0) {
        res.node.querySelector('.ft-st')!.textContent = `失败 · ${v.result_name}`;
      }
      if (seenExtra) {
        for (const k of ['xc', 'xr1']) {
          const s = this.slots.get(k)!;
          if (s.state !== 'idle') this.set(k, cls);
        }
      }
    }

    // CONFIRM:仅在 PASS 后才存在。status=1 即 S7 终端侧 BLOCKED(不发 CONFIRM)。
    if (run.confirm) {
      const ok = run.confirm.status === 0;
      this.set('cf', ok ? 'ok' : 'fail', 'up',
        ok ? '终端侧 R2 复算一致,双向闭环'
          : '终端侧检出 R2 被篡改(假基站),拒绝发 CONFIRM');
      this.slots.get('cf')!.node.querySelector('.ft-st')!.textContent =
        ok ? '通过 · 双向闭环' : '失败 · 终端侧 BLOCKED';
    }

    // 高频变更的只有"最新到达帧"高亮,值不变时不重排 DOM
    const key = `${run.run_id}:${run.frames.length}:${v?.result ?? -1}:${run.confirm?.status ?? -1}`;
    if (key === this.prevKey) return;
    this.prevKey = key;

    this.note.textContent = this.describe(run, term, last.name, seenExtra);
  }

  private describe(run: RunState, term: TerminalState | null, lastName: string,
                   seenExtra: boolean): string {
    const ms = run.endedAt != null ? `${Math.round(run.endedAt - run.startedAt)}ms` : '进行中';
    const tid = term?.id ?? run.terminal_id;
    const bits = [
      `run ${run.run_id}`, `终端 ${tid}`,
      `${run.frames.length} 帧`, seenExtra ? '灰区加测' : '常规',
      ms,
    ];
    if (run.verdict) {
      bits.push(`判定 ${run.verdict.result_name}(HD ${run.verdict.hd})`);
    } else {
      bits.push(`最新 ${MSG_NAMES[run.frames[run.frames.length - 1].msg_id] ?? lastName}`);
    }
    return bits.join(' · ');
  }
}
