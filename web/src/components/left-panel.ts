/* ============================================================
 * 左栏 —— 报告 §6.1 / §6.2 / §6.3
 * 上:终端注册表(terminal 卡,复用 components/terminal-card)
 * 下:S1–S7 场景工具条(常驻)—— 点击即单跑该幕
 *
 * 卡片按 id 复用实例:store 每次事件都广播,若每帧重建卡片,按钮会丢失
 * hover/focus 且动画重排 —— 故用 Map<id, TerminalCard> 增量对齐。
 * ============================================================ */
import { TerminalCard, type TerminalCardActions } from './terminal-card';
import { SCENARIOS, type ScenarioId } from '../core/scenario';
import type { AppState, TerminalState } from '../core/store';

export interface LeftPanelDeps extends TerminalCardActions {
  runScenario(id: ScenarioId): void;
}

export class LeftPanel {
  readonly el: HTMLElement;
  private deps: LeftPanelDeps;
  private list!: HTMLElement;
  private empty!: HTMLElement;
  private count!: HTMLElement;
  private cards = new Map<number, TerminalCard>();
  private scenBtns = new Map<ScenarioId, HTMLButtonElement>();

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
        尚无终端。<br />桥接启动时会幂等注册演示终端(7/8/9);注册键位于各终端卡内,为既有终端补测模板。
      </div>

      <div class="lp-head lp-head-scen">
        <span class="lp-title">一键演示场景 S1–S7</span>
      </div>
      <div class="lp-scen" id="lp-scen"></div>`;

    this.list = this.q('#lp-list');
    this.empty = this.q('#lp-empty');
    this.count = this.q('#lp-count');

    const scenBox = this.q('#lp-scen');
    for (const s of SCENARIOS) {
      const b = document.createElement('button');
      b.className = 'btn scen-btn';
      b.dataset.scen = s.id;
      b.setAttribute('aria-pressed', 'false');
      b.innerHTML = `<b>${s.id}</b><span>${s.name}</span>`;
      b.title = `预期:${s.expect}\nUI 焦点:${s.focus}`
        + (s.tid != null ? `\n固定终端:tid ${s.tid}` : '')
        + `\n快捷键:Shift+${s.id.slice(1)}`;
      b.addEventListener('click', () => this.deps.runScenario(s.id));
      scenBox.append(b);
      this.scenBtns.set(s.id, b);
    }
  }

  private q<T extends HTMLElement>(sel: string): T { return this.el.querySelector<T>(sel)!; }

  update(s: AppState, currentScenario: ScenarioId | null): void {
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

    for (const [id, b] of this.scenBtns) {
      const running = id === currentScenario;
      b.classList.toggle('running', running);
      // 「哪一幕正在跑」此前只有 .running 的配色在说;读屏与色觉障碍都取不到
      b.setAttribute('aria-pressed', String(running));
    }
  }
}
