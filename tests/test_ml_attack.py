"""W4-P5 ML attack unit tests (plan v2 section 4)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.python.evaluation.ml_attack import (
    gen_arbiter_crps,
    gen_distinct_freq_puf,
    extract_unordered_observations,
    majority_vote_unordered,
    topo_sort_with_cycle_break,
    kendall_tau_positions,
    N_RINGS,
)
from src.python.evaluation.puf_model import ROPairingPUF, decode_pair_table


class TestArbiter(unittest.TestCase):
    def test_noiseless_lr_meets_floor(self) -> None:
        """Frozen floor: sigma=0 + 1k training -> >=95%."""
        from sklearn.linear_model import LogisticRegression
        rng = np.random.default_rng(7)
        X_tr, y_tr, w, _ = gen_arbiter_crps(1000, 0.0, rng)
        X_te, y_te, _, _ = gen_arbiter_crps(2000, 0.0, rng, w)
        acc = LogisticRegression().fit(X_tr, y_tr).score(X_te, y_te)
        self.assertGreaterEqual(acc, 0.95, f"LR floor not met: {acc}")

    def test_relative_noise_scales(self) -> None:
        """alpha=0.3 accuracy must be strictly below alpha=0.05 (informative curve)."""
        from sklearn.linear_model import LogisticRegression
        rng = np.random.default_rng(11)
        w = rng.normal(size=64)
        accs = {}
        for a in (0.05, 0.30):
            X_tr, y_tr, _, _ = gen_arbiter_crps(5000, a, rng, w)
            X_te, y_te, _, _ = gen_arbiter_crps(5000, a, rng, w)
            accs[a] = LogisticRegression().fit(X_tr, y_tr).score(X_te, y_te)
        self.assertLess(accs[0.30], accs[0.05] - 0.02,
                        f"noise lines not separated: {accs}")


class TestMajorityVote(unittest.TestCase):
    def test_unordered_mixed_orientations(self) -> None:
        """Both orientations of the same pair must vote together (P1-2)."""
        puf = ROPairingPUF(freqs=[100, 200, 300] + list(range(400, 413)), flip_prob=0.0)
        seeds = [0x1111, 0x2222, 0x3333, 0x4444, 0x5555]
        responses = [puf.ideal(s) for s in seeds]
        obs = extract_unordered_observations(seeds, responses)
        votes = majority_vote_unordered(obs)
        # Verify against ground truth
        for (lo, hi), (winner, c0, c1) in votes.items():
            true_winner = lo if puf.freqs[lo] > puf.freqs[hi] else hi
            self.assertEqual(winner, true_winner,
                             f"pair ({lo},{hi}): vote={winner} truth={true_winner}")

    def test_noiseless_sufficient_crps_exact(self) -> None:
        """flip=0 + N=20 CRPs -> exact reconstruction (T14-style sanity)."""
        rng = np.random.default_rng(42)
        puf, _ = gen_distinct_freq_puf(rng, flip_prob=0.0)
        truth = sorted(range(N_RINGS), key=lambda i: -puf.freqs[i])
        seeds = [int(rng.integers(0, 2**63)) for _ in range(20)]
        responses = [puf.ideal(s) for s in seeds]
        obs = extract_unordered_observations(seeds, responses)
        votes = majority_vote_unordered(obs)
        rec, _ = topo_sort_with_cycle_break(votes)
        self.assertEqual(rec, truth, "noiseless + 20 CRPs must give exact ordering")


class TestTopoSort(unittest.TestCase):
    def test_known_dag(self) -> None:
        """A clean tournament (ring 0 fastest ... ring 15 slowest) -> known order."""
        votes = {}
        for lo in range(N_RINGS):
            for hi in range(lo + 1, N_RINGS):
                votes[(lo, hi)] = (lo, 10, 0)  # lo always wins
        rec, cyc = topo_sort_with_cycle_break(votes)
        self.assertEqual(rec, list(range(N_RINGS)))
        self.assertEqual(cyc, 0)

    def test_cycle_break(self) -> None:
        """A 3-cycle (0>1>2>0) must be detected, broken, and produce a valid
        ordering with cycle_breaks >= 1 (P2-2 fix: real assertions)."""
        votes = {}
        # Construct a 3-cycle among rings 0,1,2 with known strengths:
        #   0 beats 1 (8-2), 1 beats 2 (6-4), 2 beats 0 (5-5 tie -> weak)
        # The weakest edge (2>0, strength 0) should be deleted.
        votes[(0, 1)] = (0, 8, 2)  # 0 beats 1, strong
        votes[(1, 2)] = (1, 6, 4)  # 1 beats 2, medium
        votes[(0, 2)] = (2, 5, 5)  # 2 beats 0, weakest (tie)
        # Fill remaining pairs (3..15): linear order 3>4>...>15, and
        # 0,1,2 each beat 3..15
        for lo in range(N_RINGS):
            for hi in range(lo + 1, N_RINGS):
                if (lo, hi) not in votes:
                    if lo < 3:
                        votes[(lo, hi)] = (lo, 10, 0)  # 0/1/2 beat all higher
                    else:
                        votes[(lo, hi)] = (lo, 10, 0)  # linear among 3..15
        rec, cyc = topo_sort_with_cycle_break(votes)
        # After breaking the weakest edge (2>0), order should be 0>1>2>3>...>15
        self.assertEqual(rec[:3], [0, 1, 2],
                         f'first 3 should be [0,1,2] after cycle break, got {rec[:3]}')
        self.assertEqual(rec, list(range(N_RINGS)),
                         f'full ordering should be linear, got {rec}')
        self.assertGreaterEqual(cyc, 1,
                                f'at least 1 cycle break needed, got {cyc}')


class TestKendallTau(unittest.TestCase):
    def test_identity_is_one(self) -> None:
        tau = kendall_tau_positions(list(range(N_RINGS)), list(range(N_RINGS)))
        self.assertAlmostEqual(tau, 1.0)

    def test_reversed_is_minus_one(self) -> None:
        tau = kendall_tau_positions(list(range(N_RINGS)), list(reversed(range(N_RINGS))))
        self.assertAlmostEqual(tau, -1.0)

    def test_random_near_zero(self) -> None:
        rng = np.random.default_rng(5)
        perm = list(range(N_RINGS))
        rng.shuffle(perm)
        tau = kendall_tau_positions(perm, list(range(N_RINGS)))
        self.assertLess(abs(tau), 0.6)  # random 16-element perm tau is small


class TestSmoke(unittest.TestCase):
    def test_arbiter_gen_smoke(self) -> None:
        rng = np.random.default_rng(1)
        X, y, w, std = gen_arbiter_crps(100, 0.1, rng)
        self.assertEqual(X.shape, (100, 64))
        self.assertEqual(y.shape, (100,))
        self.assertGreater(std, 0)
        self.assertTrue(set(y.tolist()) <= {0, 1})

    def test_distinct_freq_puf(self) -> None:
        rng = np.random.default_rng(3)
        puf, rej = gen_distinct_freq_puf(rng)
        self.assertEqual(len(set(puf.freqs)), N_RINGS)
        self.assertIsInstance(rej, int)


if __name__ == "__main__":
    unittest.main(verbosity=2)