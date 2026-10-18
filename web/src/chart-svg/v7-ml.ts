import { svgRoot, el, linear } from './axis';
import type { MlBundle } from '../core/types';

/* B1:V7 ML 攻击双图 —— 实验 A(LR 建模基线,贴 Bayes 上界)与
 * 实验 B(自家 RO 排序重构)。左右双面板一张 SVG,一个导出件。 */
const COLORS = ['var(--green)', 'var(--cyan)', 'var(--amber)', 'var(--red)'];

function panel(svg: SVGSVGElement, x0: number, x1: number, y0: number, y1: number,
               title: string, xLabels: string[], series: { label: string; vals: number[]; dashed?: boolean }[],
               yDomain: [number, number], yFmt: (v: number) => string, xTitle: string, highlight = -1): void {
  const t = el('text', { x: x0, y: y0 - 26, class: 'pl-sec-title' }, svg);
  t.textContent = title;
  const sx = linear([0, xLabels.length - 1], [x0 + 10, x1 - 10]);
  const sy = linear(yDomain, [y1, y0]);
  for (const v of [yDomain[0], (yDomain[0] + yDomain[1]) / 2, yDomain[1]]) {
    el('line', { x1: x0, y1: sy(v), x2: x1, y2: sy(v), class: 'pl-gridline' }, svg);
    const tx = el('text', { x: x0 - 6, y: sy(v) + 4, 'text-anchor': 'end', class: 'pl-tick' }, svg);
    tx.textContent = yFmt(v);
  }
  xLabels.forEach((lab, i) => {
    const tx = el('text', { x: sx(i), y: y1 + 16, 'text-anchor': 'middle', class: 'pl-tick' }, svg);
    tx.textContent = lab;
  });
  const xt = el('text', { x: (x0 + x1) / 2, y: y1 + 34, 'text-anchor': 'middle', class: 'pl-axis-title' }, svg);
  xt.textContent = xTitle;
  series.forEach((s, idx) => {
    const color = COLORS[idx % COLORS.length];
    const cls = 'pl-line' + (idx === highlight ? ' pl-line-hl' : '');
    if (s.dashed) {
      const y = sy(s.vals[0]);
      el('line', { x1: x0 + 10, y1: y, x2: x1 - 10, y2: y, stroke: color, 'stroke-dasharray': '5 4', opacity: 0.55 }, svg);
    } else {
      const d = s.vals.map((v, i) => sx(i).toFixed(1) + ',' + sy(v).toFixed(1)).join(' ');
      el('polyline', { points: d, class: cls, stroke: color }, svg);
      s.vals.forEach((v, i) => el('circle', { cx: sx(i), cy: sy(v), r: 2.5, class: 'pl-dot', fill: color }, svg));
    }
  });
  /* 图例:右上角竖排 */
  series.forEach((s, idx) => {
    const color = COLORS[idx % COLORS.length];
    const legAttrs: Record<string, string | number> = { x1: x1 - 96, y1: y0 - 8 + idx * 14, x2: x1 - 82, y2: y0 - 8 + idx * 14, stroke: color, 'stroke-width': 2 };
    if (s.dashed) legAttrs['stroke-dasharray'] = '4 3';
    el('line', legAttrs, svg);
    const lg = el('text', { x: x1 - 78, y: y0 - 4 + idx * 14, class: 'pl-tick' }, svg);
    lg.textContent = s.label;
  });
}

export function renderV7(ml: MlBundle): SVGSVGElement {
  const W = 980, H = 330;
  const svg = svgRoot(W, H);
  if (ml.a) {
    const a = ml.a;
    const series: { label: string; vals: number[] }[] = [];
    const bays: { label: string; vals: number[]; dashed: boolean }[] = [];
    a.noise_rel.forEach(n => {
      const key = n.toFixed(2);
      series.push({ label: '\u03b1=' + key, vals: a.train_sizes.map(t => a.accuracy[key][String(t)]) });
      bays.push({ label: 'Bayes ' + key, vals: [a.bayes_acc[key]], dashed: true });
    });
    panel(svg, 44, 470, 60, 268, '\u5b9e\u9a8c A \u00b7 LR \u5efa\u6a21\u653b\u51fb\uff08\u5408\u6210 arbiter \u57fa\u7ebf\uff09',
      a.train_sizes.map(t => t >= 1000 ? (t / 1000) + 'k' : String(t)),
      [...series, ...bays], [0.85, 1.0], v => (v * 100).toFixed(0) + '%', '\u8bad\u7ec3\u6837\u672c\u6570');
  }
  if (ml.b) {
    const b = ml.b;
    const series = b.flip_levels.map(f => ({
      label: 'flip=' + f.toFixed(2),
      vals: b.n_sweep.map(n => (b.aggregated[f.toFixed(2)] || {})[String(n)]?.exact_rate ?? 0),
    }));
    panel(svg, 530, 956, 60, 268, '\u5b9e\u9a8c B \u00b7 RO \u6392\u5e8f\u91cd\u6784\uff08\u81ea\u5bb6\u5668\u4ef6\uff09',
      b.n_sweep.map(String), series, [0, 1], v => (v * 100).toFixed(0) + '%', 'CRP \u6570\uff08\u8f6e\u6362\u9600 \u2265120\uff09', 1);
  }
  return svg;
}
