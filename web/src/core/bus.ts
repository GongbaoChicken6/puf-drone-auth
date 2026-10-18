/* ============================================================
 * puf:* 事件总线 —— 报告 §8.5 SSE type → puf:* 全量映射
 * detail 一律为对应 SSE payload 原样;3D 模块(three/main.ts)
 * 与 2D 保底(stages/stage2d.ts)消费同一总线、数据同源
 * ============================================================ */
import type { PayloadMap } from './types';

/* SSE type → puf:* 事件名(frame.tx/frame.rx 合并为 puf:frame,dir 区分)。
 * as const 不可省:PufPayload 靠字面量类型把每个 puf:* 名反查回 payload 类型,
 * 一旦退化成 string,onPuf 的载荷就全变 never,订阅处会静默拿到 undefined。 */
export const PUF_EVENT = {
  'link.status': 'puf:link',
  'session.update': 'puf:session',
  'frame.tx': 'puf:frame',
  'frame.rx': 'puf:frame',
  'gray.extra': 'puf:gray',
  'verdict': 'puf:verdict',
  'replay.reject': 'puf:replay',
  'confirm.done': 'puf:confirm',
  'enroll.done': 'puf:enroll',
  'pool.warning': 'puf:pool',
  'server.log': 'puf:log',
  'run.error': 'puf:runerror',
} as const;

/* 舞台握手与舞台侧指令(§8.5:页面与 3D 模块的挂载契约)。
 * camera/shot 不属 SSE 契约,只在页面与 3D chunk 之间走 —— 后端永远看不到。 */
export const STAGE_READY = 'puf:stage.ready';   // 页面 DOM 就绪后广播
export const STAGE_TAKEN = 'puf:stage.taken';   // 3D 初始化成功
export const STAGE_ERROR = 'puf:stage.error';   // 3D 失败 → 2D 保底接管
export const STAGE_CAMERA = 'puf:stage.camera'; // 页面快捷键 1–4 → 相机预设
export const STAGE_SHOT = 'puf:stage.shot';     // 页面快捷键 F → 截图

type StageEvent = typeof STAGE_READY | typeof STAGE_TAKEN | typeof STAGE_ERROR
  | typeof STAGE_CAMERA | typeof STAGE_SHOT;

/* puf 名 → SSE type 的反向表(仅用于类型推导;puf:frame 反查得
 * 'frame.tx' | 'frame.rx',二者载荷同型,合并后仍是 FrameEvent) */
type SseOfPuf = { [K in keyof typeof PUF_EVENT as typeof PUF_EVENT[K]]: K };

export type PufEventName = keyof typeof PUF_EVENT extends never
  ? never
  : typeof PUF_EVENT[keyof typeof PUF_EVENT] | StageEvent;

export interface StageDetail {
  [STAGE_READY]: { mount: string };
  [STAGE_TAKEN]: { by: 'three' };
  [STAGE_ERROR]: { reason: string };
  [STAGE_CAMERA]: { preset: number };
  [STAGE_SHOT]: { name: string };
}

/* puf:* 事件名 → payload 类型 */
export type PufPayload<E extends PufEventName> =
  E extends keyof StageDetail ? StageDetail[E] :
  E extends keyof SseOfPuf ? PayloadMap[SseOfPuf[E] & keyof PayloadMap] :
  never;

/* 舞台是否已 ready(晚加载的 3D 模块查询,避免错过 ready 广播) */
let stageReadyFlag = false;
export function stageReady(): boolean { return stageReadyFlag; }

export function dispatchPuf<E extends keyof PayloadMap>(type: E, payload: PayloadMap[E]): void {
  window.dispatchEvent(new CustomEvent(PUF_EVENT[type], { detail: payload }));
}

export function emit<E extends StageEvent>(name: E, detail: StageDetail[E]): void {
  if (name === STAGE_READY) stageReadyFlag = true;
  window.dispatchEvent(new CustomEvent(name, { detail }));
}

/* 类型化订阅;返回解绑函数 */
export function onPuf<E extends PufEventName>(
  name: E, fn: (payload: PufPayload<E>, ev: Event) => void,
): () => void {
  const h = (ev: Event) => fn((ev as CustomEvent).detail as PufPayload<E>, ev);
  window.addEventListener(name, h as EventListener);
  return () => window.removeEventListener(name, h as EventListener);
}
