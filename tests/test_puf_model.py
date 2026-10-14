"""W4-P1 puf_model unit tests: frozen goldens + semantic properties.

Locks the three cross-checked pair tables (RTL == Python == contract S8)
and the R1 bit/byte semantics independent of the RTL.

Run from the repository root::

    python tests\\test_puf_model.py
    python -m unittest tests.test_puf_model -v
"""

import random
import subprocess
import sys
import unittest
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.python.evaluation.puf_model import (
    DEFAULT_FREQ_MAX,
    DEFAULT_FREQ_MIN,
    GOLDEN_SEED_A,
    GOLDEN_SEED_B,
    GOLDEN_SEED_C,
    KDF_KEY_SEED,
    N_RINGS,
    N_ROUNDS,
    PAIRS_PER_ROUND,
    ROPairingPUF,
    decode_pair_table,
    derive_device_key,
    pair_table_hex,
    pair_table_int,
)

GOLDEN_HEX_A = ("ed95c642731b8f0a3d64759e182a0bcf54de39c86a0f7b1249102586ba7fec3d"
                "1749f508cda26be309d643e7b2ca85f1c37451df82a690be0fe8b7251ac3d469")
GOLDEN_HEX_B = ("c1fe30d6875ab294315b0f4e2dac689730478cef9a5bd12604b16ce3af89752d"
                "5b6d302a849e1f7cd7e6519af4c320b849a0f32cb1875ed6f038d25be71ca496")
GOLDEN_HEX_C = ("4867c915fea0bd23f8b243dc1a7e6590cd50162ea87fb9346140b2ac8fed9573"
                "875ed203f61ab49c1ab245c09fd6837e38c496a2ef501d7becfba16d28395740")


class TestGoldenTables(unittest.TestCase):
    def test_frozen_seed_a_matches_contract(self) -> None:
        self.assertEqual(pair_table_hex(GOLDEN_SEED_A), GOLDEN_HEX_A)

    def test_frozen_seed_b_matches_contract(self) -> None:
        self.assertEqual(pair_table_hex(GOLDEN_SEED_B), GOLDEN_HEX_B)

    def test_frozen_seed_c_matches_contract(self) -> None:
        self.assertEqual(pair_table_hex(GOLDEN_SEED_C), GOLDEN_HEX_C)

    def test_int_and_hex_agree(self) -> None:
        for seed in (GOLDEN_SEED_A, GOLDEN_SEED_B, GOLDEN_SEED_C):
            self.assertEqual(f"{pair_table_int(seed):0128x}", pair_table_hex(seed))


class TestDecodeProperties(unittest.TestCase):
    def test_each_round_is_a_permutation(self) -> None:
        rng = random.Random(0xC0FFEE)
        for _ in range(20):
            seed = rng.getrandbits(64)
            for pairs in decode_pair_table(seed):
                # A-side and B-side hold 8 rings EACH; only the union of
                # the 16 nibbles must be a permutation of 0..15.
                combined = sorted([a for a, _ in pairs] + [b for _, b in pairs])
                self.assertEqual(combined, list(range(N_RINGS)))

    def test_deterministic(self) -> None:
        for seed in (0, 1, GOLDEN_SEED_B, GOLDEN_SEED_C):
            self.assertEqual(decode_pair_table(seed), decode_pair_table(seed))

    def test_zero_seed_still_permutation(self) -> None:
        for pairs in decode_pair_table(0):
            combined = sorted([a for a, _ in pairs] + [b for _, b in pairs])
            self.assertEqual(combined, list(range(N_RINGS)))

    def test_bytes_seed_matches_int_seed(self) -> None:
        seed_bytes = GOLDEN_SEED_A.to_bytes(8, "big")
        self.assertEqual(decode_pair_table(seed_bytes), decode_pair_table(GOLDEN_SEED_A))


class TestResponseSemantics(unittest.TestCase):
    def test_ideal_via_independent_hex_path(self) -> None:
        """Rebuild R1 from the pair-table HEX (independent path) and
        compare with ROPairingPUF.ideal for a monotonic frequency vector."""
        freqs = list(range(100, 100 + N_RINGS))  # strictly increasing
        puf = ROPairingPUF(freqs=freqs)
        hx = pair_table_hex(GOLDEN_SEED_A)
        nibbles = [int(c, 16) for c in hx]        # MSB first = round 7 .. 0
        expected = 0
        for r in range(N_ROUNDS):
            # hex chars are MSB-first: within a round word the FIRST char
            # is the HIGHEST nibble (order[15]), so reverse the slice to
            # get nibble[2p] == order[2p].
            round_nibbles = nibbles[(N_ROUNDS - 1 - r) * 16:(N_ROUNDS - r) * 16][::-1]
            for p in range(PAIRS_PER_ROUND):
                ring_a = round_nibbles[2 * p]
                ring_b = round_nibbles[2 * p + 1]
                if freqs[ring_b] > freqs[ring_a]:
                    expected |= 1 << (63 - (r * PAIRS_PER_ROUND + p))
        self.assertEqual(puf.ideal(GOLDEN_SEED_A), expected.to_bytes(8, "big"))

    def test_flip_prob_one_complements(self) -> None:
        freqs = list(range(200, 200 + N_RINGS))
        ideal = ROPairingPUF(freqs=freqs).ideal(GOLDEN_SEED_B)
        noisy = ROPairingPUF(freqs=freqs, flip_prob=1.0,
                             rng=random.Random(7)).respond(GOLDEN_SEED_B)
        complement = (int.from_bytes(ideal, "big") ^ ((1 << 64) - 1)).to_bytes(8, "big")
        self.assertEqual(noisy, complement)

    def test_different_devices_differ(self) -> None:
        puf_a = ROPairingPUF(freqs=list(range(300, 300 + N_RINGS)))
        puf_b = ROPairingPUF(freqs=list(reversed(range(300, 300 + N_RINGS))))
        self.assertNotEqual(puf_a.ideal(GOLDEN_SEED_C), puf_b.ideal(GOLDEN_SEED_C))

    def test_measure_jitter_bounds(self) -> None:
        freqs = [5000] * N_RINGS
        puf = ROPairingPUF(freqs=freqs, rng=random.Random(3))
        for f in puf.measure(jitter_pct=5.0):
            self.assertGreaterEqual(f, int(5000 * 0.95) - 1)
            self.assertLessEqual(f, int(5000 * 1.05) + 1)

    def test_bad_freq_count_raises(self) -> None:
        with self.assertRaises(ValueError):
            ROPairingPUF(freqs=[1, 2, 3])


class TestFixtureScript(unittest.TestCase):
    def test_gen_puf_fixtures_golden_runs(self) -> None:
        root = Path(__file__).resolve().parents[1]
        proc = subprocess.run(
            [sys.executable, str(root / "scripts" / "gen_puf_fixtures.py"), "--golden"],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("PUF_SEED_A", proc.stdout)
        self.assertIn(GOLDEN_HEX_A.upper()[:32], proc.stdout.upper())



class TestKeyDerivation(unittest.TestCase):
    """W4-P4 T1: derive_device_key golden vectors and properties."""

    def test_golden_k_from_fixture_freqs(self) -> None:
        """Golden K from the frozen fixture frequencies (CI cross-check anchor)."""
        import random
        rng = random.Random(0x0044_3450)
        freqs = sorted(rng.sample(range(DEFAULT_FREQ_MIN, DEFAULT_FREQ_MAX + 1), N_RINGS))
        puf = ROPairingPUF(freqs=freqs)
        k = derive_device_key(puf)
        self.assertEqual(len(k), 12)
        # Golden vector (generated 2026-10-13, frozen for RTL cross-check)
        self.assertEqual(k.hex(), "ee1d0425f39f31ba61ecc426")

    def test_k_boot_is_puf_response_to_key_seed(self) -> None:
        freqs = list(range(5000, 5016))
        puf = ROPairingPUF(freqs=freqs)
        kb = puf.ideal(KDF_KEY_SEED)
        self.assertEqual(len(kb), 8)
        # Deterministic: same device → same K_boot
        self.assertEqual(kb, puf.ideal(KDF_KEY_SEED))

    def test_different_devices_different_keys(self) -> None:
        puf_a = ROPairingPUF(freqs=list(range(4000, 4016)))
        puf_b = ROPairingPUF(freqs=list(reversed(range(4000, 4016))))
        k_a = derive_device_key(puf_a)
        k_b = derive_device_key(puf_b)
        self.assertNotEqual(k_a, k_b)
        self.assertEqual(len(k_a), 12)
        self.assertEqual(len(k_b), 12)

    def test_key_not_public_vector(self) -> None:
        """P1-1: derived key must not equal the known NSA public vector."""
        NSA_PUBLIC = bytes.fromhex("0001020308090a0b10111213")
        puf = ROPairingPUF(freqs=list(range(5000, 5016)))
        k = derive_device_key(puf)
        self.assertNotEqual(k, NSA_PUBLIC,
            "P1-1 regression: derived key equals public NSA vector")


if __name__ == "__main__":
    unittest.main(verbosity=2)