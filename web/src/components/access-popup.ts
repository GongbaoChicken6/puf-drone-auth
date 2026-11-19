/* ============================================================
 * finals-demo-N6: 接入闸门弹窗 —— SW7 主动认证人工选择队列
 *
 * 自订阅悬浮组件(IdsBanner 同款先例,不动 store/topbar,写域最小):
 *  · puf:access-requested → 入队并自动弹出(演示步骤②「蹦出弹窗」)
 *  · 点「开始验证」→ POST /api/access/select(桥端 2.2s 对齐+AUTH_POLL 唤醒,
 *    最坏 ~10s,按钮转圈承载) → ok/access.selected 即收起,五帧动画走现有事件流
 *  · 另一台留在队列(徽标常驻「待接入 N」,点击重开);可手动「撤下」
 *  · 刷新恢复:构造时 GET /api/access/queue
 * ============================================================ */
import { api } from '../core/api';
import { onPuf } from '../core/bus';
import { store } from '../core/store';
import type { AccessQueueEntry } from '../core/types';

function fmtWait(ts: number): string {
  const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
  return s < 60 ? s + ' 秒' : Math.floor(s / 60) + ' 分 ' + (s % 60) + ' 秒';
}

export class AccessPopup {
  readonly el: HTMLElement;
  readonly badgeEl: HTMLButtonElement;
  private entries = new Map<number, AccessQueueEntry>();
  private selected: number | null = null;
  private busyTid: number | null = null;
  private errText = '';
  private openFlag = false;

  constructor() {
    this.el = document.createElement('div');
    this.el.className = 'ap-overlay';
    this.el.hidden = true;
    this.el.setAttribute('role', 'dialog');
    this.badgeEl = document.createElement('button');
    this.badgeEl.className = 'ap-badge';
    this.badgeEl.type = 'button';
    this.badgeEl.hidden = true;
    this.badgeEl.addEventListener('click', () => this.show());
    this.wireEvents();
    this.render();
    /* 刷新恢复:拉一次队列快照(桥未开闸门时 enabled=false,静默) */
    void api.getAccessQueue().then(q => {
      if (!q || !q.enabled) return;
      for (const e of q.entries) this.entries.set(e.terminal_id, e);
      this.selected = q.selected;
      if (this.entries.size > 0) { this.show(); }
      this.render();
    }).catch(() => { /* 桥未起/旧版本端点:静默(徽标也不显示) */ });
  }

  private wireEvents(): void {
    onPuf('puf:access-requested', p => {
      const cur = this.entries.get(p.terminal_id);
      this.entries.set(p.terminal_id, {
        terminal_id: p.terminal_id, port: p.port, label: p.label,
        first_seen_ts: p.first_seen_ts,
        last_request_ts: cur ? cur.last_request_ts : Date.now() / 1000,
        repeats: p.repeats,
      });
      this.errText = '';
      this.show();          /* 演示语义:新接入请求 → 弹窗蹦出 */
      this.render();
    });
    onPuf('puf:access-selected', p => {
      this.selected = p.terminal_id;
      this.busyTid = null;
      this.hide();          /* 选中即收起,五帧动画接管屏幕 */
      /* 舞台焦点跟随人工选择:否则 stageAccepts() 过滤掉该终端事件,
       * 五帧/判定/激光只进日志不上演(2026-11-16 现场复现) */
      store.select(p.terminal_id);
      this.render();
    });
    onPuf('puf:access-finished', p => {
      this.entries.delete(p.terminal_id);
      if (this.selected === p.terminal_id) this.selected = null;
      this.render();
    });
    onPuf('puf:access-dismissed', p => {
      this.entries.delete(p.terminal_id);
      this.render();
    });
  }

  private show(): void { this.openFlag = true; this.el.hidden = false; }
  private hide(): void { this.openFlag = false; this.el.hidden = true; }

  private select(tid: number): void {
    if (this.busyTid != null) return;
    this.busyTid = tid;
    this.errText = '';
    this.render();
    api.accessSelect(tid).then(r => {
      this.busyTid = null;
      if (r.ok) {
        this.hide();        /* 保险:事件先到也已收起 */
        store.select(tid);  /* 舞台锁定被选终端(与 access.selected 双保险) */
      } else {
        this.errText = r.reason ?? '未知错误';
        this.show();        /* 409/404 时保持弹窗,原因上屏 */
      }
      this.render();
    });
  }

  private dismiss(tid: number): void {
    void api.accessDismiss(tid).then(r => {
      if (!r.ok) { this.errText = r.reason ?? '撤下失败'; this.render(); }
    });
  }

  private render(): void {
    const list = Array.from(this.entries.values())
      .sort((a, b) => a.first_seen_ts - b.first_seen_ts);
    /* 徽标:队列非空即常驻 */
    this.badgeEl.hidden = list.length === 0;
    this.badgeEl.textContent = '待接入 ' + list.length;
    if (!this.openFlag && list.length === 0) { this.el.hidden = true; }
    const rows = list.map(e => {
      const busy = this.busyTid === e.terminal_id;
      const sel = this.selected === e.terminal_id;
      return [
        '<div class="ap-row">',
        '  <div class="ap-info">',
        '    <span class="ap-name">' + e.label + '</span>',
        '    <span class="ap-meta">终端 ' + e.terminal_id + ' · ' + e.port +
        '      · 已等待 ' + fmtWait(e.first_seen_ts) +
        (e.repeats > 0 ? ' · 重复按压 ' + e.repeats + ' 次' : '') + '</span>',
        '  </div>',
        '  <div class="ap-actions">',
        (sel ? '<span class="ap-sel">验证中…</span>'
      : busy ? '<span class="ap-busy">处理中…</span>'
      : '<button class="btn green" data-select="' + e.terminal_id + '">开始验证</button>'),
        '    <button class="btn ghost" data-dismiss="' + e.terminal_id + '">撤下</button>',
        '  </div>',
        '</div>',
      ].join('');
    }).join('');
    this.el.innerHTML = [
      '<div class="ap-card">',
      '  <div class="ap-head">',
      '    <span>接入请求 · 人工选择验证顺序</span>',
      '    <button class="btn ghost" data-close title="收起(徽标仍在)">✕</button>',
      '  </div>',
      '  <div class="ap-body">',
      (rows || '<div class="ap-empty">队列为空——在板上按 SW7 发起认证</div>'),
      (this.errText ? '<div class="ap-error">' + this.errText +
        '<div class="ap-hint">板端无响应时可按 SW13 复位后重试</div></div>' : ''),
      '  </div>',
      '</div>',
    ].join('');
  }

  /** 挂载后绑定(innerHTML 每次重建,事件用委托) */
  bind(): void {
    this.el.addEventListener('click', ev => {
      const t = ev.target as HTMLElement;
      if (t.matches('[data-close]')) { this.hide(); return; }
      const s = t.closest('[data-select]') as HTMLElement | null;
      if (s) { this.select(Number(s.dataset.select)); return; }
      const d = t.closest('[data-dismiss]') as HTMLElement | null;
      if (d) { this.dismiss(Number(d.dataset.dismiss)); return; }
    });
  }
}
