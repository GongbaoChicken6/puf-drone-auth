/* ============================================================
 * terminal 卡 —— 报告 §6.2「左栏·终端注册表」
 *
 * 展示口径全部来自 /api/status 与事件流,不派生臆造值:
 *  · stable bits 显示为 `n/64`;上游 stable_bits 可为 null(掩码未算出),
 *    此时显示「—」而非 0 —— 0/64 是"算出来全不稳定",两者语义完全不同。
 *  · 池水位分母取 pool_size(组员口径:该设备的历史容量上限,非当前余额)。
 *  · C2 窗状态:桥接只暴露"是否已清空"这一可观测量,故未清空时显示「—」,
 *    不假装知道窗口内的计数。
 * ============================================================ */
import type { TerminalState } from '../core/store';
import { barScale } from '../core/format';
import { RESULT_CN, type AuthMode, type ResultCode } from '../core/types';

export interface TerminalCardActions {
  select(id: number): void;
  auth(id: number, mode: AuthMode): void;
  enroll(id: number): void;
  c2reset(id: number): void;
  setkey(id: number): void;
}

export class TerminalCard {
  readonly el: HTMLElement;
  private t: TerminalState;
  private act: TerminalCardActions;
  private busy = false;

  constructor(t: TerminalState, act: TerminalCardActions) {
    this.t = t;
    this.act = act;
    this.el = document.createElement('div');
    this.el.className = 'card term-card';
    this.el.dataset.tid = String(t.id);
    this.el.addEventListener('click', (e) => {
      if ((e.target as HTMLElement).closest('button')) return;
      this.act.select(t.id);
    });
    /* 键盘选中(R5 无障碍)。卡片整体是「选中该终端」的点击目标,但它是 div,
     * 键走查时根本停不下来 —— 键盘用户只能操作卡内按钮,选不了终端,而整个
     * 右栏(判定/HD/R2/池/会话)都跟着「当前选中的终端」走,等于右栏对键盘不可达。
     *
     * 这里**不**加 role="button":卡内已经有四个真实的 <button>,按钮里套按钮
     * 是无效结构,读屏会二选一地念。改用 tabindex=0 + aria-label 自述 + 选中态
     * 用 aria-current,结构合法且语义不丢。 */
    this.el.tabIndex = 0;
    this.el.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      // 卡内按钮自己会响应 Enter/Space,别再冒泡一次触发选中
      if ((e.target as HTMLElement).closest('button')) return;
      // Space 默认会滚动页面,而这里 Space 是「按下」
      e.preventDefault();
      this.act.select(t.id);
    });
    this.render();
    this.wire();
  }

  private render(): void {
    const t = this.t;
    const pct = t.pool_size > 0 ? t.pool_pct : 0;
    // 水位条常驻告警色仅当真的低;poolWarn 只用来加一次闪光动效
    const lowCls = pct < 20 ? 'warn' : '';
    const flashCls = t.poolWarn && pct < 20 ? 'flash' : '';
    const stableTxt = t.stable_bits == null
      ? '—'
      : `${t.stable_bits}/${64}`;
    const stablePct = t.stability_pct == null ? '' : ` (${t.stability_pct}%)`;
    const dec = t.lastDecision;

    this.el.innerHTML = `
      <div class="tc-head">
        <span class="tc-id mono">tid ${t.id}</span>
        ${this.decChip(dec)}
      </div>
      <div class="tc-rows">
        <div class="tc-row"><span class="k">模板对</span>
          <span class="v mono">${t.n_pairs}</span></div>
        <div class="tc-row"><span class="k">稳定位</span>
          <span class="v mono" title="稳定位掩码由 TemplateDB.compute_stability 在注册时算出(64 位,翻转率阈值 0.1);「—」表示该终端尚无掩码,不是 0 位">${stableTxt}${stablePct}</span></div>
        <div class="tc-row"><span class="k">CRP 池</span>
          <span class="v mono">${t.pool_remaining}/${t.pool_size || '—'}</span></div>
        <div class="tc-bar ${lowCls} ${flashCls}" title="CRP 池剩余 ${t.pool_remaining} / 容量 ${t.pool_size} — 池容量是该设备的历史上限(CRPPool.pool_size),不是当前余额"><i style="${barScale(pct)}"></i></div>
        <div class="tc-row"><span class="k">C2 窗</span>
          <span class="v mono ${t.c2Cleared ? 'ok' : 'dim'}">${t.c2Cleared ? '已清空' : '—'}</span>
          <span class="k">会话</span>
          <span class="v mono dim">${t.sessionState ?? '—'}</span></div>
      </div>
      <div class="tc-actions">
        <button class="btn green" data-mode="normal">认证</button>
        <button class="btn red"   data-mode="spoof">仿冒</button>
        <button class="btn amber" data-mode="replay">重放</button>
      </div>
      <div class="tc-actions">
        <button class="btn" data-act="enroll" ${t.enrolling ? 'disabled' : ''}>
          ${t.enrolling ? '<span class="spin"></span>注册中…' : '注册'}</button>
        <button class="btn ghost" data-act="c2reset">清 C2 窗</button>
        <button class="btn ghost" data-act="setkey"
          title="装入 W3 演示密钥 0001020308090a0b10111213(与 docs/protocol_contract.md §4 黄金帧同一把);装入后全新终端首次认证的 R2 应与黄金 R2 一致">
          ${t.keyInstalled ? '演示密钥 ✓' : '演示密钥'}</button>
      </div>`;
  }

  private decChip(d: ResultCode | null): string {
    if (d == null) return '<span class="chip">未判定</span>';
    const cls = d === 0 ? 'green' : d === 4 ? 'amber' : d === 3 ? 'amber' : 'red';
    return `<span class="chip ${cls}">${RESULT_CN[d]}</span>`;
  }

  private wire(): void {
    this.el.querySelectorAll<HTMLButtonElement>('[data-mode]').forEach(b => {
      b.addEventListener('click', () => {
        if (this.busy) return;
        this.busy = true;
        this.el.classList.add('sent');
        this.act.auth(this.t.id, b.dataset.mode as AuthMode);
        // 仅作去抖:后端每个 run 都是独立 REST 调用,不阻塞后续
        window.setTimeout(() => { this.busy = false; this.el.classList.remove('sent'); }, 260);
      });
    });
    this.el.querySelector<HTMLButtonElement>('[data-act="enroll"]')
      ?.addEventListener('click', () => this.act.enroll(this.t.id));
    this.el.querySelector<HTMLButtonElement>('[data-act="c2reset"]')
      ?.addEventListener('click', () => this.act.c2reset(this.t.id));
    this.el.querySelector<HTMLButtonElement>('[data-act="setkey"]')
      ?.addEventListener('click', () => this.act.setkey(this.t.id));
  }

  update(t: TerminalState, selected: boolean): void {
    this.t = t;
    this.el.classList.toggle('selected', selected);
    this.el.classList.toggle('warn-card', t.poolWarn && t.pool_pct < 20);
    /* R8 D19:最近判定左轨(decChip 同一映射:0=绿 / 3、4=琥珀 / 其余=红),
     * 状态画在卡边缘 —— 列表里不必读字就知道哪台刚 PASS/被拒。 */
    const dec = t.lastDecision;
    this.el.classList.toggle('tc-ok', dec === 0);
    this.el.classList.toggle('tc-warn', dec === 3 || dec === 4);
    this.el.classList.toggle('tc-fail', dec === 1 || dec === 2);
    // 自述与选中态:必须写在这里而不是 render() 里 —— render() 只重写 innerHTML,
    // 碰不到卡片自身的属性,而签名挡重绘时 update() 仍是每次都跑的
    this.el.setAttribute('aria-current', selected ? 'true' : 'false');
    this.el.setAttribute('aria-label',
      `终端 tid ${t.id}${selected ? '(当前选中)' : ''}`
      + ` · 模板对 ${t.n_pairs} · CRP 池 ${t.pool_remaining}/${t.pool_size || '未知'}`
      + ` · 按 Enter 选中该终端`);
    // store 每次事件都会广播,而卡片内容绝大多数时候不变 —— 用签名挡住重复
    // 重绘,否则会反复重建按钮节点、吃掉 hover/focus 状态
    const sig = [t.id, t.n_pairs, t.stable_bits, t.pool_remaining, t.pool_size,
      t.pool_pct, t.lastDecision, t.sessionState, t.c2Cleared, t.keyInstalled,
      t.enrolling, t.poolWarn, selected].join('|');
    if (sig === this.sig) return;
    this.sig = sig;
    this.render();
    this.wire();
  }
  private sig = '';
}
