/* ============================================================
 * N6(finals-demo) 帧飞行动画 —— 数据流具象化
 * 订阅 puf:frame:每帧从终端侧(左)飞向基站侧(右)或反向,
 * 携带 帧名+字节数+方向箭头,~900ms 过渡(transform/opacity,
 * 与 §4.3 动效规范一致)。并发上限 6,三条泳道错开防重叠。
 * 悬浮 body 全幅覆盖(不占网格),pointer-events:none。
 * ============================================================ */
import { onPuf } from '../core/bus';
import type { FrameEvent } from '../core/types';

const MAX_CHIPS = 6;
const FLIGHT_MS = 900;

export class FrameFlight {
  readonly el: HTMLElement;
  private chips = 0;

  constructor() {
    this.el = document.createElement('div');
    this.el.className = 'frame-flight';
    onPuf('puf:frame', p => this.launch(p));
  }

  private launch(f: FrameEvent): void {
    if (this.chips >= MAX_CHIPS) return;
    const chip = document.createElement('div');
    const up = f.dir === 'term->server';
    chip.className = 'ff-chip' + (up ? ' up' : ' down');
    chip.textContent = `${f.name} ${f.len}B ${up ? '→基站' : '←基站'}`;
    this.el.append(chip);
    this.chips++;

    const W = window.innerWidth;
    const y = 96 + (this.chips % 3) * 36;          // 三条泳道
    const x0 = up ? 236 : W - 300;                 // 左=终端带 / 右=基站带
    const x1 = up ? W - 300 : 236;
    chip.style.top = `${y}px`;
    const anim = chip.animate([
      { transform: `translate(${x0}px,0)`, opacity: 0 },
      { transform: `translate(${(x0 + x1) / 2}px,-10px)`, opacity: 1, offset: 0.2 },
      { transform: `translate(${x1}px,0)`, opacity: 0 },
    ], { duration: FLIGHT_MS, easing: 'cubic-bezier(.4,0,.6,1)' });
    // finished 在 finish 与 cancel 两种收尾都走 finally——cancel 路径不再
    // 永久泄漏一次 chips 计数(R2 ar-defect-c1:泄漏满 6 次动画静默停摆)
    void anim.finished.finally(() => { chip.remove(); this.chips--; });
  }
}
