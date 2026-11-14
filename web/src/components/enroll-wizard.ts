/* ============================================================
 * N5(finals-demo) 真板指纹录入向导
 *
 * 模态覆盖层:tid/挑战数/测量数 → POST /api/enroll_real → 进度条
 * (enroll.progress SSE) → 结果(stable bits / n_pairs / 稳定性)
 * → 完成后可选"验证认证"(POST /api/poll = N4 AUTH_POLL)。
 * ============================================================ */
import { api } from '../core/api';

export class EnrollWizard {
  readonly el: HTMLElement;
  private tidInput!: HTMLInputElement;
  private nInput!: HTMLInputElement;
  private mInput!: HTMLInputElement;
  private startBtn!: HTMLButtonElement;
  private closeBtn!: HTMLButtonElement;
  private progressBar!: HTMLElement;
  private progressText!: HTMLElement;
  private resultBox!: HTMLElement;
  private verifyBtn!: HTMLButtonElement;
  private errBox!: HTMLElement;
  private active = false;

  constructor() {
    this.el = document.createElement('div');
    this.el.className = 'enroll-wizard';
    this.el.hidden = true;
    this.el.setAttribute('role', 'dialog');
    this.el.innerHTML = `
      <div class="ew-card">
        <div class="ew-head">
          <span>真板指纹录入</span>
          <button class="btn ghost" data-close title="关闭">✕</button>
        </div>
        <div class="ew-body">
          <div class="ew-form" data-step="form">
            <label>终端 ID (tid)
              <input type="number" data-tid value="7" min="1" max="255" class="mono">
            </label>
            <label>挑战数
              <input type="number" data-n value="100" min="4" max="500" class="mono">
            </label>
            <label>测量次数
              <input type="number" data-m value="3" min="1" max="10" class="mono">
            </label>
            <div class="ew-hint">确保板子已上电、拨码 SW12 设为正确 tid、ENROLL_EN=1</div>
            <button class="btn green" data-start>开始录入</button>
          </div>
          <div class="ew-progress" data-step="progress" hidden>
            <div class="ew-bar"><div data-bar class="ew-fill"></div></div>
            <div class="mono" data-ptext>准备中…</div>
          </div>
          <div class="ew-result" data-step="result" hidden>
            <div class="ew-stats mono" data-stats></div>
            <button class="btn" data-verify title="POST /api/poll (AUTH_POLL)">验证认证</button>
          </div>
          <div class="ew-error" data-error hidden></div>
        </div>
      </div>`;
    this.tidInput = this.el.querySelector('[data-tid]')!;
    this.nInput = this.el.querySelector('[data-n]')!;
    this.mInput = this.el.querySelector('[data-m]')!;
    this.startBtn = this.el.querySelector('[data-start]')!;
    this.progressBar = this.el.querySelector('[data-bar]')!;
    this.progressText = this.el.querySelector('[data-ptext]')!;
    this.resultBox = this.el.querySelector('[data-stats]')!;
    this.verifyBtn = this.el.querySelector('[data-verify]')!;
    this.errBox = this.el.querySelector('[data-error]')!;
    this.closeBtn = this.el.querySelector('[data-close]')!;

    this.startBtn.addEventListener('click', () => void this.start());
    this.closeBtn.addEventListener('click', () => this.close());
    this.verifyBtn.addEventListener('click', () => void this.verify());
    this.el.addEventListener('click', (e) => {
      if (e.target === this.el) this.close();
    });

    // SSE 进度订阅
    window.addEventListener('puf:enrollprogress', ((e: CustomEvent) => {
      if (!this.active) return;
      const p = e.detail;
      const pct = Math.round(100 * ((p.batch - 1) * p.rounds + p.round) /
                             (p.batches * p.rounds));
      this.progressBar.style.width = pct + '%';
      this.progressText.textContent =
        `批 ${p.batch}/${p.batches} · 测量 ${p.round}/${p.rounds} — ${pct}%`;
    }) as EventListener);

    // enroll.done → 结果
    window.addEventListener('puf:enroll', ((e: CustomEvent) => {
      if (!this.active) return;
      const d = e.detail;
      this.showStep('result');
      this.resultBox.innerHTML = `
        <div><b>tID</b> ${d.terminal_id}</div>
        <div><b>模板对</b> ${d.n_pairs}</div>
        <div><b>新增</b> ${d.added}</div>
        <div><b>稳定位</b> ${d.stable_bits}/64 (${d.stability_pct}%)</div>`;
      this.active = false;
    }) as EventListener);

    // run.error → 错误
    window.addEventListener('puf:runerror', ((e: CustomEvent) => {
      if (!this.active) return;
      const d = e.detail;
      if (d.stage === 'enroll_real') {
        this.showStep('form');
        this.errBox.textContent = '❌ ' + d.error;
        this.errBox.hidden = false;
        this.active = false;
      }
    }) as EventListener);
  }

  open(): void {
    this.el.hidden = false;
    this.showStep('form');
    this.errBox.hidden = true;
    this.active = false;
  }

  close(): void {
    this.el.hidden = true;
    this.active = false;
  }

  private showStep(step: string): void {
    for (const s of this.el.querySelectorAll<HTMLElement>('[data-step]')) {
      s.hidden = s.dataset.step !== step;
    }
  }

  private async start(): Promise<void> {
    const tid = parseInt(this.tidInput.value, 10);
    const n = parseInt(this.nInput.value, 10);
    const m = parseInt(this.mInput.value, 10);
    if (!tid || !n || !m) return;
    this.active = true;
    this.errBox.hidden = true;
    this.showStep('progress');
    this.progressBar.style.width = '0%';
    this.progressText.textContent = '发送注册请求…';
    try {
      await api.enrollReal({ terminal_id: tid, n, measurements: m });
    } catch (e) {
      this.showStep('form');
      this.errBox.textContent = '❌ ' + (e instanceof Error ? e.message : String(e));
      this.errBox.hidden = false;
      this.active = false;
    }
  }

  private async verify(): Promise<void> {
    const tid = parseInt(this.tidInput.value, 10);
    try {
      await api.poll(tid);
      this.verifyBtn.textContent = '✓ 已发送巡检(AUTH_POLL)';
      this.verifyBtn.disabled = true;
    } catch { /* audit log captures */ }
  }
}
