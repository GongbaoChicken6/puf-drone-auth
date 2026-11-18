/* ============================================================
 * N11(finals-demo) 伪基站大警报弹窗
 * 订阅 puf:intrusion(channel.intrusion) 与 puf:basespoof:
 * 站端方向注入帧 / 未注册终端接入请求 / 终端拒认矛盾告警,
 * 一律弹全屏红色警报(三角感叹号),确认知悉前常驻不自动消失。
 * 取代 N2 小横幅的演示位(ids-banner.ts 保留为组件备用)。
 * ============================================================ */
import { onPuf } from '../core/bus';
import type { BaseSpoofSuspected, ChannelIntrusion } from '../core/types';

type AlarmRow = ChannelIntrusion | { spoof: BaseSpoofSuspected };

export class AlarmModal {
  readonly el: HTMLElement;
  private rows: AlarmRow[] = [];

  constructor() {
    this.el = document.createElement('div');
    this.el.className = 'alarm-modal';
    this.el.hidden = true;
    onPuf('puf:intrusion', p => this.push(p));
    onPuf('puf:basespoof', p => this.push({ spoof: p }));
    this.el.addEventListener('click', e => {
      if ((e.target as HTMLElement).closest('[data-dismiss]')) this.dismiss();
    });
    window.addEventListener('keydown', e => {
      if (e.key === 'Escape' && !this.el.hidden) this.dismiss();
    });
  }

  push(row: AlarmRow): void {
    this.rows.push(row);
    if (this.rows.length > 8) this.rows.shift();
    this.render();
  }

  dismiss(): void {
    this.rows = [];
    this.render();
  }

  private render(): void {
    if (!this.rows.length) { this.el.hidden = true; return; }
    const last = this.rows[this.rows.length - 1];
    const extra = this.rows.length - 1;
    const t = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    this.el.innerHTML = `
      <div class="alarm-box" role="alertdialog" aria-modal="true" aria-label="伪基站警报">
        <svg class="alarm-tri" viewBox="0 0 100 88" aria-hidden="true">
          <path d="M50 5 96 84 H4 Z" class="alarm-tri-bg"></path>
          <rect x="46" y="28" width="8" height="30" rx="3.5" class="alarm-mark"></rect>
          <rect x="46" y="64" width="8" height="8" rx="3.5" class="alarm-mark"></rect>
        </svg>
        <div class="alarm-title">警 报 ：检 测 到 伪 基 站 信 号</div>
        <div class="alarm-detail">${this.describe(last)}</div>
        <div class="alarm-time mono">${t} · 信道监测 IDS</div>
        ${extra > 0 ? `<div class="alarm-extra">另有 ${extra} 条告警待查阅（审计日志）</div>` : ''}
        <button class="alarm-btn" data-dismiss>确认知悉</button>
      </div>`;
    this.el.hidden = false;
  }

  private describe(r: AlarmRow): string {
    if ('spoof' in r) {
      return `tid=${r.spoof.terminal_id} 拒认本站判决（${r.spoof.own_verdict}→${r.spoof.terminal_says}）——终端识破伪基站，双向认证生效`;
    }
    if (r.kind === 'access') {
      return `未注册设备 tid=${r.terminal_id} 发起接入请求——非本站无人机，按攻击处置，未进入接入队列`;
    }
    return `注入帧 0x${r.msg_id.toString(16).padStart(4, '0')} ${r.name} · ${r.len}B——站端方向帧出现在信道，疑似伪基站注入`;
  }
}
