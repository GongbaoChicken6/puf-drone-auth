/* ============================================================
 * 顶栏 —— 报告 §6.1 / §6.2
 * 品牌｜链路徽章(可点开详情)｜池水位概览(悬停分终端)｜帧速滑杆
 * ｜剧本模式键｜数据源徽章(三态,可点开清单)｜时钟+run 计数
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
import { QUEUE_ALL, QUEUE_MUTEX, SCENARIOS, type PlayerStatus } from '../core/scenario';

export interface TopbarDeps {
  onFrameMs(ms: number): void;
  onPlay(ids: readonly ('S1' | 'S2' | 'S3' | 'S4' | 'S5' | 'S6' | 'S7')[]): void;
  onStep(): void;
  onPauseToggle(): void;
  onStop(): void;
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
  private scenStat!: HTMLElement;
  private playBtn!: HTMLButtonElement;
  private stepBtn!: HTMLButtonElement;
  private pauseBtn!: HTMLButtonElement;
  private popup: HTMLElement | null = null;

  constructor(deps: TopbarDeps) {
    this.deps = deps;
    this.el = document.createElement('div');
    this.el.className = 'topbar';
    this.el.innerHTML = `
      <div class="tb-brand">
        <span class="tb-logo"></span>
        <span class="tb-title">PUF 无人机认证 <em>· 演示控制台</em></span>
      </div>

      <button class="tb-link" id="tb-link" aria-expanded="false" title="点击查看链路详情">
        <i class="dot"></i><span id="tb-link-text">连接中…</span>
      </button>

      <div class="tb-pool" id="tb-pool" title="所有终端 CRP 池最低水位">
        <span class="k">池最低水位</span>
        <span class="v mono" id="tb-pool-text">—</span>
        <div class="tb-bar"><i id="tb-pool-bar" style="transform:scaleX(0)"></i></div>
      </div>

      <label class="tb-slider" title="帧速滑杆:仅调整前端动画节奏,不改变后端时序(§6.2)">
        <span class="k">帧速</span>
        <input type="range" id="tb-ms" min="200" max="2000" step="50" value="600"
          aria-label="帧速:每帧推进的毫秒数" />
        <span class="v mono" id="tb-ms-val">600 ms</span>
      </label>

      <div class="tb-scripts">
        <span class="k">剧本</span>
        <button class="btn ghost" id="tb-play-mutex" title="一键连播 S1→S2(默认互斥叙事)">S1→S2</button>
        <button class="btn ghost" id="tb-play-all" title="全场景连播 S1…S7">全场景</button>
        <button class="btn ghost" id="tb-step" title="逐幕单步(暂停态下推一幕)">单步</button>
        <button class="btn ghost" id="tb-pause" title="暂停/继续自动推进">暂停</button>
        <button class="btn ghost" id="tb-stop" title="停止并清空剧本队列">停止</button>
        <span class="tb-scen-stat mono" id="tb-scen-stat">idle</span>
      </div>

      <span class="tb-spacer"></span>

      <button class="tb-source" id="tb-source" aria-expanded="false" title="点击查看数据源清单(§4.4)">
        <i class="dot"></i><span id="tb-source-text">REAL-LIVE</span>
      </button>

      <div class="tb-clock">
        <span class="mono" id="tb-run">run 0</span>
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
    this.scenStat = this.q('#tb-scen-stat');
    this.playBtn = this.q<HTMLButtonElement>('#tb-play-mutex');
    this.stepBtn = this.q<HTMLButtonElement>('#tb-step');
    this.pauseBtn = this.q<HTMLButtonElement>('#tb-pause');

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

    this.playBtn.addEventListener('click', () => this.deps.onPlay(QUEUE_MUTEX));
    this.q('#tb-play-all').addEventListener('click', () => this.deps.onPlay(QUEUE_ALL));
    this.stepBtn.addEventListener('click', () => this.deps.onStep());
    this.pauseBtn.addEventListener('click', () => this.deps.onPauseToggle());
    this.q('#tb-stop').addEventListener('click', () => this.deps.onStop());

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
        <dt>transport</dt><dd class="mono">${link ? (link.mode === 'loopback' ? 'loopback(PC 自环)' : '串口 serial') : '—'}</dd>
        <dt>connected</dt><dd class="mono">${link ? String(link.connected) : '—'}</dd>
        <dt>uptime</dt><dd class="mono">${link ? `${link.uptime_s.toFixed(1)} s` : '—'}</dd>
        <dt>终端侧代演</dt><dd class="mono">${link ? (link.proxy ? '是(proxy=true)' : '否') : '—'}</dd>
        <dt>桥接版本</dt><dd class="mono">${link?.version ?? '—'}</dd>
        <dt>SSE</dt><dd class="mono">${this.sseState}</dd>
      </dl>
      ${link?.version?.endsWith('-mock')
        ? '<div class="tp-warn">该桥接以 --mock 启动:以下全部事件为 MOCK 回放,不可作为实测证据。</div>'
        : ''}
      ${link?.proxy
        ? '<div class="tp-note">终端侧三帧由桥接代演(§8.1)。答辩话术:PC 模拟终端行为,板可用后换真终端。</div>'
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
      ['REAL-LIVE', '桥接层实时产生的事件(含代演终端)。本页默认态。'],
      ['REAL-STATIC', '落盘后回读的数据:tools/sample_hd.py 采样 JSON、导入文件。'],
      ['MOCK', '内置样例 / 桥接 --mock 回放。页内一律以前缀 MOCK 标注,不可作为实测证据。'],
    ] as const;
    this.sourceTip.innerHTML = `
      <div class="tp-title">数据源清单(§4.4)</div>
      <ul class="tp-src">
        ${rows.map(([n, d]) => `
          <li class="${n === cur ? 'cur' : ''}">
            <span class="chip ${n === 'MOCK' ? 'amber' : n === 'REAL-STATIC' ? '' : 'green'}">${n}</span>
            <span class="tp-src-d">${d}</span>
            ${n === cur ? '<span class="tp-src-cur">当前</span>' : ''}
          </li>`).join('')}
      </ul>
      <div class="tp-note">切换:viz 页右上角三态选择器;console 页跟随桥接(link.version 以 -mock 结尾即 MOCK)。</div>`;
    this.place(this.sourceTip, this.sourceBadge);
  }

  /* ---------- 池水位概览 ---------- */
  private showPoolTip(): void {
    const ts = this.terminals;
    this.poolTip.innerHTML = `
      <div class="tp-title">分终端 CRP 池</div>
      ${ts.length === 0 ? '<div class="tp-note">尚无终端</div>' : `
      <ul class="tp-pool">
        ${ts.map(t => `
          <li>
            <span class="mono">tid ${t.id}</span>
            <div class="tb-bar ${t.pool_pct < 20 ? 'warn' : ''}"><i style="${barScale(t.pool_pct)}"></i></div>
            <span class="mono">${t.pool_remaining}/${t.pool_size || '—'} (${t.pool_pct}%)</span>
          </li>`).join('')}
      </ul>`}
      <div class="tp-note">分母 pool_size 是该设备的历史容量上限,不是当前余额。</div>`;
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

  update(s: AppState, sse: SseState, player: PlayerStatus): void {
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
      ? `SERIAL${s.link?.connected ? '' : '(未连接)'}`
      : bs === 'RECONNECTING' ? '重连中…' : bs === 'OFFLINE' ? '离线' : 'LOOPBACK';
    this.linkBadge.className = `tb-link st-${bs.toLowerCase()}`
      + (bs === 'RECONNECTING' ? ' blink' : '');
    this.q('#tb-link-text').textContent = label;

    /* 池水位概览:取所有终端的最小百分比 */
    const withPool = this.terminals.filter(t => t.pool_size > 0);
    const min = withPool.length === 0 ? null
      : withPool.reduce((a, b) => (a.pool_pct <= b.pool_pct ? a : b));
    this.q('#tb-pool-text').textContent = min == null
      ? '—'
      : `${min.pool_pct}%  (tid ${min.id} ${min.pool_remaining}/${min.pool_size})`;
    const bar = this.q('#tb-pool-bar');
    bar.setAttribute('style', barScale(min?.pool_pct));
    bar.parentElement!.className = 'tb-bar' + ((min?.pool_pct ?? 100) < 20 ? ' warn' : '');

    /* 帧速滑杆:仅回填外部改动,避免打断用户拖动 */
    if (document.activeElement !== this.slider) {
      this.slider.value = String(s.ui.frameMs);
      this.sliderVal.textContent = `${s.ui.frameMs} ms`;
    }

    /* 剧本状态 */
    const cur = player.current;
    const scen = cur ? SCENARIOS.find(x => x.id === cur) : null;
    /* 序号必须夹到 [1, len]:advanceOne() 返回时 index 已指向**下一幕**,
     * 单步到末幕时 index === queue.length,`index+1` 会渲染成「2/1」。
     * 连播态看不出这个毛病 —— loop() 末尾会把 index 归零,而那条清理只在
     * 'running' 下执行,暂停态永远走不到。夹一下,并把「已完成全部」也读作
     * 末幕,是这里能给出的最不误导的读数。 */
    const n = player.queue.length;
    const at = n ? Math.min(player.index + 1, n) : 0;
    this.scenStat.textContent = player.state === 'idle'
      ? 'idle'
      : `${player.state === 'paused' ? '暂停' : '连播'} ${at}/${n}`
        + (scen ? ` · ${scen.id} ${scen.name}` : '');
    this.scenStat.title = scen ? `焦点:${scen.focus}\n预期:${scen.expect}` : '';
    this.pauseBtn.textContent = player.state === 'paused' ? '继续' : '暂停';
    this.pauseBtn.disabled = player.state === 'idle';
    this.stepBtn.disabled = player.state === 'running';

    /* 数据源徽章 */
    const src = s.source;
    this.sourceBadge.className = 'tb-source st-'
      + (src === 'MOCK' ? 'mock' : src === 'REAL-STATIC' ? 'static' : 'live');
    this.q('#tb-source-text').textContent = src;

    this.counter.textContent = `run ${s.runCount}`;
  }
}
