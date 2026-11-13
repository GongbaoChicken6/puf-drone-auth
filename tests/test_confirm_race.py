"""R4 defect-c1 P1: CONFIRM wait frame-synchronization regression tests.

Uses reactive serial (DanceSerial pattern from test_poll_bridge.py):
station writes CHALLENGE → serial generates real RESPONSE_R1 →
then serves attack RESULT + CONFIRM_FAIL tail (race simulation).

Run: python -m pytest tests/test_confirm_race.py -q
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
_spec = importlib.util.spec_from_file_location("web_bridge_crt", _BRIDGE)
web_bridge = importlib.util.module_from_spec(_spec)
sys.modules["web_bridge_crt"] = web_bridge
_spec.loader.exec_module(web_bridge)


class AttackDanceSerial:
    """Reactive serial: responds to CHALLENGE with real R1, then serves tail.

    Simulates race: RESPONSE_R1 goes out cleanly, then attack RESULT
    and CONFIRM_FAIL arrive during the sleep window.
    """

    def __init__(self, term, tail_chunks):
        self.term = term
        self.tail = [bytes(c) for c in tail_chunks]
        self.chunks = []
        self.written = []

    @property
    def in_waiting(self):
        return sum(len(c) for c in self.chunks)

    def read(self, n):
        out = b""
        while n > 0 and self.chunks:
            take = min(n, len(self.chunks[0]))
            out += self.chunks[0][:take]
            self.chunks[0] = self.chunks[0][take:]
            if not self.chunks[0]:
                del self.chunks[0]
            n -= take
        return out

    def write(self, data):
        data = bytes(data)
        self.written.append(data)
        try:
            mid, _ = HFIDAProtocol.parse(data)
            if mid == HFIDAProtocol.MSG_CHALLENGE:
                resp = self.term.on_reply(data)
                self.chunks.append(resp)
                self.chunks.extend(self.tail)
        except Exception:
            pass

    def flush(self):
        pass


class CapHub:
    def __init__(self):
        self.events = []

    def publish(self, etype, payload):
        self.events.append((etype, payload))


def make_listener(protocol, ser):
    hub = CapHub()
    ln = web_bridge.RealSerialListener.__new__(web_bridge.RealSerialListener)
    ln.ser = ser
    ln.proto = protocol
    ln.P = HFIDAProtocol
    ln.hub = hub
    ln.app = types.SimpleNamespace(
        hub=hub, enroll_session_active=False,
        serial_bus_lock=threading.Lock(), auth_in_progress=False,
        last_access_request_ts=0.0)
    ln.running = True
    return ln, hub


def events_of(hub, etype):
    return [e[1] for e in hub.events if e[0] == etype]


class TestConfirmRace(SerialLoopTest):

    def _walk_to_auth(self, protocol, term, tail_chunks):
        """Create AR + reactive serial. _auth generates its own CHALLENGE."""
        term.access_request()  # discard golden-C2 first call
        ar = term.access_request()
        _, ar_f = protocol.parse(ar)
        tid = int(ar_f["terminal_id"])
        ser = AttackDanceSerial(term, tail_chunks)
        ln, hub = make_listener(protocol, ser)
        return ln, hub, tid, ar, ar_f

    def test_race_attack_three_evidence(self):
        """Core: [attack RESULT + CONFIRM_FAIL] in tail → all 3 events + BLOCKED."""
        protocol = self.build_protocol()
        term = self.make_terminal()
        self.enroll_ideal(protocol, term)
        tid = int(protocol.templates.templates.keys().__iter__().__next__())

        attack = protocol.pack(
            HFIDAProtocol.MSG_RESULT, result=0, hd=0, r2=bytes([0xDE] * 8))
        confirm_fail = protocol.pack(
            HFIDAProtocol.MSG_CONFIRM, terminal_id=tid, status=1)

        ln, hub, tid2, ar, ar_f = self._walk_to_auth(
            protocol, term, [attack, confirm_fail])
        ln._auth(tid2, ar_f, ar)

        etypes = [e[0] for e in hub.events]
        self.assertIn("channel.intrusion", etypes,
            "attack RESULT not routed to IDS; events: " + str(etypes))
        self.assertIn("confirm.rejected", etypes,
            "CONFIRM_FAIL not parsed; events: " + str(etypes))
        self.assertIn("base.spoof.suspected", etypes)
        ses = [e for e in hub.events if e[0] == "session.update"]
        self.assertTrue(len(ses) > 0, "session.update missing")
        final_state = ses[-1][1]["state"]
        self.assertEqual(final_state, "BLOCKED",
                         "must be BLOCKED, got: " + str(final_state))

    def test_clean_pass_regression(self):
        """Normal CONFIRM_OK → confirm.done + SESSION, no IDS."""
        protocol = self.build_protocol()
        term = self.make_terminal()
        self.enroll_ideal(protocol, term)
        tid = int(protocol.templates.templates.keys().__iter__().__next__())

        confirm_ok = protocol.pack(
            HFIDAProtocol.MSG_CONFIRM, terminal_id=tid, status=0)

        ln, hub, tid2, ar, ar_f = self._walk_to_auth(
            protocol, term, [confirm_ok])
        ln._auth(tid2, ar_f, ar)

        etypes = [e[0] for e in hub.events]
        self.assertIn("confirm.done", etypes)
        self.assertNotIn("channel.intrusion", etypes)
        self.assertNotIn("confirm.rejected", etypes)
        ses = [e for e in hub.events if e[0] == "session.update"]
        self.assertEqual(ses[-1][1]["state"], "SESSION")

    def test_garbage_then_race(self):
        """Noise prefix + attack + confirm: resync + all evidence."""
        protocol = self.build_protocol()
        term = self.make_terminal()
        self.enroll_ideal(protocol, term)
        tid = int(protocol.templates.templates.keys().__iter__().__next__())

        garbage = b"\x00\x01\x02\x03\xff"
        attack = protocol.pack(
            HFIDAProtocol.MSG_RESULT, result=0, hd=0, r2=bytes([0xAA] * 8))
        confirm_fail = protocol.pack(
            HFIDAProtocol.MSG_CONFIRM, terminal_id=tid, status=1)

        ln, hub, tid2, ar, ar_f = self._walk_to_auth(
            protocol, term, [garbage, attack, confirm_fail])
        ln._auth(tid2, ar_f, ar)

        etypes = [e[0] for e in hub.events]
        self.assertIn("channel.intrusion", etypes)
        self.assertIn("confirm.rejected", etypes)
        self.assertIn("base.spoof.suspected", etypes)

    def test_attack_no_confirm(self):
        """Attack only (no CONFIRM, board blocked): IDS + BLOCKED + no hang."""
        protocol = self.build_protocol()
        term = self.make_terminal()
        self.enroll_ideal(protocol, term)
        tid = int(protocol.templates.templates.keys().__iter__().__next__())

        attack = protocol.pack(
            HFIDAProtocol.MSG_RESULT, result=0, hd=0, r2=bytes([0xBB] * 8))

        ln, hub, tid2, ar, ar_f = self._walk_to_auth(
            protocol, term, [attack])

        t0 = time.time()
        ln._auth(tid2, ar_f, ar)
        elapsed = time.time() - t0

        self.assertLess(elapsed, 4.0)
        etypes = [e[0] for e in hub.events]
        self.assertIn("channel.intrusion", etypes)
        ses = [e for e in hub.events if e[0] == "session.update"]
        self.assertEqual(ses[-1][1]["state"], "BLOCKED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
