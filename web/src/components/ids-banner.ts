/* ============================================================
 * N2(finals-demo) 信道 IDS 红警横幅
 * 订阅 puf:intrusion(channel.intrusion):站端专用方向帧被听到 =
 * 共享信道上疑似伪基站注入。顶部弹出、5s 自动衰减、最多堆 4 行。
 * 悬浮 body(不占 console.html 网格),审计行由后端配套
 * server.log(CHANNEL IDS...)走既有 puf:log 通道,此处不重复记。
 * ============================================================ */
import { onPuf } from '../core/bus';
import type { BaseSpoofSuspected, ChannelIntrusion } from '../core/types';

const SHOW_MS = 5000; // 设计文档 N2 口径:5s 自动衰减
const MAX_ROWS = 4;

/* 判别联合:侵入行与矛盾告警行各自成模板,不伪造共形字段(R2 ar-type-c1) */
type BannerRow = ChannelIntrusion | { spoof: BaseSpoofSuspected };

export class IdsBanner {
  readonly el: HTMLElement;
  private rows: BannerRow[] = [];
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
    this.rows.push({ spoof: p });
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
      ${this.rows.map(r => 'spoof' in r
        ? `<div class="ids-row mono">tid=${r.spoof.terminal_id} 拒认本站判决（${r.spoof.own_verdict}→${r.spoof.terminal_says}）—— 疑似伪基站注入</div>`
        : `<div class="ids-row mono">0x${r.msg_id.toString(16).padStart(4, '0')} ${r.name} · ${r.len}B · ${r.note}</div>`).join('')}`;
    this.el.hidden = false;
    if (this.timer != null) window.clearTimeout(this.timer);
    this.timer = window.setTimeout(() => {
      this.rows = [];
      this.render();
    }, SHOW_MS);
  }
}
