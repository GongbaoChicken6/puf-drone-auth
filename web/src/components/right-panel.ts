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
  private blockBox!: HTMLElement;
  private r2Hex!: HTMLElement;
  private r2Badge!: HTMLElement;
  private r2Note!: HTMLElement;
  private r2Copy!: HTMLButtonElement;
  private poolText!: HTMLElement;
  private poolBar!: HTMLElement;
  private sess!: HTMLElement;
  private golden: GoldenVector = { r2: null, note: '' };
  private lastR2 = '';

  constructor() {
    this.el = document.createElement('div');
    this.el.className = 'right-panel';
    this.el.innerHTML = `
      <div class="rp-verdict" id="rp-verdict">
        <div class="rp-big" id="rp-big">待判定</div>
        <div class="rp-sub" id="rp-sub">等待一次认证</div>
        <div class="rp-meta mono" id="rp-meta">—</div>
        <div class="rp-idle" id="rp-idle" hidden>
          开始演示:左栏 <b>S1–S7</b> 场景 · 终端卡「认证」<br />
          <span class="mono">Shift+1–7</span> 快捷触发 · <span class="mono">?</span> 全部快捷键
        </div>
      </div>

      <div class="rp-block" id="rp-block" hidden>
        <div class="rp-block-t">终端侧:BLOCKED</div>
        <div class="rp-block-d">检出假基站(R2 被篡改)—— 终端拒绝发 CONFIRM,双向认证未闭环。</div>
      </div>

      <section class="rp-card" id="rp-hd"></section>

      <section class="rp-card">
        <div class="rp-card-h">
          <span>R2(K_terminal 派生的会话确认值)</span>
          <span class="chip gold" id="rp-r2-badge" hidden>黄金 R2 ✓</span>
        </div>
        <div class="rp-r2">
          <code class="mono" id="rp-r2">—</code>
          <button class="btn ghost" id="rp-r2-copy" title="复制 R2(hex)">复制</button>
        </div>
        <div class="rp-note" id="rp-r2-note"></div>
      </section>

      <section class="rp-card">
        <div class="rp-card-h"><span>CRP 池水位</span><span class="mono" id="rp-pool-text">—</span></div>
        <div class="tb-bar rp-pool-bar"><i id="rp-pool-bar" style="transform:scaleX(0)"></i></div>
        <div class="rp-note">分母 pool_size = 该设备历史容量上限;pool.warning 在 remaining_pct &lt; 20 时下发。</div>
      </section>

      <section class="rp-card">
        <div class="rp-card-h"><span>会话计数</span><span class="mono" id="rp-sess-state">—</span></div>
        <div class="rp-kv" id="rp-sess"></div>
      </section>`;

    this.vBig = this.q('#rp-big');
    this.vSub = this.q('#rp-sub');
    this.vMeta = this.q('#rp-meta');
    this.vCard = this.q('#rp-verdict');
    this.blockBox = this.q('#rp-block');
    this.r2Hex = this.q('#rp-r2');
    this.r2Badge = this.q('#rp-r2-badge');
    this.r2Note = this.q('#rp-r2-note');
    this.r2Copy = this.q<HTMLButtonElement>('#rp-r2-copy');
    this.poolText = this.q('#rp-pool-text');
    this.poolBar = this.q('#rp-pool-bar');
    this.sess = this.q('#rp-sess');
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

    /* R7:idle 引导。只在「本会话还一次认证都没跑过」时出现 —— 跑过之后再
     * 空闲,操作者已经知道路,这行字就从引导降级成噪音。 */
    this.q('#rp-idle').hidden = !(run == null && s.runCount === 0);

    /* ---------- 大字判定 ---------- */
    const v = run?.verdict ?? null;
    if (!v) {
      this.vBig.textContent = '待判定';
      this.vBig.className = 'rp-big';
      /* R8 D19:判定卡本体也随结果挂状态类(卡底渐变/描边),不只大字变色 */
      this.vCard.className = 'rp-verdict';
      this.vSub.textContent = t ? `tid ${t.id} · 等待一次认证` : '等待一次认证';
      this.vMeta.textContent = '—';
    } else {
      this.vBig.textContent = RESULT_CN[v.result];
      this.vBig.className = `rp-big ${RESULT_CLS[v.result]}`;
      this.vCard.className = `rp-verdict st-${RESULT_CLS[v.result]}`;
      this.vSub.textContent = `${v.result_name} · tid ${v.terminal_id}`
        + ` · ${v.n_responses} 个响应参与判定`;
      /* R8 D19 修订:阈值词上语义色(绿=PASS 界 / 红=REJECT 界)。值来自
       * /api/status 的数字字段,拼进 innerHTML 无注入面。 */
      this.vMeta.innerHTML = `run ${v.run_id} · HD ${v.hd}`
        + ` · 阈值 <span class="th-ok">绿&lt;${v.thresholds.scaled_pass}</span>`
        + ` / <span class="th-no">红≥${v.thresholds.scaled_reject}</span>`;
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

    /* ---------- 会话计数 ---------- */
    const u = t?.lastSession ?? null;
    this.q('#rp-sess-state').textContent = u?.state ?? '—';
    const kv: [string, string][] = u == null ? [
      ['challenges_issued', '—'], ['responses_scored', '—'], ['hd_sum', '—'],
    ] : [
      ['challenges_issued', String(u.challenges_issued)],
      ['responses_scored', String(u.responses_scored)],
      ['hd_sum', u.hd_sum == null ? '—' : String(u.hd_sum)],
      ['last_decision', u.last_decision ?? '—'],
      ['terminal_id', String(u.terminal_id)],
    ];
    this.sess.replaceChildren(...kv.map(([k, val]) => {
      const d = document.createElement('div');
      d.className = 'rp-kv-row';
      const a = document.createElement('span'); a.className = 'k'; a.textContent = k;
      const b = document.createElement('span'); b.className = 'v mono'; b.textContent = val;
      d.append(a, b);
      return d;
    }));
  }

  private paintR2(run: RunState | null, t: TerminalState | null): void {
    const r2 = run?.verdict?.result === 0 ? (run.verdict.r2 ?? '') : '';
    this.lastR2 = r2;
    this.r2Hex.textContent = r2 ? r2.replace(/(..)/g, '$1 ').trim() : '—';
    this.r2Copy.disabled = !r2;

    if (!r2) {
      this.r2Badge.hidden = true;
      this.r2Note.textContent = 'R2 仅在判定 PASS 时下发(RESULT 载荷 result|hd|R2,R2 占 8B)。';
      return;
    }

    // 本 run 首条 ACCESS_REQUEST 的 C2 —— 只作展示,不作点亮条件(见文件头说明)
    const acc = run?.frames.find(f => c2OfAccessRequest(f.hex) != null);
    const c2 = acc ? c2OfAccessRequest(acc.hex) : null;
    const gr2 = this.golden.r2;
    const isGold = gr2 != null && r2 === gr2;

    this.r2Badge.hidden = !isGold;
    this.r2Badge.title = `触发节拍:装入 W3 演示密钥 → 全新终端首次认证 → R2 与黄金向量`
      + ` RESULT_A1_GOLDEN 逐字符一致(黄金值 ${gr2 ?? '—'})`;

    const parts: string[] = [];
    if (isGold) {
      parts.push(`与 docs/protocol_contract.md §4 的 RESULT_A1_GOLDEN 逐字符一致(${gr2})。`);
    } else if (gr2 == null) {
      parts.push('黄金向量未就绪(未取到 /api/golden-frames),无法比对。');
    } else {
      parts.push(`非黄金 R2:黄金值为 ${gr2}。`);
    }
    parts.push(`本 run 的 C2=${c2 ?? '—'}`
      + (t?.keyInstalled ? '(已装入演示密钥)' : '(该终端未装演示密钥)') + '。');
    // 黄金帧自述原文 —— 它的前提条件(如 K_terminal=W3、C2=a1..a8)写在这里,
    // 原样引用而不复述,避免本页转述走样。
    if (this.golden.note) parts.push(`黄金帧自述:${this.golden.note}`);
    this.r2Note.textContent = parts.join(' ');
  }
}
