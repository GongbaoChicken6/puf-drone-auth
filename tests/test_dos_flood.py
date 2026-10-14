"""W4-P4 T4: DoS rate-limiting flood test (pool not exhausted)."""
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.python.evaluation.puf_model import ROPairingPUF
from src.python.server.crp_pool import CRPPoolRegistry
from src.python.server.hsm import SpeckHSM
from src.python.server.protocol import (
    HFIDAProtocol,
    RESULT_ERROR,
    RESULT_PASS,
    RESULT_REJECT,
)
from src.python.server.template_db import TemplateDB


class TestDoSFlood(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_flood_does_not_exhaust_pool(self):
        """Burst 50 forged ACCESS_REQUESTs: pool must NOT be drained.

        Rate limiter (10/min) rejects most; the few that pass
        consume at most 4 seeds each.  Pool=100 must stay >50%.
        """
        protocol = HFIDAProtocol(
            templates=TemplateDB(self.tmp / "t.json"),
            hsm=SpeckHSM(),
            pools=CRPPoolRegistry(self.tmp / "pools", pool_size=100),
        )
        puf = ROPairingPUF(flip_prob=0.0)
        # Enroll 100 seeds
        seeds = protocol.pools.get(1).reserve(100)
        pairs = [(s, puf.ideal(s)) for s in seeds]
        protocol.templates.enroll(1, pairs)
        protocol.hsm.set_key(1, bytes(12))
        pool_before = protocol.pools.get(1).remaining
        self.assertEqual(pool_before, 100)

        # Flood: 50 forged requests with random C2
        import secrets
        rejected = 0
        accepted = 0
        for i in range(50):
            c2 = secrets.token_bytes(8)
            reply = protocol.on_access_request(1, c2=c2, nonce=i)
            msg_id, fields = HFIDAProtocol.parse(reply)
            if fields.get("result") == RESULT_ERROR:
                rejected += 1
            else:
                accepted += 1
                # Clean up the pending session (simulate terminal responding)
                protocol.on_response(1, [puf.ideal(s) for s in
                    protocol._pending[1].seeds] if 1 in protocol._pending else [bytes(8)]*4)

        pool_after = protocol.pools.get(1).remaining
        # Pool should NOT be exhausted (was 100, flood consumed < 50)
        self.assertGreater(pool_after, 50,
            f"pool drained to {pool_after}/100 after 50-request flood")
        self.assertGreater(rejected, 30,
            f"rate limiter rejected only {rejected}/50 requests")
        print(f"[FLOOD] {rejected}/50 rejected, {accepted} passed, "
              f"pool {pool_after}/100 remaining")

    def test_rate_limit_recovers(self):
        """After burst + wait, legitimate auth succeeds again."""
        protocol = HFIDAProtocol(
            templates=TemplateDB(self.tmp / "t2.json"),
            hsm=SpeckHSM(),
            pools=CRPPoolRegistry(self.tmp / "p2", pool_size=200),
        )
        puf = ROPairingPUF(flip_prob=0.0)
        seeds = protocol.pools.get(1).reserve(200)
        pairs = [(s, puf.ideal(s)) for s in seeds]
        protocol.templates.enroll(1, pairs)
        protocol.hsm.set_key(1, bytes(12))

        # Exhaust the rate budget
        import secrets
        for i in range(15):
            protocol.on_access_request(1, c2=secrets.token_bytes(8), nonce=i)

        # Simulate 61+ seconds passing (lazy refill)
        with patch.object(time, 'monotonic', return_value=time.monotonic() + 61):
            reply = protocol.on_access_request(1, c2=b"\x00"*8, nonce=999)
            msg_id, fields = HFIDAProtocol.parse(reply)
            # Should NOT be rejected by rate limiter (tokens refilled)
            self.assertNotEqual(fields.get("result"), RESULT_ERROR,
                "rate limiter did not recover after 61s")


    def test_failed_auth_returns_seeds_to_pool(self) -> None:
        """T4 staging-release: a REJECTed auth must not burn its draw.

        Before: draw() marked seeds used permanently, so an attacker
        flooding ACCESS_REQUEST drained the pool even through the rate
        limiter (B-P2 F5).  Now a failed auth calls unuse() and the pool
        only shrinks on successful authentications.
        """
        protocol = HFIDAProtocol(
            templates=TemplateDB(self.tmp / 't3.json'),
            hsm=SpeckHSM(),
            pools=CRPPoolRegistry(self.tmp / 'p3', pool_size=100),
        )
        puf = ROPairingPUF(flip_prob=0.0)
        seeds = protocol.pools.get(1).reserve(100)
        protocol.templates.enroll(1, [(s, puf.ideal(s)) for s in seeds])
        protocol.hsm.set_key(1, bytes(12))

        before = protocol.pools.get(1).remaining
        reply = protocol.on_access_request(1, c2=b'\x11' * 8, nonce=1)
        _mid, fields = HFIDAProtocol.parse(reply)
        self.assertIn('seeds', fields, 'expected CHALLENGE')
        drawn = protocol.pools.get(1).remaining
        self.assertEqual(drawn, before - protocol.N_CHALLENGES,
                         'draw should reduce remaining by N_CHALLENGES')

        # Wrong R1 -> REJECT -> staged seeds returned
        bad = [bytes(8) for _ in fields['seeds']]
        reply2 = protocol.on_response(1, bad)
        _m2, f2 = HFIDAProtocol.parse(reply2)
        self.assertEqual(f2['result'], RESULT_REJECT)
        after = protocol.pools.get(1).remaining
        self.assertEqual(after, before,
                         f'failed auth must return the draw: {before} -> {drawn} -> {after}')

    def test_stalled_session_swept_and_seeds_returned(self) -> None:
        """T4: a session that opens then goes silent releases its seeds.

        Closes the flood-without-response vector (attacker never answers
        the CHALLENGE; without the sweep the staged seeds stay pinned).
        """
        protocol = HFIDAProtocol(
            templates=TemplateDB(self.tmp / 't4.json'),
            hsm=SpeckHSM(),
            pools=CRPPoolRegistry(self.tmp / 'p4', pool_size=100),
        )
        puf = ROPairingPUF(flip_prob=0.0)
        seeds = protocol.pools.get(1).reserve(100)
        protocol.templates.enroll(1, [(s, puf.ideal(s)) for s in seeds])
        protocol.hsm.set_key(1, bytes(12))

        before = protocol.pools.get(1).remaining
        protocol.on_access_request(1, c2=b'\x22' * 8, nonce=1)
        staged = protocol.pools.get(1).remaining
        self.assertEqual(staged, before - protocol.N_CHALLENGES)

        # No response; advance past the session timeout and poke again.
        base = time.monotonic()
        with patch.object(time, 'monotonic', return_value=base + 31.0):
            protocol.on_access_request(1, c2=b'\x33' * 8, nonce=2)
        # Without the sweep this would be before - 2*N (both draws burned);
        # with it, only the live session's draw counts.
        after = protocol.pools.get(1).remaining
        self.assertEqual(
            after, before - protocol.N_CHALLENGES,
            f'stalled session must be swept: {before} -> {staged} -> {after} '
            f'(expected {before - protocol.N_CHALLENGES}; '
            f'{before - 2 * protocol.N_CHALLENGES} would mean no sweep)')
        # The stalled entry's timestamp must have been replaced by the live
        # session's (i.e. the old one was swept, not merely overwritten by luck).
        self.assertGreater(
            protocol._staged_at[1], base + protocol.SESSION_TIMEOUT_S - 1.0,
            'stalled session timestamp must be replaced by the fresh one')


if __name__ == "__main__":
    unittest.main(verbosity=2)