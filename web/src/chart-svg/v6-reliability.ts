import { svgRoot, el, linear } from './axis';
import type { ReliabilityData } from '../core/types';

/* B2:V6 温度/电压 reliability —— ROPairingPUF 黄金模型推演曲线(source=MODEL)。
 * 上下面板:平均 HD(带 TAU 参考线)与单响应通过率;x 为缩放因子 s(温度/电压
 * 的单变量代理)。数据点小圆点 + 折线;琥珀色 s=1.0 基准线。 */
export function renderV6(rel: ReliabilityData, tauPass = 6, tauReject = 16): SVGSVGElement {
  const pts = rel.points;
  const W = 760, H = 340;
  const svg = svgRoot(W, H);
  const x0 = 56, x1 = 730;
  const sx = linear([pts[0].scale, pts[pts.length - 1].scale], [x0, x1]);

  /* 面板一:mean_hd */
  const yA0 = 44, yA1 = 168;
  const maxHd = Math.max(...pts.map(p => p.mean_hd), tauReject * 1.1);
  const syA = linear([0, maxHd], [yA1, yA0]);
  const t1 = el('text', { x: x0, y: 26, class: 'pl-sec-title' }, svg);
  t1.textContent = '平均 HD vs 缩放因子 s(模型推演)';
  for (const h of [0, Math.round(maxHd / 2), Math.round(maxHd)]) {
    el('line', { x1: x0, y1: syA(h), x2: x1, y2: syA(h), class: 'pl-gridline' }, svg);
    const tx = el('text', { x: x0 - 8, y: syA(h) + 4, 'text-anchor': 'end', class: 'pl-tick' }, svg);
    tx.textContent = String(h);
  }
  for (const [val, cls, lab] of [[tauPass, 'vl-tau', 'TAU_PASS'], [tauReject, 'vl-tau vl-tau-gray', 'TAU_REJECT']] as const) {
    el('line', { x1: x0, y1: syA(val), x2: x1, y2: syA(val), class: cls, 'stroke-dasharray': '6 4' }, svg);
    const tx = el('text', { x: x1, y: syA(val) - 4, 'text-anchor': 'end', class: 'pl-vlabel ' + cls }, svg);
    tx.textContent = lab + ' = ' + val;
  }
  const d1 = pts.map(p => sx(p.scale).toFixed(1) + ',' + syA(p.mean_hd).toFixed(1)).join(' ');
  el('polyline', { points: d1, class: 'pl-line' }, svg);
  for (const p of pts) el('circle', { cx: sx(p.scale), cy: syA(p.mean_hd), r: 3, class: 'pl-dot' }, svg);

  /* 面板二:pass_rate */
  const yB0 = 208, yB1 = 312;
  const syB = linear([0, 1], [yB1, yB0]);
  const t2 = el('text', { x: x0, y: 194, class: 'pl-sec-title' }, svg);
  t2.textContent = '单响应通过率(HD ≤ TAU_PASS)';
  for (const v of [0, 0.25, 0.5, 0.75, 1]) {
    el('line', { x1: x0, y1: syB(v), x2: x1, y2: syB(v), class: 'pl-gridline' }, svg);
    const tx = el('text', { x: x0 - 8, y: syB(v) + 4, 'text-anchor': 'end', class: 'pl-tick' }, svg);
    tx.textContent = Math.round(v * 100) + '%';
  }
  const d2 = pts.map(p => sx(p.scale).toFixed(1) + ',' + syB(p.pass_rate).toFixed(1)).join(' ');
  el('polyline', { points: d2, class: 'pl-line', stroke: 'var(--green)' }, svg);
  for (const p of pts) el('circle', { cx: sx(p.scale), cy: syB(p.pass_rate), r: 3, class: 'pl-dot', fill: 'var(--green)' }, svg);

  /* x 轴刻度(隔一个标)与 s=1.0 基准 */
  pts.forEach((p, i) => {
    if (i % 2 === 0 || p.scale === 1) {
      const tx = el('text', { x: sx(p.scale), y: yB1 + 16, 'text-anchor': 'middle', class: 'pl-tick' }, svg);
      tx.textContent = p.scale.toFixed(2);
    }
  });
  el('line', { x1: sx(1), y1: yA0, x2: sx(1), y2: yB1, stroke: 'var(--amber)', 'stroke-dasharray': '2 3', opacity: 0.5 }, svg);
  const xl = el('text', { x: (x0 + x1) / 2, y: H - 6, 'text-anchor': 'middle', class: 'pl-axis-title' }, svg);
  xl.textContent = '缩放因子 s(温度/电压单变量代理;s=1 为标称工作点)';
  return svg;
}
