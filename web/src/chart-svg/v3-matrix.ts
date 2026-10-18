/* ============================================================
 * V3 —— 模板响应位矩阵 + 稳定掩码条(报告 §7.1 V3,REAL-LIVE)
 *
 * 数据:templates.json 的每 seed 一条多数投票响应 + .stability.json sidecar
 * 的 64 字符掩码,两者都由组员 TemplateDB 真实落盘,经 /api/viz/templates 只读导出。
 *
 * 口径必须写在图上,否则这张图会被误读:
 *  · 位序 **MSB 在前**(位 63 在最左)—— 与 template_db.compute_stability 的
 *    掩码布局一致(mask[0] ↔ 响应位 63)。若按 LSB 画,掩码条与矩阵列会整体镜像,
 *    「第几列不稳」就对不上了。
 *  · 掩码是**每 seed 的多次测量**求翻位率、再**跨 seed 平均**后的结果,
 *    不是「该位上所有 seed 的一致度」。因此全 1 的掩码不代表每个 CRP 都稳 ——
 *   逐 CRP 的抖动要看 V4。报告 §7.1 对 V3 的原话也是这么界定的
 *    («**不含**「每 CRP 稳定性」»),此处照抄不越界。
 * ============================================================ */
import { el, hatch, svgRoot } from './axis';
import { COLOR } from './legend';
import type { VizTemplates } from '../core/types';

const BITS = 64;
const W = 760;

/** 单条 seed 的标签:取 hex 前 8 字符(完整 seed 在 tooltip 里) */
const shortSeed = (h: string) => (h.length > 8 ? h.slice(0, 8) + '…' : h);

export interface V3Opts { maxRows?: number; }

export function renderV3(
  dev: VizTemplates['terminals'][string], tid: string, o: V3Opts = {},
): SVGSVGElement {
  const maxRows = o.maxRows ?? 40;
  const seeds = Object.keys(dev.responses).sort();
  const shown = seeds.slice(0, maxRows);
  const total = seeds.length;

  const cellW = 8;
  const cellH = 13;
  const labW = 76;
  const matX = labW + 16;
  const matY = 46;
  const matW = BITS * cellW;
  const matH = shown.length * cellH;
  const maskY = matY + matH + 30;
  const H = maskY + 46;

  const svg = svgRoot(W, H);
  const title = el('text', { x: 16, y: 20, class: 'pl-title' }, svg);
  title.textContent = `终端 ${tid} · 模板响应位矩阵(每 seed 一条多数投票响应)`;
  const sub = el('text', { x: 16, y: 36, class: 'pl-sec-sub' }, svg);
  sub.textContent = `显示 ${shown.length} / ${total} 条 CRP · 位序 MSB 在左(列 1 = 位 63)`;
  if (shown.length < total) {
    const more = el('text', { x: matX + matW, y: 36, 'text-anchor': 'end', class: 'pl-sec-sub' }, svg);
    more.textContent = `另有 ${total - shown.length} 条未显示(受图高限制)`;
  }

  /* ---------- 位矩阵 ----------
   *
   * 0 位从 bg4 改成 bg2 + 发丝描边(D14)。原先 0 位用 bg4 —— 阶梯里**最亮**
   * 的一档,于是整张矩阵的图底是亮的、1 位是青的,「亮 = 0、青 = 1」这套读法
   * 和全页其余所有图相反(那里亮 = 有数据)。改后 0 位沉到 bg2 并镶一条发丝线,
   * 青色 1 位成为唯一的图形,与「暗底上只点亮有信息的东西」一致。 */
  shown.forEach((seed, row) => {
    const y = matY + row * cellH;
    const lab = el('text', { x: labW, y: y + 10, 'text-anchor': 'end', class: 'pl-rowlab mono' }, svg);
    lab.textContent = shortSeed(seed);
    const hex = dev.responses[seed].padStart(16, '0');
    for (let col = 0; col < BITS; col++) {
      const bit = bitAt(hex, col);
      const x = matX + col * cellW;
      el('rect', {
        x: x + 0.5, y: y + 0.5, width: cellW - 1, height: cellH - 1, rx: 1.5,
        fill: bit ? COLOR.comm : 'var(--bg2)',
        stroke: bit ? 'none' : 'var(--border)',
        'stroke-width': 1,
        opacity: bit ? .9 : 1,
      }, svg);
      const hit = el('rect', { x, y, width: cellW, height: cellH, class: 'pl-hit' }, svg);
      hit.dataset.tip = `seed 0x${seed}\n位 ${BITS - 1 - col} = ${bit}\n响应 ${hex}`;
      hit.dataset.hl = 'band';
    }
  });

  // 每 8 位的列标尺(位号从 63 递减到 0)
  for (let col = 0; col < BITS; col += 8) {
    const t = el('text', {
      x: matX + col * cellW + cellW / 2, y: matY - 6,
      'text-anchor': 'middle', class: 'pl-tick',
    }, svg);
    t.textContent = String(BITS - 1 - col);
  }

  /* ---------- 稳定掩码条 ---------- */
  const mask = dev.stability_mask.padEnd(BITS, '1');
  const ones = mask.split('').filter(c => c === '1').length;
  const mTitle = el('text', { x: 16, y: maskY - 8, class: 'pl-sec-title' }, svg);
  mTitle.textContent = `稳定掩码(64 位,稳定 ${ones}/${BITS})`;
  const mNote = el('text', {
    x: matX + matW, y: maskY - 8, 'text-anchor': 'end', class: 'pl-sec-sub',
  }, svg);
  mNote.textContent = '绿=稳定 · 琥珀斜纹=不稳定 · 判稳口径:翻位率 ≤10%(template_db.DEFAULT_FLIP_THRESHOLD)';

  /* 不稳定位加斜纹(D14 色觉冗余)。掩码条是 64 个 8×18 的窄格,绿/琥珀这一对
   * 在色觉障碍下会一起向黄绿偏移 —— 色板验证脚本给「状态三色」算的最小 CVD
   * ΔE 是 11.3(过线),但那是线性衰减的模型估计,而这条掩码只靠颜色区分
   * 「稳 / 不稳」两态、没有别的线索可用。给**不稳定**一侧加斜纹,等于把二值
   * 语义从色相搬到「有纹 / 无纹」上,同时顺带让黑白复印也能读 —— 掩码条是
   * 报告里最常被单独截出来用的一小块。 */
  /* 线宽/不透明度是**量出来的**不是估的:先写了 .55/1.8,把 pattern 抠出来贴到
   * 琥珀底上光栅化,全图最暗像素仍在 90 以上(琥珀亮度 166)—— 45° 细线经抗锯齿
   * 后绝大多数像素只是部分覆盖,实际读出来是一片中间调,等于没纹。改成 .72/2.2
   * 后最暗像素落到 60 以下,「有纹/无纹」才真正成为可读的二值。 */
  const unsteady = hatch(svg, 'v3-unsteady', { color: 'rgba(7,11,20,.72)', size: 5, width: 2.2 });
  for (let col = 0; col < BITS; col++) {
    const ok = mask[col] === '1';
    const x = matX + col * cellW;
    el('rect', {
      x: x + 0.5, y: maskY, width: cellW - 1, height: 18, rx: 2,
      fill: ok ? COLOR.pass : COLOR.amber,
      opacity: ok ? .85 : .95,
    }, svg);
    if (!ok) {
      el('rect', {
        x: x + 0.5, y: maskY, width: cellW - 1, height: 18, rx: 2,
        fill: unsteady,
      }, svg);
    }
    const hit = el('rect', { x, y: maskY, width: cellW, height: 18, class: 'pl-hit' }, svg);
    hit.dataset.tip = `位 ${BITS - 1 - col}:${ok ? '稳定' : '不稳定(斜纹标记)'}`;
    hit.dataset.hl = 'band';
  }

  const foot = el('text', { x: 16, y: maskY + 38, class: 'pl-sec-sub' }, svg);
  foot.textContent = '掩码 = 每 seed 多次测量的翻位率,再跨 seed 取平均 —— 全 1 不等于每个 CRP 都稳,逐 CRP 抖动见 V4。';

  return svg;
}

/** 第 col 列(MSB 起算)的位值:hex 是 MSB 在前的 16 字符大端表示 */
function bitAt(hex: string, col: number): number {
  const bit = BITS - 1 - col;
  const byteIdx = Math.floor(bit / 8);
  const byte = parseInt(hex.slice(byteIdx * 2, byteIdx * 2 + 2), 16);
  return (byte >> (bit % 8)) & 1;
}
