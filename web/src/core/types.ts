/* ============================================================
 * 契约类型 —— 报告 §8.2/§8.3 逐字段镜像(tsc 即合约)
 * 字段名/取值域与桥接层 web_bridge.py 一一对应,改动须双侧同步
 * ============================================================ */

/* ---------- SSE 信封(§8.3) ---------- */
export interface Envelope<T = unknown> {
  seq: number;      // 自增整数;断档触发 /api/status 重同步
  ts: string;       // ISO8601
  type: EventType;
  payload: T;
}

export type EventType =
  | 'link.status' | 'session.update' | 'frame.tx' | 'frame.rx'
  | 'gray.extra' | 'verdict' | 'confirm.done' | 'enroll.done'
  | 'pool.warning' | 'replay.reject' | 'server.log' | 'run.error'
  | 'channel.intrusion' | 'channel.noise'
  | 'poll.sent' | 'confirm.rejected' | 'base.spoof.suspected'
  | 'drone.state' | 'drone.attitude' | 'drone.cmd_ack' | 'drone.reject';

/* 运行期事件名清单(§8.3 表 11 行的 12 个原生死类 + finals-demo 扩展 5 类
 * + finals-demo-drone 扩展 4 类(drone.state/attitude/cmd_ack/reject),
 * 共 21 个 type —— frame.tx 与 frame.rx 同行但为两类)。
 * 桥接层把 SSE 帧写成**具名事件**(web_bridge.py:1233 `event: <type>`),
 * 因此 EventSource 的 onmessage 不会触发,订阅方必须按名 addEventListener;
 * 这里同时是审计日志过滤器的选项来源。新增事件类型须双侧同步(扩展时同步更新计数)。
 * satisfies 交叉约束 + 下方两条穷尽断言把四处一致性(EventType/EVENT_TYPES/
 * PUF_EVENT/PayloadMap)全部锁进编译期 —— 漏配任何一处 tsc 直接报错。 */
export const EVENT_TYPES = [
  'link.status', 'session.update', 'frame.tx', 'frame.rx',
  'gray.extra', 'verdict', 'confirm.done', 'enroll.done',
  'pool.warning', 'replay.reject', 'server.log', 'run.error',
  'channel.intrusion', 'channel.noise',
  'poll.sent', 'confirm.rejected', 'base.spoof.suspected',
  'drone.state', 'drone.attitude', 'drone.cmd_ack', 'drone.reject',
] as const satisfies readonly (EventType & keyof PayloadMap)[];

type _EventTypesExhaustive =
  Exclude<EventType, (typeof EVENT_TYPES)[number]> extends never ? true : never;
type _PayloadMapExhaustive =
  Exclude<EventType, keyof PayloadMap> extends never ? true : never;
/** 编译期穷尽检查锚点:改事件清单漏配任一处,这里的类型不再是 [true, true] */
const _eventTypeExhaustiveCheck: [_EventTypesExhaustive, _PayloadMapExhaustive] = [true, true];
void _eventTypeExhaustiveCheck;

/* ---------- 协议帧常量(protocol.py 口径) ---------- */
export const MSG = {
  ACCESS_REQUEST: 0x0090,
  CHALLENGE: 0x0091,
  RESPONSE_R1: 0x0092,
  RESULT: 0x0093,
  CONFIRM: 0x0094,
  EXTRA_CHALLENGE: 0x0095,
  AUTH_POLL: 0x0097,       // finals-demo N4: 基站主动巡检(板端等效 SW7)
} as const;

export const MSG_NAMES: Record<number, string> = {
  [MSG.ACCESS_REQUEST]: 'ACCESS_REQUEST',
  [MSG.CHALLENGE]: 'CHALLENGE',
  [MSG.RESPONSE_R1]: 'RESPONSE_R1',
  [MSG.RESULT]: 'RESULT',
  [MSG.CONFIRM]: 'CONFIRM',
  [MSG.EXTRA_CHALLENGE]: 'EXTRA_CHALLENGE',
  [MSG.AUTH_POLL]: 'AUTH_POLL',
};

/* 判定码(RESULT 帧 result 字段;main.py _RESULT_NAMES 同源) */
export type ResultCode = 0 | 1 | 2 | 3 | 4;
export const RESULT_CN: Record<ResultCode, string> = {
  0: '通过', 1: '拒绝', 2: '错误', 3: '池耗尽', 4: '重放嫌疑',
};

/* ---------- 事件 payload(§8.3 表逐行) ---------- */
export interface LinkStatus {
  mode: 'loopback' | 'serial';
  connected: boolean;
  uptime_s: number;
  proxy: boolean;           // 是否终端侧代演
  version?: string;         // 桥接版本(链路详情弹层)
}
export interface SessionUpdate {
  terminal_id: number;
  state: string;
  challenges_issued: number;
  responses_scored: number;
  hd_sum: number | null;
  last_decision: string | null;
}
export interface FrameEvent {
  run_id: string;
  terminal_id: number;
  msg_id: number;
  name: string;
  hex: string;
  len: number;
  dir: 'server->term' | 'term->server';
  source: 'simulated-terminal' | 'real-terminal';
}
export interface GrayExtra {
  run_id: string;
  terminal_id: number;
  seeds: string[];
  n: number;
}
export interface Thresholds {
  tau_pass: number; tau_reject: number;
  scaled_pass: number; scaled_reject: number;
}
export interface PoolState { remaining: number; pool_size: number; pct: number; }
export interface Verdict {
  run_id: string;
  terminal_id: number;
  result: ResultCode;
  result_name: string;
  n_responses: number;
  hd: number;                        // = min(Σ, 0xFE)
  hd_per_response: number[];
  r2?: string;                       // 仅 PASS
  pool: PoolState;
  thresholds: Thresholds;            // 桥接按本轮 n_responses 以 decide_scaled 口径下发
}
export interface ConfirmDone {
  run_id: string; terminal_id: number;
  status: number;                    // 0 = CONFIRM_OK
  verified_r2: boolean;
}
export interface EnrollDone {
  terminal_id: number;
  n_pairs: number; added: number;
  stable_bits: number;               // 分母 64(展示层标注)
  stability_pct: number;
  pool: PoolState;
}
export interface PoolWarning { terminal_id: number; remaining: number; pct: number; }
export interface ReplayReject { run_id: string; terminal_id: number; result: 4; }

/* N2(finals-demo): 站端专用方向帧(0x0091/0x0093/0x0095)出现在 RX 路径
 * —— 共享信道上疑似伪基站注入。来源 RealSerialListener._loop IDS 分支。 */
export interface ChannelIntrusion {
  msg_id: number;
  name: string;
  hex: string;
  len: number;
  note: string;
}

/* N2(finals-demo): 1s 滑窗内 >=3 次 resync —— 信道噪声洪泛疑似 DoS。
 * 限速发布(同窗只发一次);审计/记录用,横幅不消费。 */
export interface ChannelNoise {
  events: number;
  window_s: number;
  dropped_bytes: number;
  note: string;
}

/* N4(finals-demo): 巡检帧已发出(等效遥控 SW7)。 */
export interface PollSent {
  run_id: string;
  terminal_id: number;
  nonce: number;
}

/* N3(finals-demo): 终端回 CONFIRM_FAIL 拒认本站判决。 */
export interface ConfirmRejected {
  run_id: string;
  terminal_id: number;
  status: number;
  own_verdict: number;
  evidence: string;
}

/* N3(finals-demo): 矛盾关联告警——本站判 PASS 而终端拒认 = 疑似伪基站注入。 */
export interface BaseSpoofSuspected {
  run_id: string;
  terminal_id: number;
  own_verdict: 'PASS' | 'FAIL';   // 桥端发字面量(Python 侧该分支仅 PASS 判决可达)
  terminal_says: 'FAIL';
  evidence: string;
}
/* ---------- finals-demo-drone:无人机演示层事件 ---------- */
/* 飞行状态机:LANDED→ARMED→TAKEOFF→HOVER→MOVE→LAND/RTL(设计 §3.2)。 */
export type DroneFlightState =
  'LANDED' | 'ARMED' | 'TAKEOFF' | 'HOVER' | 'MOVE' | 'LAND' | 'RTL';

export interface DroneStateEvent {
  terminal_id: number;
  state: DroneFlightState;
  unlocked: boolean;          // 认证门控:verdict PASS 解锁,REJECT/上锁清除
  pos: [number, number, number];   // x=北, y=东, alt=高度(米)
  yaw: number;                // deg,北为 0
  reason?: string;            // 如 "verdict:0"
}
export interface DroneAttitudeEvent {
  terminal_id: number;
  state: DroneFlightState;
  x: number; y: number; alt: number;
  vx: number; vy: number; vz: number;
  roll: number; pitch: number; yaw: number;   // deg,演示级动力学
}
export interface DroneCmdAck { terminal_id: number; cmd: string; ok: boolean; reason?: string; }
export interface DroneReject { terminal_id: number; cmd: string; reason: string; }

export interface ServerLog { level: 'info' | 'warn' | 'error'; msg: string; }
export interface RunError { run_id: string; stage: string; error: string; terminal_id?: number | null; }

/* 事件 type → payload 类型映射 */
export interface PayloadMap {
  'link.status': LinkStatus;
  'session.update': SessionUpdate;
  'frame.tx': FrameEvent;
  'frame.rx': FrameEvent;
  'gray.extra': GrayExtra;
  'verdict': Verdict;
  'confirm.done': ConfirmDone;
  'enroll.done': EnrollDone;
  'pool.warning': PoolWarning;
  'replay.reject': ReplayReject;
  'server.log': ServerLog;
  'run.error': RunError;
  'channel.intrusion': ChannelIntrusion;
  'channel.noise': ChannelNoise;
  'poll.sent': PollSent;
  'confirm.rejected': ConfirmRejected;
  'base.spoof.suspected': BaseSpoofSuspected;
  'drone.state': DroneStateEvent;
  'drone.attitude': DroneAttitudeEvent;
  'drone.cmd_ack': DroneCmdAck;
  'drone.reject': DroneReject;
}

/* ---------- REST(§8.2) ---------- */
/* GET /api/status → sessions[]:逐字段镜像 HFIDAProtocol.status()(protocol.py:670) */
export interface SessionRow extends SessionUpdate {}

/* GET /api/status → templates[]:逐字段镜像 TemplateDB.status()(template_db.py:391),
 * 桥接层原样透传,不做归一 —— 故沿组员原生口径的两处反直觉之处必须显式记录:
 *   · terminal_id 是**字符串**(上游 self.terminals() 返回 str;见 template_db.py:383),
 *     templates[] 与 pools[] 的 tid 类型因此不同,比较前一律经 tidNum() 归一;
 *   · stable_bits 可为 **null**(该终端尚未算出稳定掩码时,上游返回 None)。
 * 注意 stability_pct 不是服务端字段,展示层由 stableBitsPct() 现算。 */
export interface TemplateRow {
  terminal_id: string;
  n_pairs: number;
  stable_bits: number | null;
}

/* GET /api/status → pools[]:桥接层由 CRPPool.status() 已归一(remaining_pct→pct,
 * 丢弃 available/used/state_file),与 SSE verdict.pool 同形,故复用 PoolState。 */
export interface PoolRow extends PoolState { terminal_id: number; }

export interface StatusResponse {
  link: LinkStatus;
  sessions: SessionRow[];
  templates: TemplateRow[];
  pools: PoolRow[];
  hsm: { available: boolean; keys: number };
  drone?: { tids: Record<string, DroneStateEvent> };   // finals-demo-drone:断档重同步
}
export interface GoldenFrame { name: string; hex: string; note: string; }
export interface GoldenFramesResponse { frames: GoldenFrame[]; }

export type AuthMode = 'normal' | 'spoof' | 'replay' | 'gray' | 'evilbase';
export interface AuthRequest { terminal_id: number; mode: AuthMode; }
export interface RunResponse { run_id: string; }
export interface EnrollRequest { terminal_id: number; n?: number; }
export interface OkResponse { ok: boolean; }
export interface SetKeyRequest { terminal_id: number; key_hex?: string; }
/* finals-demo-drone:POST /api/drone/cmd —— 200/409 都有 JSON 体(409=业务态)。 */
export interface DroneCmdRequest {
  terminal_id: number;
  cmd: 'arm' | 'disarm' | 'launch' | 'takeoff' | 'goto' | 'hold' | 'land' | 'rtl' | 'lock';
  x?: number; y?: number; alt?: number;   // goto 航点
}
export interface DroneCmdResponse { ok: boolean; state: DroneFlightState; reason?: string; }

/* viz 数据端点 */
/** B1:ML 攻击实验数据(/api/viz/ml;W4 真实产物,source=STATIC) */
export interface MlExpA {
  repro_command: string; seed: number;
  train_sizes: number[]; noise_rel: number[];
  bayes_acc: Record<string, number>;
  accuracy: Record<string, Record<string, number>>;
  conclusion_A?: string;
  security_declarations?: string[];
}
export interface MlExpBPoint {
  tau_mean: number; tau_std: number; exact_rate: number;
  pair_acc_mean: number; cycles_mean: number;
}
export interface MlExpB {
  repro_command: string; seed: number;
  n_sweep: number[]; flip_levels: number[]; n_trials: number;
  aggregated: Record<string, Record<string, MlExpBPoint>>;
}
export interface MlBundle {
  source: string; a: MlExpA | null; b: MlExpB | null;
  note?: string; errors?: Record<string, string>;
}

/** B2:reliability 模型曲线(/api/viz/reliability;source=MODEL) */
export interface ReliabilityPoint { scale: number; mean_hd: number; max_hd: number; pass_rate: number; }
export interface ReliabilityData {
  source: string; points: ReliabilityPoint[];
  params?: { terminal_id: number; n_seeds: number; jitter_pct: number; scales: number[]; flip_prob: string };
  note?: string;
}

export interface HdSeries {
  intra: number[];
  inter: number[];
  /** 桥接写的口径说明(离线样本的采样时间/tid/加 ?fresh=1 等);MOCK 模式下是免责声明 */
  note?: string | null;
  /**
   * 这串数**是何时、由谁**算出来的 —— 与 intra/inter 同源的溯源字段(报告 §9)。
   *   SAMPLE = 读 tools/sample_hd.py 的落盘样本(桥接已校验模板与器件两端签名)
   *   LIVE   = 本次请求现算(缺省走样本,?fresh=1 或样本失效时落到这里)
   *   MOCK   = 桥接 --mock 模式 / 页面内置样例,非实测(§4.4 强制标注)
   * SAMPLE 与 LIVE 都是**真实测量**,差别只在何时算的:故它不进导出文件名的数据源
   * 标记(srcTag),只作 V1 的注记 —— 否则会与内置样例的 mock 标记撞车。
   * 可选:导入的 JSON 文件由第三方提供,没有这个字段。
   */
  source?: 'SAMPLE' | 'LIVE' | 'MOCK';
}
export interface VizTemplates {
  /** 这批模板从哪来(见 HdSeries.source 同款三态);导入文件没有此字段 */
  source?: 'SAMPLE' | 'LIVE' | 'MOCK';
  terminals: Record<string, { responses: Record<string, string>; stability_mask: string }>;
}
export interface VizMeasurements {
  terminal_id: number | null;
  captured: boolean;
  source?: 'SAMPLE' | 'LIVE' | 'MOCK';
  series: { seed: string; samples: string[] }[];   // samples = 每次重复测量的响应 hex(不是 HD)
  note?: string;
}

/* ---------- UI 本地辅助类型 ---------- */
export type LinkBadgeState = 'LOOPBACK' | 'SERIAL' | 'RECONNECTING' | 'OFFLINE';
export type SourceBadge = 'REAL-STATIC' | 'REAL-LIVE' | 'MOCK';
