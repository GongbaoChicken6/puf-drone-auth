/* ============================================================
 * MOCK 数据 —— 报告 §4.4/§8.4
 * 注意:console 的 mock 回放统一走桥接 --mock(报告 §0.1-6);
 * 本文件只提供 viz「内置样例」(显式 MOCK 徽章)与
 * console 开发期 ?mock=1 显式回放(顶栏 MOCK 徽章)。
 * 一切 MOCK 数据行前缀 MOCK。
 * ============================================================ */
import type { Envelope, FrameEvent, HdSeries, PayloadMap, Verdict, VizMeasurements } from './types';
import { MSG } from './types';

const T7 = 7;
let seq = 0;
const now = () => new Date().toISOString();
function env<K extends keyof PayloadMap>(type: K, payload: PayloadMap[K]): Envelope<PayloadMap[K]> {
  return { seq: seq++, ts: now(), type, payload };
}

/* S1 正常认证的完整事件回放(数字为演示值,非实测) */
export function mockS1Run(): Envelope[] {
  const run = 'mock-r1';
  const frames: [number, FrameEvent['dir'], string][] = [
    [MSG.ACCESS_REQUEST, 'term->server', 'FD10000001010A00009000' + '07000000' + '2B000000' + 'A1A2A3A4A5A6A7A8' + '0000'],
    [MSG.CHALLENGE, 'server->term', 'FD20000002010A00009100' + '11A0B1C2D3E4F506' + '22A0B1C2D3E4F506' + '33A0B1C2D3E4F506' + '44A0B1C2D3E4F506' + '0000'],
    [MSG.RESPONSE_R1, 'term->server', 'FD20000003010A00009200' + 'DEADBEEFDEADBEE0' + 'CAFEBABECAFEBAB0' + '0123456789ABCDF0' + 'FEDCBA9876543210' + '0000'],
    [MSG.RESULT, 'server->term', 'FD0A000004010A00009300' + '00' + '05' + '94AA595E54B0457B' + '0000'],
    [MSG.CONFIRM, 'term->server', 'FD05000005010A00009400' + '07000000' + '00' + '0000'],
  ];
  const out: Envelope[] = [env('link.status', { mode: 'loopback', connected: true, uptime_s: 42, proxy: true, version: 'mock' })];
  for (const [mid, dir, hex] of frames) {
    out.push(env(dir === 'server->term' ? 'frame.tx' : 'frame.rx', {
      run_id: run, terminal_id: T7, msg_id: mid,
      name: { [MSG.ACCESS_REQUEST]: 'ACCESS_REQUEST', [MSG.CHALLENGE]: 'CHALLENGE', [MSG.RESPONSE_R1]: 'RESPONSE_R1', [MSG.RESULT]: 'RESULT', [MSG.CONFIRM]: 'CONFIRM' }[mid]!,
      hex, len: hex.replace(/[^0-9A-F]/gi, '').length / 2, dir, source: 'simulated-terminal',
    }));
  }
  const v: Verdict = {
    run_id: run, terminal_id: T7, result: 0, result_name: 'PASS', n_responses: 4,
    hd: 5, hd_per_response: [1, 2, 1, 1], r2: 'MOCK-7B45B0545E59AA94',
    pool: { remaining: 484, pool_size: 500, pct: 96 },
    thresholds: { tau_pass: 6, tau_reject: 16, scaled_pass: 24, scaled_reject: 64 },
  };
  out.push(env('verdict', v));
  out.push(env('confirm.done', { run_id: run, terminal_id: T7, status: 0, verified_r2: true }));
  return out;
}

/* viz 内置样例(显式 MOCK):HD 双系列 0..48 环境下同设备集中、跨设备离散 */
export function mockHdSeries(): HdSeries {
  const intra: number[] = [], inter: number[] = [];
  let s1 = 12345, s2 = 67890;
  const rnd = () => { s1 = (s1 * 1103515245 + 12345) & 0x7fffffff; return s1 / 0x7fffffff; };
  const rnd2 = () => { s2 = (s2 * 1103515245 + 12345) & 0x7fffffff; return s2 / 0x7fffffff; };
  for (let i = 0; i < 400; i++) intra.push(Math.max(0, Math.round(2 + rnd() * 8)));
  for (let i = 0; i < 400; i++) inter.push(Math.max(0, Math.round(26 + rnd2() * 14)));
  // source:'MOCK' 写进字段而不是只写进图注 —— §4.4 要求非真数据必须可辨,而图注是
  // 渲染时才拼的文案,改版时最容易丢;字段则一路跟着数据走。
  return { intra, inter, source: 'MOCK', note: '页面内置样例:数据由本页伪随机生成,非实测' };
}

/* ------------------------------------------------------------------
 * viz 内置样例(显式 MOCK) —— 模板 / 多次测量 / 掩码三者**内部自洽**
 *
 * 为什么不再用 Math.random():§7.2 要求每图可导出,导出件会被放进报告。
 * 若每次刷新页面样例都变,同一份报告里的两张同名图会长得不一样 ——
 * 用固定种子的 LCG 生成,则「同一份 MOCK 样例」在任何机器任何时刻都相同,
 * 导出的图可复现、可对照。
 *
 * 为什么掩码要**由样例测量算出来**而不是手编一个好看的花纹:
 * 掩码是 V3 里唯一带判据的量(翻位率 ≤10%)。手编花纹会与 V4 的抖动自相矛盾,
 * 演示时一旦有人同时看 V3 和 V4 就会露馅。此处按与 template_db 相同的口径
 * 真算一遍,哪怕结果偏朴素 —— 朴素但自洽远胜好看但打架。
 * ------------------------------------------------------------------ */

/** 固定种子的线性同余发生器(LCG);仅用于生成 MOCK 样例 */
function lcg(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (Math.imul(s, 1103515245) + 12345) >>> 0;
    return s / 0x100000000;
  };
}

const MOCK_SEEDS_N = 16;
const MOCK_ROUNDS = 3;

/** 翻转响应中的第 bit 位(位 0 = 最低位,与 template_db 的掩码布局一致) */
function flipBit(chars: string[], bit: number): void {
  const idx = 15 - Math.floor(bit / 8);
  const v = parseInt(chars[idx], 16) ^ (1 << (bit % 8));
  chars[idx] = v.toString(16).toUpperCase();
}

export interface MockVizBundle {
  templates: { terminals: Record<string, { responses: Record<string, string>; stability_mask: string }> };
  measurements: VizMeasurements;
  /** 样例所对应的终端,供 V3/V4 的终端选择器使用 */
  tid: string;
}

export function mockVizBundle(): MockVizBundle {
  const rnd = lcg(0x5eed1234);
  const responses: Record<string, string> = {};
  const series: VizMeasurements['series'] = [];

  for (let s = 0; s < MOCK_SEEDS_N; s++) {
    // 器件真值:与样例 seed 一一对应,模拟真实 PUF 的确定性响应
    const truth: string[] = [];
    for (let b = 0; b < 8; b++) {
      truth.push(Math.floor(rnd() * 256).toString(16).padStart(2, '0').toUpperCase());
    }
    const truthArr = truth.join('').split('');
    const seed = `MOCKSEED${s.toString(16).padStart(2, '0').toUpperCase()}`;

    // 每次重复测量 = 真值翻转 0..3 位(量级与 §9「噪声期望约 1.3bit/64bit」同量纲)
    const samples: string[] = [];
    for (let r = 0; r < MOCK_ROUNDS; r++) {
      const chars = [...truthArr];
      const n = Math.floor(rnd() * 3.4);
      for (let k = 0; k < n; k++) flipBit(chars, Math.floor(rnd() * 64));
      samples.push(chars.join('').toLowerCase());
    }

    responses[seed] = majorityHex(samples);
    series.push({ seed, samples });
  }

  // 掩码按 template_db 的口径真算:每 seed 求每位的翻位率,跨 seed 平均,≤10% 判稳
  const rates = new Array(64).fill(0) as number[];
  for (const item of series) {
    for (let bit = 0; bit < 64; bit++) {
      const ones = item.samples.filter(s => bitOf(s, bit) === 1).length;
      rates[bit] += Math.min(ones, item.samples.length - ones) / item.samples.length;
    }
  }
  const stability_mask = rates.map(r => (r / series.length <= 0.1 ? '1' : '0')).join('');

  return {
    templates: { terminals: { '1': { responses, stability_mask } } },
    measurements: { terminal_id: 1, captured: true, series },
    tid: '1',
  };
}

/** 逐位多数投票(平票取 0,与 enroll.py majority_bytes 一致) */
function majorityHex(samples: string[]): string {
  let out = '';
  for (let i = 0; i < 16; i++) {
    let nib = 0;
    for (let b = 0; b < 4; b++) {
      const ones = samples.filter(s => (parseInt(s[i], 16) >> b) & 1).length;
      if (ones * 2 > samples.length) nib |= 1 << b;
    }
    out += nib.toString(16);
  }
  return out;
}

function bitOf(hex: string, bit: number): number {
  const idx = 15 - Math.floor(bit / 8);
  return (parseInt(hex[idx], 16) >> (bit % 8)) & 1;
}
