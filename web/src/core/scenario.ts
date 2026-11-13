/* ============================================================
 * 演示剧本 S1–S7 —— 报告 §6.3 / §6.4
 *
 * 边界声明:本模块**不产生任何演示数据**,只按剧本顺序调用桥接的 REST 端点
 * (POST /api/auth|enroll|c2reset|setkey)。事件的真实产生方是桥接层的
 * ScenarioEngine,它复用组员的公共 API 与真实算法。前端在此仅做「节奏器」:
 *  · 每幕按 run_id 等**真实终态事件**到达再推进,不使用固定延迟蒙混过关
 *    (固定延迟会在慢机上让两幕叠在一起,录屏时后果明显);
 *  · 找不到对应事件流时退回超时兜底,剧本不会卡死。
 *
 * S5 的「反复认证至抽干」由本模块循环驱动 —— 因为它是「同一动作重复到某结果」
 * 而非单次调用,桥接侧无对应单端点;循环在 result=3 或达上限时终止。
 * ============================================================ */
import { store } from './store';
import type { AuthMode, DroneCmdRequest, DroneFlightState } from './types';

export type ScenarioId = 'S1' | 'S2' | 'S3' | 'S4' | 'S5' | 'S6' | 'S7' | 'S8';

export interface Scenario {
  id: ScenarioId;
  name: string;
  /* 空表示该幕不是单次 auth 调用(见 kind) */
  mode: AuthMode | null;
  kind: 'auth' | 'enroll' | 'drain' | 'drone';
  /* 指定终端;null = 跟随当前选中终端 */
  tid: number | null;
  focus: string;      // UI 焦点(§6.3 表末列,用于工具条 tooltip 与日志)
  expect: string;     // 预期事件序列(工具条 tooltip)
}

/* 单幕终态等待上限。串口模式帧超时 3s(§6.4),叠加编排开销给到 8s;
 * 超时只记一条日志并继续下一幕,不中断剧本。 */
const RUN_TIMEOUT_MS = 8000;
const DRAIN_MAX = 24;          // S5 抽干循环上限(池容量 20,留余量)

export const SCENARIOS: readonly Scenario[] = [
  {
    id: 'S1', name: '正常认证', mode: 'normal', kind: 'auth', tid: null,
    focus: '五帧全绿 + 大字 PASS + R2',
    expect: 'ACCESS_REQUEST → CHALLENGE → RESPONSE_R1 → RESULT(PASS) → CONFIRM(OK)',
  },
  {
    id: 'S2', name: '仿冒攻击', mode: 'spoof', kind: 'auth', tid: null,
    focus: '大字 REJECT + 逐响应 HD 差异高亮',
    expect: '同上但 RESULT(REJECT)',
  },
  {
    id: 'S3', name: '重放攻击', mode: 'replay', kind: 'auth', tid: null,
    focus: '琥珀警示 + 日志高亮',
    expect: '旧 C2 重发 → RESULT(result=4 重放嫌疑)',
  },
  {
    id: 'S4', name: '灰区加测', mode: 'gray', kind: 'auth', tid: null,
    focus: 'EXTRA_CHALLENGE 分支展开动画',
    expect: 'CHALLENGE → RESPONSE → gray.extra(加测) → RESULT',
  },
  {
    id: 'S5', name: '池耗尽', mode: 'normal', kind: 'drain', tid: 99,
    focus: '池水位空 + 维护引导',
    expect: '反复认证至 draw 失败 → RESULT(result=3 池耗尽)',
  },
  {
    id: 'S6', name: '注册刷新', mode: null, kind: 'enroll', tid: null,
    focus: '左栏卡片刷新',
    expect: 'POST /api/enroll → enroll.done(n_pairs / added / stable bits)',
  },
  {
    id: 'S7', name: '假基站', mode: 'evilbase', kind: 'auth', tid: null,
    focus: '双向拒绝另一半:终端侧 BLOCKED',
    expect: 'RESULT(PASS 但 R2 被篡改) → 终端侧 BLOCKED(不发 CONFIRM)',
  },
  {
    /* finals-demo-drone:认证解锁飞行(设计 §4.5)。mode 字段对 drone 幕
     * 仍是 'normal'(第一拍先跑真认证);每步等真实 drone.state 终态推进,
     * 与其他幕同一"等终态不蒙延迟"纪律。 */
    id: 'S8', name: '认证解锁飞行', mode: 'normal', kind: 'drone', tid: null,
    focus: 'PASS 解锁 → 起飞 → 航点A → 返航降落',
    expect: 'verdict(PASS) → drone.state(TAKEOFF→HOVER→MOVE→HOVER→RTL→LANDED)',
  },
] as const;

export function scenarioById(id: ScenarioId): Scenario {
  return SCENARIOS.find(s => s.id === id)!;
}

export interface ScenarioDeps {
  /* 返回桥接下发的 run_id(null = 调用失败,已由入口记日志) */
  auth(terminalId: number, mode: AuthMode): Promise<string | null>;
  enroll(terminalId: number): Promise<void>;
  /* finals-demo-drone:S8 的飞控指令入口(REST /api/drone/cmd)。
   * 返回指令是否被接受(false=409/网络失败,S8 据此熔断,content-review P2)。 */
  drone(terminalId: number, cmd: DroneCmdRequest['cmd'],
        extra?: { x?: number; y?: number }): Promise<boolean>;
}

export type PlayerState = 'idle' | 'running' | 'paused';

export interface PlayerStatus {
  state: PlayerState;
  queue: ScenarioId[];
  index: number;          // 正在跑/即将跑的那一幕的下标
  current: ScenarioId | null;
}

const delay = (ms: number) => new Promise<void>(r => window.setTimeout(r, ms));

export class ScenarioPlayer {
  private deps: ScenarioDeps;
  private queue: ScenarioId[] = [];
  private index = 0;
  private state: PlayerState = 'idle';
  private stopFlag = false;
  private listeners = new Set<(s: PlayerStatus) => void>();

  constructor(deps: ScenarioDeps) { this.deps = deps; }

  onChange(fn: (s: PlayerStatus) => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  status(): PlayerStatus {
    return {
      state: this.state, queue: [...this.queue], index: this.index,
      current: this.state === 'idle' ? null : (this.queue[this.index] ?? null),
    };
  }

  private emit(): void { const s = this.status(); this.listeners.forEach(f => f(s)); }

  /* 修复(按钮审计 P2-3):代际令牌。play/resume/stop/step 递增 gen,使旧异步
   * 循环在下一个检查点自然失效,杜绝运行中重复触发的「双 loop 并发、
   * 同幕双发 POST、共享 index 双 ++ 跳幕」。 */
  private gen = 0;

  /* 连播:入队并立即开始 */
  play(ids: ScenarioId[]): void {
    this.queue = [...ids];
    this.index = 0;
    this.stopFlag = false;
    this.gen++;
    this.state = 'running';
    this.emit();
    void this.loop(this.gen);
  }

  /* 逐帧(逐幕)单步:暂停态下推一幕 */
  step(ids?: ScenarioId[]): void {
    if (this.state === 'running') { this.pause(); return; }
    /* P3(按钮审计 N6):idle 空队列单步不再进入「暂停 0/0」死态 —— 给可见提示 */
    if (this.queue.length === 0 && !ids) {
      store.log({
        tone: 'replay', sev: 'warn', terminalId: null, runId: null, type: 'server.log',
        text: '单步需要先有剧本:点任一场景键或连播,暂停后即可逐幕单步。',
      });
      return;
    }
    if (ids && this.queue.length === 0) this.queue = [...ids];
    if (this.index >= this.queue.length) this.index = 0;
    this.stopFlag = false;
    this.gen++;
    this.state = 'paused';
    this.emit();
    void this.advanceOne(this.gen);
  }

  pause(): void {
    if (this.state !== 'running') return;
    this.state = 'paused';
    this.emit();
  }

  resume(): void {
    if (this.state !== 'paused') return;
    this.stopFlag = false;
    this.gen++;
    this.state = 'running';
    this.emit();
    void this.loop(this.gen);
  }

  stop(): void {
    this.stopFlag = true;
    this.gen++;
    this.state = 'idle';
    this.queue = [];
    this.index = 0;
    this.emit();
  }

  private async loop(g: number): Promise<void> {
    while (this.state === 'running' && this.index < this.queue.length && g === this.gen) {
      await this.advanceOne(g);
      if (this.stopFlag || g !== this.gen) return;
    }
    if (this.index >= this.queue.length && this.state === 'running') {
      this.state = 'idle';
      this.index = 0;
      this.emit();
    }
  }

  /* finals-demo-drone:轮询 store.drones 等飞行终态(150ms 粒度)。
   * 窗口取 RUN_TIMEOUT_MS×4:飞行链长于单次认证。
   * 返回是否等到终态(false=超时/被新代际取代,S8 据此熔断,content P2)。 */
  private async waitDroneState(tid: number, states: readonly DroneFlightState[],
                               g: number): Promise<boolean> {
    const t0 = performance.now();
    while (performance.now() - t0 < RUN_TIMEOUT_MS * 4) {
      const d = store.snapshot.drones.get(tid);
      if (d && states.includes(d.state)) return true;
      if (this.stopFlag || g !== this.gen) return false;
      await delay(150);
    }
    store.log({
      tone: 'replay', sev: 'warn', terminalId: tid, runId: null, type: 'server.log',
      text: `S8:等待无人机状态 ${states.join('/')} 超时。`,
    });
    return false;
  }

  /* 执行一幕并等待其终态事件;返回后 index 指向下一幕 */
  private async advanceOne(g: number = this.gen): Promise<void> {
    const id = this.queue[this.index];
    if (id == null) return;
    if (g !== this.gen) return;                 // 代际已失效:让位给新循环
    const s = scenarioById(id);
    this.emit();

    const tid = s.tid ?? store.snapshot.selectedTerminal;
    if (tid == null) {
      store.log({
        tone: 'error', sev: 'error', terminalId: null, runId: null,
        type: 'run.error', text: `${s.id} 无法执行:没有可用终端(请先注册或等待 bootstrap)`,
      });
      this.index++;
      this.emit();
      return;
    }

    // 舞台按 run_id 锁定当前选中终端(§6.4),故执行前先把选中切到本幕目标,
    // 否则 S5(终端 99)的事件会被判为非选中终端而只进日志、不进舞台。
    store.select(tid);
    store.log({
      tone: 'info', sev: 'info', terminalId: tid, runId: null, type: 'server.log',
      text: `▶ ${s.id} ${s.name} —— 焦点:${s.focus}`,
    });

    switch (s.kind) {
      case 'enroll':
        await this.deps.enroll(tid);
        await delay(1200);      // enroll.done 异步到达,留出进度态可见时间
        break;
      case 'drain': {
        for (let i = 0; i < DRAIN_MAX && !this.stopFlag && g === this.gen
          && (this.state === 'running' || this.state === 'paused'); i++) {
          const runId = await this.deps.auth(tid, s.mode!);
          await this.waitRunEnd(runId, g);
          const r = store.snapshot.run;
          if (r?.verdict?.result === 3) break;      // 抽干达成
          if (this.state === 'paused') break;
        }
        break;
      }
      case 'auth': {
        const runId = await this.deps.auth(tid, s.mode!);
        await this.waitRunEnd(runId, g);
        break;
      }
      case 'drone': {
        /* finals-demo-drone(S8):认证解锁 → 起飞 → 航点A → 航点B → 返航
         * (spec §4.5,content-review P2 补 B 拍)。每步等**真实** drone.state
         * 终态;任一拍指令被拒或超时即**熔断本幕**(content-review P2:原版
         * 链断后三拍各空等 32s,合计 64~96s 假死画面),红字提示后收尾。 */
        const runId = await this.deps.auth(tid, s.mode!);
        await this.waitRunEnd(runId, g);
        const fly = async (cmd: DroneCmdRequest['cmd'],
                           extra: { x?: number; y?: number } | undefined,
                           until: readonly DroneFlightState[]): Promise<boolean> => {
          if (!(await this.deps.drone(tid, cmd, extra))) return false;
          return this.waitDroneState(tid, until, g);
        };
        /* 可重入预拍:上次飞行残态先收敛回地面,否则 launch 必 409 触发熔断
         * (content-review e2e 实证:悬停态点 S8 → BAD_STATE:HOVER → 熔断)。 */
        const d0 = store.snapshot.drones.get(tid);
        if (d0 && d0.state !== 'LANDED' && d0.state !== 'ARMED') {
          if (d0.state === 'TAKEOFF') await fly('land', undefined, ['LANDED']);
          else if (d0.state === 'HOVER' || d0.state === 'MOVE') await fly('rtl', undefined, ['LANDED']);
          else await this.waitDroneState(tid, ['LANDED'], g);   // RTL/LAND 收尾中
        }
        const chainOk = await fly('launch', undefined, ['HOVER'])
          && await fly('goto', { x: 5, y: -2 }, ['HOVER'])
          && await fly('goto', { x: -3, y: 4 }, ['HOVER'])
          && await fly('rtl', undefined, ['LANDED']);
        if (!chainOk) {
          store.log({
            tone: 'error', sev: 'error', terminalId: tid, runId: null,
            type: 'server.log',
            text: 'S8 已中止:飞控指令被拒或状态超时(见上方琥珀行)。检查认证是否 PASS、无人机是否处于可起飞状态。',
          });
        }
        break;
      }
    }

    if (!this.stopFlag && g === this.gen) {
      await delay(2000);        // 让判定大字与舞台动效停留可见(700→2000:连播时 PASS/REJECT 定格足够入镜)
      if (g !== this.gen) return;               // 停留期间被新循环取代
      this.index++;
      this.emit();
    }
  }

  /* 等该 run 的终态事件真的到达(verdict 非 PASS 时 endedAt 即判定时刻;
   * PASS 要等 CONFIRM 闭环)。超时兜底保证剧本不卡死。 */
  private waitRunEnd(runId: string | null, g: number = this.gen): Promise<void> {
    if (!runId) return delay(600);
    return new Promise<void>(resolve => {
      const t0 = performance.now();
      const tick = () => {
        if (this.stopFlag || g !== this.gen) { resolve(); return; }
        const r = store.snapshot.run;
        if (r && r.run_id === runId && r.endedAt != null) { resolve(); return; }
        if (performance.now() - t0 > RUN_TIMEOUT_MS) { resolve(); return; }
        window.setTimeout(tick, 60);
      };
      tick();
    });
  }
}

/* 顶栏剧本键的预设队列(§6.4:默认 S1→S2 互斥叙事,亦可全场景) */
export const QUEUE_MUTEX: ScenarioId[] = ['S1', 'S2'];
export const QUEUE_ALL: ScenarioId[] = SCENARIOS.map(s => s.id);
