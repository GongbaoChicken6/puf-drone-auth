/* ============================================================
 * viz.html 入口 —— 报告 §7 全量装配
 *
 * 页面结构(自上而下):
 *   页头(标题 + 数据源三态选择器 + 数据源徽章)
 *   指标卡 ×4(逐数溯源)
 *   阈值控制条(滑杆联动 V1 分割线 / V2 工作点 / 混淆矩阵)
 *   V1 V2 / V3 V4 / V5 V6 V7
 *
 * 数据源三态(§7.2)贯穿全页:
 *   live   运行实测 —— 经桥接 REST 现取现算
 *   file   导入文件 —— 答辩前离线回放(读一份 JSON,不联网)
 *   sample 内置样例 —— 显式 MOCK(§4.4 三件套齐全)
 * 切换即整体重绘,且**导出文件名携带数据源**(§7.2),避免不同口径的图混淆。
 * ============================================================ */
import './styles/tokens.css';
import './styles/base.css';
import './styles/viz.css';

import { api } from './core/api';
import { mockHdSeries, mockVizBundle } from './core/mock';
import type { HdSeries, VizMeasurements, VizTemplates } from './core/types';

import { Figure, type Grade } from './chart-svg/figure';
import { Metrics } from './chart-svg/metrics';
import { MOCK_SPECS, renderMock } from './chart-svg/placeholder';
import { bindTooltips } from './chart-svg/tooltip';
import { mean, renderV1 } from './chart-svg/v1-hist';
import { computeRoc, renderV2 } from './chart-svg/v2-roc';
import { renderV3 } from './chart-svg/v3-matrix';
import { computeJitter, renderV4 } from './chart-svg/v4-jitter';
import { renderV6 } from './chart-svg/v6-reliability';
import { renderV7 } from './chart-svg/v7-ml';

/* ============================================================
 * TAU 常量 —— 逐字取自组员 threshold.py,已实读核对(报告 §9 登记为 REAL-STATIC 代码)
 *
 * 为什么在 viz 页里可以写死而 console 页不行:console 的每个判决都伴随一次
 * verdict 事件,桥接会把**本轮缩放后**的 scaled_pass/scaled_reject 随事件下发,
 * 前端据实显示即可;viz 页不跑认证、收不到任何 verdict,而阈值的**来源仍是代码常量**,
 * 故在此显式声明并标注出处,不假装它是运行期数据。
 *   TAU_PASS   = 6    → hd <= 6 判 PASS
 *   TAU_REJECT = 16   → hd >= 16 判 REJECT;7..15 为灰区(加测)
 * ============================================================ */
const TAU_PASS = 6;
const TAU_REJECT = 16;

/* ============================================================
 * 数据源与状态
 * ============================================================ */
type Src = 'live' | 'file' | 'sample';

interface Bundle {
  hd: HdSeries | null;
  templates: VizTemplates | null;
  measurements: VizMeasurements | null;
  /** 数据源自述(桥接的 note 字段、导入文件名、MOCK 声明) */
  notes: string[];
  /** 现成可选的终端列表(V3/V4 选择器) */
  tids: string[];
  tid: string | null;
}

const EMPTY: Bundle = { hd: null, templates: null, measurements: null, notes: [], tids: [], tid: null };

let src: Src = 'live';
let bundle: Bundle = { ...EMPTY };
let tau = TAU_PASS;              // 接受上界:HD ≤ τ 判接受(decide() 口径)
let loading = false;

const SRC_LABEL: Record<Src, string> = {
  live: '运行实测', file: '导入文件', sample: '内置样例',
};
const SRC_GRADE: Record<Src, Grade> = {
  live: 'REAL-LIVE', file: 'IMPORTED', sample: 'MOCK',
};
/** 导出文件名里的数据源标记(§7.2 文件名含数据源) */
function srcTag(): string {
  return src === 'live' ? 'live' : src === 'sample' ? 'mock' : 'imported';
}

/* ============================================================
 * 页面骨架
 * ============================================================ */
const app = document.getElementById('app')!;
const page = document.createElement('div');
page.className = 'viz-page';
app.replaceWith(page);

/* ---------- 页头 ---------- */
const head = document.createElement('header');
head.className = 'viz-head';
head.innerHTML = `
  <div>
    <div class="vh-title">PUF 无人机认证 · 数据可视化</div>
    <div class="vh-sub">报告 §7 · V1–V7;每图可导出 SVG / PNG(2×)</div>
  </div>
  <span class="vh-spacer"></span>
  <div class="vh-group">
    <span class="vh-label">数据源</span>
    <div class="src-seg" id="src-seg" role="group" aria-label="数据源">
      <button data-src="live" class="on" aria-pressed="true" title="经桥接 REST 现取现算(需 web_bridge.py 在 127.0.0.1:8642 运行)">运行实测</button>
      <button data-src="file" aria-pressed="false" title="读一份本地 JSON 离线回放(答辩现场无桥接时的兜底)">导入文件</button>
      <button data-src="sample" aria-pressed="false" title="页面内置的固定样例,显式 MOCK(§4.4)">内置样例 MOCK</button>
    </div>
  </div>
  <div class="vh-group" id="tid-group">
    <span class="vh-label">终端</span>
    <select class="btn ghost" id="tid-sel" style="font-size:12px;padding:4px 8px"></select>
  </div>
  <button class="btn ghost" id="refresh" title="运行实测:强制现场重采(?fresh=1);导入文件:重选文件">刷新</button>
  <span class="viz-status" id="status">就绪</span>
  <input type="file" id="file-in" accept=".json,application/json" hidden />`;

const seg = head.querySelector<HTMLElement>('#src-seg')!;
const tidSel = head.querySelector<HTMLSelectElement>('#tid-sel')!;
const tidGroup = head.querySelector<HTMLElement>('#tid-group')!;
const statusEl = head.querySelector<HTMLElement>('#status')!;
const fileIn = head.querySelector<HTMLInputElement>('#file-in')!;
const refreshBtn = head.querySelector<HTMLButtonElement>('#refresh')!;
page.append(head);

/* ---------- 指标卡 ---------- */
const metrics = new Metrics();
page.append(metrics.el);

/* ---------- 阈值控制条 ---------- */
const tauBar = document.createElement('div');
tauBar.className = 'viz-tau';
tauBar.innerHTML = `
  <span class="vt-title">阈值 τ</span>
  <div class="vt-range">
    <input type="range" id="tau" min="0" max="63" step="1" value="${TAU_PASS}"
      aria-label="接受上界 τ(HD ≤ τ 判接受)"
      title="接受上界:HD ≤ τ 判接受。与 threshold.py decide() 同向(含等号)" />
    <span class="vt-val mono" id="tau-val">τ = ${TAU_PASS}</span>
  </div>
  <div class="vt-quick">
    <button class="btn ghost" data-tau="${TAU_PASS}">TAU_PASS 6</button>
    <button class="btn ghost" data-tau="${TAU_REJECT - 1}">灰区上沿 15</button>
    <button class="btn ghost" data-tau="32">随机猜测 32</button>
  </div>
  <div class="vt-note">
    <b>滑杆联动</b>:V1 的接受上界分割线 · V2 的 ROC 工作点与混淆矩阵四数。
    <b>图内直拖</b>:在 V1 绘图区或 V2 曲线附近<b>按住水平拖动</b>同样改 τ,松手后全图联动。
    <b>灰区</b>:τ ∈ 7–15 时协议既不判 PASS 也不判 REJECT,而是加测 EXTRA_CHALLENGE ——
    该区间的工作点在图上有琥珀色提示,不应作为最终门限。
    <b>口径</b>:TAU_PASS=${TAU_PASS} / TAU_REJECT=${TAU_REJECT} 源自 threshold.py 代码常量(实读核对)。
  </div>`;
const tauInput = tauBar.querySelector<HTMLInputElement>('#tau')!;
const tauVal = tauBar.querySelector<HTMLElement>('#tau-val')!;
page.append(tauBar);

/* ---------- 图卡 ---------- */
const grid = document.createElement('div');
grid.className = 'viz-grid';
page.append(grid);

const figV1 = new Figure({
  id: 'v1', title: 'V1 · HD 分布(同设备 vs 跨设备)', grade: 'REAL-LIVE',
  source: SRC_LABEL.live,
  subtitle: '双系列直方图 · 量程固定 0–64(HD 是 64 位响应上的协议量纲)',
});
const figV2 = new Figure({
  id: 'v2', title: 'V2 · ROC / EER(阈值扫掠)', grade: 'REAL-LIVE',
  source: SRC_LABEL.live,
  subtitle: '由 V1 两组分布前端计算 · 判决口径逐字对齐 threshold.py decide()',
});
const figV3 = new Figure({
  id: 'v3', title: 'V3 · 模板响应位矩阵 + 稳定掩码条', grade: 'REAL-LIVE',
  source: SRC_LABEL.live,
  subtitle: 'templates.json 的多数投票响应 + .stability.json sidecar 掩码',
});
const figV4 = new Figure({
  id: 'v4', title: 'V4 · 注册测量抖动(每 CRP 多次测量)', grade: 'REAL-LIVE(捕获后)',
  source: SRC_LABEL.live,
  subtitle: '桥接旁路捕获原始重复测量 · 每 CRP 一点集,非箱线(3 样本画箱线是统计学噪声)',
});
const figV5 = new Figure({
  id: 'v5', title: MOCK_SPECS.v5.title, grade: 'MOCK', source: SRC_LABEL.sample,
  mockReason: '上板 W1 阶段的 VIO 频率读数尚未产生(data/w1_readings 现为空目录)',
  mockReplace: MOCK_SPECS.v5.replace,
});
const figV6 = new Figure({
  id: 'v6', title: MOCK_SPECS.v6.title, grade: 'MOCK', source: SRC_LABEL.sample,
  mockReason: '温度-可靠度实验属上板实验,未编码',
  mockReplace: MOCK_SPECS.v6.replace,
});
const figV7 = new Figure({
  id: 'v7', title: MOCK_SPECS.v7.title, grade: 'MOCK', source: SRC_LABEL.sample,
  mockReason: 'docs/project_design.md §W4 的两组攻击实验未编码',
  mockReplace: MOCK_SPECS.v7.replace,
});

figV1.el.classList.add('wide');
grid.append(figV1.el, figV2.el, figV3.el, figV4.el, figV5.el, figV6.el, figV7.el);

/* V5–V7 是静态占位,只渲染一次(MOCK 声明不随数据源变化) */
figV5.setSvg(renderMock(MOCK_SPECS.v5));
figV6.setSvg(renderMock(MOCK_SPECS.v6));
figV7.setSvg(renderMock(MOCK_SPECS.v7));
figV5.setNote(`MOCK 占位:${MOCK_SPECS.v5.replace}。**本图不含任何具体数值** —— 占位图出现数字,哪怕带 MOCK 前缀,也会在快速翻阅时被当成结论。`);
figV6.setNote(`MOCK 占位:${MOCK_SPECS.v6.replace}。坐标轴量纲已按目标实验定稿,数据落地即可直接替换。`);
figV7.setNote(`MOCK 占位:${MOCK_SPECS.v7.replace}。实验 A(合成 Arbiter 基线)/ 实验 B(自家 RO 排序重构)两条曲线将并列呈现。`);

bindTooltips(grid);

/* ============================================================
 * 渲染
 * ============================================================ */
function setStatus(text: string, kind: '' | 'ok' | 'err' = ''): void {
  statusEl.textContent = text;
  statusEl.className = 'viz-status' + (kind ? ' ' + kind : '');
}

function renderTidSelect(): void {
  tidGroup.hidden = src === 'sample';
  const want = bundle.tid ?? (bundle.tids[0] ?? '');
  tidSel.replaceChildren(...bundle.tids.map(t => {
    const o = document.createElement('option');
    o.value = t;
    o.textContent = `tid ${t}`;
    return o;
  }));
  if (want) tidSel.value = want;
  tidGroup.hidden = bundle.tids.length === 0;
}

/** 把当前 bundle 铺到各图卡上。数据源标签/分级也随之刷新(§4.4)。 */
function renderAll(): void {
  const label = src === 'sample' ? '内置样例 MOCK' : SRC_LABEL[src];
  const grade = SRC_GRADE[src];

  /* ---- V1 / V2:同一份 HD 双系列 ---- */
  const hd = bundle.hd;
  if (hd && hd.intra.length && hd.inter.length) {
    /* V1 的溯源注记。SAMPLE 与 LIVE **都是真测量** —— 报告 §9 把「采样脚本产物」
     * 与「桥接事件流」一并登记为 REAL-LIVE,故分级不动(这里刻意不敢自创
     * REAL-STATIC:§4.4 把它定义为「溯源静态文件」,指 docs/ 里那些引用的文档数字,
     * 用它标一份实测量出来的谱属于误用术语)。两者差别只在「何时算的」,而答辩现场
     * 被问「这数什么时候跑的」要能当场答出来,故摆在副标题上而不是埋进小字。 */
    /* 只在「运行实测」下加这句:它是**桥接**对这份 HD 的产出方式的交代。
     * 内置样例与导入文件各有自己的 label,再挂一句「桥接 MOCK」会把页面自己
     * 编的数说成桥接给的 —— 溯源的错法比没有溯源更坏。 */
    const prov = src !== 'live' ? ''
      : hd.source === 'SAMPLE' ? '离线样本'
        : hd.source === 'LIVE' ? '本次现算'
          : hd.source === 'MOCK' ? '桥接 MOCK(非实测)' : '';
    figV1.setSource(srcTag());
    figV1.setSubtitle(`${label} · 同设备 ${hd.intra.length} 条 / 跨设备 ${hd.inter.length} 条`
      + (prov ? ` · ${prov}` : ''));
    figV1.setSvg(renderV1(hd, {
      tau, tauPass: TAU_PASS, tauReject: TAU_REJECT,
      onTauPick: (t, phase) => tauFromChart(t, phase),
    }));

    const roc = computeRoc(hd, tau, { tauPass: TAU_PASS, tauReject: TAU_REJECT });
    figV2.setSource(srcTag());
    figV2.setSubtitle(`${label} · τ 扫掠 0–64 · EER=${(roc.eer * 100).toFixed(2)}%`);
    figV2.setSvg(renderV2(roc, {
      tau, tauPass: TAU_PASS, tauReject: TAU_REJECT,
      onTauPick: (t, phase) => tauFromChart(t, phase),
    }));

    /* 「这图里的数是伪造的」有两种来源,必须合成一个判据:页面自己选了内置样例,
     * 或桥接跑在 --mock(此时 URL 是 /api/*、src 仍是 live,但一个真数字都没有)。
     * 只看 src 的话,后一种会配上「loopback 仿真理想性的直接体现」的图注 —— 把
     * 一句完全是编的分离度说成实测结论(§4.4 要防的就是这一条)。 */
    const hdMock = hd.source === 'MOCK' || src === 'sample';
    const gap = Math.min(...hd.inter) - Math.max(...hd.intra);
    figV1.setNote(
      `同设备 μ=${mean(hd.intra).toFixed(2)} bit、最大 ${Math.max(...hd.intra)};`
      + `跨设备 μ=${mean(hd.inter).toFixed(2)} bit、最小 ${Math.min(...hd.inter)}。`
      + (gap > 0
        ? ` <b>两分布完全分离</b>(间隔 ${gap} bit),故 EER=0.00%。`
          /* 分离的成因随数据源不同,不能一律说成 loopback 理想性 ——
           * MOCK 的图注里出现「loopback 仿真」会让人以为这张图是桥接跑出来的。 */
          + (hdMock
            ? ' <span class="warn">本图为 MOCK 数据(桥接 --mock 或页面内置样例),'
              + '分离度是构造出来的</span>,仅用于演示图形形制,不可作为任何结论的依据。'
            : src === 'live'
              ? ' 这是 loopback 仿真理想性的直接体现,<span class="warn">不代表真实器件</span>:'
                + '真实 RO-PUF 的类内分布会更宽,答辩时以实测为准。'
              : ' 分离度取决于导入数据的来源与器件状态,请自行确认该文件的采集条件。')
        : ` 两分布存在重叠(gap=${gap}),EER 即为重叠区的代价。`)
      /* 桥接自述的采集条件(采样时间/tid/种子数,或空序列的原因)接在图注末尾:
       * 它是唯一能回答「这份谱什么时候、在哪台器件上量的」的话。 */
      + (hd.note ? `<br><span class="vh-dim">${hd.note}</span>` : ''));

    figV2.setNote(
      `接受 ⇔ <b>HD ≤ τ</b>(含等号,与 threshold.py <span class="mono">decide()</span> 同向)。`
      + ` 绿点 TAU_PASS=${TAU_PASS}、红圈灰区上沿=${TAU_REJECT - 1}(HD≥${TAU_REJECT} 即 REJECT)。`
      + ` τ∈${TAU_PASS + 1}–${TAU_REJECT - 1} 为灰区:协议加测 EXTRA_CHALLENGE 而非直接判决,`
      + ` 故该段曲线用琥珀虚线重描,不是可选工作点。`);
  } else {
    figV1.setSvg(emptySvg('V1', bundle));
    figV2.setSvg(emptySvg('V2', bundle));
    figV1.setNote(gapNote(bundle));
    figV2.setNote(gapNote(bundle));
  }

  /* ---- V3 ---- */
  const t = bundle.tid;
  const dev = t ? bundle.templates?.terminals[t] ?? null : null;
  if (dev && t) {
    const n = Object.keys(dev.responses).length;
    figV3.setSource(srcTag());
    figV3.setSubtitle(`${label} · 终端 ${t} · ${n} 条 CRP · 掩码 ${dev.stability_mask.slice(0, 12)}…`);
    figV3.setSvg(renderV3(dev, t, { maxRows: 40 }));
    const ones = dev.stability_mask.split('').filter(c => c === '1').length;
    const allStable = ones === 64;
    figV3.setNote(
      `掩码 ${ones}/64 判稳(翻位率 ≤10%,template_db.DEFAULT_FLIP_THRESHOLD)。`
      + (allStable
        ? ` <b>全 1 不等于每个 CRP 都稳</b>:该口径是「每 seed 求翻位率 → 跨 ${n} 个 seed 取平均」,`
          + `少数 CRP 上的翻位会被平均掉。逐 CRP 的真实抖动见 V4 —— 两张图不矛盾,是同一现象的两种投影。`
        : ''));
  } else {
    figV3.setSvg(emptySvg('V3', bundle));
    figV3.setNote(gapNote(bundle));
  }

  /* ---- V4 ---- */
  const m = bundle.measurements;
  if (m && m.captured && m.series.length && dev) {
    const st = computeJitter(m, dev.responses);
    figV4.setSource(srcTag());
    figV4.setSubtitle(`${label} · ${st.crps.length} 个 CRP × ${st.rounds} 次测量 = ${st.all.length} 个样本`);
    figV4.setSvg(renderV4(st, { expectMean: 1.3 }));
    figV4.setNote(
      `${src === 'live' ? '实测' : src === 'sample' ? 'MOCK 样例' : '导入数据'}抖动均值 `
      + `<b>${st.mean.toFixed(2)} bit / 64</b>,最大 ${st.peak} bit;`
      + ` 报告 §9 的注释口径为「噪声期望约 1.3bit/64bit」,两者同量纲。`
      + ` 另有 <b>${st.unstablePositions}/64</b> 个位位置曾在某个 CRP 上翻过 —— `
      + `<span class="warn">这正是 V3 掩码平均后看不见的部分</span>。`
      + (st.missing ? ` 有 ${st.missing} 个 seed 不在当前模板中(数据不一致,请检查)。` : '')
      + (src === 'live' ? ` 捕获仅存内存:桥接进程重启后需重跑 S6 注册。` : ''));
  } else {
    figV4.setSvg(emptySvg('V4', bundle));
    const note = m?.note
      ?? `本次进程尚未捕获注册测量。V4 的数据来自桥接在 <span class="mono">enroll_device</span> 期间`
        + ` 旁路包装 <span class="mono">transport.respond</span> 的原始重复测量 —— `
        + `请先在 console 页跑一次 <b>S6 注册</b>(左栏「注册」按钮),再回本页刷新。`;
    figV4.setNote(note);
  }

  /* ---- 分级徽章(V5–V7 恒为 MOCK,不动) ----
   * grade 的兜底来自页面自己的数据源选择,但**以数据自述为优先**:桥接 --mock
   * 模式下 src 仍是 'live',只信它会把三张伪造的图全部标成 REAL-LIVE。
   * (页面内置样例那一态不必在此重判 —— SRC_GRADE.sample 本就是 MOCK。) */
  const hdGrade = bundle.hd?.source === 'MOCK' ? 'MOCK' : grade;
  for (const f of [figV1, figV2]) setGrade(f, hdGrade);
  setGrade(figV3, bundle.templates?.source === 'MOCK' ? 'MOCK' : grade);
  /* V4 的分级与其余图卡不同源:它的数据只可能来自「本次进程的注册捕获」
   * (live)或外部文件/样例。故不能直接套 SRC_GRADE —— 否则导入态会被标成
   * 「REAL-LIVE(捕获后)」,而那个限定语承诺的是「本进程刚抓的」。 */
  setGrade(figV4,
    bundle.measurements?.source === 'MOCK' ? 'MOCK'
      : src === 'live' ? 'REAL-LIVE(捕获后)' : grade);
  renderTidSelect();
}

/* 分级与配色、tooltip、MOCK 边框是一件事,统一由 Figure.setGrade 落地 ——
 * 本页只负责判断「这份数据该是什么级」。 */
function setGrade(f: Figure, g: Grade): void { f.setGrade(g); }

/** 数据缺失时的占位图(不是 MOCK —— 是「本条数据源没给」,两者必须区分开) */
function emptySvg(id: string, b: Bundle): SVGSVGElement {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 760 300');
  svg.setAttribute('width', '760');
  svg.setAttribute('height', '300');
  const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  t.setAttribute('x', '380');
  t.setAttribute('y', '140');
  t.setAttribute('text-anchor', 'middle');
  t.setAttribute('class', 'pl-sec-sub');
  t.textContent = `${id}:当前数据源未提供所需数据`;
  const t2 = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  t2.setAttribute('x', '380');
  t2.setAttribute('y', '162');
  t2.setAttribute('text-anchor', 'middle');
  t2.setAttribute('class', 'pl-sec-sub');
  t2.textContent = b.notes[0] ?? '切换数据源或点击刷新重试';
  svg.append(t, t2);
  return svg;
}

function gapNote(b: Bundle): string {
  if (b.notes.length) return b.notes.join(' · ');
  return '当前数据源未提供数据。';
}

/* ============================================================
 * 数据源装载
 * ============================================================ */
async function loadLive(fresh = false): Promise<Bundle> {
  const notes: string[] = [];
  const tpl = await api.getVizTemplates();
  const tids = Object.keys(tpl.terminals).sort((a, b) => Number(a) - Number(b));
  const tid = bundle.tid && tids.includes(bundle.tid) ? bundle.tid : (tids[0] ?? null);

  // /api/viz/hd 缺省**只读** tools/sample_hd.py 的落盘样本,不跑采样 —— 首屏因此很快;
  // 现场重算代价是 200 个种子 × 双系列 × Speck 复算,只在「刷新」按钮(即 fresh=true)
  // 或样本已失效时才发生。故这里单独包一层错误处理:模板拿到而 HD 拿不到时,
  // V3/V4 仍应可用,不该整页失败。
  let hd: HdSeries | null = null;
  try {
    hd = await api.getHd(fresh);
    if (!hd.intra.length) {
      notes.push('桥接返回的 HD 序列为空 —— 终端尚未注册?先在 console 页跑 S1 或 S6。');
      hd = null;
    }
  } catch (e) {
    notes.push(`GET /api/viz/hd 失败:${msg(e)}(V1/V2 不可用,其余图不受影响)`);
  }

  let meas: VizMeasurements | null = null;
  if (tid != null) {
    try {
      meas = await api.getMeasurements(Number(tid));
      if (!meas.captured) notes.push(meas.note ?? '尚未捕获重复测量');
    } catch (e) {
      notes.push(`GET /api/viz/measurements 失败:${msg(e)}`);
    }
  }

  return { hd, templates: tpl, measurements: meas, notes, tids, tid };
}

function loadSample(): Bundle {
  const b = mockVizBundle();
  return {
    hd: mockHdSeries(),
    templates: b.templates,
    measurements: b.measurements,
    notes: [],
    tids: Object.keys(b.templates.terminals),
    tid: b.tid,
  };
}

/** 导入文件:接受三种形状的任意组合(整包 / 裸 HdSeries / 裸 templates) */
function normalizeImport(raw: unknown): Bundle {
  const o = raw as Record<string, unknown>;
  const hd = pickHd(o.hd ?? (Array.isArray(o.intra) ? o : null));
  const templates = pickTemplates(o.templates ?? (o.terminals ? o : null));
  const measurements = pickMeasurements(o.measurements ?? null);
  const notes: string[] = [];
  if (!hd) notes.push('文件中没有可识别的 HD 双系列({intra:[],inter:[]})');
  if (!templates) notes.push('文件中没有可识别的模板({terminals:{tid:{responses,mask}}})');
  if (!measurements) notes.push('文件中没有可识别的重复测量({series:[{seed,samples}]})');
  const tids = templates ? Object.keys(templates.terminals) : [];
  return {
    hd, templates, measurements, notes,
    tids,
    tid: tids[0] ?? (measurements?.terminal_id != null ? String(measurements.terminal_id) : null),
  };
}

const isNumArr = (v: unknown): v is number[] =>
  Array.isArray(v) && v.every(x => typeof x === 'number');

function pickHd(v: unknown): HdSeries | null {
  const o = v as { intra?: unknown; inter?: unknown } | null;
  if (!o || !isNumArr(o.intra) || !isNumArr(o.inter)) return null;
  return { intra: o.intra, inter: o.inter };
}

function pickTemplates(v: unknown): VizTemplates | null {
  const o = v as VizTemplates | null;
  if (!o || typeof o !== 'object' || !o.terminals || typeof o.terminals !== 'object') return null;
  const clean: VizTemplates['terminals'] = {};
  for (const [tid, dev] of Object.entries(o.terminals)) {
    if (!dev || typeof dev.responses !== 'object') continue;
    clean[tid] = {
      responses: dev.responses ?? {},
      stability_mask: typeof dev.stability_mask === 'string' ? dev.stability_mask : '1'.repeat(64),
    };
  }
  return Object.keys(clean).length ? { terminals: clean } : null;
}

function pickMeasurements(v: unknown): VizMeasurements | null {
  const o = v as VizMeasurements | null;
  if (!o || !Array.isArray(o.series)) return null;
  const series = o.series.filter(s => s && typeof s.seed === 'string' && Array.isArray(s.samples));
  if (!series.length) return null;
  return { terminal_id: o.terminal_id ?? null, captured: true, series, note: o.note };
}

async function applySource(next: Src, file?: File, fresh = false): Promise<void> {
  src = next;
  seg.querySelectorAll<HTMLButtonElement>('button').forEach(b => {
    const on = b.dataset.src === next;
    b.classList.toggle('on', on);
    // 三态选择器是一组互斥选项,「当前选中哪一个」此前只有颜色在说 ——
    // 色觉障碍与读屏用户都拿不到。aria-pressed 与 .on 同源,不会各自漂移。
    b.setAttribute('aria-pressed', String(on));
  });
  loading = true;
  setStatus(next === 'live'
    ? (fresh ? '现场重采中…(200 个种子 × 双系列,约数秒)' : '拉取中…')
    : '装载中…');
  try {
    if (next === 'sample') {
      bundle = loadSample();
      setStatus('内置样例(显式 MOCK)', 'ok');
    } else if (next === 'live') {
      bundle = await loadLive(fresh);
      setStatus(`运行实测 · ${bundle.tids.length} 个终端`, bundle.notes.length ? '' : 'ok');
    } else if (file) {
      const text = await file.text();
      bundle = normalizeImport(JSON.parse(text));
      bundle.notes.unshift(`导入文件:${file.name}`);
      const usable = !!(bundle.hd || bundle.templates || bundle.measurements);
      setStatus(
        usable ? `导入文件 · ${file.name}` : `导入文件不可用 · ${file.name}(三张图所需数据一个都没识别到)`,
        usable ? 'ok' : 'err');
    }
  } catch (e) {
    bundle = { ...EMPTY };
    setStatus(`装载失败:${msg(e)}`, 'err');
    bundle.notes.push(`数据源装载失败:${msg(e)}`);
  } finally {
    loading = false;
  }
  renderAll();
}

function msg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/* ============================================================
 * 交互
 * ============================================================ */
seg.addEventListener('click', (e) => {
  const b = (e.target as HTMLElement).closest<HTMLButtonElement>('button[data-src]');
  if (!b || loading) return;
  const next = b.dataset.src as Src;
  if (next === 'file') { fileIn.click(); return; }
  // P3(按钮审计 N7b):tid 选择只对「运行实测」有意义,sample/file 态下收起,
  // 免得一个不起作用的控件留在页面上(实测与静态判据一致化)。
  tidGroup.hidden = next !== 'live';
  void applySource(next);
});

fileIn.addEventListener('change', () => {
  const f = fileIn.files?.[0];
  if (f) void applySource('file', f);
  fileIn.value = '';       // 允许连续导入同一个文件
});

refreshBtn.addEventListener('click', () => {
  if (loading) return;              // P3(按钮审计 N6):现场重采期间防叠发
  if (src === 'file') { fileIn.click(); return; }
  // 运行实测下「刷新」= 现场重采(带 ?fresh=1):否则桥接缺省读落盘样本,按钮点了
  // 也只会拿回同一串数,而用户以为「刷新过了」——一个不会报错的假动作。
  // 内置样例是一份确定性伪随机(seed 写死),重取本就同值,故 fresh 无意义。
  void applySource(src, undefined, src === 'live');
});

tauInput.addEventListener('input', () => {
  tau = Number(tauInput.value);
  paintTauVal();
  renderAll();
});

/** τ 读数统一收口:滑杆 input、V1/V2 图内拖拽、快捷档按钮走同一份画法 */
function paintTauVal(): void {
  const gray = tau > TAU_PASS && tau < TAU_REJECT;
  tauVal.textContent = `τ = ${tau}` + (gray ? '(灰区)' : '');
  tauVal.style.color = gray ? 'var(--amber)' : 'var(--cyan)';
  // 滑杆自身的读数是数字,「灰区」这层语义只在视觉上;读屏要能听到同样的判断
  tauInput.setAttribute('aria-valuetext', `τ = ${tau}` + (gray ? ',灰区,协议将加测' : ''));
}

/* 图内拖 τ(R7):move 阶段只更新读数不重绘(图表自身的 τ 线/工作点已就地平移,
 * 全页 renderAll 会销毁 svg、掐断 pointer capture);end 走滑杆同一条提交路径。 */
function tauFromChart(t: number, phase: 'move' | 'end'): void {
  tau = t;
  tauInput.value = String(t);
  paintTauVal();
  if (phase === 'end') tauInput.dispatchEvent(new Event('input'));
}

tauBar.querySelectorAll<HTMLButtonElement>('button[data-tau]').forEach(b => {
  b.addEventListener('click', () => {
    tauInput.value = b.dataset.tau!;
    tauInput.dispatchEvent(new Event('input'));
  });
});

/* 换终端:模板即刻可用,但重复测量需按 tid 重取,故走一次完整装载 */
tidSel.addEventListener('change', async () => {
  bundle.tid = tidSel.value;
  if (src === 'live') {
    try {
      bundle.measurements = await api.getMeasurements(Number(tidSel.value));
      if (bundle.measurements && !bundle.measurements.captured) {
        bundle.notes = [bundle.measurements.note ?? '尚未捕获重复测量'];
      } else {
        bundle.notes = [];
      }
    } catch (e) {
      bundle.measurements = null;
      bundle.notes = [`GET /api/viz/measurements 失败:${msg(e)}`];
    }
  } else {
    bundle.measurements = null;
  }
  renderAll();
});

/* ============================================================
 * 启动
 *
 * 默认「运行实测」。桥接不可达时**不静默**跳到 MOCK —— 那会让页面看起来
 * 有数据而其实是样例(§4.4 的初衷正是禁绝这种含糊)。故保持 live 并把
 * 错误明写到状态条与图卡注记里,由人决定是否切样例。
 * ============================================================ */
void applySource('live');

/* ============================================================
 * B1/B2:V6/V7 独立装载 —— 与 src 三态无关(MODEL/STATIC 数据不随终端数据源
 * 变化,刷新按钮也不重触发:模型推演与实验产物是「另一个数据宇宙」)。
 * 失败或 --mock(source=MOCK)时维持占位卡与 MOCK 徽章,不冒充。
 * ============================================================ */
async function loadV67(): Promise<void> {
  try {
    const rel = await api.getReliability();
    if (rel.source === 'MODEL' && rel.points.length) {
      figV6.setGrade('MODEL');
      figV6.setSource('黄金模型');
      const pm = rel.params;
      figV6.setSubtitle(pm
        ? 'ROPairingPUF 推演 · tid ' + pm.terminal_id + ' · ' + pm.n_seeds + ' 种子 · jitter ' + pm.jitter_pct + '%'
        : 'ROPairingPUF 推演');
      figV6.setSvg(renderV6(rel, TAU_PASS, TAU_REJECT));
      figV6.setNote((rel.note ?? '')
        + '<br>缩放因子 s 作用于 16 环频率(温度/电压的单变量代理);s=1 为标称点。'
        + '上板后由 VIO 高低温实测替换,schema 不变。');
    } else {
      figV6.setNote('MODEL 数据不可用:' + (rel.note ?? '桥接未返回数据') + '(维持 MOCK 占位)');
    }
  } catch (e) {
    figV6.setNote('GET /api/viz/reliability 失败:' + msg(e) + '(维持 MOCK 占位)');
  }
  try {
    const ml = await api.getMl();
    if (ml.source === 'STATIC' && (ml.a || ml.b)) {
      figV7.setGrade('REAL-STATIC');
      figV7.setSource('W4 实验产物');
      const bits: string[] = [];
      if (ml.a) bits.push('A:LR 基线 seed=' + ml.a.seed);
      if (ml.b) bits.push('B:排序重构 seed=' + ml.b.seed);
      figV7.setSubtitle(bits.join(' · ') + ' · data/ml_attack/*.json');
      figV7.setSvg(renderV7(ml));
      const decls = (ml.a?.security_declarations ?? []).join('<br>· ');
      figV7.setNote(
        '实验 A:' + (ml.a?.conclusion_A ?? '—')
        + '<br>复现:<span class="mono">' + (ml.a?.repro_command ?? '') + '</span>'
        + (decls ? '<br>安全声明:<br>· ' + decls : '')
        + (ml.b ? '<br>实验 B 复现:<span class="mono">' + ml.b.repro_command + '</span>' : ''));
    } else {
      figV7.setNote('ML 数据不可用:' + (ml.note ?? '桥接未返回数据') + '(维持 MOCK 占位)');
    }
  } catch (e) {
    figV7.setNote('GET /api/viz/ml 失败:' + msg(e) + '(维持 MOCK 占位)');
  }
}
void loadV67();

/* 供无头探针读取内部状态(不参与业务;与 console 页的探针通道同法) */
(window as unknown as Record<string, unknown>).__viz = {
  state: () => ({ src, tau, tids: bundle.tids, tid: bundle.tid,
    hd: bundle.hd ? { intra: bundle.hd.intra.length, inter: bundle.hd.inter.length } : null,
    notes: bundle.notes, figures: document.querySelectorAll('.viz-fig').length,
    grades: {
      v5: document.querySelector('#fig-v5 .fig-grade')?.textContent ?? null,
      v6: document.querySelector('#fig-v6 .fig-grade')?.textContent ?? null,
      v7: document.querySelector('#fig-v7 .fig-grade')?.textContent ?? null,
    },
  }),
};
