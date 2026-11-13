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
        self.wp: tuple[float, float] | None = None
        self.wp_alt = P["takeoff_alt"]
        self.att_acc = 0.0     # per-tid 遥测节流累加器(R1-P1-3)


class DroneSim:
    TICK = 0.05              # 20Hz

    def __init__(self, hub, autostart: bool = True) -> None:
        self._hub = hub
        self._lk = threading.Lock()
        self._st: dict[int, _St] = {}
        self._stop = threading.Event()      # 生命周期:shutdown 可停(clean thread 测试)
        self._tap: Queue = hub.add_tap()
        self._th = threading.Thread(target=self._loop, name="drone-sim",
                                    daemon=True)
        if autostart:
            self._th.start()

    def stop(self) -> None:
        """停工作线程(web_bridge shutdown 调;测试 join 用)。幂等。"""
        self._stop.set()

    # ------------------------------------------------------------------
    # 工作线程:tap 出队 + 20Hz 步进(单测 autostart=False 时直驱下列方法)
    # ------------------------------------------------------------------
    @staticmethod
    def _calc_dt(last: float, now: float) -> float:
        """墙钟步长(content-review P2):事件唤醒会让固定 TICK 的仿真时间
        随事件频率加速(28ba76d 修复)。dt=单调差分,钳制 [0, 0.25]。
        抽成纯函数供回归测试(CI-safe,无线程)。"""
        return min(0.25, max(0.0, now - last))

    def _loop(self) -> None:
        last = time.monotonic()
        while not self._stop.is_set():
            try:
                try:
                    env = self._tap.get(timeout=self.TICK)
                    self._on_event(env.get("type"), env.get("payload") or {})
                except Empty:
                    pass
                now = time.monotonic()
                dt = self._calc_dt(last, now)
                last = now
                if dt <= 0.0:
                    continue
                with self._lk:
                    # 快照迭代(R1-P1-4:防 command() 新建 tid 时 dict 变更)
                    for tid, st in list(self._st.items()):
                        self._step(tid, st, dt)
            except Exception as exc:   # 线程级防线(content-review P3):
                # _step/_on_event 任何逃逸异常都会杀死 daemon 线程 →
                # drone.* 永久停摆而 REST 面仍 200。记日志并继续循环。
                try:
                    self._hub.publish("server.log", {
                        "level": "error",
                        "msg": f"drone-sim loop error (recovered): {exc!r}"})
                except Exception:
                    pass
                time.sleep(0.1)

    def _on_event(self, etype: str, pl: dict) -> None:
        """认证门控:verdict PASS 解锁 / 非 PASS 上锁+自动降落(R2-P1);
        confirm.rejected(终端拒认本站判决)= 拒绝信号,同样上锁(G2 字面兑现,
        content-review P3)。"""
        if etype not in ("verdict", "confirm.rejected"):
            return
        if etype == "confirm.rejected":
            res = 1          # 拒认 ≙ 非 PASS:上锁(飞行中自动降落)
        else:
            res = None
        try:
            raw_tid = pl.get("terminal_id")
            if raw_tid is None:
                return       # 缺 tid 不造幻影 tid=-1(content-review P2h)
            tid = int(raw_tid)
            if res is None:
                res = int(pl.get("result", -1))
        except (TypeError, ValueError):
            # 契约字段漂移:门控失效是"认证通过了却飞不了"级故障,必须留痕
            # (content-review P3:静默 return 零线索)
            self._hub.publish("server.log", {
                "level": "warn",
                "msg": f"drone-sim: unparsable {etype} payload dropped: {pl!r}"})
            return
        with self._lk:
            st = self._st.setdefault(tid, _St())
            was = st.unlocked
            st.unlocked = (res == 0)
            if not st.unlocked and st.state in FLYING:
                st.state = "LAND"   # 认证失效自动降落,不悬空拒管
                st.wp = (st.x, st.y)   # 就地降落语义与 lock 对齐(test-review P2i)
                st.wp_alt = st.alt
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
                reason = f"UNKNOWN_CMD:{cmd}"
                self._hub.publish("drone.cmd_ack",
                                  {"terminal_id": tid, "cmd": cmd, "ok": False,
                                   "reason": reason})   # SSE 旁听齐平(content-review P3)
                return {"ok": False, "reason": reason, "state": st.state}
            if cmd == "goto" and (x is None or y is None):
                reason = "BAD_PARAM:x,y required"
                self._hub.publish("drone.cmd_ack",
                                  {"terminal_id": tid, "cmd": cmd, "ok": False,
                                   "reason": reason})
                return {"ok": False, "reason": reason, "state": st.state}
            if (cmd == "goto" and not all(
                    isinstance(v, (int, float)) and math.isfinite(v)
                    for v in (x, y) + (() if alt is None else (alt,)))):
                # NaN/Infinity 经 json.loads 合法入境,进入 wp 后永不收敛且
                # SSE 会序列化出非法 JSON(content-review P3)
                reason = "BAD_PARAM:non-finite x/y/alt"
                self._hub.publish("drone.cmd_ack",
                                  {"terminal_id": tid, "cmd": cmd, "ok": False,
                                   "reason": reason})
                return {"ok": False, "reason": reason, "state": st.state}
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
            # 到达判定 = 水平 eps 圈 ∧ 高度到位(content-review P2g:水平先到
            # 即转 HOVER 会丢弃 alt 目标,goto(x,y,alt) 永远到不了指定高度)
            at_alt = abs(st.wp_alt - st.alt) <= max(P["wp_eps"], 0.1)
            if d <= P["wp_eps"] and at_alt:
                st.state = "HOVER" if st.state == "MOVE" else "LAND"
                st.vz = 0.0
                self._publish_state(tid, st)
            else:
                # 三角减速 profile:v = min(vmax, sqrt(2*acc*d)) —— 否则全速冲
                # 航点会在 eps 圈外往复震荡永不收敛(实测 bug,2026-11-13)
                v_t = min(P["vmax"], math.sqrt(2.0 * P["acc"] * d))
                tgt = (v_t * dx / d, v_t * dy / d)
                st.yaw = math.degrees(math.atan2(dx, dy))  # 航向朝目标(北为 0°)
                # 垂直通道仅未到达时趋近(到达拍 vz 已清零,不再复写——
                # content-review P3 一帧不一致)
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
        if st.att_acc + 1e-9 < 0.1:      # epsilon:0.05+0.05 二进制和可能 <0.1
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
