/* ============================================================
 * V4 —— 注册测量抖动(报告 §7.1 V4,REAL-LIVE(捕获后))
 *
 * 数据:桥接的 MeasurementProxyTransport 在 enroll 期间旁路捕获的**原始多次测量**
 * (每 CRP 重复 `--measurements` 次,缺省 3)。这是全项目里唯一能看见
 * 「同一挑战、同一器件、重复测量之间差多少位」的数据 —— 也就是报告 §9
 * 「噪声期望约 1.3bit／64bit」这句注释口径的实测对照。
 *
 * 为什么画「每 CRP 的散点 + min–max 须」而不是箱线图:
 *   每 CRP 只有 3 个样本。3 个点的四分位数是统计学噪声,画成箱线会给出
 *   一个**看起来像分布**的形状,但它是四舍五入的产物。散点如实展示 3 个值。
 *
 * 与 V3 的分工(必须写清楚,否则两张图会被当成矛盾):
 *   V3 的掩码是「每 seed 求翻位率 → 跨 seed 平均」,所以 47/64 个位都曾在
 *   某个 CRP 上翻过,平均后仍全部 ≤5% → 掩码全 1。
 *   V4 展示的正是被那个平均抹掉的逐 CRP 抖动。两者不矛盾,是同一现象的两种投影。
 * ============================================================ */
import { Plot, el, intTicks } from './axis';
import { COLOR, drawLegend } from './legend';
import type { VizMeasurements } from '../core/types';

const BITS = 64;

/* 64 位响应用两段 32 位整数处理(而非 BigInt):16 hex 字符 → 高/低 32 位,
 * 逐位与 XOR 都在 number 的精确整数范围内,读起来也接近 C 里的 uint32。 */
function split64(hex: string): [number, number] {
  const h = hex.padStart(16, '0');
  return [parseInt(h.slice(0, 8), 16) >>> 0, parseInt(h.slice(8, 16), 16) >>> 0];
}

function popcount(x: number): number {
  let n = 0;
  while (x) { x &= x - 1; n++; }
  return n;
}

export interface JitterCrp { seed: string; hds: number[]; samples: string[]; }
export interface JitterStats {
  crps: JitterCrp[];
  all: number[];
  mean: number; peak: number;
  /** 跨 CRP 至少翻过一次的位位置数(掩码看不见的那部分) */
  unstablePositions: number;
  /** 完全没出现在模板里的 seed(理论上不该有,出现即数据不一致) */
  missing: number;
  rounds: number;
}

export function computeJitter(
  m: VizMeasurements, responses: Record<string, string>,
): JitterStats {
  const crps: JitterCrp[] = [];
  const all: number[] = [];
  let missing = 0;
  let rounds = 0;
  const touched = new Array(BITS).fill(0) as number[];

  for (const s of m.series) {
    const tpl = responses[s.seed];
    if (!tpl) { missing++; continue; }
    const [tplHi, tplLo] = split64(tpl);
    const hds: number[] = [];
    for (const hex of s.samples) {
      const [hi, lo] = split64(hex);
      const dHi = (hi ^ tplHi) >>> 0;
      const dLo = (lo ^ tplLo) >>> 0;
      const n = popcount(dHi) + popcount(dLo);
      // 逐位累积:掩码看不见的「哪个位在哪个 CRP 翻过」由此得到
      for (let b = 0; b < 32; b++) {
        if ((dLo >>> b) & 1) touched[b]++;
        if ((dHi >>> b) & 1) touched[32 + b]++;
      }
      hds.push(n);
      all.push(n);
    }
    rounds = Math.max(rounds, s.samples.length);
    crps.push({ seed: s.seed, hds, samples: s.samples });
  }
  const mean = all.length ? all.reduce((a, b) => a + b, 0) / all.length : 0;
  return {
    crps, all, mean,
    peak: all.length ? Math.max(...all) : 0,
    unstablePositions: touched.filter(c => c > 0).length,
    missing, rounds,
  };
}

export function renderV4(s: JitterStats, o: { expectMean: number }): SVGSVGElement {
  // 纵轴量程:抖动的绝对量级很小(0–4 位),自适应到 [0, max(4, peak+1)]
  const yMax = Math.max(4, s.peak + 1);
  const p = new Plot([0, Math.max(1, s.crps.length - 1)], [0, yMax], {
    w: 760, h: 320, pad: { l: 52, r: 20, t: 34, b: 44 },
    xLabel: 'CRP 序号(注册时实际测量的挑战)', yLabel: '与模板的 HD(bit)',
  });
  p.gridY(intTicks(0, yMax, 4));
  p.gridX(intTicks(0, Math.max(1, s.crps.length - 1), 10));

  const base = p.y(0);
  s.crps.forEach((c, i) => {
    const x = p.x(i);
    const lo = Math.min(...c.hds);
    const hi = Math.max(...c.hds);
    if (hi > lo) {
      el('line', { x1: x, y1: p.y(lo), x2: x, y2: p.y(hi), class: 'pl-whisker' }, p.g);
      el('line', { x1: x - 4, y1: p.y(hi), x2: x + 4, y2: p.y(hi), class: 'pl-whisker' }, p.g);
      el('line', { x1: x - 4, y1: p.y(lo), x2: x + 4, y2: p.y(lo), class: 'pl-whisker' }, p.g);
    }
    for (const hd of c.hds) {
      el('circle', {
        cx: x, cy: p.y(hd), r: 3,
        fill: hd === 0 ? COLOR.pass : hd <= 2 ? COLOR.amber : COLOR.reject,
        opacity: .9,
      }, p.g);
    }
    p.hit(x - 8, p.box.y0, 16, base - p.box.y0,
      `CRP #${i} 0x${c.seed}\nHD = ${c.hds.join(', ')}\n${s.rounds} 次重复测量`, 'band');
  });

  // 实测均值 vs 报告注释口径(~1.3bit/64bit):两者接近即为口径自洽的证据
  const ym = p.y(s.mean);
  el('line', {
    x1: p.box.x0, y1: ym, x2: p.box.x1, y2: ym, class: 'pl-mean', stroke: COLOR.comm,
  }, p.overlay);
  el('text', {
    x: p.box.x1 - 4, y: ym - 5, 'text-anchor': 'end', class: 'pl-mean-lab', fill: COLOR.comm,
  }, p.overlay).textContent = `实测均值 ${s.mean.toFixed(2)} bit`;
  const ye = p.y(o.expectMean);
  el('line', { x1: p.box.x0, y1: ye, x2: p.box.x1, y2: ye, class: 'pl-mean-ref' }, p.overlay);
  el('text', { x: p.box.x0 + 4, y: ye - 5, class: 'pl-mean-ref-lab' }, p.overlay)
    .textContent = `报告注释口径 ~${o.expectMean.toFixed(1)} bit`;

  drawLegend(p.overlay, p.box.x0 + 8, p.box.y0 - 12, [
    { label: 'HD=0(与多数投票一致)', color: COLOR.pass, kind: 'dot' },
    { label: 'HD 1–2', color: COLOR.amber, kind: 'dot' },
    { label: 'HD ≥3', color: COLOR.reject, kind: 'dot' },
    {
      label: `每 CRP ${s.rounds} 次测量 · ${s.crps.length} 个 CRP`,
      color: COLOR.dim, kind: 'line',
    },
  ], p.box.x1 - p.box.x0 - 16);

  p.frame();
  return p.svg;
}
