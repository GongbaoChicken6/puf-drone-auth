/* ============================================================
 * chart-svg tooltip —— 全局单例,事件委托
 *
 * 每张图各自 new 一个 tip 会带来两个问题:① 多图并排时可能同时浮出两个;
 * ② 导出前若忘了摘除,残留的 HTML 节点会让截图/布局出现幽灵框。
 * 故全页只留一个,挂在 body 上,靠 [data-tip] 委托 —— 图元重建时无需重新绑事件。
 *
 * 2026-10-15 UI 升级 R4(D14)在此加了**统一悬停高亮层**:命中框上写
 * data-hl="band|dot" 即可获得反白/画环反馈,由本模块在一个 svg 内惰性建
 * 一个 .pl-hl 组来承载。放在这里而不是各图自绘,理由是悬停反馈是全页同一种
 * 交互 —— 分散到七张图必然出现「有的反白有的不亮」的不一致。
 *
 * 高亮层是**临时节点**,绝不能进导出件:export.ts 在克隆时按 .pl-hl 清除。
 * 光靠 hideTooltip() 把 display 置 none 是不够的 —— inlineStyles 会把
 * fill/stroke 算成具体颜色内联下来,类名一摘,一个残留的实心色块就烙进
 * 导出的图里了(D13 那轮 border→rgba 的教训同一类:算出来的样式是会被
 * 序列化带走的)。
 * ============================================================ */

let tipEl: HTMLDivElement | null = null;

interface HlCtx {
  layer: SVGGElement;
  band: SVGRectElement;
  dot: SVGCircleElement;
}
const hlCache = new WeakMap<SVGSVGElement, HlCtx>();

function ensure(): HTMLDivElement {
  if (tipEl) return tipEl;
  const d = document.createElement('div');
  d.className = 'pl-tip';
  d.hidden = true;
  document.body.append(d);
  tipEl = d;
  return d;
}

/** 惰性建高亮层;一个 svg 一份,始终是 svg 的最后一个子节点(压在图元之上) */
function hlFor(svg: SVGSVGElement): HlCtx {
  const cached = hlCache.get(svg);
  if (cached) {
    // 图重建时 svg 内容是 replaceChildren 掉的,旧层会跟着消失 —— 需重新挂
    if (cached.layer.isConnected) return cached;
  }
  const layer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  layer.setAttribute('class', 'pl-hl');
  const band = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  band.setAttribute('class', 'pl-hoverband');
  band.setAttribute('rx', '2');
  const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
  dot.setAttribute('class', 'pl-hoverdot');
  layer.append(band, dot);
  svg.append(layer);
  const ctx = { layer, band, dot };
  hlCache.set(svg, ctx);
  return ctx;
}

function clearHover(): void {
  document.querySelectorAll<SVGGElement>('.pl-hl').forEach(g => {
    g.querySelector('.pl-hoverband')?.removeAttribute('x');
    g.querySelector('.pl-hoverdot')?.removeAttribute('cx');
  });
}

function paintHover(hit: Element): void {
  const svg = hit.closest('svg') as SVGSVGElement | null;
  if (!svg) return;
  const mode = hit.getAttribute('data-hl');
  const ctx = hlFor(svg);
  const box = (hit as SVGGraphicsElement).getBBox();

  if (mode === 'dot') {
    const r = Number(hit.getAttribute('data-hl-r') ?? 8);
    ctx.dot.setAttribute('cx', String(box.x + box.width / 2));
    ctx.dot.setAttribute('cy', String(box.y + box.height / 2));
    ctx.dot.setAttribute('r', String(r));
    ctx.band.removeAttribute('x');
  } else {
    ctx.band.setAttribute('x', String(box.x));
    ctx.band.setAttribute('y', String(box.y));
    ctx.band.setAttribute('width', String(box.width));
    ctx.band.setAttribute('height', String(box.height));
    ctx.dot.removeAttribute('cx');
  }
}

/** 在 root(通常是图容器)上委托:命中 .pl-hit[data-tip] 即浮出。 */
export function bindTooltips(root: HTMLElement): void {
  const tip = ensure();

  const move = (e: MouseEvent) => {
    const hit = (e.target as Element | null)?.closest?.('[data-tip]') as Element | null;
    if (!hit) { tip.hidden = true; clearHover(); return; }
    tip.textContent = hit.getAttribute('data-tip') ?? '';
    tip.hidden = false;
    paintHover(hit);
    // 先置可见再量尺寸,否则 offsetWidth 恒为 0,会贴着右边界溢出
    const pad = 14;
    const w = tip.offsetWidth;
    const h = tip.offsetHeight;
    let x = e.clientX + pad;
    let y = e.clientY + pad;
    if (x + w > window.innerWidth - 8) x = e.clientX - w - pad;
    if (y + h > window.innerHeight - 8) y = e.clientY - h - pad;
    tip.style.left = `${Math.max(4, x)}px`;
    tip.style.top = `${Math.max(4, y)}px`;
  };

  root.addEventListener('mousemove', move);
  root.addEventListener('mouseleave', () => { tip.hidden = true; clearHover(); });
  // 滚动/缩放时指针不再位于原图元上,留着 tip 会指向错位的旧数据
  window.addEventListener('scroll', () => { tip.hidden = true; clearHover(); }, { passive: true });
}

/** 导出前调用:确保没有 tooltip 混进画布/截屏 */
export function hideTooltip(): void {
  if (tipEl) tipEl.hidden = true;
  clearHover();
}
