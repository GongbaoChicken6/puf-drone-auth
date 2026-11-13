"""drone_sim.py —— 决赛演示层无人机模拟器(finals-demo drone lite)。

纯站端演示仿真:不改线上协议、不碰 RTL、不读写任何文件/串口(仅内存态)。
认证门控经 SSEHub tap 监听 verdict:PASS(result=0)解锁飞行权,非 PASS 上锁
且飞行中自动降落——"认证是飞行的前提"的演示主线(设计 §1 G2)。

线程模型(设计 §3.2,经三轮 auto-review 修正):
  * 唯一工作线程 _loop:tap 出队(事件入口) + 20Hz 物理步进;
  * command() 由 HTTP 线程调用,与 _loop 经 self._lk 互斥——setdefault 必须
    在锁内、迭代用 list() 快照,否则 dict-changed-during-iteration 会杀死
    daemon 线程使全部 drone.* 事件永久停摆(R1-P1-4);
  * hub.publish 自带锁且为叶子锁(不回调 DroneSim),锁序 _lk→hub._lock 单向。
遥测节流为 per-tid 累加器 _St.att_acc:多终端同时飞行互不饥饿(R1-P1-3)。
单测约定:DroneSim(hub, autostart=False) 零线程零套接字直驱(CI-safe,
协调点②:不绑端口/无常驻线程/无网络/固定 dt 无 sleep)。

坐标系:本地米制,x=北、y=东、alt=高度(向上为正);姿态由速度增量推导
(演示级动力学,确定性可复现,不声称真实飞控——诚实边界见设计 §9)。
"""
from __future__ import annotations

import math
import threading
from queue import Empty, Queue
import time

FLYING = ("TAKEOFF", "HOVER", "MOVE", "LAND", "RTL")
STATES = ("LANDED", "ARMED", "TAKEOFF", "HOVER", "MOVE", "LAND", "RTL")
P = {  # 运动学参数(演示级)
    "vmax": 2.0,        # 水平巡航速度 m/s
    "climb": 1.0,       # 垂直速度上限 m/s
    "acc": 1.5,         # 水平加速度上限 m/s^2
    "takeoff_alt": 3.0, # 默认起飞悬停高度 m
    "land_v": 0.6,      # 降落垂直速度 m/s
    "wp_eps": 0.15,     # 航点到达判定半径 m
    "bank_max": 22.0,   # 演示滚转/俯仰上限 deg
}
_G = 9.8


class _St:
    """per-tid 无人机状态(全部字段均在 _lk 保护下读写)。"""
    __slots__ = ("state", "unlocked", "x", "y", "alt", "vx", "vy", "vz",
                 "yaw", "roll", "pitch", "wp", "wp_alt", "att_acc")

    def __init__(self) -> None:
        self.state, self.unlocked = "LANDED", False
        self.x = self.y = self.alt = 0.0
        self.vx = self.vy = self.vz = 0.0
        self.yaw = self.roll = self.pitch = 0.0
        self.wp, self.wp_alt = None, P["takeoff_alt"]
        self.att_acc = 0.0     # per-tid 遥测节流累加器(R1-P1-3)


class DroneSim:
    TICK = 0.05              # 20Hz

    def __init__(self, hub, autostart: bool = True) -> None:
        self._hub = hub
        self._lk = threading.Lock()
        self._st: dict[int, _St] = {}
        self._tap: Queue = hub.add_tap()
        self._th = threading.Thread(target=self._loop, name="drone-sim",
                                    daemon=True)
        if autostart:
            self._th.start()

    # ------------------------------------------------------------------
    # 工作线程:tap 出队 + 20Hz 步进(单测 autostart=False 时直驱下列方法)
    # ------------------------------------------------------------------
    def _loop(self) -> None:
        # 步长取**真实墙钟差分**(S8 e2e 实测 bug,2026-11-13):事件会唤醒
        # q.get 提前返回,若每次迭代都推进固定 TICK,仿真时间会随事件频率
        # 加速(10Hz 自发遥测即自我加速,起飞 3.2s 压缩成 ~1.9s)。墙钟差分
        # + 0.25s 钳制(防卡顿后跳变)让物理与真实时间一致。
        last = time.monotonic()
        while True:
            try:
                env = self._tap.get(timeout=self.TICK)
                self._on_event(env.get("type"), env.get("payload") or {})
            except Empty:
                pass
            now = time.monotonic()
            dt = min(0.25, max(0.0, now - last))
            last = now
            if dt <= 0.0:
                continue
            with self._lk:
                # 快照迭代(R1-P1-4:防 command() 新建 tid 时 dict 变更)
                for tid, st in list(self._st.items()):
                    self._step(tid, st, dt)

    def _on_event(self, etype: str, pl: dict) -> None:
        """verdict 门控:PASS 解锁 / 非 PASS 上锁+自动降落(R2-P1)。"""
        if etype != "verdict":
            return
        try:
            tid = int(pl.get("terminal_id", -1))
            res = int(pl.get("result", -1))
        except (TypeError, ValueError):
            return
        with self._lk:
            st = self._st.setdefault(tid, _St())
            was = st.unlocked
            st.unlocked = (res == 0)
            if not st.unlocked and st.state in FLYING:
                st.state = "LAND"   # 认证失效自动降落,不悬空拒管
            if was != st.unlocked:
                self._hub.publish("drone.state",
                                  self._state_ev(tid, st, reason=f"verdict:{res}"))

    # ------------------------------------------------------------------
    # REST 入口(HTTP 线程调用;结果同步返回,同时发布 cmd_ack/state SSE)
    # ------------------------------------------------------------------
    def command(self, tid: int, cmd: str,
                x=None, y=None, alt=None) -> dict:
        with self._lk:   # 全程锁内:setdefault 不落在 _loop 迭代窗口(R1-P1-4)
            st = self._st.setdefault(tid, _St())
            if cmd not in ("arm", "disarm", "launch", "takeoff", "goto",
                           "hold", "land", "rtl", "lock"):
                return {"ok": False, "reason": f"UNKNOWN_CMD:{cmd}",
                        "state": st.state}          # 失败分支也带 state(R1-P2-4)
            if cmd == "goto" and (x is None or y is None):
                return {"ok": False, "reason": "BAD_PARAM:x,y required",
                        "state": st.state}          # goto 缺参显式拒绝(R1-P1-1)
            if not st.unlocked and cmd != "lock":
                ev = {"terminal_id": tid, "cmd": cmd, "reason": "AUTH_REQUIRED"}
                self._hub.publish("drone.reject", ev)
                return {"ok": False, "reason": "AUTH_REQUIRED",
                        "state": st.state}
            ok, reason = self._transition(st, cmd, x, y, alt)
            self._hub.publish("drone.cmd_ack",
                              {"terminal_id": tid, "cmd": cmd, "ok": ok,
                               **({"reason": reason} if reason else {})})
            self._hub.publish("drone.state", self._state_ev(tid, st))
            return {"ok": ok, "reason": reason, "state": st.state}

    # ------------------------------------------------------------------
    # 状态转移表(单测锚点;与前端按钮禁用矩阵逐格镜像,设计 §4.3)
    # ------------------------------------------------------------------
    _T = {
        "arm":     (("LANDED",), "ARMED"),
        "launch":  (("LANDED",), "TAKEOFF"),
        "takeoff": (("ARMED",), "TAKEOFF"),
        "hold":    (("HOVER", "MOVE"), "HOVER"),    # HOVER 幂等(R1-P2-3)
        "land":    (("HOVER", "MOVE", "RTL", "TAKEOFF"), "LAND"),  # 中止返航/爬升
        "rtl":     (("HOVER", "MOVE"), "RTL"),
    }

    def _transition(self, st: _St, cmd: str, x, y, alt) -> tuple[bool, str | None]:
        if cmd == "lock":
            st.unlocked = False
            if st.state in FLYING:
                st.state, st.wp = "LAND", (st.x, st.y)  # 就地降落(设计 §9)
                st.wp_alt = st.alt
            return True, None
        if cmd == "disarm":
            if st.state != "ARMED":
                return False, f"BAD_STATE:{st.state}"
            st.state = "LANDED"
            return True, None
        if cmd == "goto":
            if st.state not in ("HOVER", "MOVE"):
                return False, f"BAD_STATE:{st.state}"
            st.state, st.wp = "MOVE", (float(x), float(y))
            st.wp_alt = float(alt) if alt is not None else max(st.alt, P["takeoff_alt"])
            return True, None
        src, dst = self._T[cmd]
        if st.state not in src:
            return False, f"BAD_STATE:{st.state}"
        if cmd in ("launch", "takeoff"):
            st.wp = None
            st.wp_alt = P["takeoff_alt"]
        if cmd == "rtl":
            st.wp, st.wp_alt = (0.0, 0.0), st.alt
        st.state = dst
        return True, None

    # ------------------------------------------------------------------
    # 物理步进(确定性;dt 显式传入,单测不 sleep)
    # ------------------------------------------------------------------
    def _step(self, tid: int, st: _St, dt: float) -> None:
        if st.state not in FLYING:
            return
        pvx, pvy = st.vx, st.vy
        tgt = (0.0, 0.0)
        if st.state == "TAKEOFF":
            st.vz = +P["climb"]
            if st.alt >= P["takeoff_alt"]:
                st.alt = P["takeoff_alt"]   # 钳位:消除末拍过冲,测试可精确断言
                st.vz, st.state = 0.0, "HOVER"
                self._publish_state(tid, st)
        elif st.state == "LAND":
            st.vz = -P["land_v"]
            if st.alt <= 0.0:
                st.alt = st.vz = st.vx = st.vy = 0.0
                st.roll = st.pitch = 0.0
                st.state = "LANDED"
                self._publish_state(tid, st)
        elif st.state in ("MOVE", "RTL"):
            dx, dy = st.wp[0] - st.x, st.wp[1] - st.y
            d = math.hypot(dx, dy)
            if d <= P["wp_eps"]:
                st.state = "HOVER" if st.state == "MOVE" else "LAND"
                st.vz = 0.0
                self._publish_state(tid, st)
            else:
                # 三角减速 profile:v = min(vmax, sqrt(2*acc*d)) —— 否则全速冲
                # 航点会在 eps 圈外往复震荡永不收敛(实测 bug,2026-11-13)
                v_t = min(P["vmax"], math.sqrt(2.0 * P["acc"] * d))
                tgt = (v_t * dx / d, v_t * dy / d)
                st.yaw = math.degrees(math.atan2(dx, dy))  # 航向朝目标(北为 0°)
            st.vz = max(-P["climb"], min(P["climb"], st.wp_alt - st.alt))
        else:  # HOVER
            st.vz = 0.0
        # 水平速度一阶趋近(限加速度)
        st.vx += max(-P["acc"] * dt, min(P["acc"] * dt, tgt[0] - st.vx))
        st.vy += max(-P["acc"] * dt, min(P["acc"] * dt, tgt[1] - st.vy))
        st.x += st.vx * dt
        st.y += st.vy * dt
        st.alt = max(0.0, st.alt + st.vz * dt)
        # 姿态:横向加速度 → 滚转/俯仰(演示级,±bank_max)
        ax, ay = (st.vx - pvx) / dt, (st.vy - pvy) / dt
        st.roll = max(-P["bank_max"], min(P["bank_max"],
                    math.degrees(math.atan2(-ax, _G))))
        st.pitch = max(-P["bank_max"], min(P["bank_max"],
                     math.degrees(math.atan2(ay, _G))))
        self._maybe_attitude(tid, st, dt)

    # ------------------------------------------------------------------
    # 事件与快照
    # ------------------------------------------------------------------
    def _state_ev(self, tid: int, st: _St, reason: str | None = None) -> dict:
        ev = {"terminal_id": tid, "state": st.state, "unlocked": st.unlocked,
              "pos": [round(st.x, 2), round(st.y, 2), round(st.alt, 2)],
              "yaw": round(st.yaw, 1)}
        if reason:
            ev["reason"] = reason
        return ev

    def _publish_state(self, tid: int, st: _St) -> None:
        self._hub.publish("drone.state", self._state_ev(tid, st))

    def _maybe_attitude(self, tid: int, st: _St, dt: float) -> None:
        """per-tid 10Hz 遥测节流(R1-P1-3);LANDED/ARMED 不发,状态由 drone.state 覆盖。"""
        if st.state not in FLYING:
            st.att_acc = 0.0
            return
        st.att_acc += dt
        if st.att_acc < 0.1:
            return
        st.att_acc = 0.0
        self._hub.publish("drone.attitude", {
            "terminal_id": tid, "state": st.state,
            "x": round(st.x, 2), "y": round(st.y, 2), "alt": round(st.alt, 2),
            "vx": round(st.vx, 2), "vy": round(st.vy, 2), "vz": round(st.vz, 2),
            "roll": round(st.roll, 1), "pitch": round(st.pitch, 1),
            "yaw": round(st.yaw, 1)})

    def snapshot(self) -> dict:
        """/api/status 增量重同步字段:SSE 断档后前端一次 GET 即恢复。"""
        with self._lk:
            return {"tids": {str(t): self._state_ev(t, s)
                             for t, s in self._st.items()}}


# 模块自检(直接运行时):零线程直驱一轮状态机,便于肉眼快速确认
if __name__ == "__main__":
    class _MiniHub:
        def __init__(self): self.events = []
        def add_tap(self): return Queue()
        def publish(self, etype, payload): self.events.append((etype, payload))
    hub = _MiniHub()
    sim = DroneSim(hub, autostart=False)
    sim._on_event("verdict", {"terminal_id": 7, "result": 0})
    print("unlock+launch:", sim.command(7, "launch"))
    for _ in range(80):
        with sim._lk:
            for t, s in list(sim._st.items()):
                sim._step(t, s, DroneSim.TICK)
    print("after 4s:", sim.snapshot()["tids"].get("7"))
    for e in hub.events[-3:]:
        print("event:", e[0], e[1])
