/* ============================================================
 * V2 —— ROC / EER 曲线 + 混淆矩阵(报告 §7.1 V2,REAL-LIVE)
 *
 * 阈值口径**逐字对齐 threshold.py 的 decide()**,这是本图唯一的正确性来源:
 *
 *     if hd <= TAU_PASS   -> PASS     (TAU_PASS  = 6)
 *     if hd >= TAU_REJECT -> REJECT   (TAU_REJECT= 16)
 *     else                -> GRAY     (7..15)
 *
 * 三个后果,一个都不能省:
 *  ① 接受是 **HD ≤ τ**(含等号),不是 <。差一个等号会让工作点整体偏移一格,
 *    在 TAU_PASS=6 这种小量纲上就是 17% 的相对误差。
 *  ② 判决有**第三个分支**:τ 落在 7..15 时协议既不 PASS 也不 REJECT,而是
 *    加测 EXTRA_CHALLENGE。所以这一段 τ 上的 ROC 点**不构成合法工作点**,
 *    图上用琥珀色虚线段显式标出,不许被当成可选的阈值。
 *  ③ 因此滑杆的实际可选合法位置是 τ ∈ [0,6] ∪ [15,64];落在灰区时,
 *    工作点标记变色并在混淆矩阵下方给出说明。
 *
 * 曲线由 V1 的两组分布前端计算(§7.1:不额外请求后端)。
 * ============================================================ */
import { Plot, el } from './axis';
import { COLOR, drawLegend } from './legend';
import type { HdSeries } from '../core/types';

const BITS = 64;

export interface RocPoint { tau: number; far: number; frr: number; tpr: number; }

export interface RocResult {
  points: RocPoint[];
  eer: number;
  eerTau: number;
  at: RocPoint;
  /** τ 是否落在协议灰区(既不 PASS 也不 REJECT,而是加测) */
  grayAt: boolean;
  confusion: { tp: number; fp: number; tn: number; fn: number };
}

export interface TauCfg { tauPass: number; tauReject: number; }

/** τ = 接受上界(HD ≤ τ 即接受)。扫描 0..64 全域,灰区由 tauAt() 单独判定。 */
export function computeRoc(d: HdSeries, tau: number, cfg: TauCfg): RocResult {
  const ni = Math.max(1, d.intra.length);
  const nc = Math.max(1, d.inter.length);
  const points: RocPoint[] = [];
  for (let t = 0; t <= BITS; t++) {
    const far = d.inter.filter(x => x <= t).length / nc;
    const tpr = d.intra.filter(x => x <= t).length / ni;
    points.push({ tau: t, far, frr: 1 - tpr, tpr });
  }

  // EER:FAR 与 FRR 的相交点。两级都是阶梯函数,故在跨越区间内**线性插值** ——
  // 直接取最近格点会在 τ 稀疏时报大一个格。
  let eerTau = 0;
  let eer = 1;
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1];
    const b = points[i];
    if (a.far - a.frr <= 0 && b.far - b.frr >= 0) {
      const d0 = a.far - a.frr;
      const d1 = b.far - b.frr;
      const f = d1 === d0 ? 0 : -d0 / (d1 - d0);
      eerTau = a.tau + f * (b.tau - a.tau);
      eer = a.far + f * (b.far - a.far);
      break;
    }
  }

  const t = Math.max(0, Math.min(BITS, Math.round(tau)));
  const at = points[t];
  const tp = d.intra.filter(x => x <= t).length;
  const fp = d.inter.filter(x => x <= t).length;
  return {
    points, eer, eerTau, at,
    grayAt: t > cfg.tauPass && t < cfg.tauReject,
    confusion: { tp, fp, tn: d.inter.length - fp, fn: d.intra.length - tp },
  };
}

export function renderV2(
  r: RocResult,
  o: { tau: number; onTauPick?: (tau: number, phase: 'move' | 'end') => void } & TauCfg,
): SVGSVGElement {
  // 右侧留 300px 给混淆矩阵
  const p = new Plot([0, 1], [0, 1], {
    w: 760, h: 340, pad: { l: 56, r: 300, t: 18, b: 44 },
    xLabel: 'FAR(跨设备被误接受的比例)', yLabel: 'TPR(同设备被正确接受的比例)',
  });
  const bx = p.box;
  const side = Math.min(bx.x1 - bx.x0, bx.y1 - bx.y0);
  const gy = bx.y1 - bx.y0;
  const x = (v: number) => bx.x0 + v * side;
  const y = (v: number) => bx.y1 - v * gy;

  for (const g of [0, .2, .4, .6, .8, 1]) {
    el('line', { x1: x(g), y1: bx.y0, x2: x(g), y2: bx.y1, class: 'pl-gridline' }, p.gridLayer);
    el('line', { x1: bx.x0, y1: y(g), x2: x(1), y2: y(g), class: 'pl-gridline' }, p.gridLayer);
    el('text', { x: x(g), y: bx.y1 + 16, 'text-anchor': 'middle', class: 'pl-tick' }, p.axisLayer)
      .textContent = g.toFixed(1);
    el('text', { x: bx.x0 - 8, y: y(g) + 4, 'text-anchor': 'end', class: 'pl-tick' }, p.axisLayer)
      .textContent = g.toFixed(1);
  }
  el('line', { x1: bx.x0, y1: bx.y1, x2: x(1), y2: y(1), class: 'pl-diag' }, p.gridLayer);

  /* 曲线按**阶梯**画而不是折线(D14)。
   *
   * HD 是整数,τ 扫 0..64,FAR/TPR 都是逐格跳变的阶跃函数 —— 用折线把相邻的
   * 阶跃点连起来,等于在图上画出「τ 取 8.4 时 FAR=0.13」这种协议里不存在的
   * 中间态,而这恰恰是评审最容易追问的一处(「你这个工作点在哪儿?」)。
   * 阶梯的每一段水平线就是「τ 落在这一格的整个区间里,指标没变」,竖直段是
   * 「再放一格,指标跳变」—— 曲线的形状本身在陈述协议的口径。
   *
   * 代价:曲线多出 65 个直角。故不再逐点画顶点标记 —— 阶梯已经自带顶点,
   * 只给有语义的几个点(EER / TAU_PASS / 灰区上沿 / 当前工作点)画标记。 */
  const stepD = (sel: RocPoint[]): string => {
    let d = '';
    sel.forEach((pt, i) => {
      const px = x(pt.far).toFixed(2);
      const py = y(pt.tpr).toFixed(2);
      d += i === 0 ? `M${px} ${py}` : `H${px}V${py}`;
    });
    return d;
  };
  const main = r.points;
  const areaD = `M${x(main[0].far).toFixed(2)} ${y(0).toFixed(2)}`
    + `L${x(main[0].far).toFixed(2)} ${y(main[0].tpr).toFixed(2)}`
    + stepD(main).replace(/^M[^HV]*/, '')
    + `L${x(main[main.length - 1].far).toFixed(2)} ${y(0).toFixed(2)}Z`;
  el('path', { d: areaD, fill: COLOR.comm, opacity: .1, stroke: 'none' }, p.gridLayer);
  el('path', {
    d: stepD(main), fill: 'none', stroke: COLOR.comm, 'stroke-width': 2.2,
    'stroke-linejoin': 'miter',
  }, p.g);

  // 灰区 τ ∈ (TAU_PASS, TAU_REJECT):协议不发 PASS/REJECT 而是加测 —— 该段
  // 上的曲线点不是可选工作点,用琥珀虚线重描一遍并加标注。
  const gray = r.points.filter(pt => pt.tau > o.tauPass && pt.tau < o.tauReject);
  if (gray.length > 1) {
    el('path', {
      d: stepD(gray), fill: 'none', stroke: COLOR.gray, 'stroke-width': 3.5,
      class: 'pl-grayband',
    }, p.g);
    const mid = gray[Math.floor(gray.length / 2)];
    const gl = el('text', {
      x: x(mid.far) + 8, y: y(mid.tpr) + 22, class: 'pl-grayband-lab',
    }, p.g);
    gl.textContent = `τ=${gray[0].tau}–${gray[gray.length - 1].tau} 灰区(加测,非合法工作点)`;
  }

  // EER 点
  el('circle', { cx: x(r.eer), cy: y(1 - r.eer), r: 5, fill: COLOR.amber }, p.g);
  el('text', { x: x(r.eer) + 9, y: y(1 - r.eer) - 8, class: 'pl-eer-lab' }, p.g)
    .textContent = `EER ${(r.eer * 100).toFixed(2)}% @ τ=${r.eerTau.toFixed(1)}`;

  // 代码里的两档真实阈值锚点:TAU_PASS 与「灰区上沿」(TAU_REJECT−1 是最后一个非 REJECT 的 τ)
  const mk = (tau: number, color: string, label: string) => {
    const pt = r.points[tau];
    if (!pt) return;
    el('circle', { cx: x(pt.far), cy: y(pt.tpr), r: 4, fill: 'none', stroke: color, 'stroke-width': 2 }, p.g);
    el('text', { x: x(pt.far) + 7, y: y(pt.tpr) - 6, class: 'pl-tick' }, p.g).textContent = label;
  };
  mk(o.tauPass, COLOR.pass, `TAU_PASS=${o.tauPass}`);
  mk(o.tauReject - 1, COLOR.reject, `灰区上沿=${o.tauReject - 1}`);

  /* 全 τ 逐点悬停(D14)。滑杆只能一格一格拖,而「τ 再放一格会怎样」是这张图
   * 最常被问的问题 —— 把 65 个 τ 都做成命中目标,指针扫过去就能读出该 τ 的
   * FAR/TPR/FRR,不必先拖滑杆再看矩阵。命中圆半径给到 6px(大于标记本身),
   * 密集处靠绘制顺序让邻近的 τ 覆盖前一个。 */
  r.points.forEach(pt => {
    p.hitRound(x(pt.far), y(pt.tpr), 6,
      `τ=${pt.tau}\nTPR=${(pt.tpr * 100).toFixed(1)}%(同设备接受)\n`
      + `FAR=${(pt.far * 100).toFixed(1)}%(跨设备误接受)\nFRR=${(pt.frr * 100).toFixed(1)}%\n`
      + (pt.tau > o.tauPass && pt.tau < o.tauReject ? '⚠ 灰区:协议在此 τ 下加测' : ''));
  });

  // 当前工作点(R7 加 pl-opdot 类:拖拽时要就地平移它,查询需要稳定句柄)
  const opColor = r.grayAt ? COLOR.gray : r.at.far === 0 ? COLOR.pass : COLOR.reject;
  const opDot = el('circle', {
    cx: x(r.at.far), cy: y(r.at.tpr), r: 5.5, fill: opColor, class: 'pl-opdot',
  }, p.g);
  const opLab = el('text', { x: x(r.at.far) + 9, y: y(r.at.tpr) + 16, class: 'pl-op-lab' }, p.g);
  opLab.textContent = `工作点 τ=${o.tau}${r.grayAt ? '(灰区)' : ''}`;

  /* R7:在曲线附近按住拖 = 沿 x(FAR)吸附到最近的阶梯点改 τ。
   * 与 V1 同一套 move/end 纪律:move 只平移工作点两节点,end 才提交全页重绘
   * (混淆矩阵四数随 end 更新 —— 拖动途中矩阵跟着闪反而读不了数)。
   * 指针不在曲线上也允许:ROC 的 x 就是 FAR,横着扫过去总能落到一个 τ。 */
  if (o.onTauPick) {
    const toTau = (e: PointerEvent): number => {
      const rect = p.svg.getBoundingClientRect();
      const vx = (e.clientX - rect.left) * (760 / rect.width);
      const far = Math.max(0, Math.min(1, (vx - bx.x0) / side));
      let best = 0;
      let bestD = Infinity;
      for (const pt of r.points) {
        const d = Math.abs(pt.far - far);
        if (d < bestD - 1e-9) { bestD = d; best = pt.tau; }   // 并列取较小 τ
      }
      return best;
    };
    const live = (t: number): void => {
      const pt = r.points[t];
      const g = t > o.tauPass && t < o.tauReject;
      opDot.setAttribute('cx', String(x(pt.far)));
      opDot.setAttribute('cy', String(y(pt.tpr)));
      opDot.setAttribute('fill', g ? COLOR.gray : pt.far === 0 ? COLOR.pass : COLOR.reject);
      opLab.setAttribute('x', String(x(pt.far) + 9));
      opLab.setAttribute('y', String(y(pt.tpr) + 16));
      opLab.textContent = `工作点 τ=${t}${g ? '(灰区)' : ''}`;
    };
    p.svg.addEventListener('pointerdown', (e) => {
      if (e.button !== 0 || !e.isPrimary) return;
      try { p.svg.setPointerCapture(e.pointerId); } catch { /* 合成指针无活跃 id */ }
      e.preventDefault();
      const move = (ev: PointerEvent): void => {
        const t = toTau(ev);
        live(t);
        o.onTauPick!(t, 'move');
      };
      const fin = (ev: PointerEvent): void => {
        p.svg.removeEventListener('pointermove', move);
        p.svg.removeEventListener('pointerup', fin);
        p.svg.removeEventListener('pointercancel', fin);
        o.onTauPick!(toTau(ev), 'end');
      };
      p.svg.addEventListener('pointermove', move);
      p.svg.addEventListener('pointerup', fin);
      p.svg.addEventListener('pointercancel', fin);
      move(e);
    });
  }

  drawLegend(p.overlay, bx.x0 + 8, bx.y0 + 14, [
    { label: 'ROC(HD ≤ τ 即接受)', color: COLOR.comm },
    { label: '灰区段', color: COLOR.gray, kind: 'dash' },
  ], side - 16);

  /* ---------- 混淆矩阵 ---------- */
  const mx = bx.x1 + 34;
  const cw = 250 / 2 - 6;
  const ch = 52;
  const cells: [string, number, string, string][] = [
    ['TP 同设备·接受', r.confusion.tp, 'ok', '真阳性:同设备被判通过'],
    ['FP 跨设备·接受', r.confusion.fp, 'bad', '假阳性:跨设备被误放行 —— 安全性事故'],
    ['FN 同设备·拒绝', r.confusion.fn, 'warn', '假阴性:同设备被误拒 —— 可用性事故'],
    ['TN 跨设备·拒绝', r.confusion.tn, 'ok', '真阴性:跨设备被正确拦下'],
  ];
  el('text', { x: mx, y: bx.y0 + 12, class: 'pl-sec-title' }, p.overlay)
    .textContent = `混淆矩阵 · τ=${o.tau}`;
  el('text', { x: mx, y: bx.y0 + 28, class: 'pl-sec-sub' }, p.overlay)
    .textContent = '接受 ⇔ HD ≤ τ(decide() 同向,含等号)';

  cells.forEach(([label, val, tone, tip], i) => {
    const cx = mx + (i % 2) * (cw + 12);
    const cy = bx.y0 + 40 + Math.floor(i / 2) * (ch + 10);
    el('rect', { x: cx, y: cy, width: cw, height: ch, rx: 6, class: `pl-mx pl-mx-${tone}` }, p.overlay);
    el('text', { x: cx + 8, y: cy + 20, class: 'pl-mx-lab' }, p.overlay).textContent = label;
    el('text', { x: cx + 8, y: cy + 42, class: 'pl-mx-val' }, p.overlay).textContent = String(val);
    const hit = el('rect', { x: cx, y: cy, width: cw, height: ch, class: 'pl-hit' }, p.overlay);
    hit.dataset.tip = `${label}\n${val} 条\n${tip}`;
  });

  let footY = bx.y0 + 40 + 2 * (ch + 10) + 14;
  el('text', { x: mx, y: footY, class: 'pl-sec-sub' }, p.overlay)
    .textContent = `FAR=${(r.at.far * 100).toFixed(2)}% · FRR=${(r.at.frr * 100).toFixed(2)}%`;
  if (r.grayAt) {
    footY += 16;
    const warn = el('text', { x: mx, y: footY, class: 'pl-graywarn' }, p.overlay);
    warn.textContent = `τ=${o.tau} 在灰区:协议不判 PASS/REJECT,而是加测`;
  }

  el('rect', { x: bx.x0, y: bx.y0, width: side, height: gy, class: 'pl-frame' }, p.axisLayer);
  return p.svg;
}
