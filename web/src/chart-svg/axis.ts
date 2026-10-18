/* ============================================================
 * chart-svg 基元 —— 坐标系、刻度、网格、坐标框(报告 §7)
 *
 * 为什么手写 SVG 而不用图表库(报告 §3 离线策略的延伸):
 *   1. 产物必须纯静态全离线,三入口体积已受控;引 echarts/chart.js 会把
 *      viz 包体推到几百 kB,而本页只有 7 张固定形制的图;
 *   2. §7.2 要求每图可导出 **SVG**(矢量,对齐 report/figures 排版)——
 *      库生成的 canvas 图导不出矢量;SVG 内联样式可直接序列化落盘;
 *   3. 刻度口径要严格对齐 threshold.py(0..64 的 HD 量纲),自己的
 *      scale 才能保证「分割线画在 TAU 上」这类语义不被库的自动轴吃掉。
 *
 * 坐标一律给**显式 viewBox**,导出时按 2× 光栅化即得排版尺寸,不依赖运行时测量。
 * ============================================================ */

export const SVG_NS = 'http://www.w3.org/2000/svg';

export function el<K extends keyof SVGElementTagNameMap>(
  tag: K,
  attrs: Record<string, string | number> = {},
  parent?: SVGElement,
): SVGElementTagNameMap[K] {
  const node = document.createElementNS(SVG_NS, tag);
  for (const k in attrs) node.setAttribute(k, String(attrs[k]));
  if (parent) parent.append(node);
  return node;
}

/* ---------- 标记形制(D14:细标记 · 圆角端 · 2px 缝) ---------- */

/**
 * 顶部圆角、底边平齐的柱体路径。
 *
 * 为什么不用 <rect rx>:rx 是**四角**圆角,柱体坐在基线上时会连底部一起削圆,
 * 看起来像悬空的胶囊而不是「长出来的一根柱子」—— 数据图的柱底必须与轴线
 * 严丝合缝,否则高度读数在视觉上就短了一截。故只有顶部两角给圆角。
 */
export function barTopPath(x: number, y: number, w: number, h: number, r = 2): string {
  const rr = Math.max(0, Math.min(r, w / 2, h));
  const x1 = x + w;
  const y1 = y + h;
  if (rr <= 0) return `M${x} ${y}H${x1}V${y1}H${x}Z`;
  return `M${x} ${y1}V${y + rr}Q${x} ${y} ${x + rr} ${y}`
    + `H${x1 - rr}Q${x1} ${y} ${x1} ${y + rr}V${y1}Z`;
}

/**
 * 斜纹填充图案,注册进所在 SVG 的 <defs>,返回 `url(#id)`。
 *
 * 用途是**色觉冗余**(D14):绿/红这一对在重度红绿色盲下是整页最脆的一处。
 * 色板验证脚本给 V1 双系列算的 CVD ΔE 是 13.3(过线),但那是**正常视力下的
 * 色差线性衰减**的估计;真正失去色相线索的人看的是「两块深浅相近的灰」。
 * 斜纹把其中一系列换成「有纹 / 无纹」的二值线索,顺带让黑白打印与灰度复印
 * 也能读出两条分布 —— 成本是几行 pattern,收益是这张图在任何介质上都不失效。
 *
 * 图案用**深色半透明**描线而非亮色:亮纹会把柱体的色相冲淡,而柱色本身
 * 负有语义(绿=同设备)。
 */
export function hatch(
  root: SVGSVGElement,
  id: string,
  opts: { color?: string; size?: number; angle?: number; width?: number } = {},
): string {
  let defs = root.querySelector<SVGDefsElement>(':scope > defs.pl-defs');
  if (!defs) defs = el('defs', { class: 'pl-defs' }, root);
  const size = opts.size ?? 6;
  const lw = opts.width ?? 1.6;
  const p = el('pattern', {
    id, patternUnits: 'userSpaceOnUse',
    width: size, height: size,
    patternTransform: `rotate(${opts.angle ?? 45})`,
  }, defs);
  el('line', {
    x1: 0, y1: 0, x2: 0, y2: size,
    stroke: opts.color ?? 'rgba(7,11,20,.5)', 'stroke-width': lw,
  }, p);
  return `url(#${id})`;
}

export function svgRoot(w: number, h: number): SVGSVGElement {
  const s = el('svg', {
    viewBox: `0 0 ${w} ${h}`, width: w, height: h,
    // 响应式靠 CSS 覆盖 width/height,viewBox 保证等比缩放不裁切
    preserveAspectRatio: 'xMidYMid meet', role: 'img',
  });
  return s;
}

/* ---------- 线性标度 ---------- */
export interface Scale {
  (v: number): number;
  inv(px: number): number;
  domain: [number, number];
  range: [number, number];
}

export function linear(domain: [number, number], range: [number, number]): Scale {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const dspan = (d1 - d0) || 1;
  const rspan = (r1 - r0) || 1;
  const f = ((v: number) => r0 + ((v - d0) / dspan) * (r1 - r0)) as Scale;
  f.inv = (px: number) => d0 + ((px - r0) / rspan) * dspan;
  f.domain = domain;
  f.range = range;
  return f;
}

/* 「好看」的刻度步长(1/2/5×10^n)。手写而非 d3-ticks,因为整页只有线性轴。 */
export function niceTicks(lo: number, hi: number, target = 6): number[] {
  const span = hi - lo;
  if (!(span > 0)) return [lo];
  const raw = span / Math.max(1, target);
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * mag;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) {
    out.push(Number(v.toFixed(10)));
  }
  return out;
}

/* 整数轴(HD 计数、位数这类量纲不能出现 2.5 的刻度) */
export function intTicks(lo: number, hi: number, target = 8): number[] {
  const span = Math.max(1, hi - lo);
  const step = Math.max(1, Math.ceil(span / Math.max(1, target)));
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(v);
  return out;
}

/* ---------- 绘图区 ---------- */
export interface Box { x0: number; y0: number; x1: number; y1: number; }

export interface PlotOpts {
  w?: number; h?: number;
  /** 左/右/上/下留白;左侧要放下 44px 的纵轴标签,底部放轴标题 */
  pad?: { l?: number; r?: number; t?: number; b?: number };
  xLabel?: string;
  yLabel?: string;
}

/**
 * 一张图的骨架:根 svg + 绘图区矩形 + 两轴标度。
 * 子类只管往 `g` 里塞图元;坐标框、网格、轴线由 axes() 统一收口。
 */
export class Plot {
  readonly svg: SVGSVGElement;
  readonly g: SVGGElement;          // 数据层(网格之下/之上按需再分层)
  readonly gridLayer: SVGGElement;
  readonly axisLayer: SVGGElement;
  readonly overlay: SVGGElement;
  readonly box: Box;
  readonly x: Scale;
  readonly y: Scale;
  readonly w: number;
  readonly h: number;

  constructor(xDomain: [number, number], yDomain: [number, number], opts: PlotOpts = {}) {
    this.w = opts.w ?? 760;
    this.h = opts.h ?? 360;
    const p = { l: 52, r: 18, t: 16, b: 40, ...(opts.pad ?? {}) };
    this.box = { x0: p.l, y0: p.t, x1: this.w - p.r, y1: this.h - p.b };
    this.x = linear(xDomain, [this.box.x0, this.box.x1]);
    this.y = linear(yDomain, [this.box.y1, this.box.y0]);   // SVG y 向下,须翻转

    this.svg = svgRoot(this.w, this.h);
    this.gridLayer = el('g', { class: 'pl-grid' }, this.svg);
    this.g = el('g', { class: 'pl-data' }, this.svg);
    this.axisLayer = el('g', { class: 'pl-axis' }, this.svg);
    this.overlay = el('g', { class: 'pl-overlay' }, this.svg);

    if (opts.xLabel) {
      el('text', {
        x: (this.box.x0 + this.box.x1) / 2, y: this.h - 6,
        'text-anchor': 'middle', class: 'pl-axis-title',
      }, this.axisLayer).textContent = opts.xLabel;
    }
    if (opts.yLabel) {
      const t = el('text', {
        x: 12, y: (this.box.y0 + this.box.y1) / 2,
        'text-anchor': 'middle', class: 'pl-axis-title',
        transform: `rotate(-90 12 ${(this.box.y0 + this.box.y1) / 2})`,
      }, this.axisLayer);
      t.textContent = opts.yLabel;
    }
  }

  /** 水平网格线 + 纵轴刻度数字(横向轨道图用;柱状图只画纵网格) */
  gridX(ticks: number[], fmt: (v: number) => string = String): void {
    for (const t of ticks) {
      const px = this.x(t);
      el('line', { x1: px, y1: this.box.y0, x2: px, y2: this.box.y1, class: 'pl-gridline' }, this.gridLayer);
      el('text', { x: px, y: this.box.y1 + 16, 'text-anchor': 'middle', class: 'pl-tick' }, this.axisLayer)
        .textContent = fmt(t);
    }
  }

  gridY(ticks: number[], fmt: (v: number) => string = String): void {
    for (const t of ticks) {
      const py = this.y(t);
      el('line', { x1: this.box.x0, y1: py, x2: this.box.x1, y2: py, class: 'pl-gridline' }, this.gridLayer);
      el('text', { x: this.box.x0 - 8, y: py + 4, 'text-anchor': 'end', class: 'pl-tick' }, this.axisLayer)
        .textContent = fmt(t);
    }
  }

  /** 坐标框(最后画,把网格与数据的溢出边裁住视觉) */
  frame(): void {
    el('rect', {
      x: this.box.x0, y: this.box.y0,
      width: this.box.x1 - this.box.x0, height: this.box.y1 - this.box.y0,
      class: 'pl-frame',
    }, this.axisLayer);
  }

  /** 竖直参考线(阈值分割线)。label 置顶,避免压住柱体。 */
  vline(v: number, cls: string, label?: string, atTop = true): void {
    const px = this.x(v);
    if (px < this.box.x0 - 0.5 || px > this.box.x1 + 0.5) return;
    el('line', { x1: px, y1: this.box.y0, x2: px, y2: this.box.y1, class: `pl-vline ${cls}` }, this.overlay);
    if (label) {
      el('text', {
        x: px + 4, y: atTop ? this.box.y0 + 12 : this.box.y1 - 4,
        class: `pl-vlabel ${cls}`,
      }, this.overlay).textContent = label;
    }
  }

  /**
   * HTML tooltip 的锚点(柱心 / 折线点),用不可见矩形扩大命中区。
   *
   * `hl` 打开统一悬停高亮层(tooltip.ts 委托):'band' 按命中框整体反白,
   * 'dot' 在命中框中心画环。高亮**不做**在各自的图里 —— 七张图各画各的
   * 一定出现「V1 反白、V2 画圈、V3 什么都不亮」这种不一致,而悬停反馈是
   * 全页同一种交互,理应只有一处实现。
   */
  hit(x: number, y: number, w: number, h: number, tip: string, hl?: 'band' | 'dot'): void {
    const r = el('rect', { x, y, width: w, height: h, class: 'pl-hit' }, this.overlay);
    r.dataset.tip = tip;
    if (hl) r.dataset.hl = hl;
  }

  /** 圆形命中区(散点/曲线上的工作点);r 同时是高亮环的半径 */
  hitRound(cx: number, cy: number, r: number, tip: string, hl: 'dot' | 'band' = 'dot'): void {
    const c = el('circle', { cx, cy, r: Math.max(r, 6), class: 'pl-hit' }, this.overlay);
    c.dataset.tip = tip;
    c.dataset.hl = hl;
    c.dataset.hlR = String(r + 3);
  }
}
