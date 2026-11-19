/* ============================================================
 * 顶栏 —— 报告 §6.1 / §6.2
 * 品牌｜链路徽章(可点开详情)｜池水位概览(悬停分终端)｜帧速滑杆
 * ｜数据源徽章(三态,可点开清单)｜时钟+run 计数
 *
 * 链路徽章的四态是**合成量**,不是 link.status 单字段:
 *   OFF〜   : 尚未收到 link.status(桥接未启动/首连中)
 *   RECONNECTING : SSE 非 live(断线/轮询降级)—— §6.4 要求琥珀闪烁
 *   其余由 link.mode 决定 LOOPBACK / SERIAL
 * 否则桥接一断,徽章会停在最后一次的 "LOOPBACK" 上骗人。
 * ============================================================ */
import { barScale, hhmmss } from '../core/format';
import type { SseState } from '../core/api';
import type { AppState, TerminalState } from '../core/store';
import type { LinkBadgeState } from '../core/types';

export interface TopbarDeps {
  onFrameMs(ms: number): void;
}

export class Topbar {
  readonly el: HTMLElement;
  private deps: TopbarDeps;

  private linkBadge!: HTMLElement;
  private poolOverview!: HTMLElement;
  private poolTip!: HTMLElement;
  private slider!: HTMLInputElement;
  private sliderVal!: HTMLElement;
  private sourceBadge!: HTMLElement;
  private sourceTip!: HTMLElement;
  private clock!: HTMLElement;
  private counter!: HTMLElement;
  private popup: HTMLElement | null = null;

  constructor(deps: TopbarDeps) {
    this.deps = deps;
    this.el = document.createElement('div');
    this.el.className = 'topbar';
    this.el.innerHTML = `
      <div class="tb-brand">
        <span class="tb-logo"></span>
        <span class="tb-title">基于PUF的无人机身份认证系统<em>·演示控制台</em></span>
      </div>

      <button class="tb-link" id="tb-link" aria-expanded="false" title="点击查看链路详情">
        <i class="dot"></i><span id="tb-link-text">连接中…</span>
      </button>

      <div class="tb-pool" id="tb-pool" title="所有终端挑战池余量的最低值">
        <span class="k">挑战池最低余量</span>
        <span class="v mono" id="tb-pool-text">—</span>
        <div class="tb-bar"><i id="tb-pool-bar" style="transform:scaleX(0)"></i></div>
      </div>

      <label class="tb-slider" title="动画速度:只调整界面动画节奏,不改变认证时序与判决结果">
        <span class="k">动画速度</span>
        <input type="range" id="tb-ms" min="200" max="2000" step="50" value="600"
          aria-label="动画速度:每帧推进的毫秒数" />
        <span class="v mono" id="tb-ms-val">600 ms</span>
      </label>

      <span class="tb-spacer"></span>

      <button class="tb-source" id="tb-source" aria-expanded="false" title="点击查看数据来源说明">
        <i class="dot"></i><span id="tb-source-text">实时数据</span>
      </button>

      <div class="tb-clock">
        <span class="mono" id="tb-run">第 0 轮</span>
        <span class="mono" id="tb-clock">--:--:--.---</span>
      </div>

      <span class="tb-hint" title="快捷键 H 隐藏/显示顶栏">H</span>`;

    this.linkBadge = this.q('#tb-link');
    this.poolOverview = this.q('#tb-pool');
    this.slider = this.q<HTMLInputElement>('#tb-ms');
    this.sliderVal = this.q('#tb-ms-val');
    this.sourceBadge = this.q('#tb-source');
    this.clock = this.q('#tb-clock');
    this.counter = this.q('#tb-run');

    this.poolTip = this.mkPopup('tb-pool-tip');
    this.sourceTip = this.mkPopup('tb-source-tip');

    this.wire();
    this.tickClock();
  }

  private q<T extends HTMLElement>(sel: string): T { return this.el.querySelector<T>(sel)!; }

  private mkPopup(id: string): HTMLElement {
    const p = document.createElement('div');
    p.className = 'tb-popup';
    p.id = id;
    p.hidden = true;
    document.body.appendChild(p);
    return p;
  }

  private wire(): void {
    this.slider.addEventListener('input', () => {
      const ms = Number(this.slider.value);
      this.sliderVal.textContent = `${ms} ms`;
      this.deps.onFrameMs(ms);
    });

    this.linkBadge.addEventListener('click', () => this.toggleLinkDetail());
    this.sourceBadge.addEventListener('click', () => this.toggleSourceList());
    this.poolOverview.addEventListener('mouseenter', () => this.showPoolTip());
    this.poolOverview.addEventListener('mouseleave', () => { this.poolTip.hidden = true; });

    /* 浮层要能只靠键盘关掉(R5 无障碍)。鼠标侧有「点任意处关闭」,键盘侧只有
     * Tab,而 Tab 不触发 click —— 少了这两条,Esc 之前浮层会一直盖在页面上,
     * 且焦点已经走远,读屏用户既不知道它开着、也关不掉它。 */
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape') return;
      if (this.popup) { this.closePopups(); this.linkBadge.focus(); return; }
      if (!this.sourceTip.hidden) { this.closePopups(); this.sourceBadge.focus(); }
    });
    // Tab 走出徽章与浮层之外就收起,与鼠标的 away 行为对齐
    document.addEventListener('focusin', (e) => {
      const t = e.target as Node;
      if (this.popup && !this.popup.contains(t) && !this.linkBadge.contains(t)) {
        this.closePopups();
      }
    });

    // 视口变化时已展开的浮层要跟着走位,否则会悬在半空
    window.addEventListener('resize', () => {
      if (!this.poolTip.hidden) this.showPoolTip();
      if (!this.sourceTip.hidden) this.showSourceTip();
    });
  }

  private closePopups(): void {
    this.poolTip.hidden = true;
    this.sourceTip.hidden = true;
    if (this.popup) { this.popup.remove(); this.popup = null; }
    this.syncExpanded();
  }

  /* 徽章是 <button>,键盘本来就能按;缺的是「按下去之后开着还是关着」这件事
   * 只有视觉在说。aria-expanded 把它讲出来。 */
  private syncExpanded(): void {
    this.linkBadge.setAttribute('aria-expanded', String(this.popup != null));
    this.sourceBadge.setAttribute('aria-expanded', String(!this.sourceTip.hidden));
  }

  private place(p: HTMLElement, anchor: HTMLElement): void {
    const r = anchor.getBoundingClientRect();
    p.style.left = `${Math.max(8, Math.min(r.left, window.innerWidth - p.offsetWidth - 8))}px`;
    p.style.top = `${r.bottom + 6}px`;
    p.hidden = false;
    this.syncExpanded();
  }

  /* ---------- 链路详情 ---------- */
  private toggleLinkDetail(): void {
    if (this.popup) { this.closePopups(); return; }
    this.closePopups();
    const st = this.last;
    if (!st) return;
    const link = st.link;
    const p = document.createElement('div');
    p.className = 'tb-popup tb-detail';
    p.innerHTML = `
      <div class="tp-title">链路详情</div>
      <dl>
        <dt>连接方式</dt><dd class="mono">${link ? (link.mode === 'loopback' ? '本机模拟(PC 自环)' : '串口') : '—'}</dd>
        <dt>连接状态</dt><dd class="mono">${link ? (link.connected ? '已连接' : '未连接') : '—'}</dd>
        <dt>运行时长</dt><dd class="mono">${link ? `${link.uptime_s.toFixed(1)} s` : '—'}</dd>
        <dt>终端侧响应</dt><dd class="mono">${link ? (link.proxy ? '由 PC 模拟' : '真实终端') : '—'}</dd>
        <dt>基站服务版本</dt><dd class="mono">${link?.version ?? '—'}</dd>
        <dt>实时推送</dt><dd class="mono">${this.sseState === 'live' ? '正常'
          : this.sseState === 'polling' ? '降级轮询'
            : this.sseState === 'reconnecting' ? '重连中' : '连接中'}</dd>
      </dl>
      ${link?.version?.endsWith('-mock')
        ? '<div class="tp-warn">该基站服务以示例模式启动：以下事件为示例回放，不能作为实测证据。</div>'
        : ''}
      ${link?.proxy
        ? '<div class="tp-note">终端侧响应由 PC 模拟。答辩口径：当前 PC 代替终端产生响应，接入实板后由真实终端生成。</div>'
        : ''}
      <div class="tp-note">点击任意处关闭</div>`;
    document.body.appendChild(p);
    this.popup = p;
    this.place(p, this.linkBadge);
    const away = (ev: MouseEvent) => {
      if (p.contains(ev.target as Node) || this.linkBadge.contains(ev.target as Node)) return;
      this.closePopups();
      document.removeEventListener('click', away, true);
    };
    window.setTimeout(() => document.addEventListener('click', away, true), 0);
  }

  /* ---------- 数据源清单(§4.4 三态) ---------- */
  private toggleSourceList(): void {
    if (!this.sourceTip.hidden) { this.closePopups(); return; }
    this.closePopups();
    this.showSourceTip();
  }

  private showSourceTip(): void {
    const cur = this.last?.source ?? 'REAL-LIVE';
    const rows = [
      ['REAL-LIVE', '实时数据', '认证过程中由基站服务实时产生的事件（含 PC 模拟的终端响应）。本页默认来源。'],
      ['REAL-STATIC', '回读数据', '已落盘后回读的数据：采样文件、导入文件。'],
      ['MOCK', '示例数据', '内置示例或基站服务示例回放，仅用于界面演示，不能作为实测证据。'],
    ] as const;
    this.sourceTip.innerHTML = `
      <div class="tp-title">数据来源说明</div>
      <ul class="tp-src">
        ${rows.map(([n, cn, d]) => `
          <li class="${n === cur ? 'cur' : ''}">
            <span class="chip ${n === 'MOCK' ? 'amber' : n === 'REAL-STATIC' ? '' : 'green'}">${cn}</span>
            <span class="tp-src-d">${d}</span>
            ${n === cur ? '<span class="tp-src-cur">当前</span>' : ''}
          </li>`).join('')}
      </ul>
      <div class="tp-note">切换：系统总览页右上角选择器；本页跟随基站服务的运行模式。</div>`;
    this.place(this.sourceTip, this.sourceBadge);
  }

  /* ---------- 池水位概览 ---------- */
  private showPoolTip(): void {
    const ts = this.terminals;
    this.poolTip.innerHTML = `
      <div class="tp-title">各终端挑战池余量</div>
      ${ts.length === 0 ? '<div class="tp-note">尚无终端</div>' : `
      <ul class="tp-pool">
        ${ts.map(t => `
          <li>
            <span class="mono">终端 ${t.id}</span>
            <div class="tb-bar ${t.pool_pct < 20 ? 'warn' : ''}"><i style="${barScale(t.pool_pct)}"></i></div>
            <span class="mono">${t.pool_remaining}/${t.pool_size || '—'} 组 (${t.pool_pct}%)</span>
          </li>`).join('')}
      </ul>`}
      <div class="tp-note">分母是该设备注册时的容量上限，不是当前余量。</div>`;
    this.place(this.poolTip, this.poolOverview);
  }

  /* ---------- 渲染 ---------- */
  private last: AppState | null = null;
  private sseState: SseState = 'connecting';
  private terminals: TerminalState[] = [];
  private clockTimer = 0;

  private tickClock(): void {
    const paint = () => { this.clock.textContent = hhmmss(new Date()); };
    paint();
    this.clockTimer = window.setInterval(paint, 50);
  }

  dispose(): void {
    if (this.clockTimer) clearInterval(this.clockTimer);
    this.closePopups();
    this.poolTip.remove();
    this.sourceTip.remove();
  }

  update(s: AppState, sse: SseState): void {
    this.last = s;
    this.sseState = sse;
    this.terminals = [...s.terminals.values()].sort((a, b) => a.id - b.id);

    /* 链路徽章(四态合成) */
    let bs: LinkBadgeState;
    if (sse !== 'live' && s.link == null) bs = 'OFFLINE';
    else if (sse !== 'live') bs = 'RECONNECTING';
    else if (s.link == null) bs = 'OFFLINE';
    else bs = s.link.mode === 'loopback' ? 'LOOPBACK' : 'SERIAL';
    const label = bs === 'SERIAL'
      ? `串口${s.link?.connected ? '' : '(未连接)'}`
      : bs === 'RECONNECTING' ? '重连中…' : bs === 'OFFLINE' ? '离线' : '本机模拟';
    this.linkBadge.className = `tb-link st-${bs.toLowerCase()}`
      + (bs === 'RECONNECTING' ? ' blink' : '');
    this.q('#tb-link-text').textContent = label;

    /* 池水位概览:取所有终端的最小百分比 */
    const withPool = this.terminals.filter(t => t.pool_size > 0);
    const min = withPool.length === 0 ? null
      : withPool.reduce((a, b) => (a.pool_pct <= b.pool_pct ? a : b));
    this.q('#tb-pool-text').textContent = min == null
      ? '—'
      : `${min.pool_pct}%  (终端 ${min.id} ${min.pool_remaining}/${min.pool_size} 组)`;
    const bar = this.q('#tb-pool-bar');
    bar.setAttribute('style', barScale(min?.pool_pct));
    bar.parentElement!.className = 'tb-bar' + ((min?.pool_pct ?? 100) < 20 ? ' warn' : '');

    /* 帧速滑杆:仅回填外部改动,避免打断用户拖动 */
    if (document.activeElement !== this.slider) {
      this.slider.value = String(s.ui.frameMs);
      this.sliderVal.textContent = `${s.ui.frameMs} ms`;
    }

    /* 数据源徽章 */
    const src = s.source;
    this.sourceBadge.className = 'tb-source st-'
      + (src === 'MOCK' ? 'mock' : src === 'REAL-STATIC' ? 'static' : 'live');
    this.q('#tb-source-text').textContent =
      src === 'MOCK' ? '示例数据' : src === 'REAL-STATIC' ? '回读数据' : '实时数据';

    this.counter.textContent = `第 ${s.runCount} 轮`;
  }
}
