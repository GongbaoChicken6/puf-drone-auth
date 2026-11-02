# -*- coding: utf-8 -*-
"""PUF evaluation metrics: uniformity / uniqueness / reliability (M1, plan v2).
Port of the PUF_ARTY_S7 reference MATLAB suite (crpProcessing/*.m) to Python.

Usage (repo root):
  python tools/puf_metrics.py --templates data/templates/templates.json
  python tools/puf_metrics.py --templates ... --tids 1,2 --out data/d1_evidence/puf_metrics.json
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from itertools import combinations

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.python.server.puf_order import (  # noqa: E402
    N_RINGS, OrderResult, order_agreement, predict_response, reconstruct_order,
)

RESPONSE_BITS = 64


def uniformity(template: dict[str, str]) -> float:
    """Fraction of '1' bits across all responses (ideal 0.50)."""
    total_ones = sum(int(r, 16).bit_count() for r in template.values())
    total_bits = len(template) * RESPONSE_BITS
    return total_ones / total_bits if total_bits else 0.0


def reliability_proxy(stability_mask: str | None) -> float:
    """Stable-bit fraction from the enrollment mask (ideal 1.00).
    v1 proxy: uses the 64-char mask; v1.1 will use raw measurements."""
    if stability_mask is None:
        return -1.0
    return stability_mask.count("1") / RESPONSE_BITS


def cross_order_mismatch(order_a: list[int], order_b: list[int],
                         n_probes: int = 100, seed: int = 20261102) -> float:
    """Expected per-response HD fraction between two independent orders.
    Generates n_probes random seeds, computes predict_response under both
    orders, returns mean HD / 64.  Clone ~0.0; independent ~0.5."""
    import random
    rng = random.Random(seed)
    hds = []
    for _ in range(n_probes):
        s = rng.getrandbits(64)
        ra = predict_response(order_a, s)
        rb = predict_response(order_b, s)
        hds.append(bin(ra ^ rb).count("1") / RESPONSE_BITS)
    return sum(hds) / len(hds)


def uniqueness(templates: dict[str, dict[str, str]]) -> list[dict]:
    """Cross-template uniqueness via order-signature (seed-independent).
    Returns per-pair results: agreement (Kendall) + predicted mismatch."""
    orders = {}
    for tid, template in templates.items():
        res = reconstruct_order(template)
        orders[tid] = res
    results = []
    for (ta, ra), (tb, rb) in combinations(orders.items(), 2):
        entry = {"pair": f"{ta}vs{tb}", "usable_a": ra.usable, "usable_b": rb.usable}
        if ra.usable and rb.usable:
            entry["agreement"] = round(order_agreement(ra.order, rb.order), 4)
            entry["predicted_mismatch"] = round(cross_order_mismatch(ra.order, rb.order), 4)
        results.append(entry)
    return results


def main():
    parser = argparse.ArgumentParser(description="PUF evaluation metrics trio")
    parser.add_argument("--templates", required=True, help="path to templates.json")
    parser.add_argument("--tids", default="", help="comma-separated tids (default: all)")
    parser.add_argument("--out", default="", help="output JSON path")
    args = parser.parse_args()

    data = json.loads(Path(args.templates).read_text(encoding="utf-8"))
    tids = [t.strip() for t in args.tids.split(",") if t.strip()] or list(data.keys())

    report = {"uniformity": {}, "uniqueness": [], "reliability": {}}
    for tid in tids:
        if tid not in data:
            continue
        template = data[tid]
        report["uniformity"][tid] = round(uniformity(template), 4)
        # reliability proxy from stability mask (loaded separately)
        stab_path = Path(args.templates).with_suffix(".stability.json")
        if stab_path.exists():
            stab = json.loads(stab_path.read_text(encoding="utf-8"))
            report["reliability"][tid] = round(reliability_proxy(stab.get(tid)), 4)
        else:
            report["reliability"][tid] = -1.0

    # uniqueness across all selected tids
    selected = {t: data[t] for t in tids if t in data}
    report["uniqueness"] = uniqueness(selected)

    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("METRICS_OK")


if __name__ == "__main__":
    main()
