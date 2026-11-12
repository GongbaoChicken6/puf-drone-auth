/* ============================================================
 * N2(finals-demo) 信道 IDS 红警横幅
 * 订阅 puf:intrusion(channel.intrusion):站端专用方向帧被听到 =
 * 共享信道上疑似伪基站注入。顶部弹出、6s 自动衰减、最多堆 4 行。
 * 悬浮 body(不占 console.html 网格),审计行由后端配套
 * server.log(CHANNEL IDS...)走既有 puf:log 通道,此处不重复记。
 * ============================================================ */
import { onPuf } from '../core/bus';
import type { BaseSpoofSuspected, ChannelIntrusion } from '../core/types';

const SHOW_MS = 5000; // 设计文档 N2 口径:5s 自动衰减
const MAX_ROWS = 4;

export class IdsBanner {
  readonly el: HTMLElement;
  private rows: ChannelIntrusion[] = [];
  private timer: number | null = null;

  constructor() {
    this.el = document.createElement('div');
    this.el.className = 'ids-banner';
    this.el.setAttribute('role', 'alert');
    this.el.hidden = true;
    onPuf('puf:intrusion', p => this.push(p));
    // N3(finals-demo): 矛盾关联告警(终端拒认本站判决 = 疑似伪基站注入)
    onPuf('puf:basespoof', p => this.pushSpoof(p));
  }

  private pushSpoof(p: BaseSpoofSuspected): void {
    this.rows.push({
      msg_id: 0x0093, name: 'RESULT', hex: '', len: 0,
      note: `tid=${p.terminal_id} 拒认本站判决(${p.own_verdict}→${p.terminal_says})——疑似伪基站注入`,
    });
    if (this.rows.length > MAX_ROWS) this.rows.shift();
    this.render();
  }

  private push(p: ChannelIntrusion): void {
    this.rows.push(p);
    if (this.rows.length > MAX_ROWS) this.rows.shift();
    this.render();
  }

  private render(): void {
    if (!this.rows.length) { this.el.hidden = true; return; }
    this.el.innerHTML = `
      <div class="ids-head">⚠ 检测到伪基站注入帧（信道监测）</div>
      ${this.rows.map(r => `
        <div class="ids-row mono">
          0x${r.msg_id.toString(16).padStart(4, '0')} ${r.name} · ${r.len}B · ${r.note}
        </div>`).join('')}`;
    this.el.hidden = false;
    if (this.timer != null) window.clearTimeout(this.timer);
    this.timer = window.setTimeout(() => {
      this.rows = [];
      this.render();
    }, SHOW_MS);
  }
}
