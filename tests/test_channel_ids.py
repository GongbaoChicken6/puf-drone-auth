"""N2(finals-demo) channel IDS tests -- RealSerialListener._loop direction gate.

Wire-level coverage without any hardware: a FakeSerial yields scripted frame
bytes, the listener loop (constructed without opening a port) consumes them,
and we assert the station-only-direction frames (0x0091/0x0093/0x0095) raise
"channel.intrusion" while legal RX-direction frames (0x0092) do not, and the
enroll-session window suppresses 0x0091 as designed.

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
    """Yields scripted chunks, then raises OSError on in_waiting (port lost).

    The OSError exit is the production loop own termination path, so the test
    stops the listener exactly the way a real port loss does.
    """

    def __init__(self, chunks):
        self._chunks = [bytes(c) for c in chunks]

    @property
    def in_waiting(self):
        if self._chunks:
            return len(self._chunks[0])
        raise OSError("test: scripted stream drained")

    def read(self, n):
        return self._chunks.pop(0) if self._chunks else b""


def make_listener(frames, enroll_active=False):
    listener = web_bridge.RealSerialListener.__new__(web_bridge.RealSerialListener)
    listener.ser = FakeSerial(frames)
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


def response_frame():
    return _PROTO.pack(
        HFIDAProtocol.MSG_RESPONSE_R1,
        r1s=[bytes([0xA0 + i] * 8) for i in range(4)])


def intrusions(listener):
    return [e for e in listener.hub.events if e[0] == "channel.intrusion"]


class TestChannelIds(unittest.TestCase):
    def test_station_direction_frame_raises_intrusion(self):
        # 0x0091 CHALLENGE on the station RX path = second transmitter
        listener = make_listener([challenge_frame()])
        listener._loop()
        hits = intrusions(listener)
        self.assertEqual(len(hits), 1,
                         f"exactly one intrusion, got {listener.hub.events}")
        payload = hits[0][1]
        self.assertEqual(payload["msg_id"], 0x0091)
        self.assertEqual(payload["name"], "CHALLENGE")
        self.assertEqual(payload["len"], len(challenge_frame()))
        # companion server.log error line feeds the existing audit-log path
        logs = [e for e in listener.hub.events
                if e[0] == "server.log" and "CHANNEL IDS" in e[1]["msg"]]
        self.assertEqual(len(logs), 1)

    def test_terminal_direction_frame_is_silent(self):
        # 0x0092 RESPONSE_R1 is a legal RX-direction frame: no alarm
        listener = make_listener([response_frame()])
        listener._loop()
        self.assertEqual(intrusions(listener), [])

    def test_enroll_window_suppresses_challenge_alarm(self):
        # N5 registration session: the station itself streams 0x0091 and
        # must not trip its own IDS.
        listener = make_listener([challenge_frame()], enroll_active=True)
        listener._loop()
        self.assertEqual(intrusions(listener), [])

    def test_two_injections_two_events(self):
        listener = make_listener([challenge_frame(), challenge_frame()])
        listener._loop()
        self.assertEqual(len(intrusions(listener)), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
