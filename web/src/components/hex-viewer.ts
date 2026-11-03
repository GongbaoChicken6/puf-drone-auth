/* ============================================================
 * hex 字段结构查看器 —— 报告 §6.2「中央·认证舞台 / hex 结构查看器」
 *
 * 严格按报告的两条口径分开实现,**不做实时帧与黄金帧的逐字节 diff**:
 *  ① 实时帧(live 模式):只做**字段结构对齐着色** —— 帧头/载荷/CRC 分段
 *     ＋字段名注记。黄金向量是固定回归输入,与运行时随机帧必然全差异,
 *     逐字节 diff 除了满屏红色没有任何信息量(§6.2 原话)。
 *  ② S2「差异高亮」:数据源是 verdict.hd_per_response 的逐响应 HD
 *     **与响应-模板字节对比**。这里真的去取 /api/viz/templates 的模板响应,
 *     逐位 XOR,并把算得的位数与桥接下发的 hd_per_response[i] 对账 ——
 *     对得上才说明桥接的 HD 数字是真的从模板算出来的。
 *  ③ 逐字节 diff 只在「黄金帧回放」模式启用,且只做**黄金帧之间**的对比
 *     (两条固定真实向量),用于教学讲清字段布局。
 * ============================================================ */
import { api } from '../core/api';
import {
  bitDiff, c2OfAccessRequest, frameParts, groupsOf8, hexBytes, segmentFrame,
} from '../core/format';
import type { RunState } from '../core/store';

type Mode = 'live' | 'golden';

interface GoldenFrame { name: string; hex: string; note: string; }

export class HexViewer {
  readonly el: HTMLElement;
  private mode: Mode = 'live';
  private selFrame = -1;
  private goldens: GoldenFrame[] | null = null;
  private goldSel = 0;
  private goldCmp = -1;
  private templates: Record<string, { responses: Record<string, string>; stability_mask: string }> | null = null;
  private templateTid: number | null = null;
  private lastRunKey = '';

  constructor() {
    this.el = document.createElement('div');
    this.el.className = 'hex-viewer';
    this.el.innerHTML = `
      <div class="hv-head">
        <span class="hv-title">帧结构查看器</span>
        <div class="hv-modes">
          <button class="btn hv-mode primary" data-mode="live">实时帧</button>
          <button class="btn hv-mode" data-mode="golden">黄金帧回放</button>
        </div>
        <span class="hv-note" id="hv-note"></span>
      </div>
      <div class="hv-pick" id="hv-pick"></div>
      <div class="hv-body" id="hv-body"></div>
      <div class="hv-diff" id="hv-diff"></div>`;
    this.el.querySelectorAll<HTMLButtonElement>('.hv-mode').forEach(b => {
      b.addEventListener('click', () => void this.setMode(b.dataset.mode as Mode));
    });
  }

  private get body(): HTMLElement { return this.el.querySelector('#hv-body')!; }
  private get pick(): HTMLElement { return this.el.querySelector('#hv-pick')!; }
  private get diffBox(): HTMLElement { return this.el.querySelector('#hv-diff')!; }
  private get note(): HTMLElement { return this.el.querySelector('#hv-note')!; }

  private async setMode(m: Mode): Promise<void> {
    if (this.mode === m) return;
    this.mode = m;
    this.el.querySelectorAll<HTMLButtonElement>('.hv-mode').forEach(b => {
      b.classList.toggle('primary', b.dataset.mode === m);
    });
    if (m === 'golden' && this.goldens == null) {
      this.note.textContent = '取黄金帧…';
      try {
        this.goldens = (await api.getGoldenFrames()).frames;
      } catch {
        this.goldens = [];
        this.note.textContent = '黄金帧获取失败(桥接不可达)';
      }
    }
    this.render();
  }

  update(run: RunState | null): void {
    // 换 run 时默认选中最新一帧(跟随演示)
    const key = run ? `${run.run_id}:${run.frames.length}` : '';
    if (key !== this.lastRunKey) {
      this.lastRunKey = key;
      if (run && run.frames.length > 0) this.selFrame = run.frames.length - 1;
      if (!run) this.selFrame = -1;
    }
    this.render(run);
  }

  private render(run: RunState | null = null): void {
    const r = run ?? this.lastRun;
    if (r) this.lastRun = r;
    if (this.mode === 'live') this.renderLive(this.lastRun);
    else this.renderGolden();
  }
  private lastRun: RunState | null = null;

  /* ---------------- live ---------------- */
  private renderLive(run: RunState | null): void {
    this.pick.replaceChildren();
    this.body.replaceChildren();
    this.diffBox.replaceChildren();

    if (!run || run.frames.length === 0) {
      this.note.textContent = '';
      const p = document.createElement('p');
      p.className = 'hv-empty';
      p.textContent = '尚无实时帧 —— 触发 S1 后此处逐帧展开字段结构';
      this.body.append(p);
      return;
    }
    this.note.textContent = `run ${run.run_id} · ${run.frames.length} 帧`;

    // 帧选择 chip(名称 + 字节数)
    run.frames.forEach((f, i) => {
      const b = document.createElement('button');
      b.className = 'chip hv-chip' + (i === this.selFrame ? ' cyan' : '');
      // 「选中了第几帧」此前只有 cyan 描边在说 —— 那是颜色单独承载信息
      b.setAttribute('aria-pressed', String(i === this.selFrame));
      b.textContent = `${i + 1}. ${f.name} ${f.len}B`;
      b.title = `${f.dir === 'term->server' ? '终端→基站' : '基站→终端'}`
        + ` · ${f.source === 'simulated-terminal' ? '代演' : '真机'} · seq=${frameParts(f.hex)?.seq ?? '?'}`;
      b.addEventListener('click', () => { this.selFrame = i; this.renderLive(run); });
      this.pick.append(b);
    });

    const f = run.frames[Math.max(0, Math.min(this.selFrame, run.frames.length - 1))];
    this.body.append(this.segmentBlock(f.hex, f.name, f.len, f.dir, f.source));

    // 关键字段注记(按 msg 取真实字段,不猜)
    const extra = this.fieldNotes(f.hex);
    if (extra) this.body.append(extra);

    this.renderResponseDiff(run);
  }

  private segmentBlock(hex: string, name: string, len: number,
                       dir: string, source: string): HTMLElement {
    const parts = frameParts(hex);
    const wrap = document.createElement('div');
    wrap.className = 'hv-frame';
    const head = document.createElement('div');
    head.className = 'hv-frame-head';
    head.innerHTML = `<b>${name}</b>
      <span class="chip">${dir === 'term->server' ? '终端→基站' : '基站→终端'}</span>
      <span class="chip ${source === 'simulated-terminal' ? 'amber' : 'green'}">`
      + `${source === 'simulated-terminal' ? '代演' : '真机'}</span>
      <span class="hint">msg_id=0x${(parts?.msgId ?? 0).toString(16).padStart(4, '0')}`
      + ` · len=${len} · seq=${parts?.seq ?? '?'} · 共 ${hexBytes(hex).length}B</span>`;
    wrap.append(head);

    const segs = segmentFrame(hex, parts?.msgId ?? 0);
    const grid = document.createElement('div');
    grid.className = 'hv-grid';
    for (const s of segs) {
      const cell = document.createElement('div');
      cell.className = `hv-seg hv-${s.tone}`;
      const lab = document.createElement('span');
      lab.className = 'hv-label';
      lab.textContent = s.label;
      const bytes = document.createElement('span');
      bytes.className = 'hv-bytes mono';
      for (const by of s.bytes) {
        const sp = document.createElement('i');
        sp.textContent = by;
        bytes.append(sp);
      }
      cell.append(lab, bytes);
      cell.title = `${s.label} · ${s.bytes.length} 字节`;
      grid.append(cell);
    }
    wrap.append(grid);
    return wrap;
  }

  /* 逐帧的"人话"字段注记 */
  private fieldNotes(hex: string): HTMLElement | null {
    const p = frameParts(hex);
    if (!p) return null;
    const rows: [string, string][] = [];
    if (p.msgId === 0x0090) {
      const c2 = c2OfAccessRequest(hex);
      rows.push(['terminal_id', String(leU32(p.payload, 0))],
        ['nonce', `0x${leU32(p.payload, 4).toString(16).padStart(8, '0')}`],
        ['C2(8B 计数器)', c2 ?? '—']);
    } else if (p.msgId === 0x0091 || p.msgId === 0x0095) {
      groupsOf8(p.payload).forEach((g, i) => rows.push([`seed${i + 1}`, g]));
    } else if (p.msgId === 0x0092) {
      groupsOf8(p.payload).forEach((g, i) => rows.push([`r1_${i + 1}`, g]));
    } else if (p.msgId === 0x0093) {
      const res = parseInt(p.payload[0] ?? '0', 16);
      rows.push(['result', `${res}(${['PASS', 'REJECT', 'ERROR', 'POOL_EMPTY', 'REPLAY'][res] ?? '?'})`],
        ['hd', String(parseInt(p.payload[1] ?? '0', 16))]);
      if (p.payload.length >= 10) rows.push(['R2(8B)', p.payload.slice(2, 10).join('').toLowerCase()]);
    } else if (p.msgId === 0x0094) {
      rows.push(['terminal_id', String(leU32(p.payload, 0))],
        ['status', `${parseInt(p.payload[4] ?? '0', 16)}(0=CONFIRM_OK)`]);
    }
    if (rows.length === 0) return null;
    const box = document.createElement('div');
    box.className = 'hv-fields';
    for (const [k, v] of rows) {
      const row = document.createElement('div');
      row.className = 'hv-field';
      row.innerHTML = `<span class="k">${k}</span><span class="v mono">${v}</span>`;
      box.append(row);
    }
    return box;
  }

  /* S2 差异高亮:响应 vs 模板,逐位 XOR,并与 hd_per_response 对账 */
  private renderResponseDiff(run: RunState): void {
    const v = run.verdict;
    if (!v || v.hd_per_response.length === 0) return;

    const seeds: string[] = [];
    for (const f of run.frames) {
      const p = frameParts(f.hex);
      if (p && (p.msgId === 0x0091 || p.msgId === 0x0095)) seeds.push(...groupsOf8(p.payload));
    }
    const r1s: string[] = [];
    for (const f of run.frames) {
      const p = frameParts(f.hex);
      if (p && p.msgId === 0x0092) r1s.push(...groupsOf8(p.payload));
    }

    /* 双阈值语义:单响应 HD≤τ_pass(TAU_PASS=6)属测量噪声内的「一致」,
     * 只有超门限才叫「与模板不一致」——否则 PASS 判定下 HD=[2,0,1,1] 会被
     * 误报成「3/4 不一致」,与右上角大字判定自相矛盾(录像事故源)。 */
    const tau = v.thresholds?.tau_pass ?? 6;
    const mismatched = v.hd_per_response.some(h => h > tau);
    const nBad = v.hd_per_response.filter(h => h > tau).length;
    const box = document.createElement('div');
    box.className = 'hv-rdiff' + (mismatched ? ' has-diff' : '');
    const head = document.createElement('div');
    head.className = 'hv-rdiff-head';
    head.innerHTML = `<b>逐响应差异</b>
      <span class="chip ${mismatched ? 'red' : 'green'}">`
      + `${mismatched
          ? `${nBad} / ${v.hd_per_response.length} 个响应与模板不一致(HD>τ=${tau})`
          : `全部响应与模板一致(翻转位在噪声门限 τ=${tau} 内)`}</span>
      <span class="hint">数据源:verdict.hd_per_response[] × /api/viz/templates 模板响应(逐位 XOR 复算;τ=TAU_PASS 单响应门限)</span>`;
    box.append(head);

    if (v.hd_per_response.every(h => h === 0)) {
      const t = document.createElement('p');
      t.className = 'hv-empty';
      t.textContent = `HD 全 0(共 ${v.hd_per_response.length} 个响应)—— 无需差异高亮。`
        + `触发 S2 仿冒攻击可看到高亮效果。`;
      box.append(t);
      this.diffBox.append(box);
      return;
    }

    void this.ensureTemplates(run.terminal_id).then(() => {
      for (let i = 0; i < r1s.length && i < v.hd_per_response.length; i++) {
        const seed = seeds[i], resp = r1s[i];
        /* 桥侧模板键为小写 hex,帧解析出的 seed 为大写 —— 统一小写再查,
         * 否则每个 seed 都「查无此键」,面板永远显示「模板中无该 seed」。 */
        const tplHex = this.templates?.[String(run.terminal_id)]
          ?.responses?.[seed.toLowerCase()] ?? null;
        box.append(this.bitRow(i + 1, resp, tplHex, v.hd_per_response[i], seed, tau));
      }
      if (r1s.length === 0) {
        const t = document.createElement('p');
        t.className = 'hv-empty';
        t.textContent = '本轮帧序列里没有 RESPONSE_R1,无法做响应-模板比对。';
        box.append(t);
      }
    });

    this.diffBox.append(box);
  }

  private async ensureTemplates(tid: number): Promise<void> {
    if (this.templateTid === tid && this.templates) return;
    try {
      const raw = await api.getVizTemplates();
      /* 键统一小写(桥侧为小写;此处兜一层,防未来大小写漂移再炸查找) */
      const norm: typeof raw.terminals = {};
      for (const [tid, t] of Object.entries(raw.terminals)) {
        const responses: Record<string, string> = {};
        for (const [k, val] of Object.entries(t.responses)) responses[k.toLowerCase()] = val;
        norm[tid] = { responses, stability_mask: t.stability_mask };
      }
      this.templates = norm;
      this.templateTid = tid;
    } catch {
      this.templates = null;
    }
  }

  private bitRow(idx: number, respHex: string, tplHex: string | null,
                 claimedHd: number, seed: string, tau = 6): HTMLElement {
    const row = document.createElement('div');
    row.className = 'hv-bitrow';
    const d = tplHex ? bitDiff(tplHex, respHex) : null;
    const agree = d ? d.count === claimedHd : false;

    const head = document.createElement('div');
    head.className = 'hv-bitrow-head';
    head.innerHTML = `<b>响应 #${idx}</b>
      <span class="chip ${claimedHd <= tau ? 'green' : 'red'}" title="单响应噪声门限 τ=${tau}(TAU_PASS)">HD ${claimedHd}</span>`
      + (d ? `<span class="chip ${agree ? 'green' : 'amber'}"
        title="${agree ? '前端由模板逐位 XOR 复算的位数与桥接下发的 hd_per_response 完全一致 —— 说明该 HD 确实是从模板算出的'
          : '前端复算位数与桥接下发的 hd_per_response 不一致,须核对(可能模板在注册后被刷新)'}"
        >前端复算 ${d.count}${agree ? ' ✓口径一致' : ' ⚠ 与下发不一致'}</span>` : '')
      + `<span class="hint">seed ${seed}</span>`;
    row.append(head);

    const paint = (title: string, hex: string, other: string | null) => {
      const line = document.createElement('div');
      line.className = 'hv-bitline';
      const tag = document.createElement('span');
      tag.className = 'hv-bittag';
      tag.textContent = title;
      line.append(tag);
      const otherBytes = other ? hexBytes(other) : null;
      hexBytes(hex).forEach((by, bi) => {
        const cell = document.createElement('i');
        cell.className = 'mono';
        const otherByte = otherBytes?.[bi] ?? '';
        cell.textContent = by;
        if (otherByte !== '' && otherByte !== by) {
          cell.classList.add('diff');
          const dd = bitDiff(otherByte, by);
          cell.title = `第 ${bi + 1} 字节(0 基 ${bi})不同:${otherByte} → ${by}`
            + `;该字节内差异位(MSB first)${dd.bits.join(',')},共 ${dd.count} 位`;
        }
        line.append(cell);
      });
      return line;
    };
    row.append(paint('终端响应', respHex, tplHex));
    if (tplHex) row.append(paint('模板', tplHex, respHex));
    else {
      const p = document.createElement('p');
      p.className = 'hv-empty';
      p.textContent = '模板中无该 seed 的响应(未注册或已被重注册刷新)';
      row.append(p);
    }
    return row;
  }

  /* ---------------- golden ---------------- */
  private renderGolden(): void {
    this.pick.replaceChildren();
    this.body.replaceChildren();
    this.diffBox.replaceChildren();
    const gs = this.goldens;
    if (!gs) { this.note.textContent = '取黄金帧…'; return; }
    if (gs.length === 0) {
      this.note.textContent = '';
      const p = document.createElement('p');
      p.className = 'hv-empty';
      p.textContent = '黄金帧不可用(桥接不可达)。这 7 条取自 docs/protocol_contract.md §4,是固定回归输入。';
      this.body.append(p);
      return;
    }
    this.note.textContent = `${gs.length} 条黄金帧 · 固定真实向量(docs/protocol_contract.md §4)`;

    gs.forEach((g, i) => {
      const b = document.createElement('button');
      b.className = 'chip hv-chip' + (i === this.goldSel ? ' cyan' : '');
      b.setAttribute('aria-pressed', String(i === this.goldSel));
      b.textContent = g.name;
      b.addEventListener('click', () => { this.goldSel = i; this.renderGolden(); });
      this.pick.append(b);
    });
    const cmpBar = document.createElement('div');
    cmpBar.className = 'hv-cmpbar';
    cmpBar.innerHTML = `<span class="hint">逐字节对比基线(仅黄金帧之间 —— 与实时帧对比无意义,见报告 §6.2):</span>`;
    const sel = document.createElement('select');
    sel.className = 'hv-select';
    sel.append(new Option('（不对比)','-1'));
    gs.forEach((g, i) => sel.append(new Option(g.name, String(i))));
    sel.value = String(this.goldCmp);
    sel.addEventListener('change', () => { this.goldCmp = Number(sel.value); this.renderGolden(); });
    cmpBar.append(sel);
    this.pick.append(cmpBar);

    const g = gs[Math.min(this.goldSel, gs.length - 1)];
    const p = frameParts(g.hex);
    this.body.append(this.segmentBlock(g.hex, g.name,
      p?.len ?? 0, p && isUplink(p.msgId) ? 'term->server' : 'server->term', 'real-terminal'));
    const noteEl = document.createElement('p');
    noteEl.className = 'hv-goldnote';
    noteEl.textContent = g.note;
    this.body.append(noteEl);

    const cmpH = this.goldCmp >= 0 && this.goldCmp < gs.length ? gs[this.goldCmp] : null;
    if (cmpH && cmpH.hex !== g.hex) {
      const d = this.byteDiffBlock(g, cmpH);
      this.diffBox.append(d);
    }
  }

  private byteDiffBlock(a: GoldenFrame, b: GoldenFrame): HTMLElement {
    const box = document.createElement('div');
    box.className = 'hv-rdiff has-diff';
    const ab = hexBytes(a.hex), bb = hexBytes(b.hex);
    const diffs = ab.map((x, i) => (bb[i] !== undefined && bb[i] !== x ? i : -1)).filter(i => i >= 0);
    const head = document.createElement('div');
    head.className = 'hv-rdiff-head';
    head.innerHTML = `<b>逐字节 diff</b>
      <span class="chip amber">${diffs.length} 字节不同</span>
      <span class="hint">${a.name} 对比 ${b.name} · 长度 ${ab.length}B / ${bb.length}B</span>`;
    box.append(head);
    const grid = document.createElement('div');
    grid.className = 'hv-diffgrid';
    ab.forEach((x, i) => {
      const cell = document.createElement('i');
      cell.className = 'mono' + (diffs.includes(i) ? ' diff' : '');
      cell.textContent = x;
      if (diffs.includes(i)) cell.title = `字节 ${i}(0 基):${x} → ${bb[i] ?? '—'}`;
      grid.append(cell);
    });
    box.append(grid);
    if (diffs.length) {
      const p = document.createElement('p');
      p.className = 'hv-empty';
      p.textContent = `差异字节位序(0 基):${diffs.join(', ')}。`
        + `两条都是固定黄金向量,差异全部落在各自随机的载荷字段上 —— 这正是「不宜与实时帧做逐字节 diff」的原因。`;
      box.append(p);
    }
    return box;
  }
}

/* 小端 u32 读取(载荷为字节 hex 串数组) */
function leU32(payload: string[], off: number): number {
  let v = 0;
  for (let i = 3; i >= 0; i--) v = v * 256 + parseInt(payload[off + i] ?? '0', 16);
  return v;
}

/* 上行帧(终端→基站):ACCESS_REQUEST / RESPONSE_R1 / CONFIRM */
function isUplink(msgId: number): boolean {
  return msgId === 0x0090 || msgId === 0x0092 || msgId === 0x0094;
}
