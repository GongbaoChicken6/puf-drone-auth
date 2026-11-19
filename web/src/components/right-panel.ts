/* ============================================================
 * 右栏 —— 报告 §6.1 / §6.2「判定面板」
 * 大字判定(48–72px)｜HD 仪表｜逐响应 HD 条｜R2 hex + 复制 + 金角标
 * ｜池水位｜会话计数
 *
 * 金角标的口径(§6.2 末行)必须**实测比较**,不能凭"装了密钥就点亮":
 *   条件 = 本 run 判定 PASS  ∧  verdict.r2 与黄金 R2 **逐字符一致**
 * 黄金 R2 从 GET /api/golden-frames 的 RESULT_A1_GOLDEN 向量解析得出
 * (经 format.resultOfFrame),本文件不硬编码 —— 常量一旦与组员
 * docs/protocol_contract.md §4 漂移,角标就会说谎。
 *
 * 为什么**不**把「首证 C2 = a1..a8」也做成点亮条件:黄金向量表里根本没有
 * 携带该 C2 的 ACCESS_REQUEST 帧(表内那条 ACCESS_REQUEST 属于另一组向量,
 * c2=000102…07),a1..a8 只作为散文出现在 RESULT_A1_GOLDEN 的 note 里。
 * 若强行解析散文去比对,就会在 R2 明明逐字节相同的情况下漏亮角标(实测踩过)。
 * 故此处只承诺可验证的那一句,并把黄金帧自述的 note 原文附在下方供人核对。
 * ============================================================ */
import { barScale, c2OfAccessRequest } from '../core/format';
import type { AppState, RunState, TerminalState } from '../core/store';
import { RESULT_CN, type ResultCode } from '../core/types';
import { HdGauge } from './hd-gauge';

/* 大字判定的配色类(result → 视觉语义) */
const RESULT_CLS: Record<ResultCode, string> = {
  0: 'pass', 1: 'reject', 2: 'error', 3: 'drain', 4: 'replay',
};

export interface GoldenVector {
  r2: string | null;      // RESULT_A1_GOLDEN 的 R2(唯一被"金角标"承诺比对的量)
  note: string;           // 该黄金帧的自述(note 原文,含 "C2=a1..a8" 等前提)
}

export class RightPanel {
  readonly el: HTMLElement;
  private gauge = new HdGauge();

  private vBig!: HTMLElement;
  private vSub!: HTMLElement;
  private vMeta!: HTMLElement;
  private vCard!: HTMLElement;
  private statHd!: HTMLElement;
  private statN!: HTMLElement;
  private statTh!: HTMLElement;
  private blockBox!: HTMLElement;
  private r2Hex!: HTMLElement;
  private r2Badge!: HTMLElement;
  private r2Note!: HTMLElement;
  private r2Copy!: HTMLButtonElement;
  private poolText!: HTMLElement;
  private poolBar!: HTMLElement;
  private golden: GoldenVector = { r2: null, note: '' };
  private lastR2 = '';

  constructor() {
    this.el = document.createElement('div');
    this.el.className = 'right-panel';
    this.el.innerHTML = `
      <div class="rp-verdict" id="rp-verdict">
        <div class="rp-eyebrow">判定结果</div>
        <div class="rp-big" id="rp-big">待判定</div>
        <div class="rp-sub" id="rp-sub">等待一次认证</div>
        <div class="rp-stats" id="rp-stats">
          <div class="rp-stat" title="汉明距离：指纹响应与注册模板逐位比对后不一致的位数">
            <span class="rp-stat-k">汉明距离</span>
            <span class="rp-stat-v mono" id="rp-stat-hd">—</span>
          </div>
          <div class="rp-stat" title="参与本轮判决的指纹响应组数">
            <span class="rp-stat-k">响应组数</span>
            <span class="rp-stat-v mono" id="rp-stat-n">—</span>
          </div>
          <div class="rp-stat" title="双阈值判决：偏差不超过通过阈值判通过，不小于拒绝阈值判拒绝，两者之间进入待定区加测">
            <span class="rp-stat-k">判决阈值</span>
            <span class="rp-stat-v mono" id="rp-stat-th">—</span>
          </div>
        </div>
        <div class="rp-meta mono" id="rp-meta">—</div>
      </div>

      <div class="rp-block" id="rp-block" hidden>
        <div class="rp-block-t">终端侧拒绝确认</div>
        <div class="rp-block-d">终端复算的 R2 与基站应答不一致，判定对方为假冒基站，拒绝回送确认帧，双向认证未闭环。</div>
      </div>

      <section class="rp-card" id="rp-hd"></section>

      <section class="rp-card">
        <div class="rp-card-h">
          <span>基站应答 R2</span>
          <span class="chip gold" id="rp-r2-badge" hidden>标准 R2 ✓</span>
        </div>
        <div class="rp-r2">
          <code class="mono" id="rp-r2">—</code>
          <button class="btn ghost" id="rp-r2-copy" title="复制 R2(hex)">复制</button>
        </div>
        <div class="rp-note" id="rp-r2-note"></div>
      </section>

      <section class="rp-card">
        <div class="rp-card-h"><span>挑战池余量</span><span class="mono" id="rp-pool-text">—</span></div>
        <div class="tb-bar rp-pool-bar"><i id="rp-pool-bar" style="transform:scaleX(0)"></i></div>
        <div class="rp-note">分母为注册时容量上限；低于 20% 预警。</div>
      </section>`;

    this.vBig = this.q('#rp-big');
    this.vSub = this.q('#rp-sub');
    this.vMeta = this.q('#rp-meta');
    this.vCard = this.q('#rp-verdict');
    this.statHd = this.q('#rp-stat-hd');
    this.statN = this.q('#rp-stat-n');
    this.statTh = this.q('#rp-stat-th');
    this.blockBox = this.q('#rp-block');
    this.r2Hex = this.q('#rp-r2');
    this.r2Badge = this.q('#rp-r2-badge');
    this.r2Note = this.q('#rp-r2-note');
    this.r2Copy = this.q<HTMLButtonElement>('#rp-r2-copy');
    this.poolText = this.q('#rp-pool-text');
    this.poolBar = this.q('#rp-pool-bar');
    this.q('#rp-hd').append(this.gauge.el);

    this.r2Copy.addEventListener('click', () => { void this.copyR2(); });
  }

  private q<T extends HTMLElement>(sel: string): T { return this.el.querySelector<T>(sel)!; }

  /* 由入口在 GET /api/golden-frames 到达后注入(解析自黄金向量,非硬编码) */
  setGolden(g: GoldenVector): void {
    this.golden = g;
    this.paintR2(this.lastRun, this.lastTerminal);
  }

  private lastRun: RunState | null = null;
  private lastTerminal: TerminalState | null = null;

  private async copyR2(): Promise<void> {
    if (!this.lastR2) return;
    try {
      await navigator.clipboard.writeText(this.lastR2);
      this.r2Copy.textContent = '已复制 ✓';
    } catch {
      // 非安全上下文(如 http:// 局域网 IP)下 clipboard 不可用 —— 退回选中文本
      const r = document.createRange();
      r.selectNodeContents(this.r2Hex);
      const sel = window.getSelection();
      sel?.removeAllRanges();
      sel?.addRange(r);
      this.r2Copy.textContent = '请按 Ctrl+C';
    }
    window.setTimeout(() => { this.r2Copy.textContent = '复制'; }, 1400);
  }

  update(s: AppState): void {
    const run = s.run;
    const t = s.selectedTerminal != null ? s.terminals.get(s.selectedTerminal) ?? null : null;
    this.lastRun = run;
    this.lastTerminal = t;

    /* ---------- 大字判定 ---------- */
    const v = run?.verdict ?? null;
    if (!v) {
      this.vBig.textContent = '待判定';
      this.vBig.className = 'rp-big';
      /* R8 D19:判定卡本体也随结果挂状态类(卡底渐变/描边),不只大字变色 */
      this.vCard.className = 'rp-verdict idle';
      this.vSub.textContent = t ? `终端 ${t.id} · 等待一次认证` : '等待一次认证';
      this.vMeta.textContent = '—';
      this.statHd.textContent = '—';
      this.statN.textContent = '—';
      this.statTh.textContent = '—';
    } else {
      this.vBig.textContent = RESULT_CN[v.result];
      this.vBig.className = `rp-big ${RESULT_CLS[v.result]}`;
      this.vCard.className = `rp-verdict st-${RESULT_CLS[v.result]}`;
      this.vSub.textContent = `终端 ${v.terminal_id} · ${v.n_responses} 组响应参与判决`;
      /* 专家读数三块:HD / 参与响应数 / 绿-红阈值。数字字段来自
       * /api/status 与 verdict 载荷,阈值两块用语义色。 */
      this.statHd.textContent = String(v.hd);
      this.statN.textContent = String(v.n_responses);
      this.statTh.replaceChildren();
      const ok = document.createElement('span');
      ok.className = 'th-ok';
      ok.textContent = `<${v.thresholds.scaled_pass}`;
      const sep = document.createElement('span');
      sep.className = 'th-sep';
      sep.textContent = '/';
      const no = document.createElement('span');
      no.className = 'th-no';
      no.textContent = `≥${v.thresholds.scaled_reject}`;
      this.statTh.append(ok, sep, no);
      this.vMeta.textContent = `认证轮次 ${v.run_id}`;
    }

    /* S7:终端侧 BLOCKED 由桥接显式下发的 confirm.done(status=1) 得出 */
    this.blockBox.hidden = !run?.terminalBlocked;

    this.gauge.update(v);

    /* ---------- R2 ---------- */
    this.paintR2(run, t);

    /* ---------- 池水位 ---------- */
    const pct = t && t.pool_size > 0 ? t.pool_pct : 0;
    this.poolText.textContent = t
      ? `${t.pool_remaining} / ${t.pool_size || '—'}  (${pct}%)`
      : '—';
    this.poolBar.setAttribute('style', barScale(pct));
    this.poolBar.parentElement!.className = 'tb-bar rp-pool-bar'
      + (pct < 20 ? ' warn' : '') + (t?.poolWarn && pct < 20 ? ' flash' : '');
  }

  private paintR2(run: RunState | null, t: TerminalState | null): void {
    const r2 = run?.verdict?.result === 0 ? (run.verdict.r2 ?? '') : '';
    this.lastR2 = r2;
    this.r2Hex.textContent = r2 ? r2.replace(/(..)/g, '$1 ').trim() : '—';
    this.r2Copy.disabled = !r2;

    if (!r2) {
      this.r2Badge.hidden = true;
      this.r2Note.textContent = '判定通过时下发，占 8 字节。';
      return;
    }

    // 本 run 首条 ACCESS_REQUEST 的 C2 —— 只作展示,不作点亮条件(见文件头说明)
    const acc = run?.frames.find(f => c2OfAccessRequest(f.hex) != null);
    const c2 = acc ? c2OfAccessRequest(acc.hex) : null;
    const gr2 = this.golden.r2;
    const isGold = gr2 != null && r2 === gr2;

    this.r2Badge.hidden = !isGold;
    this.r2Badge.title = `触发条件：装入公开测试密钥 → 新终端首次认证 → R2 与标准应答`
      + ` 逐字符一致（标准值 ${gr2 ?? '—'}）`;

    const parts: string[] = [];
    if (isGold) {
      parts.push(`与标准应答一致（${gr2}）。`);
    } else if (gr2 == null) {
      parts.push('标准应答未载入。');
    } else {
      parts.push(`非标准应答（标准值 ${gr2}）。`);
    }
    parts.push(`C2=${c2 ?? '—'}` + (t?.keyInstalled ? ' · 测试密钥' : '') + '。');
    this.r2Note.textContent = parts.join(' ');
    // 标准帧的自述前提放在悬停提示里,正文不再展开。
    this.r2Note.title = this.golden.note ? `标准帧自述：${this.golden.note}` : '';
  }
}
