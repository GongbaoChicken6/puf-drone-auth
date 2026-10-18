/* ============================================================
 * HD 仪表 + 逐响应 HD 条 —— 报告 §6.2「右栏·判定面板」
 *
 * 量程与阈值口径(全部取运行期下发的 verdict.thresholds,不硬编码):
 *   量程 = 0 .. 64×n_responses
 *   阈值带 = [0, scaled_pass) 绿 | [scaled_pass, scaled_reject) 琥珀灰区 |
 *            [scaled_reject, 量程] 红
 *   scaled_* 由桥接按 decide_scaled(hd_sum, n_responses) 口径下发
 *   (threshold.py 的 TAU × n_responses),故**指针进绿区 ⇔ 判定 PASS**,
 *   杜绝"PASS 但指针越线"。
 *
 * 两处必须显式处理的边界:
 *  · n_responses = 0(池耗尽/重放被拒于挑战之前):量程为 0,无指针可画。
 *    此时 hd = 255 = HD_NONE(protocol.py 的哨兵),须显示「无响应」而非
 *    254/0 之类伪值。
 *  · hd = 254:上游 _finish_reject/_finish_pass 把 hd_sum 以 min(Σ, 0xFE) 封顶,
 *    故 254 的含义是「≥254 且已饱和」,刻度需注明,否则会被读成精确值。
 * ============================================================ */
import type { Verdict } from '../core/types';

const HD_NONE = 0xFF;        // protocol.py HD_NONE
const HD_SATURATED = 0xFE;   // _finish_* 的封顶值

export class HdGauge {
  readonly el: HTMLElement;
  private bandPass!: HTMLElement;
  private bandGray!: HTMLElement;
  private bandReject!: HTMLElement;
  private pointer!: HTMLElement;
  private scale!: HTMLElement;
  private caption!: HTMLElement;
  private bars!: HTMLElement;

  constructor() {
    this.el = document.createElement('div');
    this.el.className = 'hd-gauge';
    this.el.innerHTML = `
      <div class="hg-head">
        <span class="hg-title">HD 汉明距离仪</span>
        <span class="hg-caption chip" id="hg-cap">待判定</span>
      </div>
      <div class="hg-track" id="hg-track">
        <div class="hg-band hg-pass"  id="hg-pass"></div>
        <div class="hg-band hg-gray"  id="hg-gray"></div>
        <div class="hg-band hg-reject" id="hg-reject"></div>
        <div class="hg-pointer" id="hg-ptr"><i></i></div>
      </div>
      <div class="hg-scale" id="hg-scale"></div>
      <div class="hg-bars" id="hg-bars"></div>`;
    this.bandPass = this.q('#hg-pass');
    this.bandGray = this.q('#hg-gray');
    this.bandReject = this.q('#hg-reject');
    this.pointer = this.q('#hg-ptr');
    this.scale = this.q('#hg-scale');
    this.caption = this.q('#hg-cap');
    this.bars = this.q('#hg-bars');
    this.clear();
  }

  private q<T extends HTMLElement>(sel: string): T {
    return this.el.querySelector<T>(sel)!;
  }

  clear(): void {
    this.bandPass.style.display = 'none';
    this.bandGray.style.display = 'none';
    this.bandReject.style.display = 'none';
    this.pointer.style.display = 'none';
    this.scale.textContent = '';
    this.bars.replaceChildren();
    this.caption.className = 'hg-caption chip';
    this.caption.textContent = '待判定';
  }

  update(v: Verdict | null): void {
    if (!v) { this.clear(); return; }
    const n = v.n_responses;
    const max = 64 * n;
    const noData = n === 0 || v.hd === HD_NONE;

    if (noData) {
      this.bandPass.style.display = 'none';
      this.bandGray.style.display = 'none';
      this.bandReject.style.display = 'none';
      this.pointer.style.display = 'none';
      this.scale.textContent = '量程 0(本轮 0 个响应,HD 哨兵值 0xFF)';
      this.caption.className = 'chip ' + (v.result === 3 ? 'amber' : 'red');
      this.caption.textContent = v.result === 3 ? '池耗尽 · 无响应' : '无响应(HD_NONE)';
      this.bars.replaceChildren();
      return;
    }

    const { scaled_pass: sp, scaled_reject: sr } = v.thresholds;
    const at = (x: number) => `${Math.max(0, Math.min(100, (x / max) * 100))}%`;

    this.bandPass.style.display = '';
    this.bandPass.style.left = '0%';
    this.bandPass.style.width = at(sp);

    if (sr > sp) {
      this.bandGray.style.display = '';
      this.bandGray.style.left = at(sp);
      this.bandGray.style.width = `${((Math.min(sr, max) - sp) / max) * 100}%`;
    } else {
      this.bandGray.style.display = 'none';
    }

    if (max > sr) {
      this.bandReject.style.display = '';
      this.bandReject.style.left = at(sr);
      this.bandReject.style.width = `${((max - sr) / max) * 100}%`;
    } else {
      this.bandReject.style.display = 'none';
    }

    // hd 可能到 254(饱和);量程上界 max 可能 <254 → 夹取到末端
    this.pointer.style.display = '';
    this.pointer.style.left = at(Math.min(v.hd, max));

    const inPass = v.hd < sp;
    const inReject = v.hd >= sr;
    this.caption.className = 'chip ' + (v.result === 0 ? 'green' : v.result === 1 ? 'red' : 'amber');
    this.caption.textContent =
      `HD ${v.hd}${v.hd >= HD_SATURATED ? '+(已封顶 0xFE)' : ''} / ${max}`
      + (inPass ? ' · 绿区' : inReject ? ' · 红区' : ' · 灰区');

    // 刻度只放**数字**(位置精确,故必须窄);阈值语义交给下面那行图例。
    // 早先把「PASS< 24」「REJECT≥ 64」整串贴在刻度上,在 300px 栏宽里
    // 两个标签会叠成一团(PASS<24REJECT≥64),故拆成两行各司其职。
    this.scale.replaceChildren();
    const mk = (x: number, label: string, cls: string, edge: boolean) => {
      const s = document.createElement('span');
      s.className = 'hg-tick ' + cls;
      if (edge) s.style.left = at(x);
      else { s.style.left = 'auto'; s.style.right = `${100 - (x / max) * 100}%`; }
      s.textContent = label;
      return s;
    };
    this.scale.append(
      mk(0, '0', 'hg-tick-0', true),
      mk(sp, String(sp), 'hg-tick-pass', false),
      mk(sr, String(sr), 'hg-tick-reject', false),
      mk(max, String(max), 'hg-tick-max', false),
    );

    const legend = document.createElement('div');
    legend.className = 'hg-legend';
    legend.innerHTML = `<span class="lg lg-pass">绿区 &lt;${sp}</span>`
      + (sr > sp ? `<span class="lg lg-gray">灰区 ${sp}–${sr}·加测</span>` : '')
      + `<span class="lg lg-reject">红区 ≥${sr}</span>`
      + `<span class="lg lg-dim">阈值由桥接按本轮 ${n} 个响应下发</span>`;
    this.scale.append(legend);

    this.renderBars(v);
  }

  /* 逐响应 HD 条(S2 差异高亮的数据源:verdict.hd_per_response) */
  private renderBars(v: Verdict): void {
    this.bars.replaceChildren();
    if (v.hd_per_response.length === 0) return;
    const head = document.createElement('div');
    head.className = 'hg-bars-head';
    head.textContent = `逐响应 HD(共 ${v.hd_per_response.length} 个响应,各自 0–64)`;
    this.bars.append(head);

    const row = document.createElement('div');
    row.className = 'hg-bars-row';
    const tauPass = v.thresholds.tau_pass;
    const tauReject = v.thresholds.tau_reject;
    v.hd_per_response.forEach((hd, i) => {
      const cell = document.createElement('div');
      cell.className = 'hg-bar';
      // 单响应口径:与未缩放阈值 TAU_PASS/TAU_REJECT 比(每响应满分 64)
      cell.classList.add(hd < tauPass ? 'ok' : hd >= tauReject ? 'bad' : 'gray');
      cell.title = `响应 #${i + 1}:HD=${hd}`
        + `(单响应阈值 PASS<${tauPass} / REJECT≥${tauReject})`;
      const fill = document.createElement('i');
      fill.style.height = `${Math.max(3, Math.min(100, (hd / 64) * 100))}%`;
      cell.append(fill);
      const lab = document.createElement('span');
      lab.textContent = String(hd);
      cell.append(lab);
      row.append(cell);
    });
    this.bars.append(row);
  }
}
