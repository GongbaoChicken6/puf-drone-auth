/* ============================================================
 * 审计日志 —— 报告 §6.2「底栏·审计日志」
 *
 * 虚拟滚动:store 的日志封顶 2000 行,底栏可视区仅约 9 行,全量铺 DOM 会在
 * 演示时掉帧。这里用固定行高的窗口化渲染(只挂可见区 ± 缓冲),行高写在
 * CSS 变量 --log-row 里并由本模块读取,保证 JS 与样式不各说各话。
 *
 * 过滤维度按 §6.2 的三种:terminal / 严重级 / 类型(type 取自原始 SSE type)。
 * 配色按 tone(不是 sev)—— 同为 warn 的 gray.extra 与 replay.reject 颜色不同。
 *
 * 「导出本次运行 JSON」导出的是**原始事件流**(含 seq/ts 信封),由入口用
 * SseClient.onEnvelope 旁路留存的账本提供,不是这里的派生日志行。
 * ============================================================ */
import { hhmmss } from '../core/format';
import type { LogEntry, LogSev } from '../core/store';

const ROW_H = 22;
const BUFFER = 6;

export interface AuditLogDeps {
  /* runId=null 表示导出全部;由入口决定落盘方式并给出反馈 */
  exportRun(runId: string | null): void;
}

export class AuditLog {
  readonly el: HTMLElement;
  private deps: AuditLogDeps;

  private viewport!: HTMLElement;
  private spacer!: HTMLElement;
  private layer!: HTMLElement;
  private countEl!: HTMLElement;
  private filterTid!: HTMLSelectElement;
  private filterSev!: HTMLSelectElement;
  private filterType!: HTMLSelectElement;

  private rows: LogEntry[] = [];
  private all: LogEntry[] = [];
  private currentRunId: string | null = null;
  private exportRunBtn!: HTMLButtonElement;
  private follow = true;
  private painted = '';

  constructor(deps: AuditLogDeps) {
    this.deps = deps;
    this.el = document.createElement('div');
    this.el.className = 'audit-log';
    this.el.innerHTML = `
      <div class="al-head">
        <span class="al-title">审计日志</span>
        <label class="al-filter">终端 <select id="al-tid"><option value="all">全部</option></select></label>
        <label class="al-filter">严重级 <select id="al-sev">
          <option value="all">全部</option><option value="info">info</option>
          <option value="warn">warn</option><option value="error">error</option></select></label>
        <label class="al-filter">类型 <select id="al-type"><option value="all">全部</option></select></label>
        <span class="al-count" id="al-count">0 行</span>
        <span class="al-spacer"></span>
        <button class="btn ghost" id="al-follow" aria-pressed="true" title="钉在底部自动跟随最新事件">跟随 ✓</button>
        <button class="btn ghost" id="al-export-run"
          title="导出当前 run 的原始 SSE 事件流(含 seq/ts 信封),作为答辩证据附件">
          导出本次运行</button>
        <button class="btn ghost" id="al-export-all"
          title="导出全部已缓存事件(同为本进程真实收到的原始信封)">导出全部</button>
        <button class="btn ghost" id="al-clear">清屏</button>
      </div>
      <div class="al-viewport" id="al-vp">
        <div class="al-scroll" id="al-sp"><div class="al-layer" id="al-ly"></div></div>
      </div>`;

    this.viewport = this.q('#al-vp');
    this.spacer = this.q('#al-sp');
    this.layer = this.q('#al-ly');
    this.countEl = this.q('#al-count');
    this.filterTid = this.q<HTMLSelectElement>('#al-tid');
    this.filterSev = this.q<HTMLSelectElement>('#al-sev');
    this.filterType = this.q<HTMLSelectElement>('#al-type');

    this.filterTid.addEventListener('change', () => { this.follow = true; this.apply(); });
    this.filterSev.addEventListener('change', () => { this.follow = true; this.apply(); });
    this.filterType.addEventListener('change', () => { this.follow = true; this.apply(); });
    this.exportRunBtn = this.q('#al-export-run');
    /* 修复(按钮审计 P2-6):无当前运行时「导出本次运行」与实际范围(全部)错位。
     * 改为按钮如实禁用并说明原因,杜绝静默降级。 */
    this.exportRunBtn.disabled = this.currentRunId == null;
    this.exportRunBtn.addEventListener('click',
      () => this.deps.exportRun(this.currentRunId));
    this.q('#al-export-all').addEventListener('click', () => this.deps.exportRun(null));
    this.q('#al-clear').addEventListener('click', () => this.clear());
    const fb = this.q('#al-follow');
    fb.addEventListener('click', () => {
      this.setFollow(!this.follow);
      if (this.follow) this.scrollToEnd();
    });

    this.viewport.addEventListener('scroll', () => {
      const atBottom = this.viewport.scrollTop + this.viewport.clientHeight
        >= this.viewport.scrollHeight - 4;
      // 用户往上翻即自动解除跟随 —— 这条**隐式**状态变化也要能被读到,
      // 故与点击走同一个出口,不在别处单独改 textContent。
      if (!atBottom && this.follow) this.setFollow(false);
      this.paint();
    });
    window.addEventListener('resize', () => this.paint());
  }

  private q<T extends HTMLElement>(sel: string): T {
    return this.el.querySelector<T>(sel)!;
  }

  /* 「跟随」是一个开关,文字 ✓/✗ 是给眼睛看的,aria-pressed 是给读屏听的。
   * 两处写在同一行,避免以后有人在别处改文字而忘了改状态。 */
  private setFollow(on: boolean): void {
    this.follow = on;
    const fb = this.q('#al-follow');
    fb.textContent = on ? '跟随 ✓' : '跟随 ✗';
    fb.setAttribute('aria-pressed', String(on));
  }

  clear(): void {
    // 只清本组件的视图,不动 store 的账本(导出仍可用)
    this.rows = [];
    this.painted = '';
    this.spacer.style.height = '0px';
    this.layer.replaceChildren();
    this.countEl.textContent = '视图已清屏(账本保留,导出不受影响)';
  }

  private populateFilters(): void {
    const tids = new Set<number>();
    const types = new Set<string>();
    for (const l of this.all) {
      if (l.terminalId != null) tids.add(l.terminalId);
      types.add(l.type);
    }
    const keepTid = this.filterTid.value;
    if (this.filterTid.options.length - 1 !== tids.size) {
      this.filterTid.replaceChildren(new Option('全部', 'all'));
      [...tids].sort((a, b) => a - b)
        .forEach(t => this.filterTid.append(new Option(`tid ${t}`, String(t))));
      this.filterTid.value = keepTid;
    }
    const keepType = this.filterType.value;
    if (this.filterType.options.length - 1 !== types.size) {
      this.filterType.replaceChildren(new Option('全部', 'all'));
      [...types].sort().forEach(t => this.filterType.append(new Option(t, t)));
      this.filterType.value = keepType;
    }
  }

  update(all: LogEntry[], currentRunId: string | null): void {
    this.all = all;
    this.currentRunId = currentRunId;
    if (this.exportRunBtn) {
      this.exportRunBtn.disabled = currentRunId == null;
      this.exportRunBtn.title = currentRunId == null
        ? '当前无运行:按钮禁用(「导出全部」仍可用)'
        : '导出当前 run 的原始 SSE 事件流(含 seq/ts 信封),作为答辩证据附件';
    }
    this.populateFilters();
    this.apply();
  }

  private apply(): void {
    const tid = this.filterTid.value;
    const sev = this.filterSev.value as LogSev | 'all';
    const type = this.filterType.value;
    this.rows = this.all.filter(l =>
      (tid === 'all' || String(l.terminalId) === tid)
      && (sev === 'all' || l.sev === sev)
      && (type === 'all' || l.type === type));
    this.painted = '';
    this.spacer.style.height = `${this.rows.length * ROW_H}px`;
    this.countEl.textContent = `${this.rows.length} / ${this.all.length} 行`
      + (this.currentRunId ? ` · 当前 run ${this.currentRunId}` : '');
    if (this.follow) this.scrollToEnd();
    else this.paint();
  }

  private scrollToEnd(): void {
    this.viewport.scrollTop = this.spacer.offsetHeight;
    this.paint();
  }

  /* 窗口化绘制:只挂可见区的行,用 translateY 定位,行数再多也不会爆 DOM */
  private paint(): void {
    const start = Math.max(0, Math.floor(this.viewport.scrollTop / ROW_H) - BUFFER);
    const visible = Math.ceil(this.viewport.clientHeight / ROW_H) + BUFFER * 2;
    const end = Math.min(this.rows.length, start + visible);
    const key = `${start}:${end}:${this.rows.length}`;
    if (key === this.painted) return;
    this.painted = key;

    this.layer.style.transform = `translateY(${start * ROW_H}px)`;
    const frag = document.createDocumentFragment();
    for (let i = start; i < end; i++) {
      const l = this.rows[i];
      const row = document.createElement('div');
      row.className = `al-row tone-${l.tone} sev-${l.sev}`;
      row.style.height = `${ROW_H}px`;
      const ts = document.createElement('span');
      ts.className = 'al-ts mono';
      ts.textContent = hhmmss(l.ts);
      const ty = document.createElement('span');
      ty.className = 'al-type mono';
      ty.textContent = l.type;
      const tid = document.createElement('span');
      tid.className = 'al-tid mono';
      tid.textContent = l.terminalId != null ? `t${l.terminalId}` : '—';
      const tx = document.createElement('span');
      tx.className = 'al-text';
      tx.textContent = l.text;
      row.append(ts, ty, tid, tx);
      row.title = `${l.ts}\n${l.type}${l.runId ? ` · run ${l.runId}` : ''}`
        + `\n${l.text}`;
      frag.append(row);
    }
    this.layer.replaceChildren(frag);
  }
}
