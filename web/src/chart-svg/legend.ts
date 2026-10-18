/* ============================================================
 * chart-svg 图例 —— 画在 SVG 内部,不画成 HTML
 *
 * 理由:§7.2 要求每图「导出 SVG/PNG」。HTML 图例在序列化时不在 SVG 树里,
 * 导出的图会丢掉「哪条绿哪条红」——而这恰恰是 V1/V2 最要紧的信息。
 * 所以图例、标题、单位全部进 SVG,导出即所见。
 * ============================================================ */
import { el } from './axis';

export type MarkKind = 'bar' | 'line' | 'dash' | 'dot';

export interface LegendItem {
  label: string;
  color: string;          // CSS 颜色字面量(导出时变量会被内联替换,见 export.ts)
  kind?: MarkKind;
  /** 追加说明(如样本量),以小字灰显示 */
  note?: string;
  /** 覆盖在色块上的第二层填充(纹理),D14 —— 色觉冗余线索须在图例里同步可见 */
  overlay?: string;
}

export const COLOR = {
  intra: 'var(--green)',
  inter: 'var(--red)',
  pass: 'var(--green)',
  gray: 'var(--amber)',
  amber: 'var(--amber)',
  reject: 'var(--red)',
  comm: 'var(--comm)',
  server: 'var(--server)',
  /** **只许画线**,不许写字(D15):--dim 对文字不达 4.5:1,只达图形所需的 3:1。
   *  当前唯一使用处是 V4 的「报告注释口径」参照线图例项 —— 它的 color 经
   *  drawLegend 落在 stroke 上,合规。若要拿它填文字,请改用 muted。 */
  dim: 'var(--dim)',
  muted: 'var(--muted)',
} as const;

/**
 * 在图内左上角画一行图例;返回占用的高度,便于调用方依次下移。
 * `maxWidth` 用于自动换行 —— V1/V2 的图例项带样本量注记,一行放不下。
 */
export function drawLegend(
  parent: SVGGElement, x: number, y: number, items: LegendItem[],
  maxWidth = 9999, lineH = 16,
): number {
  const g = el('g', { class: 'pl-legend' }, parent);
  let cx = x;
  let cy = y;
  let rows = 1;

  for (const it of items) {
    const labelW = it.label.length * 6.6 + (it.note ? it.note.length * 5.6 + 8 : 0);
    const itemW = 20 + labelW + 14;
    if (cx > x && cx + itemW > x + maxWidth) { cx = x; cy += lineH; rows++; }

    const kind = it.kind ?? 'line';
    if (kind === 'bar') {
      el('rect', { x: cx, y: cy - 7, width: 12, height: 10, rx: 2, fill: it.color, opacity: .85 }, g);
      if (it.overlay) {
        el('rect', { x: cx, y: cy - 7, width: 12, height: 10, rx: 2, fill: it.overlay }, g);
      }
    } else if (kind === 'dot') {
      el('circle', { cx: cx + 6, cy: cy - 2, r: 4, fill: it.color }, g);
    } else {
      el('line', {
        x1: cx, y1: cy - 2, x2: cx + 13, y2: cy - 2,
        stroke: it.color, 'stroke-width': 2,
        'stroke-dasharray': kind === 'dash' ? '4 3' : 'none',
      }, g);
    }

    el('text', { x: cx + 18, y: cy + 2, class: 'pl-legend-label' }, g).textContent = it.label;
    if (it.note) {
      el('text', { x: cx + 18 + it.label.length * 6.6 + 6, y: cy + 2, class: 'pl-legend-note' }, g)
        .textContent = it.note;
    }
    cx += itemW;
  }
  return rows * lineH + 6;
}
