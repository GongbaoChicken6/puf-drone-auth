/* ============================================================
 * 指标卡 ×4 —— 逐数溯源(报告 §7.2 / §9)
 *
 * 每张卡右上角的「溯源」角标不是装饰:§7.2 原话是「角标逐数标注出处,
 * **禁止笼统引用**」。所以每个数字都必须能点开看到
 *   「出自哪个文件的哪句话 / 是实测还是估算 / 快照于哪一天 / 有无并存口径」。
 *
 * 两处必须显式声明的口径冲突(报告 §7.2 已点名,不能掩盖):
 *   ① 全握手延迟:~14 ms 是 project_flow.html 的汇总口径;project_design.md
 *      另有「10 ms(PUF 测量)+ 20 ms(MAVLink 帧传输)」的分项口径。
 *      两者并存,答辩以汇总为准并注明刷新日期 —— 卡片里两个都列出。
 *   ② 元数据陈旧:报告 §9 记「CI 12 套 TB / 单测 44 个」,本机实测为
 *      「13 套 TB / 77 个单测」。卡片按**实测**登记,并注明报告原值已陈旧,
 *      避免答辩时被问「到底几个」而两处对不上。
 * ============================================================ */

export interface Provenance {
  /** 显示在主数值旁的注记 */
  source: string;
  /** 精确到「哪句话 / 哪个字段」 */
  quote: string;
  grade: 'REAL-STATIC' | 'REAL-LIVE' | 'MOCK';
  snapshot: string;
  /** 并存口径或陈旧声明 */
  caveat?: string;
}

export interface MetricCard {
  key: string;
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  prov: Provenance;
}

export const METRICS: MetricCard[] = [
  {
    key: 'entropy',
    label: '有效熵(设备秘密)',
    value: '≈44',
    unit: 'bit',
    sub: '16 环频率的总排序;非 2⁶⁴',
    prov: {
      source: 'docs/project_design.md',
      quote: '「设备秘密本质是 16 个环频的总排序(有效熵 ≈ log2(16!) ≈ 44 bit)」'
        + ' —— 明确否定「2^64」的口径',
      grade: 'REAL-STATIC',
      snapshot: '仓库静态文件,2026-10-14 读取',
    },
  },
  {
    key: 'crp',
    label: '有效 CRP 空间',
    value: '120',
    unit: '种配对',
    sub: 'C(16,2),而非 2⁶⁴',
    prov: {
      source: 'docs/project_design.md',
      quote: '「有效 CRP 空间 = C(16,2)=120 种配对比较,而非 2^64」'
        + ';同文件实验 B 亦写「~120 条带噪 CRP 即可高概率重构」',
      grade: 'REAL-STATIC',
      snapshot: '仓库静态文件,2026-10-14 读取',
    },
  },
  {
    key: 'lut',
    label: '资源与延迟(W3 综合)',
    value: '653',
    unit: 'LUT',
    sub: '1.23% · FF 1,033(0.97%)· 全握手 ~14 ms',
    prov: {
      source: 'docs/project_flow.html(2026-10-12 手刷汇总)',
      quote: '「653 / LUT 实测 (1.23%)」「1,033 / FF (0.97%)」「~14ms / 全握手延迟」',
      grade: 'REAL-STATIC',
      snapshot: '看板刷新日 2026-10-12',
      caveat: '① 延迟存在**并存口径**:project_design.md 记「认证延迟:10ms(PUF 测量)'
        + '+ 20ms(MAVLink 帧传输)」。答辩以 project_flow.html 汇总口径为准,并注明刷新日期。'
        + ' ② LUT 区间下限来自 A1 speck 计划底稿,属**可行性估算**,非实测 —— 本条只登记实测值 653,'
        + '估算下限不在此卡展示。',
    },
  },
  {
    key: 'assets',
    label: '验证资产(本机实测)',
    value: '13',
    unit: '套 TB',
    sub: '单测 77 个 · 黄金帧 7 条 · 测试向量 1,195 行',
    prov: {
      source: '组员仓库 sim/ · tests/ · docs/protocol_contract.md §4',
      quote: 'sim/ 下 tb_*.v 共 13 个,scripts/ci_regression.ps1 全部引用'
        + ';tests/ 下 def test_ 共 77 个'
        + ';sim/**/testvector 下 speck_random.mem 1,179 行 + puf_tb_freqs.mem 16 行'
        + ';/api/golden-frames 返回 7 条',
      grade: 'REAL-STATIC',
      snapshot: '本机实测,2026-10-14',
      caveat: '报告 §9 记「CI 12 套 TB / 测试向量 1175 组 / 单测 44 个」。'
        + '本机实测为 13 套 TB、77 个单测、1,195 行向量 —— 报告数字系快照较早,此处按实测登记。',
    },
  },
];

export class Metrics {
  readonly el: HTMLElement;

  constructor() {
    this.el = document.createElement('div');
    this.el.className = 'viz-metrics';

    for (const m of METRICS) {
      const card = document.createElement('section');
      card.className = 'metric card';
      card.id = `metric-${m.key}`;

      const head = document.createElement('div');
      head.className = 'm-head';
      const lab = document.createElement('span');
      lab.className = 'm-label';
      lab.textContent = m.label;
      const toggle = document.createElement('button');
      toggle.className = 'm-prov-btn';
      toggle.textContent = '溯源 ⓘ';
      toggle.title = '逐数标注出处(报告 §7.2 强制)';
      toggle.setAttribute('aria-expanded', 'false');
      head.append(lab, toggle);

      const val = document.createElement('div');
      val.className = 'm-value mono';
      val.textContent = m.value;
      if (m.unit) {
        const u = document.createElement('span');
        u.className = 'm-unit';
        u.textContent = m.unit;
        val.append(u);
      }

      const sub = document.createElement('div');
      sub.className = 'm-sub';
      sub.textContent = m.sub ?? '';

      const prov = document.createElement('div');
      prov.className = 'm-prov';
      prov.hidden = true;
      prov.innerHTML = `
        <div class="mp-row"><span class="mp-k">来源</span>
          <span class="mp-v">${esc(m.prov.source)}</span></div>
        <div class="mp-row"><span class="mp-k">原文依据</span>
          <span class="mp-v">${esc(m.prov.quote)}</span></div>
        <div class="mp-row"><span class="mp-k">快照</span>
          <span class="mp-v">${esc(m.prov.snapshot)}</span></div>
        <div class="mp-row"><span class="mp-k">分级</span>
          <span class="mp-v"><span class="chip purple">${m.prov.grade}</span></span></div>
        ${m.prov.caveat ? `<div class="mp-row mp-caveat"><span class="mp-k">口径声明</span>
          <span class="mp-v">${esc(m.prov.caveat)}</span></div>` : ''}`;

      toggle.addEventListener('click', () => {
        prov.hidden = !prov.hidden;
        toggle.textContent = prov.hidden ? '溯源 ⓘ' : '收起 ⓘ';
        toggle.setAttribute('aria-expanded', String(!prov.hidden));
      });

      card.append(head, val, sub, prov);
      this.el.append(card);
    }
  }
}

/* 纯文本转义:溯源面板里的引号/斜杠来自静态文档,直接 innerHTML 会踩 HTML 语义 */
function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
