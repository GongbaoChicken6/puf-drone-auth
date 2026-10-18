/* ============================================================
 * chart-svg 导出 —— SVG(矢量)/ PNG(2× 光栅),报告 §7.2
 *
 * 关键难点:**CSS 变量在序列化后就失效了**。页内图元用的是
 * fill:var(--green) 这类 class 驱动配色,一旦把 SVG 单独存成文件,
 * 没有 stylesheet 也没有 :root,颜色会全部塌成黑色 —— 导出的图等于废图。
 * 故导出前把 getComputedStyle 的结果**内联**到克隆体的每个节点上。
 *
 * 另一条:PNG 走 canvas.drawImage(svgImage)。blob: URL 与页面同源,
 * canvas 不会被污染,toDataURL 可用;若改用 <img src> 指向外链则会被
 * taint 到无法导出 —— 这也是本页禁 CDN 的又一处收益。
 * ============================================================ */
import { hideTooltip } from './tooltip';

/* 只内联「画出来能看见」的属性。全量拷贝会把 getComputedStyle 的
 * 数百个默认值塞进每个节点,导出的 SVG 从几十 kB 膨胀到几 MB。 */
const INLINE_PROPS = [
  'fill', 'fill-opacity', 'stroke', 'stroke-width', 'stroke-dasharray',
  'stroke-opacity', 'stroke-linecap', 'stroke-linejoin',
  'opacity', 'font-family', 'font-size', 'font-weight', 'font-style',
  'text-anchor', 'dominant-baseline', 'letter-spacing', 'shape-rendering',
] as const;

function inlineStyles(src: SVGSVGElement, dst: SVGSVGElement): void {
  const a = [src, ...Array.from(src.querySelectorAll('*'))];
  const b = [dst, ...Array.from(dst.querySelectorAll('*'))];
  for (let i = 0; i < a.length && i < b.length; i++) {
    const from = a[i] as Element;
    const to = b[i] as Element;
    const cs = getComputedStyle(from);
    let style = '';
    for (const p of INLINE_PROPS) {
      const v = cs.getPropertyValue(p);
      // 'none' 对 stroke/fill 是有效值(表示不描边),对 dasharray 也是;
      // 但把一整排默认 'none' 写进 style 只会让文件变胖,故除了 dasharray 一律跳过
      if (!v || (v === 'none' && p !== 'stroke-dasharray')) continue;
      style += `${p}:${v};`;
    }
    to.setAttribute('style', style);
    to.removeAttribute('class');   // class 已无用,留着会让人以为还依赖样式表
  }
}

/** 克隆 + 内联样式 + 铺一层不透明底色(PPT 里透明底会变成黑块) */
function serialize(svg: SVGSVGElement, bg = '#070b14'): string {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  /* 悬停高亮层必须在**内联样式之前**物理删除,不能只靠 hideTooltip() 改可见性:
   * 它是运行期临时节点,而 inlineStyles 会把它的 fill/stroke 算成具体颜色烙进
   * 克隆体;一旦类名被摘掉、可见性样式又没被内联,一个实心高亮块就会留在导出
   * 的图里。删除是唯一与调用时机无关的做法。 */
  clone.querySelectorAll('.pl-hl').forEach(n => n.remove());
  inlineStyles(svg, clone);
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  clone.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink');

  const vb = (clone.getAttribute('viewBox') ?? '0 0 760 360').split(/\s+/).map(Number);
  const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  rect.setAttribute('x', '0'); rect.setAttribute('y', '0');
  rect.setAttribute('width', String(vb[2])); rect.setAttribute('height', String(vb[3]));
  rect.setAttribute('fill', bg);
  clone.insertBefore(rect, clone.firstChild);

  return '<?xml version="1.0" encoding="UTF-8"?>\n'
    + new XMLSerializer().serializeToString(clone);
}

/** 文件名含**数据源与时间戳**(§7.2),便于答辩时追溯某张图是哪个口径出的 */
export function figName(chart: string, source: string, ext: string): string {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  return `puf-${chart}-${source}-${stamp}.${ext}`;
}

export function downloadSvg(svg: SVGSVGElement, chart: string, source: string): void {
  hideTooltip();
  const text = serialize(svg);
  const url = URL.createObjectURL(new Blob([text], { type: 'image/svg+xml;charset=utf-8' }));
  triggerDownload(url, figName(chart, source, 'svg'));
  window.setTimeout(() => URL.revokeObjectURL(url), 4000);
}

export async function downloadPng(
  svg: SVGSVGElement, chart: string, source: string, scale = 2,
): Promise<void> {
  hideTooltip();
  const vb = (svg.getAttribute('viewBox') ?? '0 0 760 360').split(/\s+/).map(Number);
  const w = vb[2] || 760;
  const h = vb[3] || 360;
  const bg = getComputedStyle(document.body).backgroundColor || '#070b14';

  const blob = new Blob([serialize(svg, bg)], { type: 'image/svg+xml;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  try {
    const img = new Image();
    img.width = w; img.height = h;
    await new Promise<void>((res, rej) => {
      img.onload = () => res();
      img.onerror = () => rej(new Error('SVG 光栅化失败(序列化结果不是合法 SVG?)'));
      img.src = url;
    });
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(w * scale);
    canvas.height = Math.round(h * scale);
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('2D 上下文不可用');
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    const out = canvas.toDataURL('image/png');
    triggerDownload(out, figName(chart, source, 'png'));
  } finally {
    URL.revokeObjectURL(url);
  }
}

function triggerDownload(href: string, name: string): void {
  const a = document.createElement('a');
  a.href = href;
  a.download = name;
  a.click();
}
