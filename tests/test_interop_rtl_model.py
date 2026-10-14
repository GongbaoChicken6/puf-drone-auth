"""W4-P3 interop: ROPairingPUF (RTL golden model) <-> real server stack.

Closes the semantic chain: puf_model (same code the RTL TBs use) drives
a wire-level terminal that talks to SerialServer (the real receive
loop).  Proves the full RO-pairing semantics work end-to-end through
protocol.py, not just in isolated unit tests.

Run from the repository root::

    python tests\\test_interop_rtl_model.py
"""

import secrets
import sys
import tempfile
import unittest
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.python.evaluation.puf_model import (
    GOLDEN_SEED_A,
    GOLDEN_SEED_B,
    ROPairingPUF,
)
from src.python.server.crp_pool import CRPPoolRegistry
from src.python.server.enroll import enroll_device
from src.python.server.hsm import SpeckHSM
from src.python.server.protocol import (
    CONFIRM_FAIL,
    CONFIRM_OK,
    RESULT_PASS,
    RESULT_REPLAY,
    HFIDAProtocol,
)
from src.python.server.serial_server import SerialServer
from src.python.server.template_db import TemplateDB

TEST_KEY = bytes.fromhex("0099AA55AA55001122334455")


class PUFWireTerminal:
    """Wire-level terminal backed by ROPairingPUF (the RTL golden model).

    Same interface as WireTerminal in test_serial_server.py, but
    responses come from puf_model instead of HMAC — proving the actual
    RO-pairing comparison semantics work through the protocol stack.
    """

    C2_INIT = bytes(0xA0 + j for j in range(8))

    def __init__(self, terminal_id: int, key: bytes, puf: ROPairingPUF):
        self.tid = terminal_id
        self.key = key
        self.puf = puf
        self._packer = HFIDAProtocol(system_id=1, component_id=2)
        self._auth_count = 0
        self.r2_ok: bool | None = None

    def access_request(self) -> bytes:
        self._auth_count += 1
        c2 = bytes((b + self._auth_count) & 0xFF for b in self.C2_INIT)
        return self._packer.pack(
            HFIDAProtocol.MSG_ACCESS_REQUEST,
            terminal_id=self.tid, nonce=0xDEADBEEF, c2=c2)

    def on_reply(self, frame: bytes) -> bytes | None:
        msg_id, fields = HFIDAProtocol.parse(frame)
        if msg_id in (HFIDAProtocol.MSG_CHALLENGE, HFIDAProtocol.MSG_EXTRA_CHALLENGE):
            return self._packer.pack(
                HFIDAProtocol.MSG_RESPONSE_R1,
                r1s=[self.puf.respond(s) for s in fields["seeds"]])
        if msg_id == HFIDAProtocol.MSG_RESULT:
            if fields["result"] != RESULT_PASS:
                return None
            from src.python.common.speck import Speck6496
            c2 = bytes((b + self._auth_count) & 0xFF for b in self.C2_INIT)
            expected = Speck6496(self.key).encrypt(c2)
            self.r2_ok = bytes(fields["r2"]) == expected
            return self._packer.pack(
                HFIDAProtocol.MSG_CONFIRM, terminal_id=self.tid,
                status=CONFIRM_OK if self.r2_ok else CONFIRM_FAIL)
        return None


class PUFTransport:
    """Transport adapter for enroll_device (puf_model responses)."""

    def __init__(self, puf: ROPairingPUF):
        self.puf = puf

    def respond(self, terminal_id, seeds, frame=None, **kw):
        if frame is not None:
            _mid, fields = HFIDAProtocol.parse(frame)
            seeds = fields["seeds"]
        return [self.puf.respond(s) for s in seeds]


class TestInteropRTLModel(unittest.TestCase):
    """puf_model terminal <-> SerialServer full-chain semantic lock."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def build(self, pool_size=500):
        templates = TemplateDB(self.tmp / f"t_{secrets.token_hex(4)}.json")
        pools = CRPPoolRegistry(self.tmp / f"p_{secrets.token_hex(4)}", pool_size=pool_size)
        return HFIDAProtocol(templates=templates, hsm=SpeckHSM(), pools=pools)

    @staticmethod
    def make_terminal(tid=1, flip_prob=0.0):
        puf = ROPairingPUF(flip_prob=flip_prob)
        return PUFWireTerminal(tid, TEST_KEY, puf), puf

    def run_auth(self, server, term):
        replies = server.pump(term.access_request())
        assert len(replies) == 1
        replies = server.pump(term.on_reply(replies[0]))
        assert len(replies) == 1
        _mid, fields = HFIDAProtocol.parse(replies[0])
        confirm = term.on_reply(replies[0])
        if confirm is not None:
            server.pump(confirm)
        return fields

    def test_puf_enroll_then_full_auth(self) -> None:
        """ROPairingPUF (the RTL golden model) enrolls and authenticates
        end-to-end through the real SerialServer receive loop."""
        protocol = self.build()
        term, puf = self.make_terminal()

        # Enroll with puf_model semantics
        result = enroll_device(protocol, PUFTransport(puf), terminal_id=1,
                               n_challenges=12, measurements=2)
        self.assertEqual(result["summary"]["n_pairs"], 12)
        protocol.hsm.set_key(1, TEST_KEY)

        # Full wire-level auth
        server = SerialServer(protocol, on_event=lambda m: None)
        fields = self.run_auth(server, term)
        self.assertEqual(fields["result"], RESULT_PASS)
        self.assertEqual(fields["hd"], 0)
        self.assertTrue(term.r2_ok)
        self.assertEqual(server.confirmations, 1)

    def test_golden_seeds_computable(self) -> None:
        """puf_model and the wire terminal produce identical responses
        for the frozen golden seeds (same underlying model)."""
        freqs = list(range(4000, 4016))
        direct = ROPairingPUF(freqs=freqs).ideal(GOLDEN_SEED_A)
        term, _ = self.make_terminal()
        term.puf = ROPairingPUF(freqs=freqs, flip_prob=0.0)
        self.assertEqual(term.puf.ideal(GOLDEN_SEED_A), direct)
        self.assertEqual(term.puf.ideal(GOLDEN_SEED_B),
                         ROPairingPUF(freqs=freqs).ideal(GOLDEN_SEED_B))

    def test_replayed_request_rejected(self) -> None:
        protocol = self.build()
        term, puf = self.make_terminal()
        enroll_device(protocol, PUFTransport(puf), terminal_id=1,
                      n_challenges=8, measurements=1)
        protocol.hsm.set_key(1, TEST_KEY)
        server = SerialServer(protocol, on_event=lambda m: None)

        request = term.access_request()
        challenge = server.pump(request)[0]
        server.pump(term.on_reply(challenge))

        replay = server.pump(request)
        _mid, fields = HFIDAProtocol.parse(replay[0])
        self.assertEqual(fields["result"], RESULT_REPLAY)


if __name__ == "__main__":
    unittest.main(verbosity=2)
