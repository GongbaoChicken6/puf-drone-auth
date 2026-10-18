/* ============================================================
 * 类型化 API 客户端 —— 报告 §8.4
 * - fetch 封装(POST 带 Content-Length 由浏览器处理)
 * - EventSource 订阅 SSE:指数退避 1s→30s,3 次失败降级 1s 轮询
 *   /api/status,重连后以 /api/status 全量重同步(seq 断档不回放)
 * ============================================================ */
import { dispatchPuf } from './bus';
import { EVENT_TYPES } from './types';
import type {
  AuthRequest, EnrollRequest, Envelope, GoldenFramesResponse, HdSeries,
  MlBundle, OkResponse, PayloadMap, ReliabilityData, SetKeyRequest,
  StatusResponse, RunResponse, VizMeasurements, VizTemplates,
} from './types';

const BASE = '/api';
const BACKOFF_MIN_MS = 1000, BACKOFF_MAX_MS = 30000;

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  getStatus: () => fetch(`${BASE}/status`).then(r => json<StatusResponse>(r)),
  getGoldenFrames: () => fetch(`${BASE}/golden-frames`).then(r => json<GoldenFramesResponse>(r)),
  getHd: (fresh = false) => fetch(`${BASE}/viz/hd${fresh ? '?fresh=1' : ''}`).then(r => json<HdSeries>(r)),
  getVizTemplates: () => fetch(`${BASE}/viz/templates`).then(r => json<VizTemplates>(r)),
  getMl: () => fetch(`${BASE}/viz/ml`).then(r => json<MlBundle>(r)),
  getReliability: () => fetch(`${BASE}/viz/reliability`).then(r => json<ReliabilityData>(r)),
  getMeasurements: (terminalId?: number) =>
    fetch(`${BASE}/viz/measurements${terminalId != null ? `?terminal_id=${terminalId}` : ''}`).then(r => json<VizMeasurements>(r)),

  auth: (body: AuthRequest) => post<RunResponse>('/auth', body),
  enroll: (body: EnrollRequest) => post<RunResponse>('/enroll', body),
  c2reset: (terminalId: number) => post<OkResponse>('/c2reset', { terminal_id: terminalId }),
  setkey: (body: SetKeyRequest) => post<OkResponse>('/setkey', body),
};

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return json<T>(res);
}

/* ---------- SSE 订阅(单页一个实例) ---------- */
export type SseState = 'connecting' | 'live' | 'reconnecting' | 'polling';

export interface SseOptions {
  onState?: (s: SseState) => void;
  onGap?: () => void;          // seq 断档/重连 → 调用方以 /api/status 全量重同步
  onPoll?: () => void;         // 3 次失败后的 1s 轮询降级;缺省复用 onGap
  /* 原始信封(含 seq/ts)回调。§6.2 的「导出本次运行 JSON」要的是**原始事件流**
   * 作为答辩证据附件,而 puf:* 总线只派发 payload —— 故在此另留一条原样通道。 */
  onEnvelope?: (env: Envelope<unknown>) => void;
}

export class SseClient {
  private es: EventSource | null = null;
  private state: SseState = 'connecting';
  private failures = 0;
  private backoff = 0;
  private retryTimer: number | null = null;
  private pollTimer: number | null = null;
  private lastSeq = -1;
  private opts: SseOptions;
  private closed = false;

  constructor(opts: SseOptions = {}) { this.opts = opts; this.open(); }

  get currentState(): SseState { return this.state; }

  private setState(s: SseState): void {
    if (this.state === s) return;
    this.state = s;
    this.opts.onState?.(s);
  }

  private open(): void {
    if (this.closed) return;
    this.clearTimers();
    this.setState(this.failures === 0 ? 'connecting' : 'reconnecting');
    const es = new EventSource(`${BASE}/events`);
    this.es = es;

    es.onopen = () => {
      this.failures = 0; this.backoff = 0;
      this.stopPolling();
      this.setState('live');
    };

    es.onerror = () => {
      // onerror 可能对同一实例连发多次;只让第一次生效,否则会排多个重连定时器
      if (this.es !== es) return;
      es.close();
      this.es = null;
      if (this.closed) return;
      this.failures++;
      if (this.failures >= 3) this.startPolling();
      const wait = Math.min(BACKOFF_MIN_MS * 2 ** this.backoff, BACKOFF_MAX_MS);
      this.backoff++;
      this.retryTimer = window.setTimeout(() => this.open(), wait);
    };

    // 桥接层把每帧写成具名事件(web_bridge.py:1233),故 onmessage 收不到;
    // 必须按 12 个 type 逐个监听。onmessage 仅作无名帧的兜底(与具名互斥,不会重复派发)。
    const handle = (ev: Event) => this.handleFrame((ev as MessageEvent).data);
    es.onmessage = handle;
    for (const t of EVENT_TYPES) es.addEventListener(t, handle);
  }

  private handleFrame(raw: string): void {
    try {
      const env = JSON.parse(raw) as Envelope<never> & { type: keyof PayloadMap };
      // seq 断档 → 调用方重同步后会把 lastSeq 交给 syncAt(),避免二次触发
      if (this.lastSeq >= 0 && env.seq > this.lastSeq + 1) this.opts.onGap?.();
      this.lastSeq = env.seq;
      this.opts.onEnvelope?.(env as Envelope<unknown>);
      dispatchPuf(env.type, env.payload);
    } catch { /* 非 JSON(如 ": ping" 注释行不会进 handle)忽略 */ }
  }

  /* 3 次失败后的降级:1s 轮询 /api/status(同时继续后台重试 SSE) */
  private startPolling(): void {
    if (this.pollTimer != null) return;
    this.setState('polling');
    const poll = this.opts.onPoll ?? this.opts.onGap;
    this.pollTimer = window.setInterval(() => { void poll?.(); }, 1000);
  }
  private stopPolling(): void {
    if (this.pollTimer != null) { clearInterval(this.pollTimer); this.pollTimer = null; }
  }

  private clearTimers(): void {
    if (this.retryTimer != null) { clearTimeout(this.retryTimer); this.retryTimer = null; }
    this.stopPolling();
  }

  close(): void {
    this.closed = true;
    this.clearTimers();
    this.es?.close();
    this.es = null;
  }
}
