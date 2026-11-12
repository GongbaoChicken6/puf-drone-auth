"""R2(auto-review) bridge-level tests -- N4 _do_poll dispatch/semantics + N3 confirm alerts.

Locks the two P2/P1 seams ar-test-c1/ar-defect-c1 found in round 2:
  * _do_poll MUST live on Orchestrator (dispatch is getattr(self, "_do_poll")
    with self=Orchestrator) -- P1 regression lock.
  * write-before-publish evidence ordering (anti-fabrication rule of this bridge).
  * busy reject / loopback reject / 3s timeout paths with their exact hints.
  * confirm.rejected + base.spoof.suspected publish when the board answers a
    PASS verdict with CONFIRM(status=1) -- the Day4 "triple evidence" seam.

Run from the repository root::

    python -m pytest tests/test_poll_bridge.py -q
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
from tests.test_serial_server import SerialLoopTest

_BRIDGE = Path(__file__).resolve().parents[1] / "web" / "bridge" / "web_bridge.py"
_spec = importlib.util.spec_from_file_location("web_bridge_pbt", _BRIDGE)
web_bridge = importlib.util.module_from_spec(_spec)
sys.modules["web_bridge_pbt"] = web_bridge
_spec.loader.exec_module(web_bridge)

_PROTO = HFIDAProtocol()


class SeqHub:
    """CaptureHub with a global sequence (for write-vs-publish ordering)."""

    def __init__(self, seq):
        self.events = []
        self._seq = seq

    def publish(self, etype, payload):
        self.events.append((etype, payload))
        self._seq.append(etype)


class SeqSerial:
    def __init__(self, seq, chunks=None):
        self.seq = seq
        self.chunks = [bytes(c) for c in (chunks or [])]
        self.written = []

    @property
    def in_waiting(self):
        if self.chunks:
            return len(self.chunks[0])
        raise OSError("drained")

    def read(self, n):
        return self.chunks.pop(0) if self.chunks else b""

    def write(self, data):
        self.written.append(bytes(data))
        self.seq.append("WRITE")

    def flush(self):
        self.seq.append("FLUSH")


def make_app(seq, listener=None, busy=False):
    return types.SimpleNamespace(
        hub=None,
        protocol=_PROTO,
        mods=types.SimpleNamespace(HFIDAProtocol=HFIDAProtocol),
        serial_bus_lock=threading.Lock(),
        auth_in_progress=busy,
        last_access_request_ts=0.0,
        serial_listener=listener,
    )


def make_orch(app):
    orch = web_bridge.Orchestrator.__new__(web_bridge.Orchestrator)
    orch.app = app
    return orch


def running_listener(seq):
    return types.SimpleNamespace(running=True, ser=SeqSerial(seq))


def job():
    return web_bridge.Job(kind="poll", tid=7, run_id="r-pbt")


class TestDoPollDispatchAndSemantics(unittest.TestCase):
    def test_handler_lives_on_orchestrator_p1_regression(self):
        # R2 P1 regression lock: dispatch is getattr(Orchestrator, "_do_poll")
        self.assertTrue(callable(getattr(web_bridge.Orchestrator, "_do_poll", None)))
        self.assertFalse(hasattr(web_bridge.RealApp, "_do_poll"))

    def test_positive_path_write_before_publish(self):
        seq = []
        app = make_app(seq, listener=running_listener(seq))
        app.hub = SeqHub(seq)
        orch = make_orch(app)

        def board_answers():
            time.sleep(0.15)
            app.last_access_request_ts = time.time()

        threading.Thread(target=board_answers, daemon=True).start()
        res = orch._do_poll(job())
        self.assertEqual(res, {"polled": True, "tid": 7})
        # evidence order: WRITE+FLUSH must precede poll.sent / frame.tx
        self.assertLess(seq.index("WRITE"), seq.index("poll.sent"))
        self.assertLess(seq.index("FLUSH"), seq.index("frame.tx"))
        mid, fl = HFIDAProtocol.parse(app.serial_listener.ser.written[0])
        self.assertEqual(mid, 0x0097)
        self.assertEqual(fl["terminal_id"], 7)
        etypes = [e[0] for e in app.hub.events]
        self.assertIn("poll.sent", etypes)
        self.assertIn("frame.tx", etypes)

    def test_busy_reject(self):
        seq = []
        app = make_app(seq, listener=running_listener(seq), busy=True)
        orch = make_orch(app)
        with self.assertRaises(RuntimeError) as cm:
            orch._do_poll(job())
        self.assertIn("auth in progress", str(cm.exception))
        self.assertEqual(app.serial_listener.ser.written, [])
        self.assertEqual(seq, [])

    def test_loopback_reject(self):
        seq = []
        app = make_app(seq, listener=None)
        app.hub = SeqHub(seq)
        orch = make_orch(app)
        with self.assertRaises(RuntimeError) as cm:
            orch._do_poll(job())
        self.assertIn("real-serial mode", str(cm.exception))

    def test_timeout_hint_mentions_sw13(self):
        seq = []
        app = make_app(seq, listener=running_listener(seq))
        app.hub = SeqHub(seq)
        orch = make_orch(app)
        t0 = time.time()
        with self.assertRaises(RuntimeError) as cm:
            orch._do_poll(job())
        self.assertGreaterEqual(time.time() - t0, 2.9)
        self.assertIn("SW13", str(cm.exception))


class DanceSerial:
    """应答式串口:站端写出 CHALLENGE 的瞬间现场生成终端应答。

    不能预跑 on_access_request 拿 challenge——那会把该 C2 记入重放窗,
    _auth 重放同一 ACCESS_REQUEST 时撞 RESULT_REPLAY(黄金 C2 陷阱)。
    """

    def __init__(self, term, tail_chunks):
        self.term = term
        self.chunks = [bytes(c) for c in tail_chunks]
        self.written = []

    @property
    def in_waiting(self):
        if self.chunks:
            return len(self.chunks[0])
        raise OSError("drained")

    def read(self, n):
        return self.chunks.pop(0) if self.chunks else b""

    def write(self, data):
        data = bytes(data)
        self.written.append(data)
        try:
            mid, _ = HFIDAProtocol.parse(data)
        except Exception:
            return
        if mid == HFIDAProtocol.MSG_CHALLENGE:
            self.chunks.insert(0, self.term.on_reply(data))

    def flush(self):
        pass


class TestConfirmRejectedBridge(SerialLoopTest):
    """N3: board answers a PASS verdict with CONFIRM(status=1) -> both alerts."""

    def test_confirm_fail_publishes_contradiction_alerts(self):
        protocol = self.build_protocol()
        term = self.make_terminal()
        self.enroll_ideal(protocol, term)
        ar = term.access_request()
        _, ar_f = protocol.parse(ar)
        tid = int(ar_f["terminal_id"])
        confirm_fail = protocol.pack(
            HFIDAProtocol.MSG_CONFIRM, terminal_id=tid, status=1)

        seq = []
        hub = SeqHub(seq)
        listener = web_bridge.RealSerialListener.__new__(
            web_bridge.RealSerialListener)
        listener.ser = DanceSerial(term, [confirm_fail])
        listener.proto = protocol
        listener.P = HFIDAProtocol
        listener.hub = hub
        listener.app = types.SimpleNamespace(
            hub=hub, enroll_session_active=False,
            serial_bus_lock=threading.Lock(), auth_in_progress=False,
            last_access_request_ts=0.0)
        listener.running = True

        listener._auth(tid, ar_f, ar)

        etypes = [e[0] for e in hub.events]
        self.assertIn("confirm.rejected", etypes)
        self.assertIn("base.spoof.suspected", etypes)
        spoof = [e[1] for e in hub.events
                 if e[0] == "base.spoof.suspected"][0]
        self.assertEqual(spoof["terminal_id"], tid)
        self.assertEqual(spoof["own_verdict"], "PASS")
        self.assertEqual(spoof["terminal_says"], "FAIL")
        logs = [e for e in hub.events
                if e[0] == "server.log" and "BASE SPOOF SUSPECTED" in e[1]["msg"]]
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0][1]["level"], "error")


if __name__ == "__main__":
    unittest.main(verbosity=2)
