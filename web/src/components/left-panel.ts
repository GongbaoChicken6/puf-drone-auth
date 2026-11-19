/* ============================================================
 * 左栏 —— 报告 §6.1 / §6.2
 * 终端注册表(terminal 卡,复用 components/terminal-card)
 *
 * 卡片按 id 复用实例:store 每次事件都广播,若每帧重建卡片,按钮会丢失
 * hover/focus 且动画重排 —— 故用 Map<id, TerminalCard> 增量对齐。
 * ============================================================ */
import { TerminalCard, type TerminalCardActions } from './terminal-card';
import type { AppState, TerminalState } from '../core/store';

export type LeftPanelDeps = TerminalCardActions;

export class LeftPanel {
  readonly el: HTMLElement;
  private deps: LeftPanelDeps;
  private list!: HTMLElement;
  private empty!: HTMLElement;
  private count!: HTMLElement;
  private cards = new Map<number, TerminalCard>();

  constructor(deps: LeftPanelDeps) {
    this.deps = deps;
    this.el = document.createElement('div');
    this.el.className = 'left-panel';
    this.el.innerHTML = `
      <div class="lp-head">
        <span class="lp-title">终端注册表</span>
        <span class="lp-count mono" id="lp-count">0</span>
      </div>
      <div class="lp-list" id="lp-list"></div>
      <div class="lp-empty" id="lp-empty">
        尚无终端。基站服务会自动注册演示终端（7/8/9），各卡内可补注册。
      </div>`;

    this.list = this.q('#lp-list');
    this.empty = this.q('#lp-empty');
    this.count = this.q('#lp-count');
  }

  private q<T extends HTMLElement>(sel: string): T { return this.el.querySelector<T>(sel)!; }

  update(s: AppState): void {
    const list: TerminalState[] = [...s.terminals.values()].sort((a, b) => a.id - b.id);
    this.count.textContent = String(list.length);
    this.empty.hidden = list.length > 0;

    // 增量对齐:新增建卡、消失移除、其余原位更新(保持用户滚动位置)
    const seen = new Set<number>();
    for (const t of list) {
      seen.add(t.id);
      let card = this.cards.get(t.id);
      if (!card) {
        card = new TerminalCard(t, this.deps);
        this.cards.set(t.id, card);
        this.list.append(card.el);
      }
      card.update(t, s.selectedTerminal === t.id);
    }
    for (const [id, card] of [...this.cards]) {
      if (!seen.has(id)) { card.el.remove(); this.cards.delete(id); }
    }
  }
}
