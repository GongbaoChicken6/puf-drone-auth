# 决赛演示 · 无人机飞控演示层（站端模拟 Lite）实现设计（2026-11-12）

> 决策链：需求（前端显示 + 板端有反应，不接真实无人机组件）→ 调研报告
> `D:/文件/ssssssss/FPGA/RESEARCH_drone_flight_components_20261112.md` §5 L1/L2 →
> 用户拍板走精简版。本设计 = L1 核心 + L2 顺风车（复用已落地的 N4 `/api/poll`）。
> **零 RTL、零线上协议改动、零 CI BOARD_LOCK 影响、零重新固化**。

---

## 0. 基线（2026-11-12 晚实测）

- 分支 `finals-demo`，HEAD 829d77c（串口竞态修复 b8461af 已并入：serial_bus_lock/auth_in_progress 忙拒/_do_poll 移入 Orchestrator，suite 141 passed）或更新，A 层站端功能全部完成：N2/N3/N4(站端)/N6/N9/N10。并行对话下一步=B 层批次R（纯 RTL，与本方案零交集）。
- RTL 批次R（N1/N3/N4 板侧）未动，`src/rtl` 无 0x0097。板上解锁路径现状 = SW7 物理按键；
  批次R 落地后追加"巡检"按钮（前端 `terminal-card.ts` 已有按钮 + `api.poll` 已通）。
- 前端事件契约是**四处编译期锁死**的（`types.ts` L27-42 satisfies + 两条穷尽断言；
  `EVENT_TYPES`/`PayloadMap`/`PUF_EVENT`/`EventType`），新增事件必须四处同步，否则 tsc 报错。
- `SSEHub.publish`（web_bridge.py 方法体 L127-154）自带锁，工作线程直接 publish 是既有惯例
  （Orchestrator worker、RealSerialListener 线程均如此）。
- **另一对话正在同分支活跃开发**（dist 20:56 刚重建）：本方案全部新逻辑进新文件，
  共享文件只做最小侵入（见 §7 写域表）。

## 1. 目标 / 非目标

**目标**
- G1 桥端无人机模拟引擎：per-tid 飞行状态机 + 确定性运动学（20Hz），纯 Python。
- G2 认证门控：verdict PASS 解锁飞行权；REJECT/重放/拒认 → 上锁（把飞控绑进 PUF 主线叙事）。
- G3 REST `/api/drone/cmd` + 4 个 `drone.*` SSE 事件 + `/api/status` 增量重同步字段。
- G4 前端：3D 舞台无人机按遥测飞行（位置/偏航/滚转/俯仰），HUD 姿态仪 + 指令面板，
  2D 保底可降级；npm run build + 截图（铁律4）。
- G5 演示剧本 S8「认证解锁→起飞→航点→返航」一键化。
- G6 pytest 全绿 + 证据落盘 `data/d1_evidence/finals_demo/drone/`（铁律1）。

**非目标**：任何 RTL/线上帧改动；MAVLink 实帧/QGC（L3 预留，见调研报告 §3）；
不影响既有 18 项 CI 与 135 个 pytest 用例语义。

## 2. 架构总览

```
浏览器 console.html
  ├─ drone-panel.ts(新,右下悬浮) ── HUD姿态仪+按钮 ──POST /api/drone/cmd──┐
  ├─ stage3d.ts  无人机网格按 drone.attitude 飞行;光束端点跟随             │
  └─ store.ts    drones 状态;SSE 断档→/api/status.drone 重同步            │
        ▲ SSE: drone.state / drone.attitude / drone.cmd_ack / drone.reject │
web_bridge.py                                                            ▼
  ├─ SSEHub(+tap,§3.1) ──tap队列──▶ drone_sim.py(新,§3.2)
  │     publish("verdict"/"confirm.rejected"/…)        DroneSim 20Hz tick
  └─ RealApp / MockApp 各持一个 DroneSim 实例(loopback 演示同样可飞)
板子(ZC706)：不改动。解锁输入 = SW7 真认证(现状) / AUTH_POLL(批次R后)；
             板上 DS9 busy→DS8 绿 = 评委可见的"板端反应"。
```

## 3. 后端规格

### 3.1 SSEHub 增加内部 tap（web_bridge.py，唯一的基础设施改动）

`verdict` 的 publish 点有多个（loopback `_emit_verdict` L592、真板 RealSerialListener
L2122、Mock 回放），逐点挂钩必漏。改为 **hub 侧单一 choke point**：

```python
# SSEHub.__init__ (L107 附近) 追加:
self._taps: list[Queue] = []

# SSEHub 新增方法 (subscribe 旁):
def add_tap(self) -> "Queue":
    """内部事件引出线:DroneSim 等站内消费者用,不入 SSE 客户端计数。
    复用 publish 的锁与丢旧保新策略;tap 消费者不得在回调内再 publish
    (锁递归)——DroneSim 在自己线程里出队后再发布。"""
    q: Queue = Queue(maxsize=512)
    with self._lock:
        self._taps.append(q)
    return q

# SSEHub.publish (方法体 L127-154;锁内、L154 return 前) 追加:
for q in self._taps:
    try:
        q.put_nowait(env)
    except Exception:          # queue.Full: 丢最旧保最新(与 SSE 客户端同策略)
        try:
            q.get_nowait(); q.put_nowait(env)
        except Exception:
            pass
```

### 3.2 新文件 `web/bridge/drone_sim.py`（全部新逻辑，约 260 行）

坐标系：本地米制，x=北、y=东、alt=高度（向上为正，事件面向前端直读）。
姿态由速度增量推导（演示级动力学，确定性、无随机源——可单测复现）：

```python
"""DroneSim —— 决赛演示层无人机模拟器(finals-demo drone lite)。

纯站端:不改线上协议、不碰 RTL。认证门控经 SSEHub tap 监听 verdict,
PASS(=0) 解锁、非 PASS 上锁——"认证解锁飞行权"的演示主线。
线程模型:add_tap 出队 + 20Hz 物理tick 共用一个工作线程;command() 由
HTTP 线程调用,与 tick 经 self._lk 互斥;hub.publish 线程安全(web_bridge.py publish 锁 L128)。
"""
import math, threading, time
from queue import Empty, Queue

FLYING = ("TAKEOFF", "HOVER", "MOVE", "LAND", "RTL")
STATES = ("LANDED", "ARMED", "TAKEOFF", "HOVER", "MOVE", "LAND", "RTL")
P = dict(vmax=2.0, climb=1.0, acc=1.5, yaw_rate=90.0,     # m/s, m/s², deg/s
         takeoff_alt=3.0, land_v=0.6, wp_eps=0.15, bank_max=22.0)

class _St:                                            # per-tid 状态
    __slots__ = ("state", "unlocked", "x", "y", "alt", "vx", "vy", "vz",
                 "yaw", "roll", "pitch", "wp", "wp_alt", "att_acc")
    def __init__(self):
        self.state, self.unlocked = "LANDED", False
        self.x = self.y = self.alt = self.vx = self.vy = self.vz = 0.0
        self.yaw = self.roll = self.pitch = 0.0
        self.wp, self.wp_alt = None, P["takeoff_alt"]
        self.att_acc = 0.0                            # per-tid 遥测节流累加器(R1-P1-3)

class DroneSim:
    TICK = 0.05
    def __init__(self, hub, clock=time.monotonic, autostart: bool = True):
        # autostart=False 供单测:零线程、零套接字、零网络 —— CI-safe
        # (批次R 对话的 ci_regression.ps1 会收编 tests/ 全量 pytest,用例不得
        # 绑端口/留常驻线程/外网/超时长;协调点②,2026-11-12)
        self._hub, self._clock = hub, clock
        self._lk = threading.Lock()
        self._st: dict[int, _St] = {}
        self._tap: Queue = hub.add_tap()
        self._th = threading.Thread(target=self._loop, name="drone-sim",
                                    daemon=True)
        if autostart:
            self._th.start()

    # ---- 事件入口(tap 出队;单测可直接调 _on_event) ----
    def _loop(self):
        while True:
            try:
                env = self._tap.get(timeout=self.TICK)
                self._on_event(env.get("type"), env.get("payload") or {})
            except Empty:
                pass
            with self._lk:
                for tid, st in list(self._st.items()):   # 快照迭代(R1-P1-4:防 command() 新建 tid 时 dict 变更)
                    self._step(tid, st, self.TICK)          # 纯物理,无IO

    def _on_event(self, etype, pl):
        if etype != "verdict":
            return
        tid = int(pl.get("terminal_id", -1))
        res = int(pl.get("result", -1))
        with self._lk:                                # setdefault 必须在锁内(R1-P1-4)
            st = self._st.setdefault(tid, _St())
            was = st.unlocked
            st.unlocked = (res == 0)
            if not st.unlocked and st.state in FLYING:
                st.state = "LAND"                     # 认证失效自动降落(R2-P1:REJECT 后不得悬空拒管)
            if was != st.unlocked:
                self._hub.publish("drone.state",
                                  self._state_ev(tid, st, reason=f"verdict:{res}"))

    # ---- REST 入口(HTTP 线程调用) ----
    def command(self, tid, cmd, x=None, y=None, alt=None) -> dict:
        with self._lk:                    # 全程锁内:setdefault 不落在 _loop 迭代窗口(R1-P1-4)
            st = self._st.setdefault(tid, _St())
            if cmd not in ("arm", "disarm", "launch", "takeoff", "goto",
                           "hold", "land", "rtl", "lock"):
                return {"ok": False, "reason": f"UNKNOWN_CMD:{cmd}",
                        "state": st.state}            # 失败分支也带 state(R1-P2-4)
            if cmd == "goto" and (x is None or y is None):
                return {"ok": False, "reason": "BAD_PARAM:x,y required",
                        "state": st.state}            # goto 缺参显式拒绝(R1-P1-1)
            if not st.unlocked and cmd != "lock":
                ev = {"terminal_id": tid, "cmd": cmd, "reason": "AUTH_REQUIRED"}
                self._hub.publish("drone.reject", ev)       # 门控:未认证
                return {"ok": False, **ev, "state": st.state}
            ok, reason = self._transition(st, cmd, x, y, alt)
            self._hub.publish("drone.cmd_ack",
                              {"terminal_id": tid, "cmd": cmd, "ok": ok,
                               **({"reason": reason} if reason else {})})
            self._hub.publish("drone.state", self._state_ev(tid, st))
            return {"ok": ok, "reason": reason, "state": st.state}

    # ---- 状态转移表(单测锚点) ----
    def _transition(self, st, cmd, x, y, alt) -> tuple[bool, str | None]:
        T = {"arm":     (("LANDED",), "ARMED"),
             "launch":  (("LANDED",), "TAKEOFF"),
             "takeoff": (("ARMED",), "TAKEOFF"),
             "hold":    (("HOVER", "MOVE"), "HOVER"),   # HOVER 幂等(R1-P2-3)
             "land":    (("HOVER", "MOVE", "RTL", "TAKEOFF"), "LAND"),  # RTL 中止/爬升中止(R1-P2-3)
             "rtl":     (("HOVER", "MOVE"), "RTL")}
        if cmd == "lock":
            st.unlocked = False
            if st.state in FLYING: st.state, st.wp = "LAND", (0.0, 0.0)
            return True, None
        if cmd == "disarm":
            if st.state != "ARMED": return False, f"BAD_STATE:{st.state}"
            st.state = "LANDED"; return True, None
        if cmd == "goto":
            if st.state not in ("HOVER", "MOVE"): return False, f"BAD_STATE:{st.state}"
            st.state, st.wp = "MOVE", (float(x), float(y))
            st.wp_alt = float(alt) if alt is not None else max(st.alt, P["takeoff_alt"])
            return True, None
        src, dst = T[cmd]                              # (源态元组, 目标态)
        if st.state not in src:
            return False, f"BAD_STATE:{st.state}"
        if cmd in ("launch", "takeoff"): st.wp = None
        if cmd == "rtl": st.wp = (0.0, 0.0)
        st.state = dst
        return True, None

    # ---- 物理步进(确定性;dt 显式传入,单测不sleep) ----
    def _step(self, tid, st, dt):
        if st.state == "LANDED":
            return
        pvx, pvy = st.vx, st.vy
        g = 9.8
        if st.state in ("TAKEOFF", "LAND") or st.state in ("HOVER", "MOVE", "RTL"):
            tgt_v = [0.0, 0.0]
            if st.state == "TAKEOFF":
                st.vz = +P["climb"]
                if st.alt >= P["takeoff_alt"]:
                    st.vz, st.state = 0.0, "HOVER"
                    self._publish_state(tid, st)
            elif st.state == "LAND":
                st.vz = -P["land_v"]
                if st.alt <= 0.0:
                    st.alt = st.vz = st.vx = st.vy = 0.0
                    st.state = "LANDED"
                    self._publish_state(tid, st)
            elif st.state in ("MOVE", "RTL"):
                dx, dy = st.wp[0] - st.x, st.wp[1] - st.y
                d = math.hypot(dx, dy)
                if d <= P["wp_eps"]:
                    st.state = "HOVER" if st.state == "MOVE" else "LAND"
                    self._publish_state(tid, st)
                else:
                    tgt_v = [P["vmax"] * dx / d, P["vmax"] * dy / d]
                    st.yaw = math.degrees(math.atan2(dx, dy))   # 航向朝目标
            # 速度朝目标一阶趋近(限加速)
            for i, (v, tv) in enumerate(((st.vx, tgt_v[0]), (st.vy, tgt_v[1]))):
                dv = max(-P["acc"] * dt, min(P["acc"] * dt, tv - v))
                if i == 0: st.vx = v + dv
                else:      st.vy = v + dv
            st.x += st.vx * dt; st.y += st.vy * dt
            st.alt = max(0.0, st.alt + st.vz * dt)
            # 姿态:横向加速度 → 滚转/俯仰(演示级,不声称飞控)
            ax, ay = (st.vx - pvx) / dt, (st.vy - pvy) / dt
            st.roll  = max(-P["bank_max"], min(P["bank_max"],
                          math.degrees(math.atan2(-ax, g))))
            st.pitch = max(-P["bank_max"], min(P["bank_max"],
                          math.degrees(math.atan2(ay, g))))
        self._maybe_attitude(tid, st)

    # ---- 事件/快照 ----
    def _state_ev(self, tid, st, reason=None):
        ev = {"terminal_id": tid, "state": st.state, "unlocked": st.unlocked,
              "pos": [round(st.x, 2), round(st.y, 2), round(st.alt, 2)],
              "yaw": round(st.yaw, 1)}
        if reason: ev["reason"] = reason
        return ev
    def _publish_state(self, tid, st):
        self._hub.publish("drone.state", self._state_ev(tid, st))
    def _maybe_attitude(self, tid, st):                     # per-tid 10Hz 节流(R1-P1-3)
        if st.state not in FLYING:
            st.att_acc = 0.0
            return                                      # LANDED/ARMED 不发 attitude,状态由 drone.state 覆盖
        st.att_acc += self.TICK
        if st.att_acc < 0.1:
            return
        st.att_acc = 0.0
        self._hub.publish("drone.attitude", {
            "terminal_id": tid, "state": st.state,
            "x": round(st.x, 2), "y": round(st.y, 2), "alt": round(st.alt, 2),
            "vx": round(st.vx, 2), "vy": round(st.vy, 2), "vz": round(st.vz, 2),
            "roll": round(st.roll, 1), "pitch": round(st.pitch, 1),
            "yaw": round(st.yaw, 1)})
    def snapshot(self) -> dict:                             # /api/status 用
        with self._lk:
            return {"tids": {str(t): self._state_ev(t, s)
                             for t, s in self._st.items()}}
```

设计说明（防审查误判）：
- `drone.state` 载荷含 `pos/yaw`，`/api/status` 的 `drone` 字段直接复用 `snapshot()`
  ——SSE 断档后前端一次 GET 即恢复，无需补发 attitude 历史。
- 遥测节流是 **per-tid** 累加器（`_St.att_acc`）：多终端同时飞行互不饥饿
  （R1-P1-3 修正；单测双 tid 固定 dt 断言各自帧数）。LANDED/ARMED 不发 attitude，
  状态变化由 `drone.state` 事件覆盖。
- `launch` = arm+takeoff 合并便利命令（演示节奏：一键起飞）。
- 板上 SW13 复位对桥不可见：PASS 解锁后若物理复位，解锁态保持——已知边界，
  演示剧本用"上锁"按钮或再跑一次仿冒认证（REJECT→自动上锁）收尾，写入 §9 口径。

### 3.3 web_bridge.py 集成点（六小点，全部最小侵入）

```python
# ① 文件头 import 区(现有 import 块尾):
#    ⚠ 既有测试用 importlib.spec_from_file_location 加载本文件(test_channel_ids.py
#    L29-39),sys.path 不含本目录——必须先注入再 import,否则 ModuleNotFoundError
#    且 V2 门禁必挂(R1-P1-2)。
_BRIDGE_DIR = Path(__file__).resolve().parent
if str(_BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_DIR))
from drone_sim import DroneSim

# ② RealApp.__init__ (L1017 起,末尾;并行开发会漂移,以 class RealApp 语义锚定位):
self.drone = DroneSim(self.hub)

# ③ MockApp.__init__ (L1399 起,末尾): 同样一行 —— loopback/mock 演示路径一致
self.drone = DroneSim(self.hub)

# ④ 两个 App 各加一个薄方法(REST 面):
def drone_cmd(self, tid: int, cmd: str, body: dict) -> dict:
    return self.drone.command(tid, cmd, body.get("x"), body.get("y"), body.get("alt"))

# ⑤ status() 两处各加一行(RealApp L1162 返回 dict / MockApp status):
"drone": self.drone.snapshot(),

# ⑥ BridgeHandler.do_POST 路由表(/api/demo/reset(L1658)之后):
if path == "/api/drone/cmd":
    cmd = str(body.get("cmd", ""))
    r = app.drone_cmd(int(body["terminal_id"]), cmd, body)
    return self._json(r, 200 if r.get("ok") else 409)
```

不走 Orchestrator Job 的理由：drone 指令是自包含内存操作（DroneSim 自带锁，
不触碰 protocol/串口/文件），与"REST 面全部经编排器串行化"注释针对的
protocol 状态类操作不同源——写进代码注释防后人误改。

### 3.4 /api/drone/cmd 契约

请求 `{"terminal_id": 1, "cmd": "goto", "x": 5, "y": -3, "alt": 3}`；
响应 `{"ok": true|false, "state": "...", "reason"?: "..."}`，拒绝时 HTTP 409。
`reason` 枚举：`AUTH_REQUIRED`（未认证，同时发 `drone.reject` SSE）、`BAD_STATE:<cur>`（状态机拒绝）、`BAD_PARAM:x,y required`（goto 缺参）、`UNKNOWN_CMD:<cmd>`。所有失败分支均带 `state` 字段（与 DroneCmdResponse 一致）。

## 4. 前端规格（web/src）

### 4.1 types.ts —— 四处一致性（编译期锁，L29-42 断言会强制核对）

```ts
// EventType 联合(types.ts L14-19 定义处)追加 'drone.state'|'drone.attitude'|'drone.cmd_ack'|'drone.reject'
// EVENT_TYPES 数组(L29)追加 4 项(17→21;types.ts L21-23 计数注释同步改;api.ts L109
// 计数注释已被并行对话改为不写死数字,无需再动):
'drone.state', 'drone.attitude', 'drone.cmd_ack', 'drone.reject',

// 新类型(文件内 FrameEvent 等定义区之后):
export type DroneFlightState =
  'LANDED' | 'ARMED' | 'TAKEOFF' | 'HOVER' | 'MOVE' | 'LAND' | 'RTL';
export interface DroneStateEvent {
  terminal_id: number; state: DroneFlightState; unlocked: boolean;
  pos: [number, number, number]; yaw: number; reason?: string;
}
export interface DroneAttitudeEvent {
  terminal_id: number; state: DroneFlightState;
  x: number; y: number; alt: number;
  vx: number; vy: number; vz: number;
  roll: number; pitch: number; yaw: number;      // deg
}
export interface DroneCmdAck { terminal_id: number; cmd: string; ok: boolean; reason?: string; }
export interface DroneReject { terminal_id: number; cmd: string; reason: string; }
export type DroneSnapshot = DroneStateEvent;      // /api/status.drone.tids 值型

// PayloadMap(L183)追加:
'drone.state': DroneStateEvent;
'drone.attitude': DroneAttitudeEvent;
'drone.cmd_ack': DroneCmdAck;
'drone.reject': DroneReject;

// StatusResponse(L223)追加:
drone?: { tids: Record<string, DroneSnapshot> };

// 新请求体类型(AuthRequest 旁):
export interface DroneCmdRequest { terminal_id: number; cmd: string; x?: number; y?: number; alt?: number; }
export interface DroneCmdResponse { ok: boolean; state: DroneFlightState; reason?: string; }
```

### 4.2 bus.ts / api.ts / store.ts

```ts
// bus.ts PUF_EVENT 表追加(SSE type → puf:*):
'drone.state': 'puf:drone-state',
'drone.attitude': 'puf:drone-attitude',
'drone.cmd_ack': 'puf:drone-ack',
'drone.reject': 'puf:drone-reject',

// api.ts api 对象(poll 行旁)追加 —— 专用不抛错封装(R1-P2-1:既有 post→json()
// 在 !res.ok 时直接 throw,409 响应体里的 reason 会被丢弃,面板拿不到拒绝原因):
droneCmd: async (body: DroneCmdRequest): Promise<DroneCmdResponse> => {
  const res = await fetch(`${BASE}/drone/cmd`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  // 200/409 都读响应体;仅网络级失败(响应体读不出)才走 catch 兜底
  return res.json().catch(() => ({ ok: false, state: 'LANDED' as const,
    reason: `HTTP ${res.status}` }));
},

// store.ts AppState 追加字段:
drones: Map<number, DroneSnapshot & { att?: DroneAttitudeEvent }>;
// Store 增加三个方法(复刻 upsertTerminal 模式 L139-144):
upsertDrone(id: number, patch: Partial<...>) / ingestDroneStatus(snap) / clearDroneAtt()
```

`main-console.ts` 三处装配：总线汇聚区加 4 个 `onPuf` 订阅（drone-state→upsert、
drone-attitude→存 att、drone-ack→审计日志行、drone-reject→审计日志行）；
既有 /api/status 汇入点 `store.hydrateFromStatus`（main-console.ts L266 一带）
加 `drone` 字段 ingestion；IdsBanner 挂载点（L76）之后追加
`document.body.appendChild(new DronePanel().el)`。

### 4.3 新组件 `components/drone-panel.ts`（右下悬浮 HUD，约 180 行）

复刻 `ids-banner.ts` 的自订阅组件模式（L18-23）。布局：
```
┌ 无人机演示 HUD · tid <选中> ────────────┐
│ [状态徽章: 🔒未解锁/待命/起飞/悬停/巡航/降落/返航]  │
│ ┌姿态仪(SVG人工地平仪)┐  alt 3.0 m       │
│ │  roll ±22° 倾斜     │  v   1.8 m/s    │
│ │  pitch 俯仰刻度     │  yaw  045°      │
│ └────────────────────┘  pos  (2.1,-1.0) │
│ [解锁起飞] [航点A] [航点B] [悬停] [返航] [降落] [上锁] │
│ (未解锁时按钮区显示: 先认证解锁 —— SW7 或 巡检)      │
└─────────────────────────────────────────┘
```
- 姿态仪：SVG 圆形人工地平仪（天蓝/地棕两半 + roll 旋转 + pitch 平移 +
  中心固定飞机符号），纯 `transform` 动画（复刻 N6 FrameFlight 的
  transform-only 动画纪律，commit a122fc2）。
- 按钮回调 `api.droneCmd`（不抛错封装）；`ok:false` → 面板闪红行显示 `reason`
  （`AUTH_REQUIRED`→"未认证，飞行已锁定"；`BAD_STATE:<s>`→"当前状态不可用:<s>"；
  `BAD_PARAM:*`→"缺航点参数"；`drone.reject` SSE 到达时红条强调）。
- **按态禁用按钮**（与 §3.2 转移表逐格镜像，R1-P2-3/R2-P2 重写）：

  | 状态 | 解锁起飞 | 航点A/B | 悬停 | 返航 | 降落 | 上锁 |
  |------|---------|---------|------|------|------|------|
  | LANDED(未解锁) | 禁+提示"先认证" | 禁 | 禁 | 禁 | 禁 | 禁 |
  | LANDED(已解锁) | ✓ | 禁 | 禁 | 禁 | 禁 | ✓ |
  | ARMED | 禁 | 禁 | 禁 | 禁 | 禁 | ✓ |
  | TAKEOFF | 禁 | 禁 | 禁 | 禁 | ✓(中止爬升) | ✓ |
  | HOVER | 禁 | ✓ | ✓(幂等) | ✓ | ✓ | ✓ |
  | MOVE | 禁 | ✓ | ✓ | ✓ | ✓ | ✓ |
  | RTL | 禁 | 禁 | 禁 | 禁 | ✓(中止返航) | ✓ |
  | LAND | 禁 | 禁 | 禁 | 禁 | 禁(进行中) | ✓ |

  依据：goto/hold/rtl 源态=(HOVER,MOVE)；land 源态=(HOVER,MOVE,RTL,TAKEOFF)；lock 恒可用。
- 按钮回调外层仍包 try/catch（R2-P3-5）：droneCmd 的 catch 只兜响应体解析，
  fetch 网络级 reject（桥不可达）由回调捕获 → 按钮置灰 2s + 面板提示"桥不可达"。
  （演示桥在本机，风险备注级，与既有 api 层裸 fetch 惯例一致。）
- 选中 tid 绑定 `store.snapshot.selectedTerminal`；无选中时面板置灰。

### 4.4 stage3d.ts 无人机驱动

`Stage3d` 类内新增（不外溢到 scene.ts 的 World 结构，World 只加两个方法）：
```ts
// Stage3d 字段/构造(节选):
private droneAt: DroneAttitudeEvent | null = null;
onPuf('puf:drone-state', p => { if (this.isSel(p.terminal_id))
  this.world.setDroneState(p.state, p.unlocked); });          // 徽章/光环配色
onPuf('puf:drone-attitude', p => { if (this.isSel(p.terminal_id)) this.droneAt = p; });

// 渲染循环(既有 Clock 每帧):
if (this.droneAt) {
  const a = this.droneAt;
  const sx = THREE.MathUtils.clamp(ANCHOR.drone.x + a.y, -11, 12); // 东→+x
  const sz = THREE.MathUtils.clamp(a.x, -8, 8);                    // 北→+z
  const sy = ANCHOR.drone.y + a.alt;                               // 1.85+alt
  this.world.setDronePose(sx, sy, sz, a.yaw, a.roll, a.pitch);
  this.droneRx.set(sx, ANCHOR.corridorY, sz);   // 光束端点跟随(原 const 改实例字段)
}
```
- `World.setDronePose(x,y,z,yawDeg,rollDeg,pitchDeg)`：`droneGroup.position` +
  `rotation`（yaw 绕 Y、roll/pitch 小角度倾斜）。**必须门控既有待机浮动动画**
  （R1-P2-2）：scene.ts L576-578 每帧无条件覆写 `position.y/rotation.z/rotation.x`，
  与 setDronePose 同帧竞争会把无人机钉回锚点——World 加 `dronePoseActive` 标志
  （首次 setDronePose 置位，不回退），L576-578 包进 `if (!this.dronePoseActive)`；
  悬停呼吸浮动改由 setDronePose 在 HOVER 态叠加 ±0.05 sin 相位。
  `setDroneState(state, unlocked)`：`droneLabel` 文案（`无人机 · HOVER · alt 3.0m`）
  + `droneHalo` 配色（未解锁灰、待命蓝、飞行绿）。
- 模块级 `STATION_TX/DRONE_RX/DRONE_HIT/MID` 四常量（L47-50）改为实例字段并
  在无人机移动后重算——光束端点在 stage3d.ts L246-247 附近内联构造（无独立
  fx.beam 方法），verdict 特效（L259）等引用点同步换到实例字段。
- 2D 保底（`stage2d.ts`）：无人机状态以文字徽章呈现于 2D 舞台角标（
  3D 失败时 HUD 数字面板仍在，演示不空窗）。

### 4.5 演示剧本 S8（scenario.ts）

ScenarioId 联合(L17)加 `'S8'`；`Scenario` 的 kind 联合加 `'drone'`；`ScenarioPlayer` 构造参数加
`drone: (tid: number, cmd: string, extra?: object) => void` 回调（main-console
提供，内部调 api.droneCmd）；S8 定义：
```ts
{ id: 'S8', name: '认证解锁飞行', mode: 'normal', kind: 'drone', tid: null,
  focus: 'PASS 解锁 → 起飞 → 航点 → 返航降落',
  expect: 'verdict(PASS) → drone.state(TAKEOFF→HOVER→MOVE→RTL→LANDED)' },
```
播放逻辑：先按既有 auth 幕等 verdict PASS，再依次 launch → goto(A) → goto(B) →
rtl，每幕等 `drone.state` 到达预期态（复用 RUN_TIMEOUT_MS 超时兜底纪律）。
快捷键：main-console.ts L388 的 `/^[1-7]$/` 正则改为 `/^[1-8]$/`，帮助浮层同步加 S8；
**topbar.ts** 的 `TopbarDeps.onPlay` 场景 id 字面量联合 `('S1'|…|'S7')[]` 放宽含
`'S8'`（协调点③——tsc 会兜住,提前改省一轮 build 失败）。（本节行号为 2026-11-12 晚快照,实施前 rebase 后以语义锚校准。）

## 5. 验证计划（铁律映射）

| # | 验证 | 确切命令/动作 | 预期 | 证据 |
|---|------|---------------|------|------|
| V1 | 单测 | `cd D:\puf-drone-auth && python -m pytest tests/test_drone_sim.py -q` | 全绿（≥10 用例，含 4b/4c/4d/4e 回归） | 输出贴 run log |
| V2 | 全量回归 | `python -m pytest tests/ -q` | 141+新增 全绿（2026-11-12 晚基线 141） | 同上 |
| V3 | 桥联调 | 起桥 `python web/bridge/web_bridge.py --mock --port 8642`；① `curl -s -X POST http://127.0.0.1:8642/api/drone/cmd -H "Content-Type: application/json" -d "{\"terminal_id\":7,\"cmd\":\"launch\"}"`（未认证）② `curl -s -X POST .../api/auth -d "{\"terminal_id\":7,\"mode\":\"normal\"}"` 等 2s ③ 复跑① | ① 409 `ok:false,reason:AUTH_REQUIRED`（带 state）③ `ok:true,state:TAKEOFF` | 终端记录 |
| V4 | 前端构建 | `cd web && npm run build`（tsc --noEmit && vite build） | 零错误，dist 更新 | build log |
| V5 | 页面截图 | playwright-cli open http://127.0.0.1:8642 → mock S1 认证 PASS → 面板「解锁起飞」→航点→ screenshot（步骤4 时 S8 未落地，用面板按钮手动飞；步骤6 后可改跑 S8 一键链） | HUD/3D 无人机飞行可见 | `data/d1_evidence/finals_demo/drone/*.png` |
| V6 | 板上联调 | 真串口模式：SW7 认证 PASS → 解锁起飞；仿冒认证 → 自动上锁 | 闭环可演示 | 照片/视频 |

单测清单（`tests/test_drone_sim.py`，复刻 test_poll_message.py 的仓库根运行约定）：
1. verdict PASS 解锁 / REJECT 上锁（tap 事件直灌 `_on_event`）
2. 未解锁 launch → ok:False + reason=AUTH_REQUIRED + hub 收到 drone.reject
3. 状态机全转移表（ARMED→TAKEOFF→HOVER→MOVE→RTL→LAND→LANDED；HOVER 态 hold 幂等；RTL/TAKEOFF 态 land 中止；HOVER 态 arm→BAD_STATE 拒绝）
4. 运动学确定性：固定 dt 步进 N=64（3.2s）断言 alt≈3.0、goto 到达 wp_eps 内、
   rtl 回 (0,0)、roll/pitch 有界 ±22°
4b. goto 缺 x/y → ok:False、reason=BAD_PARAM、带 state（R1-P1-1 回归）
4c. 双 tid 同时飞行：固定 dt 各步进 40 tick，两 tid 的 drone.attitude 帧数各 ≥3
    （R1-P1-3 per-tid 节流回归）
4d. 快照迭代不变量：驱动 list(self._st.items()) 迭代中并发 command() 新建 tid
    不抛 dict-changed（R1-P1-4 回归）
4e. 飞行中 REJECT verdict → unlocked=False 且 state=LAND 自动降落
    （R2-P1 回归：认证失效不得悬空拒管）
5. `snapshot()` 形状与 /api/status 集成（FakeHub 复刻 test_channel_ids 构造法）
6. SSEHub.add_tap：publish 后 tap 队列收到同一 envelope（seq 单调）

## 6. 实施顺序（半天 + 半天~1天）

| 步 | 内容 | 改动面 | 依赖 |
|----|------|--------|------|
| 1 | SSEHub tap + drone_sim.py + 单测 V1/V2 | 新文件 + web_bridge.py §3.1/§3.3 | — |
| 2 | REST/status 集成 + V3 联调 | web_bridge.py §3.3 其余小点(②-⑥) | 1 |

  ⚠ 提交纪律（协调点①）：步骤 1+2 合并为**单一提交**落地——drone_sim.py 必须与
  web_bridge.py 的 import 同 commit（或更早），否则 exec_module 整体加载
  web_bridge 的既有测试（test_channel_ids/test_poll_bridge）在中间态当场红。
  单测一律 DroneSim(hub, autostart=False) + FakeHub 直驱 _on_event/_step，
  零线程零端口（V3 的 curl/起桥属手测，不进 pytest）。
| 3 | types/bus/api/store 四处契约 + 前端订阅 | 4 文件小改 | 2 |
| 4 | drone-panel.ts + V4/V5 | 新文件 + main-console 2 行 | 3 |
| 5 | stage3d 驱动 + World 两方法 + 2D 保底 | stage3d/scene/stage2d | 3 |
| 6 | S8 剧本 + Shift+8 | scenario.ts + main-console | 4 |
| 7 | 板上联调 V6（排练日） | — | 批次R 无依赖（SW7 即可） |

## 7. 协作与冲突（同分支多对话）

| 文件 | 本方案改动 | 冲突面 | 纪律 |
|------|-----------|--------|------|
| web/bridge/web_bridge.py | §3.3 六小点（约 24 行，含 sys.path 注入①） | 另一对话正在加 N5 录入 | 动手前 `git pull --rebase`；只加不改既有行；不修改 test_channel_ids.py（其 importlib 加载由 §3.3① 显式兼容） |
| web/src/core/types.ts / bus.ts / store.ts / api.ts | 各 1-4 行追加 | N5 向导可能加事件 | 同上；四处一致性由 tsc 编译期锁兜底 |
| web/src/main-console.ts | import+挂载+订阅约 10 行 | N5 面板挂载 | 同上 |
| web/bridge/drone_sim.py、components/drone-panel.ts、tests/test_drone_sim.py | 新文件 | 无 | 独占写域 |
| stage3d.ts / scene.ts / stage2d.ts | §4.4 限定区域 | N6 已收尾(a122fc2) | 低 |

## 8. 风险登记

- **多对话同文件冲突**：写域表 §7 + rebase 纪律；必要时请用户串行排班。
- **SSE 10Hz 遥测在慢机积压**：hub 已有丢旧保新（QUEUE_CAP 定义 L60/subscribe 使用 L114/丢旧保新主体 L136-145）
  + 慢客户端两级断开——drone 事件走同一通道，无需新机制；drone.attitude 10Hz×47B 远低于带宽。
- **demo_start.ps1(N9) 不感知 drone**：无影响——drone 面板随 console.html 自然加载；
  S8 进剧本条即可，N9 不改。
- **mock 模式 verdict 流**：MockApp 场景回放发 verdict（status L1419 列出）——
  tap 对 mock 同样生效，loopback 也能演示解锁飞行（V3/V5 依赖此）。
- **--mock 纪律（B1/B2）**：drone_sim 不读仓库数据、不写盘——符合 mock 零数据面约束。

## 9. 诚实边界与答辩口径

- 口径：**"飞行动力学为站端演示层仿真（20Hz 确定性模型），板上运行真实 PUF 认证
  与指令门控（PASS 解锁飞行权）"**。不得宣称飞控跑在 FPGA 内。
- 已知边界：板上 SW13 复位对桥不可见，解锁态不随物理复位撤销；演示收尾用
  "上锁"按钮或仿冒认证显式闭环——REJECT/上锁在飞行态均自动转 LAND 就地降落（§3.2
  _on_event 与 _transition lock 分支），无人机不会悬空拒管。

## 10. 审查记录（auto-review）

### R1（ar-plan-drone-r1，2026-11-12）判定 FAIL → 已全部修复
- P1-1 goto 缺 x/y 校验 → §3.2 command() 显式 BAD_PARAM 分支 + §3.4 枚举 + 单测 4b
- P1-2 模块级 import 打挂 importlib 加载的既有测试 → §3.3① sys.path 注入 + §7 写域说明
- P1-3 _att_acc 跨 tid 共享致遥测饥饿 → per-tid _St.att_acc + 单测 4c
- P1-4 command() 锁外 setdefault 可致迭代 RuntimeError 杀死线程 → 全程锁内 + 快照迭代 + 单测 4d
- P2-1 409 时 api.post 抛错丢 reason → §4.2 droneCmd 不抛错专用封装
- P2-2 scene.ts L576-578 待机浮动每帧覆写姿态 → dronePoseActive 门控 + HOVER 呼吸相位替代
- P2-3 转移表与面板按钮错配（hold 幂等/RTL 中止降落/TAKEOFF 中止）→ 转移表源态扩展 + 按态禁用矩阵
- P2-4 UNKNOWN_CMD 分支缺 state 字段 → 失败分支统一带 state
- P3 EVENT_TYPES 计数 17→21（api.ts L109 过期注释一并修）；锚点漂移 5 处（publish L127-154、
  demo/reset L1640、IdsBanner 挂载 L76、hydrateFromStatus L254-255、Shift 正则 L377/fx.beam 措辞）；
  V5 笔误 mcok→mock + 步骤序说明；V3 补完整 curl 序列

### R2（ar-plan-drone-r2，2026-11-12）判定 FAIL（1×P1+1×P2+5×P3）→ 已全部修复
- R1 九项复验 8 PASS / 1 FAIL（P2-3 按钮矩阵）→ 本轮重写为 8 状态×6 按钮逐格矩阵
- P1 §11 剧本第 5→6 步矛盾（REJECT 锁死后"返航"必 409）→ _on_event 飞行中失去认证
  自动 LAND + §9/§11 改写 + 单测 4e
- P2 按钮矩阵与转移表错配（TAKEOFF 并组 / RTL 行自相矛盾）→ 完整矩阵 + 源态尾注
- P3 §3.3 标题计数 4→六小点；docstring publish 锚点 L118→L128；§8 QUEUE_CAP 锚点
  （L60/L114/L136-145）；§4.5 ScenarioId 联合 + §4.1 EventType 联合显式列出；
  droneCmd 网络 reject 由面板 try/catch 兜底并写明

### R3（ar-plan-drone-r3，2026-11-12）判定 FAIL（1×P1+3×P3）→ 已全部修复
- R2 复验 7 项中 6 项 PASS；按钮矩阵逐格一致、代码块终读无新逻辑 bug、锁序/链路全通
- P1 §11 第 6 步残留矛盾：落地态(LANDED)直接点"返航"必 BAD_STATE:LANDED →
  改为"重新认证解锁 → 解锁起飞升空 → 返航"，并注明 LANDED 态 rtl 被拒的原理
- P3 §6 步骤2 计数与 §3.3 对齐(其余小点②-⑥)；六处行号锚点按并行开发后现状
  校准(L1017/L1399/L1162/L1658/L266/L388)并注明语义锚纪律；api.ts L109 过期
  注释已被并行对话移除,计划相应删改
- 审查员预判："修掉该句+3条P3后即可过线"。3 轮上限已用尽,按 auto-review 规则
  升级用户裁决;如需形式 PASS 判定可追加第 4 轮快速确认

### 内容审查（auto-review Mode 2，2026-11-13 上午）判定链：FAIL → 全修 → PASS_WITH_NOTES → P3 清零

- **六路审查**（复用 r1/r2/r3 + 新派 type/test，共识由 Lead 内联去重）：R1 全体 FAIL——
  P1×1（面板"解锁起飞"键 LANDED 态发 takeoff 必 409，e2e 全走探针/S8 未点过按钮=盲区实证）、
  P2×9（droneAtt 无清空路径、S8 拒后不熔断 64-96s 死画、S8 缺航点 B 拍、dist 未提交、
  4d 测试空转、墙钟修复零回归、goto alt 垂直通道未测、脏 verdict 幻影 tid、lock 就地语义未钉）、
  P3×14（引擎/前端/测试硬化项）。
- **修复**：1da9719+8e6c20a（355+/79-）；引擎加 stop() 生命周期+shutdown 挂钩；测试 14→20
  （161 passed 全绿）；e2e 补真实按钮点击（08）与可重入 S8 全链（09）。
- **复审 R2（r1 复用，清单注入）**：8 项逐项复验全 PASS/接受（亲手重跑 161 passed、dist 特征
  grep 命中），判定 **PASS_WITH_NOTES**，遗留 1×P3（S8 预拍漏 ARMED 残态）→ 71282d3 一行修。
- **熔断机制 e2e 立功实录**：悬停态点 S8 → BAD_STATE:HOVER → 即时红字中止（修复前会 96s 假死）。

## 11. 60 秒演示剧本（决赛现场）

1. (10s) 板上 SW7 → 五帧认证 → DS8 绿 PASS —— 评委看板端反应。
2. (10s) 网页 verdict 大字 PASS，drone.state 徽章"已解锁·待命"。
3. (15s) 点"解锁起飞" → 3D 无人机起飞至 3m 悬停，HUD 姿态仪滚转/俯仰随动。
4. (10s) 航点 A/B → 巡航转向；期间可切相机预设 2"跟踪终端"。
5. (10s) 左栏"仿冒"认证 → REJECT → 无人机自动上锁、徽章变灰并**自动降落**——"认证是飞行的前提"。
6. (5s) 落地后徽章回到"未解锁"。若还要演示返航：再按一次 SW7 重新认证解锁 →
   点"解锁起飞"升空悬停 → 再点"返航"回中降落（LANDED 态 rtl 会被 BAD_STATE
   拒绝，必须先升空）；或直接用 S8 一键链（认证→解锁→起飞→航点→返航）收尾。
