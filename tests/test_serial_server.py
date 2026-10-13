"""W3 serial receive-loop tests: SerialServer, FrameSync, enroll pairing.

Wire-level end-to-end coverage without any hardware: a WireTerminal
model (protocol_contract.md §5 semantics -- terminal-initiated frames,
RTL-style C2 counter, R2 verified against its own Speck key) talks to
SerialServer.pump() exactly like the FPGA will talk to serve_forever().

Run from the repository root::

    python tests\\test_serial_server.py
    python -m unittest tests.test_serial_server -v
"""

import hashlib
import hmac
import secrets
import sys
import tempfile
import unittest
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.python.common.speck import Speck6496
from src.python.server.crp_pool import CRPPoolRegistry
from src.python.server.enroll import enroll_device, majority_bytes
from src.python.server.hsm import SpeckHSM
from src.python.server.protocol import (
    CONFIRM_FAIL,
    CONFIRM_OK,
    RESULT_ERROR,
    RESULT_PASS,
    RESULT_POOL_EMPTY,
    RESULT_REPLAY,
    HFIDAProtocol,
)
from src.python.server.serial_server import FrameSync, SerialServer, serve_forever
from src.python.server.template_db import TemplateDB

#: Distinct from the W3 demo key on purpose: these tests must not
#: accidentally depend on the NSA-KAT value.
TEST_KEY = bytes.fromhex("00112233445566778899aabb")


# ---------------------------------------------------------------------
# Wire-level terminal model
# ---------------------------------------------------------------------
class WireTerminal:
    """Software model of the W3 terminal as seen on the wire (§5).

    * C2 resets to 0xA0..0xA7 and advances bytewise per authentication,
      exactly like terminal_fsm.v (SimulatedTerminal semantics).
    * On RESULT PASS the terminal re-computes R2 = Speck(K, C2) with its
      own key and only then sends CONFIRM -- bit-exact, not HD-based.
    """

    C2_INIT = bytes(0xA0 + j for j in range(8))

    def __init__(self, terminal_id: int, key: bytes, secret: bytes | None = None):
        self.tid = int(terminal_id)
        self.key = bytes(key)
        self.secret = secret if secret is not None else secrets.token_bytes(32)
        self._packer = HFIDAProtocol(system_id=1, component_id=2)
        self._auth_count = 0
        self.c2_history: list[bytes] = []
        self.last_result: dict | None = None
        self.r2_ok: bool | None = None
        #: Optional per-seed response override (gray-zone crafting).
        self.respond_fn = None

    def ideal(self, seed: bytes) -> bytes:
        digest = hmac.new(self.secret, b"resp" + bytes(seed), hashlib.sha256).digest()
        return digest[:8]

    def _respond(self, seed: bytes) -> bytes:
        if self.respond_fn is not None:
            return bytes(self.respond_fn(seed))
        return self.ideal(seed)

    def access_request(self) -> bytes:
        self._auth_count += 1
        c2 = bytes((b + self._auth_count) & 0xFF for b in self.C2_INIT)
        self.c2_history.append(c2)
        return self._packer.pack(
            HFIDAProtocol.MSG_ACCESS_REQUEST,
            terminal_id=self.tid,
            nonce=0xDEADBEEF,
            c2=c2,
        )

    def on_reply(self, frame: bytes) -> bytes | None:
        msg_id, fields = HFIDAProtocol.parse(frame)
        if msg_id in (
            HFIDAProtocol.MSG_CHALLENGE,
            HFIDAProtocol.MSG_EXTRA_CHALLENGE,
        ):
            return self._packer.pack(
                HFIDAProtocol.MSG_RESPONSE_R1,
                r1s=[self._respond(s) for s in fields["seeds"]],
            )
        if msg_id == HFIDAProtocol.MSG_RESULT:
            self.last_result = fields
            if fields["result"] != RESULT_PASS:
                return None
            expected = Speck6496(self.key).encrypt(self.c2_history[-1])
            self.r2_ok = bytes(fields["r2"]) == expected
            return self._packer.pack(
                HFIDAProtocol.MSG_CONFIRM,
                terminal_id=self.tid,
                status=CONFIRM_OK if self.r2_ok else CONFIRM_FAIL,
            )
        raise AssertionError(
            f"unexpected reply {HFIDAProtocol.msg_name(msg_id)}"
        )


class WireTransport:
    """SerialTransport-compatible enrollment view of a WireTerminal.

    Proves the registration-semantics pairing rule: enroll_device()
    collects whatever this terminal actually answers, and the very same
    semantics later authenticate through the serial server.
    """

    def __init__(self, term: WireTerminal):
        self.term = term

    def respond(self, terminal_id, seeds, frame=None, impostor=False, flip_prob=None):
        if frame is None:
            raise ValueError("wire transport needs the packed challenge frame")
        _mid, fields = HFIDAProtocol.parse(frame)
        return [self.term._respond(s) for s in fields["seeds"]]


def with_hd(base: bytes, hd: int) -> bytes:
    """Copy of base with exactly hd bit positions flipped (lowest bits)."""
    value = int.from_bytes(base, "big")
    for i in range(hd):
        value ^= 1 << i
    return value.to_bytes(8, "big")


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------
class SerialLoopTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def build_protocol(self, pool_size: int = 500) -> HFIDAProtocol:
        templates = TemplateDB(self.tmp / f"templates_{secrets.token_hex(4)}.json")
        pools = CRPPoolRegistry(self.tmp / f"pools_{secrets.token_hex(4)}",
                                pool_size=pool_size)
        return HFIDAProtocol(templates=templates, hsm=SpeckHSM(), pools=pools)

    @staticmethod
    def make_terminal(tid: int = 1) -> WireTerminal:
        return WireTerminal(tid, TEST_KEY)

    def enroll_ideal(self, protocol: HFIDAProtocol, term: WireTerminal, n: int = 16):
        seeds = protocol.pools.get(term.tid).reserve(n)
        data = {s.hex(): [term.ideal(s)] for s in seeds}
        pairs = [(s, term.ideal(s)) for s in seeds]
        summary = protocol.templates.enroll(term.tid, pairs, measurements=data)
        protocol.hsm.set_key(term.tid, term.key)
        return summary

    @staticmethod
    def make_server(protocol: HFIDAProtocol) -> SerialServer:
        return SerialServer(protocol, on_event=lambda msg: None)

    def run_auth(self, server: SerialServer, term: WireTerminal) -> dict:
        """Drive one full terminal-initiated round; returns RESULT fields."""
        replies = server.pump(term.access_request())
        self.assertEqual(len(replies), 1)
        msg_id, _fields = HFIDAProtocol.parse(replies[0])
        self.assertEqual(msg_id, HFIDAProtocol.MSG_CHALLENGE)
        replies = server.pump(term.on_reply(replies[0]))
        self.assertEqual(len(replies), 1)
        msg_id, fields = HFIDAProtocol.parse(replies[0])
        self.assertEqual(msg_id, HFIDAProtocol.MSG_RESULT)
        confirm = term.on_reply(replies[0])
        if confirm is not None:
            self.assertEqual(server.pump(confirm), [])
        return fields


# ---------------------------------------------------------------------
# FrameSync
# ---------------------------------------------------------------------
class TestFrameSync(unittest.TestCase):
    def test_exact_hd_boundaries(self) -> None:
        """Sanity for the crafted-HD helper used by the gray-zone test."""
        base = bytes(range(8))
        for hd in (0, 1, 10, 64):
            mutated = with_hd(base, hd)
            self.assertEqual(
                bin(int.from_bytes(base, "big") ^ int.from_bytes(mutated, "big")).count("1"),
                hd,
            )

    def test_garbage_prefix_and_byte_fragments(self) -> None:
        packer = HFIDAProtocol()
        frame = packer.pack(HFIDAProtocol.MSG_CHALLENGE, seeds=[bytes([i] * 8) for i in range(4)])
        sync = FrameSync()
        stream = b"\x00noise\xfd\xff" + frame  # junk + bogus LEN probe
        fed = []
        for byte in stream:  # byte-by-byte delivery
            fed += sync.feed(bytes([byte]))
        self.assertEqual(fed, [frame])

    def test_corrupted_frame_is_skipped_next_survives(self) -> None:
        packer = HFIDAProtocol()
        good = packer.pack(HFIDAProtocol.MSG_RESULT, result=RESULT_PASS, hd=1,
                           r2=bytes(8))
        bad = bytearray(good)
        bad[-1] ^= 0xFF  # break the CRC
        sync = FrameSync()
        frames = sync.feed(bytes(bad) + good)
        self.assertEqual(frames, [good])


# ---------------------------------------------------------------------
# SerialServer end-to-end
# ---------------------------------------------------------------------
class TestSerialServerFlow(SerialLoopTest):
    def test_full_pass_flow_and_mutual_confirm(self) -> None:
        protocol = self.build_protocol()
        term = self.make_terminal()
        self.enroll_ideal(protocol, term)
        server = self.make_server(protocol)

        fields = self.run_auth(server, term)
        self.assertEqual(fields["result"], RESULT_PASS)
        self.assertEqual(fields["hd"], 0)
        # Terminal verified R2 against its own key (wire C2, not a stub).
        self.assertTrue(term.r2_ok)
        self.assertEqual(server.confirmations, 1)
        self.assertTrue(any("mutual authentication complete" in e for e in server.events))
        state = {s["terminal_id"]: s["state"] for s in protocol.status()["sessions"]}
        self.assertEqual(state[term.tid], "SESSION")

    def test_c2_advances_between_authentications(self) -> None:
        protocol = self.build_protocol()
        term = self.make_terminal()
        self.enroll_ideal(protocol, term)
        server = self.make_server(protocol)

        first = self.run_auth(server, term)
        second = self.run_auth(server, term)
        self.assertEqual(first["result"], RESULT_PASS)
        self.assertEqual(second["result"], RESULT_PASS)
        self.assertEqual(term.c2_history[0], bytes.fromhex("a1a2a3a4a5a6a7a8"))
        self.assertEqual(term.c2_history[1], bytes.fromhex("a2a3a4a5a6a7a8a9"))
        self.assertEqual(server.confirmations, 2)

    def test_replayed_access_request_rejected(self) -> None:
        protocol = self.build_protocol()
        term = self.make_terminal()
        self.enroll_ideal(protocol, term)
        server = self.make_server(protocol)

        request = term.access_request()
        challenge = server.pump(request)[0]
        replies = server.pump(term.on_reply(challenge))
        _mid, fields = HFIDAProtocol.parse(replies[0])
        self.assertEqual(fields["result"], RESULT_PASS)

        replay = server.pump(request)  # identical bytes again
        _mid, rfields = HFIDAProtocol.parse(replay[0])
        self.assertEqual(rfields["result"], RESULT_REPLAY)

    def test_unenrolled_terminal_gets_result_error(self) -> None:
        protocol = self.build_protocol()
        term = WireTerminal(99, TEST_KEY)
        server = self.make_server(protocol)

        replies = server.pump(term.access_request())
        _mid, fields = HFIDAProtocol.parse(replies[0])
        self.assertEqual(fields["result"], RESULT_ERROR)

    def test_pool_exhausted_after_enrollment(self) -> None:
        protocol = self.build_protocol(pool_size=4)
        term = self.make_terminal()
        result = enroll_device(protocol, WireTransport(term), term.tid,
                               n_challenges=4, measurements=1)
        self.assertEqual(result["summary"]["n_pairs"], 4)
        protocol.hsm.set_key(term.tid, term.key)
        server = self.make_server(protocol)

        # reserve() mints seeds as available; draw() consumes them, so the
        # first (and only possible) authentication drains the 4-seed pool.
        fields = self.run_auth(server, term)
        self.assertEqual(fields["result"], RESULT_PASS)

        replies = server.pump(term.access_request())  # nothing left to draw
        _mid, empty = HFIDAProtocol.parse(replies[0])
        self.assertEqual(empty["result"], RESULT_POOL_EMPTY)

    def test_gray_zone_extra_round_routes_and_passes(self) -> None:
        protocol = self.build_protocol()
        term = self.make_terminal()
        self.enroll_ideal(protocol, term)
        server = self.make_server(protocol)

        term.respond_fn = lambda seed: with_hd(term.ideal(seed), 10)  # 4x10 = 40 -> GRAY
        replies = server.pump(term.access_request())
        challenge = replies[0]
        replies = server.pump(term.on_reply(challenge))
        msg_id, fields = HFIDAProtocol.parse(replies[0])
        self.assertEqual(msg_id, HFIDAProtocol.MSG_EXTRA_CHALLENGE)
        self.assertEqual(len(fields["seeds"]), 3)

        term.respond_fn = None  # extras land on the template: 40 + 0 <= 42
        replies = server.pump(term.on_reply(replies[0]))
        _mid, final = HFIDAProtocol.parse(replies[0])
        self.assertEqual(final["result"], RESULT_PASS)
        self.assertTrue(any("GRAY" in e for e in server.events))

    def test_unsolicited_response_dropped_server_survives(self) -> None:
        protocol = self.build_protocol()
        term = self.make_terminal()
        self.enroll_ideal(protocol, term)
        server = self.make_server(protocol)

        packer = HFIDAProtocol()
        stray = packer.pack(HFIDAProtocol.MSG_RESPONSE_R1, r1s=[bytes(8)] * 4)
        self.assertEqual(server.pump(stray), [])
        self.assertTrue(any("without pending challenge" in e for e in server.events))

        fields = self.run_auth(server, term)  # loop still healthy
        self.assertEqual(fields["result"], RESULT_PASS)

    def test_confirm_fail_closes_session(self) -> None:
        protocol = self.build_protocol()
        term = self.make_terminal(tid=7)
        self.enroll_ideal(protocol, term)
        server = self.make_server(protocol)

        replies = server.pump(term.access_request())
        replies = server.pump(term.on_reply(replies[0]))
        _mid, fields = HFIDAProtocol.parse(replies[0])
        self.assertEqual(fields["result"], RESULT_PASS)

        fail = term._packer.pack(HFIDAProtocol.MSG_CONFIRM,
                                 terminal_id=term.tid, status=CONFIRM_FAIL)
        self.assertEqual(server.pump(fail), [])
        self.assertEqual(server.rejected_confirms, 1)
        state = {s["terminal_id"]: s["state"] for s in protocol.status()["sessions"]}
        self.assertEqual(state[term.tid], "IDLE")

    def test_wrong_r2_makes_terminal_confirm_fail(self) -> None:
        protocol = self.build_protocol()
        term = self.make_terminal()
        self.enroll_ideal(protocol, term)
        # Sabotage: server uses a different key than the terminal.
        protocol.hsm.set_key(term.tid, bytes.fromhex("ff" * 12))
        server = self.make_server(protocol)

        fields = self.run_auth(server, term)
        self.assertEqual(fields["result"], RESULT_PASS)  # PUF side is fine
        self.assertFalse(term.r2_ok)  # but mutual auth failed terminal-side
        self.assertEqual(server.rejected_confirms, 1)


class TestEnrollPairing(SerialLoopTest):
    def test_enroll_device_over_wire_then_authenticate(self) -> None:
        protocol = self.build_protocol(pool_size=64)
        term = self.make_terminal(tid=5)
        result = enroll_device(protocol, WireTransport(term), term.tid,
                               n_challenges=8, measurements=3)
        self.assertEqual(result["summary"]["n_pairs"], 8)
        self.assertEqual(result["measurements"], 3)
        protocol.hsm.set_key(term.tid, term.key)

        server = self.make_server(protocol)
        fields = self.run_auth(server, term)
        self.assertEqual(fields["result"], RESULT_PASS)
        self.assertEqual(server.confirmations, 1)

    def test_majority_bytes_matches_reference(self) -> None:
        responses = [bytes([0xFF] * 8), bytes([0xFF] * 8), bytes(8)]
        self.assertEqual(majority_bytes(responses), bytes([0xFF] * 8))
        self.assertEqual(majority_bytes([bytes(8)]), bytes(8))


class TestServeForever(SerialLoopTest):
    def test_loop_writes_replies_and_stops(self) -> None:
        protocol = self.build_protocol()
        term = self.make_terminal()
        self.enroll_ideal(protocol, term)

        class FakeIO:
            def __init__(self, chunks):
                self._chunks = list(chunks)
                self.written = []

            def read(self, n):
                return self._chunks.pop(0) if self._chunks else b""

            def write(self, data):
                self.written.append(bytes(data))

            def flush(self):
                return None

            @property
            def exhausted(self):
                return not self._chunks and self.written

        request = term.access_request()
        response = term.on_reply(
            HFIDAProtocol().pack(
                HFIDAProtocol.MSG_CHALLENGE,
                seeds=[bytes([i] * 8) for i in range(4)],
            )
        )
        io = FakeIO([request, response])
        # stop once the scripted stream is drained and replies flushed
        code = serve_forever(io, protocol, on_event=lambda m: None,
                             stop=lambda: io.exhausted and len(io.written) >= 2,
                             read_size=512)
        self.assertEqual(code, 0)
        msg_ids = [HFIDAProtocol.parse(f)[0] for f in io.written]
        self.assertIn(HFIDAProtocol.MSG_CHALLENGE, msg_ids)
        self.assertIn(HFIDAProtocol.MSG_RESULT, msg_ids)


class FlakyWireTransport(WireTransport):
    """Dies on the Nth batch like a serial timeout mid-enrollment."""

    def __init__(self, term: WireTerminal, fail_on_batch: int):
        super().__init__(term)
        self.fail_on_batch = fail_on_batch
        self.batches = 0

    def respond(self, terminal_id, seeds, frame=None, impostor=False, flip_prob=None):
        self.batches += 1
        if self.batches >= self.fail_on_batch:
            raise TimeoutError(f"simulated serial timeout (batch {self.batches})")
        return super().respond(terminal_id, seeds, frame=frame)


class TestReviewFixes(SerialLoopTest):
    """Regression tests for the auto-review findings (A-P1, B-P1, B-P2)."""

    def test_enroll_abort_rolls_back_unmeasured_seeds(self) -> None:
        """B-P1: a refresh dying mid-way must not leave drawable,
        template-less seeds that later kill scoring with KeyError."""
        protocol = self.build_protocol(pool_size=64)
        term = self.make_terminal(tid=3)
        enroll_device(protocol, WireTransport(term), term.tid,
                      n_challenges=8, measurements=1)
        protocol.hsm.set_key(term.tid, term.key)
        before = protocol.pools.get(term.tid).remaining

        flaky = FlakyWireTransport(term, fail_on_batch=2)
        with self.assertRaises(TimeoutError):
            enroll_device(protocol, flaky, term.tid,
                          n_challenges=8, measurements=1)
        # minted-but-unmeasured seeds were rolled back
        self.assertEqual(protocol.pools.get(term.tid).remaining, before)

        server = self.make_server(protocol)  # loop healthy afterwards
        fields = self.run_auth(server, term)
        self.assertEqual(fields["result"], RESULT_PASS)

    def test_protocol_violation_answered_with_result_error(self) -> None:
        """B-P2: mid-session violations must get a wire reply so the
        terminal leaves its wait state instead of retrying forever."""
        protocol = self.build_protocol()
        term = self.make_terminal()
        self.enroll_ideal(protocol, term)
        server = self.make_server(protocol)
        server.pump(term.access_request())

        malformed = term._packer.pack(
            HFIDAProtocol.MSG_RESPONSE_R1, r1s=[bytes(8)] * 3  # expects 4
        )
        replies = server.pump(malformed)
        self.assertEqual(len(replies), 1)
        _mid, fields = HFIDAProtocol.parse(replies[0])
        self.assertEqual(fields["result"], RESULT_ERROR)
        self.assertTrue(any("PROTOCOL ERROR" in e for e in server.events))

    def test_events_are_bounded(self) -> None:
        """B-P2: the audit trail must not grow without bound."""
        protocol = self.build_protocol()
        server = self.make_server(protocol)
        stray = HFIDAProtocol().pack(
            HFIDAProtocol.MSG_RESPONSE_R1, r1s=[bytes(8)] * 4
        )
        server.pump(stray * 1100)  # every frame emits one event
        self.assertLessEqual(len(server.events), 1000)

    def test_script_entrypoint_imports_resolve(self) -> None:
        """A-P1: 'python src/python/server/main.py --port COMx' must load
        (both import branches) -- the serve command must not NameError."""
        import subprocess
        root = Path(__file__).resolve().parents[1]
        proc = subprocess.run(
            [sys.executable,
             str(root / "src" / "python" / "server" / "main.py"), "--help"],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--port", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
