"""finals-demo-drone station-side tests -- DroneSim engine + hub tap.

设计文档: docs/process/plans/drone_sim_lite_design_20261112.md §5
CI-safe 约定(协调点②): 全部用例 autostart=False + FakeHub 直驱,
零常驻线程、零端口绑定、零网络、固定 dt 步进无 sleep。

Run from the repository root::

    python -m pytest tests/test_drone_sim.py -q
"""

import importlib.util
import sys
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
        unlock(sim, 7, 1)
        self.assertFalse(sim._st[7].unlocked)
        self.assertEqual(sim._st[7].state, "LAND")   # 自动降落,不悬空拒管

    def test_lock_command_lands_in_place(self):
        _, sim = make_sim()
        unlock(sim, 7, 0)
        sim.command(7, "launch")
        fly_to(sim, 7, "HOVER", 100)
        sim.command(7, "goto", x=4, y=0)
        fly_to(sim, 7, "MOVE", 2)
        r = sim.command(7, "lock")
        self.assertTrue(r["ok"])
        self.assertEqual(sim._st[7].state, "LAND")
        self.assertFalse(sim._st[7].unlocked)


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
        r = s.command(7, "land")                      # TAKEOFF 中止爬升
        self.assertTrue(r["ok"])
        self.assertEqual(r["state"], "LAND")
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
        self.assertAlmostEqual(st.x, 0.0, delta=P["wp_eps"] + 0.1)
        self.assertAlmostEqual(st.alt, 0.0, delta=0.01)

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
        for tid in (1, 2):
            n = sum(1 for p in hub.of("drone.attitude") if p["terminal_id"] == tid)
            self.assertGreaterEqual(n, 3, f"tid {tid} attitude 饥饿")


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
        _, sim = make_sim()
        unlock(sim, 1, 0)
        with sim._lk:                                  # 快照迭代先取列表
            it = list(sim._st.items())
            self.assertEqual(len(it), 1)
        # command() 自行获取 _lk(引擎内聚);此处锁外调用=模拟 HTTP 线程并发
        r = sim.command(9, "arm")                      # 新 tid,不抛 dict-changed
        self.assertTrue(r["ok"] or r["reason"])

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
        hub.publish("drone.state", {"terminal_id": 7, "state": "HOVER"})
        env = tap.get_nowait()
        self.assertEqual(env["type"], "drone.state")
        self.assertEqual(env["seq"], 1)


if __name__ == "__main__":
    unittest.main()
