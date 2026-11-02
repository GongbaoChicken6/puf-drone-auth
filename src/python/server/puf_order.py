"""Ring-order reconstruction and comparison for the RO-pairing PUF.

Root-cause finding (2026-11-01, data/d1_evidence/rootcause/): the 64-bit
response is fully determined by the 16-ring frequency ORDER -- a template of
>=100 CRPs reconstructs the total order with zero contradictions (verified on
real board data, forward-recompute HD=0).  Two terminals sharing a bitstream
layout therefore share the order, and the order is a seed-independent
identity signature.  This module turns that finding into the enrollment
correlation guard (M3) and the cross-template uniqueness metric (M1).

Design anchors:
- decode_pair_table(seed) -> 8 rounds x 8 pairs of (ring_a, ring_b); bit=1
  iff freq[b] > freq[a]; winner gets one vote per observation (rootcause v3).
- MIN quality gates per plan v2 (ar-spec-r1 round-2): templates below
  MIN_CRPS / below full 120-pair coverage / above 2% contradiction rate are
  "unreliable" -- the guard skips them with a warning instead of judging.
- Kendall agreement over 120 pairs: clone ~0.98-1.0, independent ~0.5 with
  sigma=0.0932 (transitivity-correlated indicators); reject threshold 0.85.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from ..evaluation.puf_model import N_RINGS, decode_pair_table

#: Minimum CRP count for a reliable order reconstruction (plan v2).
MIN_CRPS = 100

#: Maximum tolerated pairwise contradiction rate (plan v2).
MAX_CONTRADICTION_RATE = 0.02

#: Reject threshold for Kendall agreement (round-2 review: sigma=0.0932,
#: 0.85 ~ 3.8 sigma with 0/2000 empirical false-positive on independents).
AGREE_REJECT = 0.85

_BITS_PER_RESPONSE = 64
_PAIRS_PER_RESPONSE = 8  # 8 rounds x 8 pairs = 64 comparison bits
_ALL_PAIRS = [
    (a, b) for a in range(N_RINGS) for b in range(a + 1, N_RINGS)
]  # 120 unordered pairs


@dataclass
class OrderResult:
    """Outcome of reconstructing a ring order from one template."""

    order: list[int] = field(default_factory=list)  # fast -> slow
    n_crps: int = 0
    pairs_covered: int = 0
    contradiction_rate: float = 1.0
    usable: bool = False
    reason: str = ""


def reconstruct_order(template: Mapping[str, str]) -> OrderResult:
    """Reconstruct the 16-ring total order from a {seed_hex: resp_hex} template.

    Votes: each comparison bit elects the faster ring (bit=1 -> b wins).
    Contradiction rate = fraction of covered pairs with votes for both sides.
    """
    wins = [0] * N_RINGS
    pair_votes: dict[tuple[int, int], dict[int, int]] = {}
    covered: set[tuple[int, int]] = set()
    n = 0
    for seed_hex, resp_hex in template.items():
        n += 1
        seed_int = int(seed_hex, 16)
        resp = int(resp_hex, 16)
        for r, pairs in enumerate(decode_pair_table(seed_int)):
            for p, (a, b) in enumerate(pairs):
                bit = (resp >> (63 - (r * _PAIRS_PER_RESPONSE + p))) & 1
                winner = b if bit else a
                wins[winner] += 1
                key = (min(a, b), max(a, b))
                covered.add(key)
                votes = pair_votes.setdefault(key, {})
                votes[winner] = votes.get(winner, 0) + 1

    contradictions = sum(1 for v in pair_votes.values() if len(v) > 1)
    covered_count = len(covered)
    contr_rate = (contradictions / covered_count) if covered_count else 1.0

    order = sorted(range(N_RINGS), key=lambda x: -wins[x])
    usable = (
        n >= MIN_CRPS
        and covered_count >= len(_ALL_PAIRS)
        and contr_rate <= MAX_CONTRADICTION_RATE
    )
    reason = ""
    if not usable:
        parts = []
        if n < MIN_CRPS:
            parts.append(f"n_crps={n}<{MIN_CRPS}")
        if covered_count < len(_ALL_PAIRS):
            parts.append(f"coverage={covered_count}/{len(_ALL_PAIRS)}")
        if contr_rate > MAX_CONTRADICTION_RATE:
            parts.append(f"contradiction_rate={contr_rate:.3f}")
        reason = "; ".join(parts)
    return OrderResult(
        order=order,
        n_crps=n,
        pairs_covered=covered_count,
        contradiction_rate=contr_rate,
        usable=usable,
        reason=reason,
    )


def order_agreement(order_a: list[int], order_b: list[int]) -> float:
    """Kendall agreement over all 120 unordered pairs (1.0=same, 0.5=independent)."""
    rank_a = [0] * N_RINGS
    rank_b = [0] * N_RINGS
    for pos, ring in enumerate(order_a):
        rank_a[ring] = pos
    for pos, ring in enumerate(order_b):
        rank_b[ring] = pos
    agree = sum(
        1
        for a, b in _ALL_PAIRS
        if (rank_a[a] < rank_a[b]) == (rank_b[a] < rank_b[b])
    )
    return agree / len(_ALL_PAIRS)


def predict_response(order: list[int], seed_int: int) -> int:
    """Forward-compute the 64-bit response for a seed under a given order.

    Equivalence anchor: rootcause rtl_r1_order_reconstruction_v3.py verified
    this exact bit-packing against the real board template (HD=0 over 100
    CRPs, official frame parser with CRC).
    """
    rank = [0] * N_RINGS
    for pos, ring in enumerate(order):
        rank[ring] = N_RINGS - 1 - pos  # fast -> high rank value
    bits = 0
    for r, pairs in enumerate(decode_pair_table(seed_int)):
        for p, (a, b) in enumerate(pairs):
            if rank[b] > rank[a]:
                bits |= 1 << (63 - (r * _PAIRS_PER_RESPONSE + p))
    return bits
