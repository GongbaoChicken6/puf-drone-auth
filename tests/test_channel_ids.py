"""N2(finals-demo) channel IDS tests -- RealSerialListener._loop direction gate.

Wire-level coverage without any hardware: a FakeSerial yields scripted frame
bytes, the listener loop (constructed without opening a port) consumes them.

Coverage map (auto-review ar-test-c1 gaps closed):
  * direction gate: 0x0091 alarm / 0x0092 silent
  * ALL THREE station-only variants: 0x0091 / 0x0093 (the frame fake_base
    injects on finals day) / 0x0095
  * enroll window: suppressed inside, RECOVERS after the window closes
  * noise coexistence: garbage resync then a valid intrusion frame
  * channel.noise flood: >=3 resyncs in 1s publish exactly one event
  * parse failure: corrupt-CRC 0x0091 does NOT alarm; buffer survives to the
    next good frame which does
  * payload contract: msg_id/name/hex/len/note + companion server.log level

Run from the repository root::

    python tests/test_channel_ids.py
    python -m pytest tests/test_channel_ids.py -q
"""

import importlib.util
import sys
import types
import unittest
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.python.server.protocol import HFIDAProtocol

_BRIDGE = Path(__file__).resolve().parents[1] / "web" / "bridge" / "web_bridge.py"
_spec = importlib.util.spec_from_file_location("web_bridge_n2t", _BRIDGE)
web_bridge = importlib.util.module_from_spec(_spec)
# dataclass 在类创建时回查 sys.modules[cls.__module__]，必须先注册再 exec
sys.modules["web_bridge_n2t"] = web_bridge
_spec.loader.exec_module(web_bridge)


class CaptureHub:
    def __init__(self):
        self.events = []

    def publish(self, etype, payload):
        self.events.append((etype, payload))


class FakeSerial:
    """Yields scripted chunks, then drains cooperatively and raises OSError.

    Drain sequence: fire on_drain (lets tests flip listener state / clear the
    running flag BEFORE the port-loss path), then raise OSError on in_waiting
    -- the production loop own termination path. The cooperative running=False
    keeps the suite future-proof: if the loop ever grows auto-reconnect
    (in_waiting error -> log+continue), the tests end via the flag instead of
    hanging (ar-test-c1 overfit finding).
    """

    def __init__(self, chunks, on_drain=None):
        self._chunks = [bytes(c) for c in chunks]
        self._on_drain = on_drain

    @property
    def in_waiting(self):
        if self._chunks:
            return len(self._chunks[0])
        if self._on_drain is not None:
            self._on_drain()
            self._on_drain = None
        raise OSError("test: scripted stream drained")

    def read(self, n):
        return self._chunks.pop(0) if self._chunks else b""


def make_listener(frames, enroll_active=False, on_drain=None):
    # __new__ 捏造的属性集必须跟随 RealSerialListener.__init__/start 同步维护
    # (漏捏 _loop 触碰的属性会 AttributeError 响亮失败,不会静默)。 ar-silent-c1。
    listener = web_bridge.RealSerialListener.__new__(web_bridge.RealSerialListener)
    # R2 ar-test-c1:默认接线协作退出——未来 _loop 若加自动重连,用例靠
    # running=False 结束而不是只靠 OSError(失败退化为挂死的路径被堵死)
    if on_drain is None:
        on_drain = lambda: setattr(listener, "running", False)
    listener.ser = FakeSerial(frames, on_drain=on_drain)
    listener.proto = HFIDAProtocol()
    listener.P = HFIDAProtocol
    listener.hub = CaptureHub()
    listener.app = types.SimpleNamespace(
        hub=listener.hub, enroll_session_active=enroll_active)
    listener.running = True
    return listener


_PROTO = HFIDAProtocol()


def challenge_frame():
    return _PROTO.pack(
        HFIDAProtocol.MSG_CHALLENGE,
        seeds=[bytes([i] * 8) for i in range(4)])


def extra_frame():
    return _PROTO.pack(
        HFIDAProtocol.MSG_EXTRA_CHALLENGE,
        seeds=[bytes([i] * 8) for i in range(3)])


def result_frame():
    # 0x0093 -- the exact frame fake_base.py injects on finals day (N8)
    return _PROTO.pack(
        HFIDAProtocol.MSG_RESULT, result=1, hd=2, r2=bytes(range(8)))


def response_frame():
    return _PROTO.pack(
        HFIDAProtocol.MSG_RESPONSE_R1,
        r1s=[bytes([0xA0 + i] * 8) for i in range(4)])


def events_of(listener, etype):
    return [e for e in listener.hub.events if e[0] == etype]


class TestChannelIds(unittest.TestCase):
    def test_station_direction_frame_raises_intrusion(self):
        # 0x0091 CHALLENGE on the station RX path = second transmitter
        frame = challenge_frame()
        listener = make_listener([frame])
        listener._loop()
        hits = events_of(listener, "channel.intrusion")
        self.assertEqual(len(hits), 1,
                         f"exactly one intrusion, got {listener.hub.events}")
        payload = hits[0][1]
        self.assertEqual(payload["msg_id"], 0x0091)
        self.assertEqual(payload["name"], "CHALLENGE")
        self.assertEqual(payload["len"], len(frame))
        self.assertEqual(payload["hex"], frame.hex())
        self.assertEqual(payload["note"], "station-only frame heard on RX path")
        # companion server.log error line feeds the existing audit-log path;
        # level MUST be error or the audit error filter hides IDS rows
        logs = [e for e in listener.hub.events
                if e[0] == "server.log" and "CHANNEL IDS" in e[1]["msg"]]
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0][1]["level"], "error")

    def test_all_three_station_direction_variants_alarm(self):
        # ar-test-c1 P1: the guard tuple has THREE members; finals day injects
        # 0x0093. Lock each variant explicitly.
        for frame, mid, name in [
            (challenge_frame(), 0x0091, "CHALLENGE"),
            (result_frame(), 0x0093, "RESULT"),
            (extra_frame(), 0x0095, "EXTRA_CHALLENGE"),
        ]:
            with self.subTest(mid=hex(mid)):
                listener = make_listener([frame])
                listener._loop()
                hits = events_of(listener, "channel.intrusion")
                self.assertEqual(len(hits), 1, name)
                self.assertEqual(hits[0][1]["msg_id"], mid)
                self.assertEqual(hits[0][1]["name"], name)

    def test_terminal_direction_frame_is_silent(self):
        # 0x0092 RESPONSE_R1 is a legal RX-direction frame: no alarm
        listener = make_listener([response_frame()])
        listener._loop()
        self.assertEqual(events_of(listener, "channel.intrusion"), [])
        self.assertEqual(events_of(listener, "channel.noise"), [])

    def test_enroll_window_suppresses_challenge_alarm(self):
        # N5 registration session: the station itself streams 0x0091 and
        # must not trip its own IDS.
        listener = make_listener([challenge_frame()], enroll_active=True)
        listener._loop()
        self.assertEqual(events_of(listener, "channel.intrusion"), [])

    def test_enroll_window_recovery(self):
        # ar-test-c1: suppression must END when the window closes. If N5 ever
        # hoists the flag read out of the loop, the second (post-window) frame
        # would stay muted while every test above still passes.
        listener = make_listener([challenge_frame(), challenge_frame()],
                                 enroll_active=True)
        original_read = listener.ser.read
        calls = []

        def flip_on_second_read(n):
            calls.append(n)
            if len(calls) >= 2:
                # 窗口在第二帧读出前关闭:第一帧仍处于注册窗口内(被抑制),
                # 第二帧的 IDS 判定必须看到 False 并恢复告警。
                listener.app.enroll_session_active = False
            return original_read(n)

        listener.ser.read = flip_on_second_read
        listener._loop()
        self.assertEqual(
            len(events_of(listener, "channel.intrusion")), 1,
            "first frame suppressed, second must alarm after window closes")

    def test_noise_resync_then_intrusion_coexist(self):
        # Real attack streams are not frame-aligned: garbage precedes the
        # injected frame. One resync (<3/s) must NOT emit channel.noise, and
        # the following valid 0x0091 must still alarm.
        listener = make_listener([b"\x00\x01garbage!", challenge_frame()])
        listener._loop()
        self.assertEqual(len(events_of(listener, "channel.intrusion")), 1)
        self.assertEqual(events_of(listener, "channel.noise"), [])
        resync = [e for e in listener.hub.events
                  if e[0] == "server.log" and "REAL resync" in e[1]["msg"]]
        self.assertEqual(len(resync), 1)

    def test_noise_flood_publishes_channel_noise_once(self):
        # >=3 resyncs inside 1s -> exactly one channel.noise event (rate-
        # limited: window cleared after publish).
        # 每块须 >=12B 才各自触发一次 resync(短块会在 buf 里粘连成一次)
        flood = [bytes([0x00, i]) + b"noise" * 3 for i in range(4)]
        listener = make_listener(flood)
        listener._loop()
        noise = events_of(listener, "channel.noise")
        self.assertEqual(len(noise), 1)
        self.assertEqual(noise[0][1]["events"], 3)
        self.assertEqual(noise[0][1]["window_s"], 1.0)
        logs = [e for e in listener.hub.events
                if e[0] == "server.log" and "CHANNEL NOISE" in e[1]["msg"]]
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0][1]["level"], "error")

    def test_corrupt_crc_frame_does_not_alarm_but_stream_survives(self):
        # (a) a CRC-corrupted 0x0091 must NOT alarm (only parse-failed log) --
        #     otherwise HC-12 noise triggers false red banners on finals day;
        # (b) the continue must not eat the buffer: the next good frame alarms.
        bad = bytearray(challenge_frame())
        bad[-1] ^= 0xFF
        listener = make_listener([bytes(bad), challenge_frame()])
        listener._loop()
        self.assertEqual(len(events_of(listener, "channel.intrusion")), 1)
        failed = [e for e in listener.hub.events
                  if e[0] == "server.log" and "parse failed" in e[1]["msg"]]
        self.assertEqual(len(failed), 1)

    def test_two_injections_two_events(self):
        listener = make_listener([challenge_frame(), challenge_frame()])
        listener._loop()
        self.assertEqual(len(events_of(listener, "channel.intrusion")), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
