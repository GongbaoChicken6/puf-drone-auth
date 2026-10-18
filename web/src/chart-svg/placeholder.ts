/* ============================================================
 * V5–V7 —— 显式 MOCK 占位(报告 §4.4 / §7.1 / §9)
 *
 * 三张图的共同点:数据源**现在不存在**。
 *   V5 16 环 RO 频率热图   ← 上板 W1 VIO 读数(data/w1_readings 现为空)
 *   V6 温度-reliability    ← 上板实验,尚未做
 *   V7 B6 ML 攻击准确率    ← 实验未编码(schema 见 docs/project_design.md §W4)
 *
 * 为什么仍然画出来而不是留空白:
 *   ① 报告 §7.1 要求它们在场且**明确标注**为 MOCK —— 空白等于悄悄丢掉交付项,
 *      评委看不到「我们知道要有这张图」;
 *   ② 占位图给出**目标形制与坐标口径**,上板数据一回来就能直接替换,
 *      不必再讨论图该长什么样;
 *   ③ 灰显 + 虚线 amber 边框 + 图内 MOCK 水印,做到「一眼可辨不是实测」。
 *
 * 硬约束:占位图**不得**出现任何具体数值。一旦出现数字,哪怕带 MOCK 前缀,
 * 也会在快速翻阅的截图里被当成结论(报告 §9 的溯源纪律正是为此)。
 * ============================================================ */
import { svgRoot, el, intTicks } from './axis';

export type MockKind = 'heat4x4' | 'curve';

export interface MockOpts {
  kind: MockKind;
  title: string;
  xLabel: string;
  yLabel: string;
  /** 上报什么数据、从哪来(替换条件) */
  replace: string;
}

export function renderMock(o: MockOpts): SVGSVGElement {
  const W = 760;
  const H = o.kind === 'heat4x4' ? 320 : 300;
  const svg = svgRoot(W, H);
  el('rect', { x: 1, y: 1, width: W - 2, height: H - 2, rx: 10, class: 'pl-mockframe' }, svg);

  const t = el('text', { x: 20, y: 26, class: 'pl-title' }, svg);
  t.textContent = o.title;
  const chip = el('text', { x: W - 20, y: 26, 'text-anchor': 'end', class: 'pl-mockchip' }, svg);
  chip.textContent = 'MOCK · 占位,非实测';

  if (o.kind === 'heat4x4') drawHeat(svg, W);
  else drawCurve(svg, W, H, o);

  const box = el('g', {}, svg);
  const lines = [
    '数据行:MOCK(占位)',
    `替换条件:${o.replace}`,
  ];
  lines.forEach((s, i) => {
    const tx = el('text', { x: 24, y: H - 40 + i * 16, class: 'pl-mocksub' }, box);
    tx.textContent = s;
  });

  // 右上角大水印:即便只截取图的一部分,也能看出这是占位
  const wm = el('text', {
    x: W - 24, y: H - 24, 'text-anchor': 'end', class: 'pl-mockmark',
  }, svg);
  wm.textContent = 'MOCK';
  return svg;
}

function drawHeat(svg: SVGSVGElement, W: number): void {
  const cell = 34;
  const gap = 8;
  const gridW = 4 * cell + 3 * gap;
  const x0 = (W - gridW) / 2;
  const y0 = 62;
  for (let r = 0; r < 4; r++) {
    for (let c = 0; c < 4; c++) {
      const x = x0 + c * (cell + gap);
      const y = y0 + r * (cell + gap);
      el('rect', { x, y, width: cell, height: cell, rx: 4, class: 'pl-mockcell' }, svg);
      const lab = el('text', {
        x: x + cell / 2, y: y + cell / 2 + 4, 'text-anchor': 'middle', class: 'pl-mockcell-lab',
      }, svg);
      lab.textContent = `RO${r * 4 + c}`;
    }
  }
  const note = el('text', { x: W / 2, y: y0 + gridW + 26, 'text-anchor': 'middle', class: 'pl-mocksub' }, svg);
  note.textContent = '16 环 RO 频率热图:每格一个环的振荡频率(上板 VIO 读数)';
}

function drawCurve(svg: SVGSVGElement, W: number, H: number, o: MockOpts): void {
  const l = 56, r = 24, t = 52, b = 56;
  const x0 = l, x1 = W - r, y0 = t, y1 = H - b;
  el('rect', { x: x0, y: y0, width: x1 - x0, height: y1 - y0, class: 'pl-mockplot' }, svg);
  for (const v of intTicks(0, 100, 4)) {
    const y = y1 - (v / 100) * (y1 - y0);
    el('line', { x1: x0, y1: y, x2: x1, y2: y, class: 'pl-gridline' }, svg);
    el('text', { x: x0 - 8, y: y + 4, 'text-anchor': 'end', class: 'pl-tick' }, svg).textContent = `${v}%`;
  }
  const xt = el('text', { x: (x0 + x1) / 2, y: H - 14, 'text-anchor': 'middle', class: 'pl-axis-title' }, svg);
  xt.textContent = o.xLabel;
  const yt = el('text', {
    x: 14, y: (y0 + y1) / 2, 'text-anchor': 'middle', class: 'pl-axis-title',
    transform: `rotate(-90 14 ${(y0 + y1) / 2})`,
  }, svg);
  yt.textContent = o.yLabel;
  // 虚线示意曲线(无刻度值、无数据点) —— 只表达走向,不表达数值
  const pts: string[] = [];
  for (let i = 0; i <= 10; i++) {
    const x = x0 + (i / 10) * (x1 - x0);
    const y = y1 - (0.5 + 0.42 * Math.sin((i / 10) * Math.PI)) * (y1 - y0);
    pts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  }
  el('polyline', { points: pts.join(' '), class: 'pl-mockline' }, svg);
}

/* V5/V6/V7 的占位声明(与上板/实验计划对齐,写清「何时能替换」) */
export const MOCK_SPECS: Record<'v5' | 'v6' | 'v7', MockOpts> = {
  v5: {
    kind: 'heat4x4', title: 'V5 · 16 环 RO 频率热图', xLabel: '', yLabel: '',
    replace: '上板 W1 阶段 VIO 抓取 16 环频率并落盘 data/w1_readings/(当前为空目录)',
  },
  v6: {
    kind: 'curve', title: 'V6 · 温度-reliability 曲线', xLabel: '温度(℃)', yLabel: '可靠度(%)',
    replace: '上板高低温实验:每温度点重复认证 N 次,统计通过率,落盘 CSV 后接本图',
  },
  v7: {
    kind: 'curve', title: 'V7 · B6 ML 攻击准确率(实验 A / 实验 B)', xLabel: '攻击者累计 CRP 数', yLabel: '排序重构成功率(%)',
    replace: '实现 docs/project_design.md §W4 的两组实验(合成 Arbiter 基线 / 自家 RO 排序重构),产出 JSON 后接本图',
  },
};
