"""finals-demo-drone station-side tests -- DroneSim engine + hub tap.

设计文档: docs/process/plans/drone_sim_lite_design_20261112.md §5
CI-safe 约定(协调点②): 全部用例 autostart=False + FakeHub 直驱,
零常驻线程、零端口绑定、零网络、固定 dt 步进无 sleep。

Run from the repository root::

    python -m pytest tests/test_drone_sim.py -q
"""

import importlib.util
import sys
import time
import unittest
from pathlib import Path
from queue import Queue

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web.bridge.drone_sim import DroneSim, FLYING, P


class FakeHub:
    """记录型 hub:publish 全部落列表供断言;add_tap 返回真队列。"""

    def __init__(self):
        self.events = []
        self.taps = []

    def add_tap(self):
        q = Queue(maxsize=512)
        self.taps.append(q)
        return q

    def publish(self, etype, payload):
        self.events.append((etype, payload))

    def of(self, etype):
        return [p for t, p in self.events if t == etype]


def make_sim():
    hub = FakeHub()
    return hub, DroneSim(hub, autostart=False)


def fly_to(sim, tid, state, ticks):
    """直驱 N 个物理 tick(固定 dt,无 sleep)。"""
    for _ in range(ticks):
        with sim._lk:
            for t, st in list(sim._st.items()):
                sim._step(t, st, DroneSim.TICK)
        if sim._st.get(tid) is not None and sim._st[tid].state == state:
            break


def step(sim, n):
    """原始步进 n 拍(不做状态 break——fly_to 会在目标态即刻停,不适用于
    "在 TAKEOFF 中途"这类半程断言)。"""
    for _ in range(n):
        with sim._lk:
            for t, st in list(sim._st.items()):
                sim._step(t, st, DroneSim.TICK)


def unlock(sim, tid, result=0):
    sim._on_event("verdict", {"terminal_id": tid, "result": result})


class TestGateAndReject(unittest.TestCase):
    def test_verdict_pass_unlocks_and_reject_locks(self):
        hub, sim = make_sim()
        unlock(sim, 7, 0)
        self.assertTrue(sim.command(7, "arm")["ok"])
        unlock(sim, 7, 1)                      # REJECT
        snap = sim.snapshot()["tids"]["7"]
        self.assertFalse(snap["unlocked"])
        # ARMED 非 FLYING:上锁但不触发自动降落(只有飞行态才自动 LAND)
        self.assertEqual(snap["state"], "ARMED")
        reasons = [p.get("reason") for p in hub.of("drone.state")]
        self.assertIn("verdict:1", reasons)

    def test_locked_launch_rejected_with_reason_and_event(self):
        hub, sim = make_sim()
        r = sim.command(7, "launch")
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "AUTH_REQUIRED")
        self.assertEqual(r["state"], "LANDED")
        rej = hub.of("drone.reject")
        self.assertEqual(rej[-1]["cmd"], "launch")
        self.assertEqual(rej[-1]["reason"], "AUTH_REQUIRED")

    def test_reject_while_flying_auto_lands(self):   # R2-P1 回归
        _, sim = make_sim()
        unlock(sim, 7, 0)
        sim.command(7, "launch")
        fly_to(sim, 7, "HOVER", 100)
        self.assertEqual(sim._st[7].state, "HOVER")
        rej_x, rej_y = sim._st[7].x, sim._st[7].y
        unlock(sim, 7, 1)
        self.assertFalse(sim._st[7].unlocked)
        self.assertEqual(sim._st[7].state, "LAND")   # 自动降落,不悬空拒管
        fly_to(sim, 7, "LANDED", 200)                # 4e 完成链(原版只断言到转移)
        st = sim._st[7]
        self.assertEqual(st.state, "LANDED")
        self.assertAlmostEqual(st.x, rej_x, delta=1.5)   # 就地降落,不回旧航点
        self.assertAlmostEqual(st.alt, 0.0, delta=0.01)

    def test_lock_command_lands_in_place(self):
        _, sim = make_sim()
        unlock(sim, 7, 0)
        sim.command(7, "launch")
        fly_to(sim, 7, "HOVER", 100)
        sim.command(7, "goto", x=4, y=0)
        fly_to(sim, 7, "MOVE", 2)
        lock_x, lock_y = sim._st[7].x, sim._st[7].y
        r = sim.command(7, "lock")
        self.assertTrue(r["ok"])
        self.assertEqual(sim._st[7].state, "LAND")
        self.assertFalse(sim._st[7].unlocked)
        fly_to(sim, 7, "LANDED", 200)                    # 降完(content-review P2i)
        st = sim._st[7]
        self.assertEqual(st.state, "LANDED")
        self.assertAlmostEqual(st.alt, 0.0, delta=0.01)
        self.assertAlmostEqual(st.x, lock_x, delta=1.5)  # 就地,不去旧航点(4,0)
        self.assertAlmostEqual(st.y, lock_y, delta=1.5)


class TestTransitionTable(unittest.TestCase):
    def setUp(self):
        self.hub, self.sim = make_sim()
        unlock(self.sim, 7, 0)

    def test_full_happy_path(self):
        s = self.sim
        self.assertEqual(s.command(7, "arm")["state"], "ARMED")
        self.assertEqual(s.command(7, "takeoff")["state"], "TAKEOFF")
        fly_to(s, 7, "HOVER", 100)
        self.assertEqual(s.command(7, "goto", x=5, y=0)["state"], "MOVE")
        fly_to(s, 7, "HOVER", 400)
        self.assertEqual(s.command(7, "rtl")["state"], "RTL")

    def test_hold_idempotent_in_hover(self):          # R1-P2-3
        s = self.sim
        s.command(7, "launch")
        fly_to(s, 7, "HOVER", 100)
        r = s.command(7, "hold")
        self.assertTrue(r["ok"])
        self.assertEqual(r["state"], "HOVER")

    def test_land_aborts_rtl_and_takeoff(self):       # R1-P2-3
        s = self.sim
        s.command(7, "launch")
        step(s, 30)                                   # 爬到 alt≈1.5 再中止(半空)
        self.assertGreater(s._st[7].alt, 1.0)
        r = s.command(7, "land")                      # TAKEOFF 中止爬升
        self.assertTrue(r["ok"])
        self.assertEqual(r["state"], "LAND")
        prev_alt = s._st[7].alt
        fly_to(s, 7, "LANDED", 200)
        st = s._st[7]
        self.assertEqual(st.state, "LANDED")
        self.assertLess(st.alt, prev_alt)             # 单调下降
        self.assertEqual(st.alt, 0.0)
        self.assertEqual(st.vz, 0.0)
        fly_to(s, 7, "LANDED", 200)
        s.command(7, "launch")
        fly_to(s, 7, "HOVER", 100)
        s.command(7, "rtl")
        r = s.command(7, "land")                      # RTL 中止返航
        self.assertTrue(r["ok"])
        self.assertEqual(r["state"], "LAND")

    def test_bad_state_and_unknown_and_bad_param(self):
        s = self.sim
        s.command(7, "arm")
        r = s.command(7, "arm")                       # ARMED 再 arm -> BAD_STATE
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "BAD_STATE:ARMED")
        r = s.command(7, "banana")                    # 未知指令(带 state,R1-P2-4)
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "UNKNOWN_CMD:banana")
        self.assertEqual(r["state"], "ARMED")
        s.command(7, "takeoff")
        fly_to(s, 7, "HOVER", 100)
        r = s.command(7, "goto")                      # 缺 x/y(R1-P1-1)
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "BAD_PARAM:x,y required")
        self.assertEqual(r["state"], "HOVER")
        r = s.command(7, "goto", x=1)                 # 只给 x 同样拒
        self.assertFalse(r["ok"])


class TestKinematics(unittest.TestCase):
    def test_takeoff_reaches_alt_and_hovers(self):
        _, sim = make_sim()
        unlock(sim, 7, 0)
        sim.command(7, "launch")
        fly_to(sim, 7, "HOVER", 100)
        st = sim._st[7]
        self.assertEqual(st.state, "HOVER")
        self.assertAlmostEqual(st.alt, P["takeoff_alt"], delta=0.01)

    def test_goto_arrives_then_rtl_returns_home(self):
        _, sim = make_sim()
        unlock(sim, 7, 0)
        sim.command(7, "launch")
        fly_to(sim, 7, "HOVER", 100)
        sim.command(7, "goto", x=6, y=0)
        fly_to(sim, 7, "HOVER", 600)                  # ~6m @ 2m/s + 加速段
        st = sim._st[7]
        self.assertEqual(st.state, "HOVER")
        self.assertAlmostEqual(st.x, 6.0, delta=P["wp_eps"])
        sim.command(7, "rtl")
        fly_to(sim, 7, "LANDED", 900)                 # 返航 + 降落
        st = sim._st[7]
        self.assertEqual(st.state, "LANDED")
        self.assertAlmostEqual(st.x, 0.0, delta=0.2)   # 收紧(content P3)
        self.assertAlmostEqual(st.alt, 0.0, delta=0.01)

    def test_goto_alt_vertical_channel(self):          # content-review P2
        _, sim = make_sim()
        unlock(sim, 7, 0)
        sim.command(7, "launch")
        fly_to(sim, 7, "HOVER", 100)                   # 默认 3.0m
        self.assertAlmostEqual(sim._st[7].alt, 3.0, delta=0.01)
        r = sim.command(7, "goto", x=5, y=0, alt=8.0)  # 爬升至 8m 巡航
        self.assertTrue(r["ok"])
        fly_to(sim, 7, "HOVER", 1200)                  # ~5m 水平 + 5m 爬升
        st = sim._st[7]
        self.assertEqual(st.state, "HOVER")            # 高度到位才判到达
        self.assertAlmostEqual(st.alt, 8.0, delta=0.15)
        self.assertAlmostEqual(st.x, 5.0, delta=P["wp_eps"])

    def test_attitude_bounded_and_per_tid_fair(self):  # R1-P1-3 回归
        hub, sim = make_sim()
        for tid in (1, 2):
            unlock(sim, tid, 0)
            sim.command(tid, "launch")
        for _ in range(40):                            # 双 tid 同飞 2s
            with sim._lk:
                for t, st in list(sim._st.items()):
                    sim._step(t, st, DroneSim.TICK)
        for tid in (1, 2):
            st = sim._st[tid]
            self.assertLessEqual(abs(st.roll), P["bank_max"] + 1e-6)
            self.assertLessEqual(abs(st.pitch), P["bank_max"] + 1e-6)
        # 确定性引擎:40 tick × dt 0.05s,0.1s 节流 → 恰 20 帧/tid
        # (content-review P3:≥3 只锁 15% 下限,部分饥饿漏检)
        for tid in (1, 2):
            n = sum(1 for p in hub.of("drone.attitude") if p["terminal_id"] == tid)
            self.assertEqual(n, 20, f"tid {tid} attitude 帧数(部分饥饿)")
        # 水平加速段姿态非零(纵向爬升段 roll/pitch 恒 0 是正确物理,勿在 launch 断言;
        # goto 源态须 HOVER/MOVE,先让 tid1 爬完)
        fly_to(sim, 1, "HOVER", 100)
        sim.command(1, "goto", x=3, y=0)
        step(sim, 8)                                   # 水平加速窗口
        acc_frames = [p for p in hub.of("drone.attitude")
                      if p["terminal_id"] == 1 and (p["roll"] != 0 or p["pitch"] != 0)]
        self.assertGreaterEqual(len(acc_frames), 1, "加速段姿态恒 0 = 姿态推导失效")


class TestWallClockDt(unittest.TestCase):
    """28ba76d 墙钟步长回归(content-review P2:固定 TICK 会被事件唤醒加速)。"""

    def test_calc_dt_bounds(self):
        f = DroneSim._calc_dt
        self.assertEqual(f(0.0, 0.0), 0.0)          # 同拍:不推进
        self.assertGreater(f(10.0, 10.05), 0.049)   # 正常差分 ≈ TICK
        self.assertLessEqual(f(10.0, 10.05), 0.051)
        self.assertEqual(f(10.0, 99.0), 0.25)       # 卡顿后钳制
        self.assertEqual(f(10.0, 9.9), 0.0)         # 时钟回退(不可达,防御)

    def test_dt_equals_real_elapsed_not_fixed_tick(self):
        # 语义锚:差分 0.2s(远大于 TICK)时步进 0.2,而非固定 0.05——
        # 这是 28ba76d 修复的本质(回退成固定 TICK 本断言失败)
        self.assertAlmostEqual(DroneSim._calc_dt(5.0, 5.2), 0.2, places=6)


class TestDirtyPayloads(unittest.TestCase):
    """content-review P2h:_on_event 是脏事件下 _loop 线程唯一存活防线。"""

    def test_unparsable_tid_no_phantom_no_crash(self):
        hub, sim = make_sim()
        before = set(sim._st.keys())
        sim._on_event("verdict", {"terminal_id": "abc", "result": 0})   # 非数字
        sim._on_event("verdict", {"result": 0})                         # 缺 tid
        sim._on_event("verdict", {"terminal_id": None, "result": 0})
        self.assertEqual(set(sim._st.keys()), before)                   # 无幻影 tid
        warns = [p for t, p in hub.events if t == "server.log"]
        self.assertTrue(any("unparsable" in p.get("msg", "") for p in warns))

    def test_confirm_rejected_locks(self):              # G2 字面(content-review P3)
        _, sim = make_sim()
        unlock(sim, 7, 0)
        sim.command(7, "launch")
        fly_to(sim, 7, "HOVER", 100)
        sim._on_event("confirm.rejected", {"terminal_id": 7, "run_id": "r"})
        self.assertFalse(sim._st[7].unlocked)
        self.assertEqual(sim._st[7].state, "LAND")      # 飞行中拒认 → 自动降落

    def test_bad_param_and_nonfinite_goto(self):
        hub, sim = make_sim()
        unlock(sim, 7, 0)
        r = sim.command(7, "goto", x=float("nan"), y=0)  # 非有限数拒绝
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "BAD_PARAM:non-finite x/y/alt")
        acks = hub.of("drone.cmd_ack")                   # 协议错误也走 SSE(content P3)
        self.assertTrue(any(a.get("reason") == "BAD_PARAM:non-finite x/y/alt"
                            for a in acks))


class TestSnapshotAndTap(unittest.TestCase):
    def test_snapshot_shape_for_status(self):
        _, sim = make_sim()
        unlock(sim, 7, 0)
        snap = sim.snapshot()
        self.assertIn("tids", snap)
        d = snap["tids"]["7"]
        for k in ("terminal_id", "state", "unlocked", "pos", "yaw"):
            self.assertIn(k, d)
        self.assertEqual(len(d["pos"]), 3)

    def test_iteration_snapshot_invariant(self):       # R1-P1-4 回归
        """真线程冒烟(content-review P1:原版先 list 再顺序调,删掉 _loop 的
        list() 后仍全绿——零防护)。有界/无端口/无网络/可停,CI-safe:
        锤 50 个新 tid 到运行中的 _loop,断言线程存活且状态完整,然后 stop+join。
        若 _loop 裸迭代 items()(无快照)或 command 锁外 setdefault,
        dict-changed 会杀死 daemon 线程 → is_alive 断言失败。"""
        hub = FakeHub()
        sim = DroneSim(hub, autostart=True)             # 真工作线程
        try:
            for i in range(50):                          # HTTP 线程视角并发新建
                sim.command(i, "arm")
            for i in range(5):                           # 经 tap 灌 verdict(事件路径)
                hub.taps[0].put_nowait(
                    {"type": "verdict", "payload": {"terminal_id": i, "result": 0}})
            time.sleep(0.3)                              # 有界等待
            self.assertTrue(sim._th.is_alive(), "drone-sim 线程死亡(dict-changed?)")
            self.assertEqual(len(sim._st), 50)
            self.assertFalse(sim._st[0].unlocked is False)
        finally:
            sim.stop()
            sim._th.join(timeout=2.0)
        self.assertFalse(sim._th.is_alive())

    def test_real_ssehub_tap_receives_publish(self):
        """真实 web_bridge.SSEHub.add_tap:publish 后 tap 队列收到同一信封
        (seq 单调)——同时回归协调点①:exec_module 加载 web_bridge 时
        drone_sim import 必须可用。"""
        spec = importlib.util.spec_from_file_location(
            "web_bridge_under_test",
            Path(__file__).resolve().parents[1] / "web" / "bridge" / "web_bridge.py")
        mod = importlib.util.module_from_spec(spec)
        # dataclass 处理 string annotation 时查 sys.modules[cls.__module__],
        # 不注册会 NoneType.__dict__ 崩(test_channel_ids 同款修法)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)                   # import 失败会在此炸
        hub = mod.SSEHub()
        tap = hub.add_tap()
        for i in range(3):                              # seq 单调(content P3)
            hub.publish("drone.state", {"i": i})
        seqs = [tap.get_nowait()["seq"] for _ in range(3)]
        self.assertEqual(seqs, [1, 2, 3])
        for _ in range(600):                            # 灌满 512:丢最旧保最新
            hub.publish("server.log", {"flood": True})
        kept = 0
        last_seq = 3
        while True:
            try:
                e = tap.get_nowait()
                kept += 1
                self.assertGreater(e["seq"], last_seq)  # 队列里只剩最新一段
                last_seq = e["seq"]
            except Exception:                           # queue.Empty
                break
        self.assertLess(kept, 600)                      # 旧的被挤掉
        self.assertGreaterEqual(kept, 400)              # 绝大多数仍在


if __name__ == "__main__":
    unittest.main()
