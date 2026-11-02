# -*- coding: utf-8 -*-
"""SAC (Strict Avalanche Criterion) test on the golden CRP model (M2, plan v2).

Measures challenge-decoding diffusion: flip one challenge bit, count response
bit flips.  Scope: golden model (deterministic fixture frequencies) -- this
tests the LFSR+Fisher-Yates pairing diffusion, NOT silicon near-tie noise.

Usage:
  python tools/puf_sac.py --n-base 256 --seed 20261102 --out data/d1_evidence/puf_sac.json
"""
from __future__ import annotations
import argparse, json, random, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.python.evaluation.puf_model import N_RINGS, ROPairingPUF, decode_pair_table

RESPONSE_BITS = 64


def sac_test(n_base: int, seed: int, freqs: list[int]) -> dict:
    rng = random.Random(seed)
    puf = ROPairingPUF(freqs=freqs)

    base_seeds = [rng.getrandbits(64) for _ in range(n_base)]
    base_resps = [int.from_bytes(puf.ideal(s), "big") for s in base_seeds]

    per_bit_flip_rate = [0.0] * RESPONSE_BITS
    global_flips = 0
    total_comparisons = 0

    for bit_pos in range(64):
        flipped = 0
        for i, base_seed in enumerate(base_seeds):
            mutated = base_seed ^ (1 << bit_pos)
            mutated_resp = int.from_bytes(puf.ideal(mutated), "big")
            hd = bin(base_resps[i] ^ mutated_resp).count("1")
            flipped += hd
            global_flips += hd
            total_comparisons += RESPONSE_BITS
        per_bit_flip_rate[bit_pos] = flipped / (n_base * RESPONSE_BITS)

    global_sac = global_flips / total_comparisons
    return {
        "n_base": n_base,
        "global_sac": round(global_sac, 4),
        "per_bit_min": round(min(per_bit_flip_rate), 4),
        "per_bit_max": round(max(per_bit_flip_rate), 4),
        "per_bit_mean": round(sum(per_bit_flip_rate) / len(per_bit_flip_rate), 4),
        "ideal": 0.5,
        "scope": "golden model (challenge-decoding diffusion, not silicon noise)",
    }


def main():
    parser = argparse.ArgumentParser(description="SAC test on golden model")
    parser.add_argument("--n-base", type=int, default=256)
    parser.add_argument("--seed", type=int, default=20261102)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    # Deterministic freq set (matches the rootcause order for tid=1)
    rng = random.Random(args.seed)
    freqs = sorted(rng.sample(range(3100, 9601), N_RINGS))
    result = sac_test(args.n_base, args.seed, freqs)
    print(json.dumps(result, indent=2))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("SAC_OK")


if __name__ == "__main__":
    main()
