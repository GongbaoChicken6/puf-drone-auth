/* ============================================================
 * chart-svg 图卡外壳 —— 标题/真实性徽章/导出/注记 的统一收口(报告 §4.4/§7.2)
 *
 * 「真实性分级是第一公民」(§7.1 原话),所以徽章不是装饰:它由 grade 字段
 * **强制渲染**,任何图卡都不可能忘记挂。MOCK 卡另有 amber 虚线边框 + 行前缀,
 * 满足 §4.4 的三件套(角标 chip + 数据行前缀 + tooltip 说明替换条件)。
 * ============================================================ */
import { downloadPng, downloadSvg } from './export';

/* IMPORTED 是报告 §4.4 三态词汇(REAL-STATIC / REAL-LIVE / MOCK)之外的**第四个**
 * 取值,属于有意偏离并在交接 README 中声明:导入文件走的是「答辩前离线回放」,
 * 数据本身真实,但既不是本次运行实测(LIVE 不成立),也不是仓库静态文档(STATIC 不成立)。
 * 在两个词里挑一个来贴标签都会说谎 —— §4.4 立这条规矩的用意正是禁绝含糊,
 * 故宁可多一个准确的词。 */
export type Grade = 'REAL-LIVE' | 'REAL-STATIC' | 'REAL-LIVE(捕获后)' | 'IMPORTED' | 'MODEL' | 'MOCK';

const GRADE_CLS: Record<Grade, string> = {
  'REAL-LIVE': 'cyan',
  'REAL-LIVE(捕获后)': 'cyan',
  'REAL-STATIC': 'purple',
  'IMPORTED': 'blue',
  'MODEL': 'amber',
  'MOCK': 'mock',
};

const GRADE_TIP: Record<Grade, string> = {
  'REAL-LIVE': '本机 loopback 运行时实测数据,经桥接 REST/SSE 获取',
  'REAL-LIVE(捕获后)': '注册过程经桥接旁路捕获的真实多次测量;进程重启即清空,需重跑 S6 注册',
  'REAL-STATIC': '来自仓库内静态文件(设计文档/契约/代码常量),非运行时数据',
  'IMPORTED': '真实测量数据,但来自本地导入的 JSON 文件(离线回放),并非本次运行实测',
  'MODEL': '黄金模型(ROPairingPUF)以真实器件参数推演:算法与输入真实,但非上板实测',
  'MOCK': '占位数据,非实测;报告 §4.4 强制标注',
};

export interface FigureOpts {
  id: string;                 // v1..v7,用于导出文件名
  title: string;
  grade: Grade;
  /** 数据源名(出现在文件名与副标题),如 运行实测 / 内置样例 */
  source: string;
  subtitle?: string;
  mockReason?: string;        // MOCK 卡的占位原因
  mockReplace?: string;       // MOCK 卡的替换条件
}

export class Figure {
  readonly el: HTMLElement;
  readonly body: HTMLElement;
  readonly head: HTMLElement;
  private sub: HTMLElement;
  private noteEl: HTMLElement;
  private svg: SVGSVGElement | null = null;
  private sourceName: string;
  /** 构造时定下、之后只由 setGrade 改写 —— syncDesc 要把它一并刻进导出件 */
  private grade: Grade;
  /** MOCK 卡的占位原因/替换条件(§4.4 要求 tooltip 注明),随分级一起画进 chip */
  private readonly mockReason?: string;
  private readonly mockReplace?: string;

  constructor(o: FigureOpts) {
    this.sourceName = o.source;
    this.grade = o.grade;
    this.mockReason = o.mockReason;
    this.mockReplace = o.mockReplace;
    this.el = document.createElement('section');
    this.el.className = 'viz-fig card' + (o.grade === 'MOCK' ? ' fig-mock' : '');
    this.el.id = `fig-${o.id}`;

    this.head = document.createElement('div');
    this.head.className = 'fig-head';
    const h = document.createElement('h3');
    h.className = 'fig-title';
    h.textContent = o.title;
    const chip = document.createElement('span');
    chip.className = 'chip fig-grade';
    const spacer = document.createElement('span');
    spacer.className = 'fig-spacer';
    const exSvg = mkBtn('导出 SVG', '矢量导出(内联样式,脱离页面仍可见)', () => this.doExport('svg'));
    const exPng = mkBtn('导出 PNG 2×', '光栅导出,2 倍尺寸,对齐 report/figures 排版', () => void this.doExport('png'));
    this.head.append(h, chip, spacer, exSvg, exPng);
    this.renderGrade();

    this.sub = document.createElement('div');
    this.sub.className = 'fig-sub mono';
    this.sub.textContent = o.subtitle ?? '';

    this.body = document.createElement('div');
    this.body.className = 'fig-body';

    this.noteEl = document.createElement('div');
    this.noteEl.className = 'fig-note';
    this.noteEl.hidden = true;

    this.el.append(this.head, this.sub, this.body, this.noteEl);

    if (o.grade === 'MOCK') {
      this.setNote(`MOCK 占位:${o.mockReason ?? '—'} · 替换条件:${o.mockReplace ?? '—'}`);
    }
  }

  setSvg(svg: SVGSVGElement): void {
    this.svg = svg;
    this.body.replaceChildren(svg);
    this.syncDesc();
  }

  /**
   * 改分级。集中在这里而不是让调用方去摸 DOM —— 分级、配色、tooltip 与
   * `fig-mock` 边框是一件事(§4.4),散在两处就一定会出现「数据已是 MOCK、卡片
   * 还是青色无边框」这种半改状态,而那正是最容易被当成真数据截图的形态。
   */
  setGrade(g: Grade): void {
    this.grade = g;
    this.el.classList.toggle('fig-mock', g === 'MOCK');
    this.renderGrade();
  }

  private renderGrade(): void {
    const chip = this.head.querySelector<HTMLElement>('.fig-grade');
    if (!chip) return;
    chip.className = `chip ${GRADE_CLS[this.grade]} fig-grade`;
    chip.textContent = this.grade;
    chip.title = GRADE_TIP[this.grade]
      + (this.grade === 'MOCK' && this.mockReason ? `\n占位原因:${this.mockReason}` : '')
      + (this.grade === 'MOCK' && this.mockReplace ? `\n替换条件:${this.mockReplace}` : '');
    this.syncDesc();
  }

  setSubtitle(text: string): void { this.sub.textContent = text; this.syncDesc(); }

  setSource(name: string): void { this.sourceName = name; this.syncDesc(); }

  /** 注记行:口径说明、陈旧数字声明等。传空则隐藏。 */
  setNote(html: string): void {
    this.noteEl.hidden = !html;
    if (html) this.noteEl.innerHTML = html;
    this.syncDesc();
  }

  /**
   * 把副标题与注记**写进 SVG 自身**(`<desc>`),让导出的文件自带出处。
   *
   * 导出的图是最常被引用的那一份副本 —— 它会进报告、会发给组员,而 sub/noteEl
   * 都是 svg 的**兄弟节点**,根本不进 this.svg:不写这一步,一份「离线样本」导出去
   * 就只剩一条谱加几个轴标,采样时机当场丢失,而文件名里的时间戳是**导出时刻**
   * 而非采集时刻,正好会把人引到相反的方向。§9 要求每个数字可溯源,那就得包含
   * 离开页面的那一份。
   *
   * 取 noteEl.textContent 而非 innerHTML:注记里带 <b>/<span> 标签,而 <desc>
   * 是纯文本节点,塞进标签会被当字面量显示成乱码。
   */
  private syncDesc(): void {
    if (!this.svg) return;
    let desc = this.svg.querySelector('desc');
    if (!desc) {
      desc = document.createElementNS('http://www.w3.org/2000/svg', 'desc');
      this.svg.insertBefore(desc, this.svg.firstChild);
    }
    const parts = [this.grade, this.sub.textContent ?? '', this.noteEl.textContent ?? '']
      .map(s => s.replace(/\s+/g, ' ').trim())
      .filter(Boolean);
    desc.textContent = `${this.el.id} | ${parts.join(' | ')}`;
  }

  private async doExport(kind: 'svg' | 'png'): Promise<void> {
    if (!this.svg) return;
    const id = this.el.id.replace(/^fig-/, '');
    if (kind === 'svg') downloadSvg(this.svg, id, this.sourceName);
    else await downloadPng(this.svg, id, this.sourceName);
  }
}

function mkBtn(label: string, title: string, fn: () => void): HTMLButtonElement {
  const b = document.createElement('button');
  b.className = 'btn ghost fig-btn';
  b.textContent = label;
  b.title = title;
  b.addEventListener('click', fn);
  return b;
}
