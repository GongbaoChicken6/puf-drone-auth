/* ============================================================
 * V1 —— HD 双系列直方图(报告 §7.1 V1,REAL-LIVE)
 *
 * 量纲固定 0..64:HD 是 64 位响应上的汉明距离,量程是**协议属性**而非数据
 * 决定 —— 若按数据自适应缩放,两张不同 run 的图就不能叠着看了。
 *
 * 双系列并列(而非叠加透明):两分布要比较的是**分离度**,叠加会让
 * 「同设备峰在 0–5、跨设备峰在 23–44」这个结论在视觉上糊成一团。
 *
 * 阈值分割线由外部传入(§7.2 阈值滑杆联动):本函数只管画,不管口径。
 * ============================================================ */
import { Plot, el, intTicks, barTopPath } from './axis';
import { COLOR, drawLegend } from './legend';
import type { HdSeries } from '../core/types';

const BITS = 64;

export interface V1Opts {
  /** 当前阈值滑杆位置(接受上界,HD ≤ τ 即接受 —— 与 decide() 同向) */
  tau: number;
  /** threshold.py 的两档真实阈值,用于铺出绿/灰/红三段 */
  tauPass: number;
  tauReject: number;
  /** R7:图内拖 τ 的回调。move 每帧触发(此时**不可**触发全页重渲染,
   * 否则 svg 被替换、pointer capture 随之失效,拖拽当场断线);end 在
   * 松手时触发一次,由调用方提交全量重绘。键盘/滑杆路径与拖拽路径等价,
   * 拖拽只是冗余通道,不承担唯一可达性。 */
  onTauPick?: (tau: number, phase: 'move' | 'end') => void;
}

function counts(v: number[], max = BITS): number[] {
  const c = new Array(max + 1).fill(0) as number[];
  for (const x of v) c[Math.max(0, Math.min(max, x))]++;
  return c;
}

export function renderV1(d: HdSeries, o: V1Opts): SVGSVGElement {
  const ci = counts(d.intra);
  const cc = counts(d.inter);
  const peak = Math.max(1, ...ci, ...cc);

  /* pad.t 从 16 提到 40:D14 把图例从绘图区里搬到框外上沿 —— 原位置在图内
   * 左上,而两条分布的均值线恰好落在左侧(x≈μ_intra)与中部,直接标在图上
   * 的 μ 会被图例压住。图例是「查表」,均值是「结论」,让结论给查表让位是反的;
   * 图例移出框外,绘图区顶部整条就空了。
   *
   * 40px 的顶留白要放下**两行**框内标注(均值一行、τ 滑杆线一行),行距 16px:
   * 单行放不下 —— 两条标注都贴在 μ_intra≈1.3 那一带(τ 线在 bin 7 边界,
   * 均值线在 bin 1.3),同高就会叠在一起,而这是「接受上界」和「真实均值」
   * 两个必须分清的判据。曾把 μ 直接标在同高、只错开 x,实测在真数据上
   * (μ_intra=1.30、τ=6)两串字仍然连成一片。 */
  const p = new Plot([0, BITS], [0, Math.ceil(peak * 1.12)], {
    w: 760, h: 366, pad: { t: 40 }, xLabel: '汉明距离 HD(bit,满量程 64)', yLabel: '样本数',
  });
  const ROW_MEAN = p.box.y0 + 12;   // 第一行:两条分布的均值
  const ROW_TAU = p.box.y0 + 28;    // 第二行:滑杆阈值线(与均值分行,见上)

  p.gridY(intTicks(0, Math.ceil(peak * 1.12), 5));
  p.gridX(intTicks(0, BITS, 8));

  const binW = (p.box.x1 - p.box.x0) / (BITS + 1);

  /* 三段判定带(逐响应口径,与 decide() 的分支一一对应):
   *   HD ≤ TAU_PASS              → PASS
   *   TAU_PASS < HD < TAU_REJECT → 灰区(加测 EXTRA_CHALLENGE)
   *   HD ≥ TAU_REJECT            → REJECT
   * 灰区是**开区间**(7..15),绿段含 6、红段含 16。带子按「bin 的左右沿」切,
   * 而不是按 HD 值切 —— 否则第 6 根柱子会有一半压在灰带上,看起来像 6 属于灰区。 */
  const band = (from: number, to: number, cls: string, label: string) => {
    const x0 = p.box.x0 + binW * Math.max(0, from);
    const x1 = p.box.x0 + binW * Math.min(BITS + 1, to);
    el('rect', {
      x: x0, y: p.box.y0, width: Math.max(0, x1 - x0), height: p.box.y1 - p.box.y0, class: cls,
    }, p.gridLayer);
    if (x1 - x0 > 52) {
      const t = el('text', {
        x: (x0 + x1) / 2, y: p.box.y1 - 6, 'text-anchor': 'middle', class: 'pl-band-lab',
      }, p.gridLayer);
      t.textContent = label;
    }
  };
  band(0, o.tauPass + 1, 'pl-band-pass', `PASS HD ≤${o.tauPass}`);
  band(o.tauPass + 1, o.tauReject, 'pl-band-gray', `灰区 ${o.tauPass + 1}–${o.tauReject - 1}`);
  band(o.tauReject, BITS + 1, 'pl-band-reject', `REJECT ≥${o.tauReject}`);

  /* 并列柱:intra 靠左、inter 靠右(D14 细标记 + 2px 缝 + 顶圆角)
   *
   * 组的左右各留 1px、两系列之间留 2px 的缝。缝必须存在:两根同高柱直接贴合
   * 时,在暗底上会连成一块双倍宽的色块,读数会被当成「一根粗柱」。 */
  const GAP = 2;                       // 两系列之间的缝
  const PAD = 2;                       // 组左右各留 1px,柱与柱不贴格
  const bw = Math.max(1.5, (binW - PAD - GAP) / 2);
  const base = p.y(0);
  for (let hd = 0; hd <= BITS; hd++) {
    const cx = p.box.x0 + binW * (hd + 0.5);
    const left = cx - (bw * 2 + GAP) / 2;
    const pairs: [number, number, string][] = [
      [ci[hd], left, COLOR.intra],
      [cc[hd], left + bw + GAP, COLOR.inter],
    ];
    for (const [n, x, color] of pairs) {
      if (n <= 0) continue;
      const y = p.y(n);
      el('path', {
        d: barTopPath(x, y, bw, Math.max(1, base - y), 2),
        fill: color, opacity: .92,
      }, p.g);
    }
    if (ci[hd] > 0 || cc[hd] > 0) {
      p.hit(p.box.x0 + binW * hd, p.box.y0, binW, base - p.box.y0,
        `HD=${hd}\n同设备 ${ci[hd]} 条 · 跨设备 ${cc[hd]} 条`, 'band');
    }
  }

  /* 均值直接标在图上(D14)。
   *
   * 这两个数是判据本身:同设备均值钉在 3–5、跨设备均值钉在 30 以上,「分离度」
   * 才是这张图要讲的事。原先它只以 μ=… 的小字塞在图例注记里,读者要先把两条
   * 分布和两个色块对上,再回图例里找数字 —— 而色相恰恰是红绿色盲最先丢掉的
   * 线索。直接画线 + 标签带上系列名,即使完全分不出绿红,也能读出
   * 「左边这条叫 genuine,右边这条叫 impostor」。
   *
   * 均值线画在 overlay 层(压住柱体)但只给 1.5px 虚线:它是参照,不是数据。 */
  const meanMark = (mu: number, color: string, name: string) => {
    const px = p.x(mu);
    el('line', {
      x1: px, y1: p.box.y0, x2: px, y2: p.box.y1,
      stroke: color, opacity: .9, class: 'pl-mean',
    }, p.overlay);
    const right = px > (p.box.x0 + p.box.x1) / 2;
    el('text', {
      x: px + (right ? -5 : 5), y: ROW_MEAN,
      'text-anchor': right ? 'end' : 'start',
      class: 'pl-mean-lab', fill: color,
    }, p.overlay).textContent = `${name} μ=${mu.toFixed(2)}`;
  };
  meanMark(mean(d.intra), COLOR.intra, '同设备');
  meanMark(mean(d.inter), COLOR.inter, '跨设备');

  /* 滑杆阈值画在**接受上界的右沿**(τ+1 的 bin 边界):HD ≤ τ 都属于绿区,
   * 线画在 τ 的柱心上会让第 τ 根柱子看起来被劈成两半。
   * R7:τ 线/标签落灰区时改琥珀 —— 此前「灰区」只在滑杆读数与 V2 上可见,
   * V1 自己那根线拖进 7–15 仍是青色,等于本图在附和「这也是个合法门限」。 */
  const gray = (t: number) => t > o.tauPass && t < o.tauReject;
  const tauLab = (t: number) => `接受上界 τ=${t}${gray(t) ? '(灰区)' : ''}`;
  const tauEdge = p.box.x0 + binW * (o.tau + 1);
  const tauLine = el('line', {
    x1: tauEdge, y1: p.box.y0, x2: tauEdge, y2: p.box.y1,
    class: 'pl-vline vl-tau' + (gray(o.tau) ? ' vl-tau-gray' : ''),
  }, p.overlay);
  const tauLabel = el('text', {
    x: tauEdge + 4, y: ROW_TAU, class: 'pl-vlabel vl-tau',
  }, p.overlay);
  tauLabel.textContent = tauLab(o.tau);

  /* R7:图内按住拖动 = 直接改 τ。指针 x → 最近 bin 边界;move 阶段只平移
   * 线与标签两个节点(全量重渲染会销毁本 svg,pointer capture 一并失效);
   * end 才回调出去走滑杆同一条提交路径。按下才生效,纯悬停仍归 tooltip。 */
  if (o.onTauPick) {
    const svg = p.svg;
    const toTau = (e: PointerEvent): number => {
      const r = svg.getBoundingClientRect();
      const vx = (e.clientX - r.left) * (760 / r.width);
      return Math.max(0, Math.min(BITS - 1,
        Math.round((vx - p.box.x0) / binW) - 1));
    };
    const live = (t: number): void => {
      const ex = p.box.x0 + binW * (t + 1);
      tauLine.setAttribute('x1', String(ex));
      tauLine.setAttribute('x2', String(ex));
      tauLabel.setAttribute('x', String(ex + 4));
      tauLabel.textContent = tauLab(t);
      tauLine.setAttribute('class', 'pl-vline vl-tau' + (gray(t) ? ' vl-tau-gray' : ''));
    };
    svg.addEventListener('pointerdown', (e) => {
      if (e.button !== 0 || !e.isPrimary) return;
      // 合成指针(自动化/某些辅助技术)没有活跃 pointerId,capture 会抛
      // NotFoundError —— 拖拽依赖 move/up 冒泡到 svg 也能工作,丢了 capture
      // 只降级不报错。
      try { svg.setPointerCapture(e.pointerId); } catch { /* 见上 */ }
      e.preventDefault();
      const move = (ev: PointerEvent): void => {
        const t = toTau(ev);
        live(t);
        o.onTauPick!(t, 'move');
      };
      const fin = (ev: PointerEvent): void => {
        svg.removeEventListener('pointermove', move);
        svg.removeEventListener('pointerup', fin);
        svg.removeEventListener('pointercancel', fin);
        o.onTauPick!(toTau(ev), 'end');
      };
      svg.addEventListener('pointermove', move);
      svg.addEventListener('pointerup', fin);
      svg.addEventListener('pointercancel', fin);
      move(e);
    });
  }

  /* 图例搬到绘图区**上方框外**(D14)。μ 已直接标在图上,注记里不再重复 ——
   * 同一个数字出现两次,读者会以为它们是两个不同的量。 */
  drawLegend(p.svg, p.box.x0, 16, [
    { label: '同设备(genuine)', color: COLOR.intra, kind: 'bar', note: `n=${d.intra.length}` },
    { label: '跨设备(impostor)', color: COLOR.inter, kind: 'bar', note: `n=${d.inter.length}` },
  ], p.box.x1 - p.box.x0 - 16);

  p.frame();
  return p.svg;
}

export function mean(v: number[]): number {
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : 0;
}
