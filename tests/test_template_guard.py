"""Order-signature enrollment guard (M3, plan v2) -- test suite G1-G7.

Run:  python tests/test_template_guard.py     (direct, CI-compatible)
  or: python -m pytest tests/test_template_guard.py -q
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.python.server.puf_order import (  # noqa: E402
    AGREE_REJECT,
    N_RINGS,
    order_agreement,
    predict_response,
    reconstruct_order,
)
from src.python.server.template_db import (  # noqa: E402
    CorrelatedTemplateError,
    TemplateDB,
)
from src.python.evaluation.puf_model import decode_pair_table  # noqa: E402

# Deterministic seed set (fixed -- golden reproducibility): 120 UNIQUE seeds.
import random as _random  # noqa: E402
_rng = _random.Random(0xC0FFEE)
SEEDS = []
_seen = set()
while len(SEEDS) < 120:
    s = _rng.getrandbits(64)
    if s not in _seen:
        _seen.add(s)
        SEEDS.append(s)

ORDER_A = list(range(16))            # identity order: 0 fastest
ORDER_B = list(reversed(range(16)))  # opposite: 15 fastest
ORDER_C = [7, 3, 15, 11, 1, 9, 5, 13, 0, 14, 2, 12, 6, 10, 4, 8]  # independent


def _synthetic_template(order):
    """Build a template matching a given ring order for all SEEDS."""
    return {
        format(s, "016x"): format(predict_response(order, s), "016x")
        for s in SEEDS
    }


class TestGuard(unittest.TestCase):

    def _db_with(self, template_a):
        db = TemplateDB(path=None)  # in-memory
        db.templates["1"] = dict(template_a)
        return db

    def test_G1_independent_orders_pass(self):
        """New template with an independent order enrolls successfully."""
        db = self._db_with(_synthetic_template(ORDER_A))
        summary = db.enroll("2", _synthetic_template(ORDER_C))
        agr = summary["guard"]["checked"][0]["agreement"]
        self.assertLess(agr, AGREE_REJECT)
        self.assertIn("2", db.templates)
        print("GUARD_OK G1")

    def test_G2_clone_rejected(self):
        """Same-order clone (same bitstream layout) raises."""
        db = self._db_with(_synthetic_template(ORDER_A))
        with self.assertRaises(CorrelatedTemplateError) as ctx:
            db.enroll("2", _synthetic_template(ORDER_A))
        self.assertIn("1", str(ctx.exception))
        self.assertNotIn("2", db.templates)  # no partial write
        print("GUARD_REJECT G2 tid=1")

    def test_G3_small_template_skipped(self):
        """< MIN_CRPS CRPs -> unreliable order -> skip (not reject)."""
        db = self._db_with(_synthetic_template(ORDER_A))
        small = dict(list(_synthetic_template(ORDER_A).items())[:24])
        summary = db.enroll("2", small)
        self.assertTrue(summary["guard"]["skipped"])
        self.assertIn("2", db.templates)
        print("GUARD_SKIP G3")

    def test_G4_force_override(self):
        """Clone + allow_correlated=True -> success with warning."""
        db = self._db_with(_synthetic_template(ORDER_A))
        summary = db.enroll("2", _synthetic_template(ORDER_A),
                            allow_correlated=True)
        self.assertEqual(summary["guard"]["checked"][0]["verdict"], "REJECT")
        self.assertIn("2", db.templates)
        print("GUARD_FORCE G4")

    def test_G5_empty_library(self):
        """First terminal in empty library -> no guard checks."""
        db = TemplateDB(path=None)
        summary = db.enroll("1", _synthetic_template(ORDER_A))
        self.assertEqual(summary["guard"]["checked"], [])
        self.assertIn("1", db.templates)
        print("GUARD_OK G5")

    def test_G6_unreliable_existing(self):
        """Existing terminal has unreliable order -> skip (fail-open)."""
        db = self._db_with(dict(list(_synthetic_template(ORDER_A).items())[:24]))
        summary = db.enroll("2", _synthetic_template(ORDER_C))
        self.assertTrue(any("1" in str(s) for s in summary["guard"]["skipped"]))
        print("GUARD_SKIP G6")

    def test_G7_independent_high_agreement_not_rejected(self):
        """Independent order pair hitting agreement~0.80 (round-2 max) must PASS."""
        # Exhaustively search independent orders for agreement near 0.80
        found = None
        for i in range(1, 2000):
            candidate = [(r * 7 + i * 3) % 16 for r in range(16)]
            if len(set(candidate)) < 16:
                continue
            agr = order_agreement(ORDER_A, candidate)
            if 0.74 < agr < 0.84:
                found = candidate
                break
        if found is None:
            self.skipTest("no independent order in 0.74-0.84 found in scan")
        db = self._db_with(_synthetic_template(ORDER_A))
        summary = db.enroll("2", _synthetic_template(found))
        agr = summary["guard"]["checked"][0]["agreement"]
        self.assertGreater(agr, 0.74)
        self.assertLess(agr, 0.84)
        self.assertIn("2", db.templates)  # must NOT be rejected
        print(f"GUARD_OK G7 (agreement={agr:.3f})")


class TestPufOrder(unittest.TestCase):

    def test_reconstruct_matches_input(self):
        """Round-trip: predict -> reconstruct -> same order."""
        t = _synthetic_template(ORDER_B)
        res = reconstruct_order(t)
        self.assertTrue(res.usable)
        self.assertEqual(res.order, ORDER_B)
        self.assertEqual(res.contradiction_rate, 0.0)
        print("ORDER_RECON_OK")

    def test_forward_recompute_zero_hd(self):
        """Forward predict under reconstructed order equals template exactly."""
        t = _synthetic_template(ORDER_C)
        res = reconstruct_order(t)
        hd = sum(
            bin(predict_response(res.order, int(s, 16)) ^ int(r, 16)).count("1")
            for s, r in t.items()
        )
        self.assertEqual(hd, 0)
        print("ORDER_RECON_OK forward HD=0")

    def test_kendall_properties(self):
        """Self=1.0; reversed=0.0; identity vs independent ~0.5."""
        self.assertAlmostEqual(order_agreement(ORDER_A, ORDER_A), 1.0)
        self.assertAlmostEqual(order_agreement(ORDER_A, ORDER_B), 0.0)
        agr = order_agreement(ORDER_A, ORDER_C)
        self.assertGreater(agr, 0.3)
        self.assertLess(agr, 0.7)
        print("ORDER_KENDALL_OK")


if __name__ == "__main__":
    unittest.main(verbosity=2)
