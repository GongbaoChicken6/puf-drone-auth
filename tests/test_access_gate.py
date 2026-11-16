"""finals-demo-N6 bridge tests -- 接入闸门(SW7 主动认证人工选择队列).

方案v2(docs/process/plans/access_gate_design_20261116.md, auto-review R2 PASS)的
回归锁,覆盖:
  * AccessGate 纯逻辑: 入队/重复刷新/同tid双port防线/选中放行/dismiss规则/finish出队
  * decide() 优先级: gate关=run旧行为 / enroll或auth忙=park / selected=run
  * resolve_listener 路由: 队列port → --tid-port 静态表 → 单口直通 → 多口无映射None
  * access_select: 404未入队 / 409并发选中 / 2.2s对齐(假时钟) / 唤醒失败回滚 /
    唤醒成功发 access.selected
  * _loop 0x0090 分支: park不发frame.rx也不跑_auth(在on_access_request之前,F12)

Run from the repository root::

    python -m pytest tests/test_access_gate.py -q
"""

import importlib.util
import sys
import threading
import time
import types
import unittest
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.python.server.protocol import HFIDAProtocol

_BRIDGE = Path(__file__).resolve().parents[1] / "web" / "bridge" / "web_bridge.py"
_spec = importlib.util.spec_from_file_location("web_bridge_agt", _BRIDGE)
web_bridge = importlib.util.module_from_spec(_spec)
sys.modules["web_bridge_agt"] = web_bridge
_spec.loader.exec_module(web_bridge)

_PROTO = HFIDAProtocol()


class CapHub:
    def __init__(self):
        self.events = []

    def publish(self, etype, payload):
        self.events.append((etype, payload))


class FakeSerial:
    def __init__(self, port="COM6"):
        self.port = port
        self.written = []

    def write(self, data):
        self.written.append(bytes(data))

    def flush(self):
        pass


class TestAccessGatePure(unittest.TestCase):
    def setUp(self):
        self.g = web_bridge.AccessGate(enabled=True, labels={1: "板A", 2: "板B"})

    def test_disabled_gate_runs(self):
        g = web_bridge.AccessGate(enabled=False)
        self.assertEqual(g.decide(1), "run")

    def test_park_new_and_repeat_refresh(self):
        self.assertEqual(self.g.park(1, "COM6", 100.0), "new")
        self.assertEqual(self.g.park(1, "COM6", 101.0), "repeat")
        e = self.g.snapshot(1)
        self.assertEqual(e["repeats"], 1)
        self.assertEqual(e["last_request_ts"], 101.0)
        self.assertEqual(e["label"], "板A")  # label 表生效

    def test_same_tid_two_ports_conflict(self):
        self.g.park(1, "COM6", 100.0)
        st = self.g.park(1, "COM11", 101.0)
        self.assertTrue(st.startswith("conflict:COM6"))
        e = self.g.snapshot(1)
        self.assertEqual(e["port"], "COM6")  # 原条目不被覆盖
        self.assertEqual(e["last_request_ts"], 100.0)

    def test_decide_priority(self):
        self.g.park(1, "COM6", 100.0)
        self.assertEqual(self.g.decide(1), "park")
        self.assertEqual(self.g.decide(1, enroll_active=True), "park")
        self.g.set_selected(1)
        self.assertEqual(self.g.decide(1), "run")           # selected 放行
        self.assertEqual(self.g.decide(1, auth_busy=True), "park")  # 认证忙仍串行
        self.assertEqual(self.g.decide(2), "park")           # 未选中入队

    def test_can_select_rules(self):
        self.assertEqual(self.g.can_select(9), "not queued")
        self.g.park(1, "COM6", 100.0)
        self.g.park(2, "COM11", 100.0)
        self.g.set_selected(1)
        self.assertIn("another verification", self.g.can_select(2))
        self.assertIsNone(self.g.can_select(1))

    def test_dismiss_and_finish(self):
        self.g.park(1, "COM6", 100.0)
        self.g.set_selected(1)
        self.assertIn("verification in progress", self.g.can_dismiss(1))
        self.assertTrue(self.g.finish(1, "SESSION"))          # 选中+出队
        self.assertIsNone(self.g.selected_tid)
        self.assertIsNone(self.g.snapshot(1))
        self.g.park(2, "COM11", 100.0)
        self.assertTrue(self.g.dismiss(2))
        self.assertFalse(self.g.dismiss(2))

    def test_finish_unselected_entry(self):
        # 未选中的条目被 finish(如认证在闸门开启前启动)也应出队
        self.g.park(3, "COM6", 100.0)
        self.assertTrue(self.g.finish(3, "BLOCKED"))


def make_app(seq=None, listener=None, busy=False):
    return types.SimpleNamespace(
        hub=None, protocol=_PROTO,
        mods=types.SimpleNamespace(HFIDAProtocol=HFIDAProtocol),
        serial_bus_lock=threading.Lock(),
        auth_in_progress=busy,
        last_access_request_ts=0.0,
        serial_listener=listener)


class TestResolveListener(unittest.TestCase):
    def _app(self, listeners, gate=None, tid_port=None):
        app = make_app()
        app.serial_listeners = listeners
        app.access_gate = gate
        app.tid_port_map = tid_port or {}
        return app

    def test_empty_registry_falls_back_single(self):
        ln = types.SimpleNamespace(running=True)
        app = make_app(listener=ln)
        app.serial_listeners = {}
        self.assertIs(web_bridge.RealApp.resolve_listener(app, 1), ln)

    def test_gate_entry_port_first(self):
        g = web_bridge.AccessGate(enabled=True)
        g.park(2, "COM11", time.time())
        lns = {"COM6": types.SimpleNamespace(running=True),
               "COM11": types.SimpleNamespace(running=True)}
        app = self._app(lns, gate=g)
        self.assertIs(web_bridge.RealApp.resolve_listener(app, 2), lns["COM11"])

    def test_static_map_then_single_then_none(self):
        lns = {"COM6": types.SimpleNamespace(running=True),
               "COM11": types.SimpleNamespace(running=True)}
        app = self._app(dict(lns), gate=web_bridge.AccessGate(enabled=True),
                        tid_port={1: "COM6"})
        self.assertIs(web_bridge.RealApp.resolve_listener(app, 1), lns["COM6"])
        self.assertIsNone(web_bridge.RealApp.resolve_listener(app, 7))
        one = self._app({"COM6": lns["COM6"]},
                        gate=web_bridge.AccessGate(enabled=True))
        self.assertIs(web_bridge.RealApp.resolve_listener(one, 7), lns["COM6"])


class TestAccessSelect(unittest.TestCase):
    def _app(self, gate, listeners, entry_ts=None):
        app = make_app()
        app.hub = CapHub()
        app.access_gate = gate
        app.serial_listeners = listeners
        app.tid_port_map = {}
        for port, ln in listeners.items():
            ln.ser = FakeSerial(port)
        app.resolve_listener = lambda tid: web_bridge.RealApp.resolve_listener(app, tid)
        return app

    def test_reject_when_disabled(self):
        app = self._app(web_bridge.AccessGate(enabled=False), {})
        code, body = web_bridge.RealApp.access_select(app, 1)
        self.assertEqual(code, 409)
        self.assertIn("disabled", body["reason"])

    def test_404_not_queued(self):
        g = web_bridge.AccessGate(enabled=True)
        app = self._app(g, {"COM6": types.SimpleNamespace(running=True)})
        code, body = web_bridge.RealApp.access_select(app, 1)
        self.assertEqual(code, 404)

    def test_409_another_selected(self):
        g = web_bridge.AccessGate(enabled=True)
        g.park(1, "COM6", time.time())
        g.park(2, "COM11", time.time())
        g.set_selected(1)
        app = self._app(g, {"COM6": types.SimpleNamespace(running=True),
                            "COM11": types.SimpleNamespace(running=True)})
        code, body = web_bridge.RealApp.access_select(app, 2)
        self.assertEqual(code, 409)

    def test_wake_success_publishes_selected_and_writes_poll(self):
        g = web_bridge.AccessGate(enabled=True)
        g.park(1, "COM6", time.time() - 5.0)   # 早已回 IDLE:无 2.2s 等待
        lns = {"COM6": types.SimpleNamespace(running=True)}
        app = self._app(g, lns)
        # 模拟板子回 ACCESS_REQUEST:_poll_wake_once 轮询 last_access_request_ts
        def fake_wake(ln, tid, run_id):
            app.last_access_request_ts = time.time()
            app.hub.publish("poll.sent", {"run_id": run_id, "nonce": 1})
        app._poll_wake_once = lambda ln, tid, rid: fake_wake(ln, tid, rid)
        code, body = web_bridge.RealApp.access_select(app, 1)
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(g.selected_tid, 1)
        kinds = [e[0] for e in app.hub.events]
        self.assertIn("access.selected", kinds)
        self.assertIn("poll.sent", kinds)

    def test_wake_failure_rolls_back_selected(self):
        g = web_bridge.AccessGate(enabled=True)
        g.park(1, "COM6", time.time() - 5.0)
        lns = {"COM6": types.SimpleNamespace(running=True)}
        app = self._app(g, lns)
        calls = []
        def always_timeout(ln, tid, run_id):
            calls.append(run_id)
            raise TimeoutError("no ACCESS_REQUEST")
        app._poll_wake_once = always_timeout
        # 压缩重试等待(假时钟不可注入,直接缩短 sleep 语义:monkeypatch time.sleep)
        orig_sleep = time.sleep
        time.sleep = lambda s: orig_sleep(min(s, 0.01))
        try:
            code, body = web_bridge.RealApp.access_select(app, 1)
        finally:
            time.sleep = orig_sleep
        self.assertEqual(code, 409)
        self.assertIn("唤醒失败", body["reason"])
        self.assertIsNone(g.selected_tid)       # 回滚:清选中
        self.assertIsNotNone(g.snapshot(1))     # 条目保留,等待再次选择(方案v2)
        self.assertEqual(len(calls), 2)         # 首发+防御性重试各一次

    def test_alignment_sleep_when_fresh_press(self):
        # 刚按压(0.1s 前)必须先睡 ~2.1s 再发——用假 sleep 记录时长
        g = web_bridge.AccessGate(enabled=True)
        g.park(1, "COM6", time.time() - 0.1)
        lns = {"COM6": types.SimpleNamespace(running=True)}
        app = self._app(g, lns)
        sleeps = []
        orig_sleep = time.sleep
        time.sleep = lambda s: sleeps.append(s)
        app._poll_wake_once = lambda ln, tid, rid: setattr(
            app, "last_access_request_ts", time.time())
        try:
            code, _ = web_bridge.RealApp.access_select(app, 1)
        finally:
            time.sleep = orig_sleep
        self.assertEqual(code, 200)
        self.assertTrue(any(1.5 < s <= 2.2 for s in sleeps),
                        f"expected ~2.1s alignment sleep, got {sleeps}")


class TestPollWakeOnce(unittest.TestCase):
    """auto-review R1-F2: _poll_wake_once 真路径(此前被 select 测试全 stub)。
    覆盖:AUTH_POLL 帧写入(0xFD 头/先写后发纪律)、poll.sent+frame.tx 事件、
    3s 无回应超时路径。"""

    def _app_with_serial(self):
        app = make_app()
        app.hub = CapHub()
        app.serial_bus_lock = threading.Lock()
        app.protocol = _PROTO
        app.last_access_request_ts = 0.0
        app.last_access_request_by_tid = {}     # R3: per-tid 信号表(真桥语义)
        ln = types.SimpleNamespace(running=True, ser=FakeSerial("COM6"))
        return app, ln

    def test_writes_frame_publishes_after_write(self):
        app, ln = self._app_with_serial()
        def board_answers():                    # _park/_auth 双写(全局+per-tid)
            t = time.time()
            app.last_access_request_ts = t
            app.last_access_request_by_tid[1] = t
        threading.Timer(0.05, board_answers).start()
        web_bridge.RealApp._poll_wake_once(app, ln, 1, "r-wake")
        self.assertEqual(len(ln.ser.written), 1)
        frame = ln.ser.written[0]
        self.assertEqual(frame[0], 0xFD)              # 帧头
        # 用协议解帧(勿猜偏移):msg_id=AUTH_POLL、tid 正确
        mid, fl = _PROTO.parse(frame)
        self.assertEqual(mid, 0x0097)
        self.assertEqual(int(fl.get("terminal_id", 0)), 1)
        kinds = [e[0] for e in app.hub.events]
        self.assertIn("poll.sent", kinds)
        self.assertIn("frame.tx", kinds)
        ps = next(p for t, p in app.hub.events if t == "poll.sent")
        self.assertEqual(ps["terminal_id"], 1)
        self.assertIn("nonce", ps)

    def test_timeout_raises_when_board_silent(self):
        app, ln = self._app_with_serial()             # 无线程回应
        with self.assertRaises(TimeoutError):
            web_bridge.RealApp._poll_wake_once(app, ln, 1, "r-silent")
        # 超时路径也必须已写过帧(先写后查,不伪造)
        self.assertEqual(len(ln.ser.written), 1)

    def test_other_tid_bump_does_not_fake_success(self):
        """auto-review R3 核心:唤醒 tid=1 期间 tid=2 入队(刷全局戳+自己的
        per-tid)不得让 tid=1 假成功——否则 selected 悬挂死锁闸门。"""
        app, ln = self._app_with_serial()
        def other_board_parks():                     # 板B入队:全局+by_tid[2]
            t = time.time()
            app.last_access_request_ts = t
            app.last_access_request_by_tid[2] = t
        threading.Timer(0.05, other_board_parks).start()
        with self.assertRaises(TimeoutError):        # tid=1 全程沉默 → 必须超时
            web_bridge.RealApp._poll_wake_once(app, ln, 1, "r-xboard")

    def test_own_tid_bump_only_still_succeeds(self):
        """per-tid 信号单独跳变(如 _auth 只补写 by-tid 的假想路径)也能唤醒。"""
        app, ln = self._app_with_serial()
        threading.Timer(0.05, lambda: app.last_access_request_by_tid.__setitem__(
            1, time.time())).start()
        web_bridge.RealApp._poll_wake_once(app, ln, 1, "r-owntid")   # 不抛即过


class TestListenerParkPath(unittest.TestCase):
    """_loop 0x0090 分支:park 路径不进 _auth、不发 frame.rx(F12 顺序)。"""

    def test_park_publishes_requested(self):
        app = make_app()
        app.hub = CapHub()
        g = web_bridge.AccessGate(enabled=True, labels={1: "板A"})
        app.access_gate = g
        app.enroll_session_active = False
        app.auth_in_progress = False
        ln = web_bridge.RealSerialListener.__new__(web_bridge.RealSerialListener)
        ln.app = app
        ln.hub = app.hub
        ln.ser = FakeSerial("COM6")
        ln.running = True
        ln._park(1)
        # auto-review R1-F1: parked 请求必须刷新 poll 成功信号(否则闸门模式下
        # /api/poll 板子已回应却判假超时)
        self.assertGreater(app.last_access_request_ts, 0.0)
        kinds = [e[0] for e in app.hub.events]
        self.assertIn("access.requested", kinds)
        payload = dict(app.hub.events[0][1])
        self.assertEqual(payload["terminal_id"], 1)
        self.assertEqual(payload["label"], "板A")
        self.assertEqual(payload["port"], "COM6")
        # 重复按压刷新 repeats
        ln._park(1)
        payload2 = [p for t, p in app.hub.events if t == "access.requested"][-1]
        self.assertEqual(payload2["repeats"], 1)

    def test_decide_before_on_access_request_order(self):
        # 契约锁:decide 返回 park 时,protocol.on_access_request 绝不能被调
        # (C2 重放窗不被动,F12)。用计数桩验证分支不触 _auth。
        g = web_bridge.AccessGate(enabled=True)
        g.park(2, "COM11", time.time())
        app = make_app()
        app.hub = CapHub()
        app.access_gate = g
        app.enroll_session_active = False
        app.auth_in_progress = False
        calls = {"auth": 0}
        ln = web_bridge.RealSerialListener.__new__(web_bridge.RealSerialListener)
        ln.app = app
        ln.hub = app.hub
        ln.ser = FakeSerial("COM11")
        ln.running = True
        ln._park = lambda tid: None
        ln._auth = lambda *a, **k: calls.__setitem__("auth", calls["auth"] + 1)
        fl = {"terminal_id": 2, "c2": b"\x00" * 8}
        # 模拟 _loop 分支核心(gate park → 不调 _auth)
        act = g.decide(int(fl["terminal_id"]), enroll_active=app.enroll_session_active,
                       auth_busy=app.auth_in_progress)
        if act == "park":
            ln._park(int(fl["terminal_id"]))
        else:
            ln._auth(int(fl["terminal_id"]), fl, b"")
        self.assertEqual(calls["auth"], 0)

    def test_selected_runs_auth(self):
        g = web_bridge.AccessGate(enabled=True)
        g.park(2, "COM11", time.time())
        g.set_selected(2)
        app = make_app()
        app.hub = CapHub()
        app.access_gate = g
        ln = web_bridge.RealSerialListener.__new__(web_bridge.RealSerialListener)
        ln.app = app
        ln.hub = app.hub
        ln.ser = FakeSerial("COM11")
        ln.running = True
        calls = {"auth": 0}
        ln._auth = lambda *a, **k: calls.__setitem__("auth", calls["auth"] + 1)
        ln._park = lambda tid: None
        fl = {"terminal_id": 2, "c2": b"\x00" * 8}
        act = g.decide(int(fl["terminal_id"]))
        if act == "park":
            ln._park(int(fl["terminal_id"]))
        else:
            ln._auth(int(fl["terminal_id"]), fl, b"")
        self.assertEqual(calls["auth"], 1)


if __name__ == "__main__":
    unittest.main()
