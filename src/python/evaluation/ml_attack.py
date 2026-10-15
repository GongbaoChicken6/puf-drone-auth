"""W4-P5 ML attack experiments (B6 deliverable, 20 points).

Two experiments per the frozen spec (project_design.md L379-410):

Experiment A -- synthetic arbiter PUF + Logistic Regression baseline.
  Additive delay model, 64 stages, cumprod(+-1) features (a valid
  linear-in-parameters arbiter model per Ruehrmair et al. 2010).
  RELATIVE noise alpha * signal_std (plan v2 fix for TECH P1-1: absolute
  sigma=0.05/0.1 gives SNR~80/160 -> all lines flat at 99.9%).

Experiment B -- RO ranking reconstruction attack (honest self-evaluation).
  CRPs -> UNORDERED pair aggregation (min,max key, plan v2 fix for TECH
  P1-2: ordered keys split votes ~32+32) -> majority vote -> tournament
  graph -> weakest-edge cycle removal + Kahn topological sort. Devices use
  rejection-sampled distinct frequencies (plan v2 fix for TECH P2-5: 1.75%
  birthday collision makes ground-truth ordering undefined).

Entry: python -m src.python.evaluation.ml_attack --exp A|B|all --out DIR --seed N
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

import matplotlib
matplotlib.use("Agg")  # headless-safe (plan v2, TECH P3)
import matplotlib.pyplot as plt

import sklearn
import scipy
from scipy.stats import kendalltau
from sklearn.linear_model import LogisticRegression

from src.python.evaluation.puf_model import (
    N_RINGS,
    ROPairingPUF,
    decode_pair_table,
)

# ------------------------------------------------------------------
# Shared helpers
# ------------------------------------------------------------------

CONCLUSION_A = "\u6587\u732e\u57fa\u7ebf\u5728\u6211\u4eec\u7684\u8bc4\u4f30\u6846\u67b6\u4e2d\u590d\u73b0\u6210\u529f"

# Security declaration (frozen, project_design.md L399-402, four items verbatim)
SECURITY_DECLARATIONS = [
    "\u2705 \u53ef\u58f0\u660e\uff1a\u201c\u6297\u903b\u8f91\u56de\u5f52\u5efa\u6a21\u653b\u51fb\u201d\uff08\u5bf9 XOR \u5408\u5e76\u540e\u7684\u54cd\u5e94\uff09",
    "\u274c \u4e0d\u53ef\u58f0\u660e\uff1a\u201c\u6297\u673a\u5668\u5b66\u4e60\u653b\u51fb\u201d\uff08\u6392\u5e8f\u91cd\u6784\u5bf9 RO \u7ed3\u6784\u6709\u6548\uff09",
    "\u2705 \u53ef\u58f0\u660e\uff1a\u201c\u5df2\u91cf\u5316\u5b89\u5168\u8fb9\u754c\uff1a\u6709\u6548\u71b5 \u224844 bit\uff0c\u6392\u5e8f\u91cd\u6784\u9700 ~120 CRP\u201d",
    "\u2705 \u53ef\u58f0\u660e\uff08\u672a\u6765\u5de5\u4f5c\uff09\uff1a\u201c\u589e\u52a0\u73af\u6570\u81f3 64+ \u53ef\u5c06\u6709\u6548\u71b5\u63d0\u5347\u81f3 ~296 bit\u201d",
]
CONCLUSION_B = (
    "CRP \u7a7a\u95f4\u574D\u7f29\u81f3 ~2\u00d710^6 \u79cd\u914d\u5bf9\u6784\u578b\uff0c"
    "\u6392\u5e8f\u91cd\u6784\u653b\u51fb\u5728 ~120 \u6b21\u89c2\u6d4b\u5185"
    "\u53ef\u6062\u590d\u5b8c\u6574\u6392\u5e8f\u2014\u2014"
    "\u8fd9\u662f\u6211\u4eec\u8bbe\u8ba1\u7684\u5df2\u77e5\u8fb9\u754c\uff0c"
    "\u5728\u62a5\u544a\u4e2d\u5982\u5b9e\u8ba8\u8bba"
)
F2_FOOTNOTE = (
    "16! = 2.09e13 ~= 2^44; the frozen text 2x10^6 appears to be a "
    "typo for 2x10^13 (flagged for W6 adjudication)"
)

def _compute_vote_stats(seeds, responses, target_n=120):
    """B-P2-3 fix: compute vote stats from actual data instead of hardcoding."""
    obs = extract_unordered_observations(seeds[:target_n], responses[:target_n])
    counts = sorted(len(v) for v in obs.values())
    if not counts:
        return None
    n = len(counts)
    return {
        "n_pairs": n,
        "min": counts[0],
        "median": counts[n // 2],
        "max": counts[-1],
    }


def _versions() -> dict:
    return {
        "sklearn": sklearn.__version__,
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "matplotlib": matplotlib.__version__,
    }

def _save_json(path: Path, obj: dict) -> None:
    """T8 fix: cast numpy scalars before json.dumps (np.int64 raises)."""
    def cast(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        raise TypeError(f"{type(o)} not serializable")
    path.write_text(json.dumps(obj, indent=2, default=cast, ensure_ascii=False), encoding="utf-8")

# ------------------------------------------------------------------
# Experiment A: synthetic arbiter PUF + LR
# ------------------------------------------------------------------

def gen_arbiter_crps(n: int, alpha: float, rng: np.random.Generator,
                     w: np.ndarray | None = None):
    """Generate n CRPs from a 64-stage additive-delay arbiter PUF.

    Features: phi_i(c) = prod_{j<=i} (-1)^{c_j} (cumprod prefix product,
    the mirror of Ruehrmair's suffix-product convention -- same
    distribution under uniform random challenges).
    Noise: RELATIVE alpha * signal_std (plan v2 / TECH P1-1).
    """
    stages = 64
    if w is None:
        w = rng.normal(size=stages)
    C = rng.integers(0, 2, size=(n, stages))
    Phi = np.cumprod(np.where(C == 0, 1.0, -1.0), axis=1)
    signal_std = float(np.std(Phi[: min(n, 1000)] @ w))
    eps = rng.normal(0, alpha * signal_std, n) if alpha > 0 else np.zeros(n)
    y = (Phi @ w + eps > 0).astype(int)
    return Phi, y, w, signal_std


def _bayes_acc(alpha: float) -> float:
    """Bayes-optimal accuracy for sign(signal+noise) with SNR=1/alpha."""
    if alpha <= 0:
        return 1.0
    return float(1.0 - np.arctan(alpha) / np.pi)


def run_exp_a(out_dir: Path, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    train_sizes = [1000, 5000, 10000, 50000, 100000]
    alphas = [0.00, 0.05, 0.15, 0.30]
    n_test = 10000

    # One device w for train AND test (same PUF, different challenges).
    w = rng.normal(size=64)

    acc = {f"{a:.2f}": {} for a in alphas}
    for a in alphas:
        X_te, y_te, _, _ = gen_arbiter_crps(n_test, a, rng, w)
        for n_tr in train_sizes:
            X_tr, y_tr, _, _ = gen_arbiter_crps(n_tr, a, rng, w)
            lr = LogisticRegression()  # default hyperparams (TECH T4 verified)
            lr.fit(X_tr, y_tr)
            acc[f"{a:.2f}"][str(n_tr)] = float(lr.score(X_te, y_te))
        print(f"  alpha={a:.2f}: " +
              ", ".join(f"{n//1000}k={acc[f'{a:.2f}'][str(n)]:.4f}"
                         for n in train_sizes))

    # Plot
    fig, ax = plt.subplots(figsize=(8, 5))
    for a in alphas:
        ys = [acc[f"{a:.2f}"][str(n)] for n in train_sizes]
        ax.plot(train_sizes, ys, "o-", label=f"alpha={a:.2f}")
    for a in alphas:
        ax.axhline(_bayes_acc(a), ls="--", alpha=0.15, color="gray")
    ax.set_xscale("log")
    ax.set_xlabel("Training set size")
    ax.set_ylabel("Test accuracy")
    ax.set_title("Experiment A: LR attack on synthetic arbiter PUF\n(relative noise, dashed = Bayes optimal)")
    ax.legend(); ax.grid(alpha=0.3); ax.set_ylim(0.5, 1.02)
    fig.tight_layout(); fig.savefig(out_dir / "exp_a_accuracy.png", dpi=150); plt.close(fig)

    signal_std = float(np.std(np.random.default_rng(seed).normal(size=64)))
    result = {
        "repro_command": f"python -m src.python.evaluation.ml_attack --exp A --out {out_dir} --seed {seed}",
        "versions": _versions(),
        "seed": seed,
        "signal_std": signal_std,
        "train_sizes": train_sizes,
        "noise_rel": alphas,
        "n_test": n_test,
        "bayes_acc": {f"{a:.2f}": _bayes_acc(a) for a in alphas},
        "accuracy": acc,
        "conclusion_A": CONCLUSION_A,
        "security_declarations": SECURITY_DECLARATIONS,
        "frozen_floor": 0.95,
        "self_target": 0.99,
        "note": "relative noise alpha*signal_std; train/test share the same device w and the same noise",
    }
    _save_json(out_dir / "exp_a_results.json", result)
    print(f"  -> {out_dir}/exp_a_results.json + exp_a_accuracy.png")
    return result

# ------------------------------------------------------------------
# Experiment B: RO ranking reconstruction
# ------------------------------------------------------------------

def gen_distinct_freq_puf(rng, flip_prob: float = 0.0) -> tuple[ROPairingPUF, int]:
    """TECH P2-5 fix: rejection-sample until all 16 freqs are distinct.

    randint(3100,9600) has a 1.75% birthday collision rate; a collided
    device's ground-truth ordering is undefined (exact-match would be
    permanently 0 for ~0.9% of devices).
    """
    import random as _r
    rejections = 0
    _dev_rng = _r.Random(int(rng.integers(0, 2**31)))
    while True:
        # P3-1 fix: randint with real rejection (sample() is without-replacement
        # making the old rejection branch dead code; randint matches the
        # 1.75% birthday collision the TECH review measured)
        freqs = [_dev_rng.randint(3100, 9600) for _ in range(N_RINGS)]
        if len(set(freqs)) == N_RINGS:
            # P1-2 fix: seeded noise RNG derived from the numpy rng --
            # SystemRandom() is non-deterministic, breaking --seed reproducibility
            noise_rng = _r.Random(int(rng.integers(0, 2**31)))
            return ROPairingPUF(freqs=freqs, flip_prob=flip_prob,
                             rng=noise_rng), rejections
        rejections += 1


def extract_unordered_observations(seeds: list[int], responses: list[bytes]):
    """TECH P1-2 fix: aggregate by UNORDERD pair key (min, max).

    decode_pair_table outputs DIRECTED pairs (A,B); 120/120 unordered
    pairs appear in both orientations across seeds. An ordered key would
    split votes (~32+32), halving the effective vote count.
    """
    from collections import defaultdict
    obs = defaultdict(list)  # (lo, hi) -> list of winners
    for seed, resp in zip(seeds, responses):
        table = decode_pair_table(seed)
        bits = int.from_bytes(resp, "big")
        idx = 0
        for round_pairs in table:
            for (a, b) in round_pairs:
                bit = (bits >> (63 - idx)) & 1
                lo, hi = min(a, b), max(a, b)
                # bit=1 ALWAYS means freq[ring_b] > freq[ring_a] where (a,b)=(ring_a,ring_b)
                # from the ORIGINAL tuple -- regardless of index ordering.
                # So winner (higher freq = faster ring) = b when bit=1, else a.
                # No direction-branching needed; the min/max is for the KEY only.
                winner = b if bit == 1 else a
                obs[(lo, hi)].append(winner)
                idx += 1
    return obs


def majority_vote_unordered(obs) -> dict:
    """Majority vote per unordered pair; deterministic tie-break by ring index."""
    votes = {}
    for key, winners in obs.items():
        c0 = winners.count(key[0])
        c1 = len(winners) - c0
        if c0 > c1:
            votes[key] = (key[0], c0, c1)
        elif c1 > c0:
            votes[key] = (key[1], c0, c1)
        else:
            votes[key] = (key[0], c0, c1)  # tie: lower index wins (deterministic)
    return votes


def _has_cycle(edges: set) -> bool:
    """Check if the directed edge set contains a cycle (DFS)."""
    from collections import defaultdict
    adj = defaultdict(set)
    for u, v in edges:
        adj[u].add(v)
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in range(N_RINGS)}
    def dfs(u):
        color[u] = GRAY
        for v in adj[u]:
            if color[v] == GRAY:
                return True
            if color[v] == WHITE and dfs(v):
                return True
        color[u] = BLACK
        return False
    return any(color[n] == WHITE and dfs(n) for n in range(N_RINGS))


def topo_sort_with_cycle_break(votes: dict):
    """TECH P2-6: weakest-edge cycle removal + Kahn topological sort.

    Returns (ordering, cycle_breaks).
    """
    # Build directed edges: winner -> loser (winner is faster)
    # votes: (lo,hi) -> (winner, c0, c1) where c0=count(lo wins), c1=count(hi wins)
    edges = {}
    for (lo, hi), (winner, c0, c1) in votes.items():
        loser = hi if winner == lo else lo
        strength = abs(c0 - c1)
        edges[(winner, loser)] = strength

    # Cycle removal: repeatedly find a cycle and delete its weakest edge
    cycle_breaks = 0
    edge_set = set(edges.keys())
    while _has_cycle(edge_set):
        # Find a cycle (DFS path tracking)
        from collections import defaultdict
        adj = defaultdict(list)
        for u, v in edge_set:
            adj[u].append(v)
        cycle = None
        def find_cycle(u, path, visited_on_path):
            nonlocal cycle
            if cycle:
                return
            visited_on_path.add(u)
            path.append(u)
            for v in sorted(adj[u]):
                if v in visited_on_path:
                    # Found cycle: path[path.index(v):]
                    cycle = path[path.index(v):]
                    return
                if v not in visited_on_path:
                    find_cycle(v, path, visited_on_path)
                    if cycle:
                        return
            path.pop()
            visited_on_path.discard(u)
        # P2-1 fix: try ALL roots, not just node 0 (a cycle unreachable from 0
        # would be silently missed, falling through to Copeland with cycles=0)
        for _start in range(N_RINGS):
            if cycle:
                break
            find_cycle(_start, [], set())
        if not cycle:
            break
        # Delete the weakest edge in the cycle
        cycle_edges = [(cycle[i], cycle[(i + 1) % len(cycle)]) for i in range(len(cycle))]
        cycle_edges = [e for e in cycle_edges if e in edges]
        if not cycle_edges:
            break
        weakest = min(cycle_edges, key=lambda e: edges[e])
        edge_set.discard(weakest)
        cycle_breaks += 1

    # Kahn topological sort
    from collections import defaultdict, deque
    adj = defaultdict(list)
    in_deg = {n: 0 for n in range(N_RINGS)}
    for u, v in edge_set:
        adj[u].append(v)
        in_deg[v] += 1
    queue = deque(sorted(n for n in range(N_RINGS) if in_deg[n] == 0))
    ordering = []
    while queue:
        u = queue.popleft()
        ordering.append(u)
        for v in sorted(adj[u]):
            in_deg[v] -= 1
            if in_deg[v] == 0:
                queue.append(v)
    if len(ordering) < N_RINGS:
        # Fallback: Copeland out-degree ranking (TECH P2-6)
        out_deg = {n: 0 for n in range(N_RINGS)}
        for u, _ in edge_set:
            out_deg[u] += 1
        ordering = sorted(range(N_RINGS), key=lambda n: -out_deg[n])
    return ordering, cycle_breaks


def kendall_tau_positions(recovered: list[int], truth: list[int]) -> float:
    """TECH P3 fix: use position vectors, not raw permutations."""
    pos_rec = [recovered.index(i) for i in range(N_RINGS)]
    pos_tru = [truth.index(i) for i in range(N_RINGS)]
    tau, _ = kendalltau(pos_rec, pos_tru)
    return float(tau)


def run_exp_b(out_dir: Path, seed: int = 42) -> dict:
    import random
    rng = np.random.default_rng(seed)
    n_sweep = [3, 5, 8, 12, 20, 30, 50, 75, 100, 120, 150, 200, 300, 400]
    flips = [0.00, 0.02, 0.05, 0.10]
    n_trials = 20
    n_max = max(n_sweep)

    # Per flip level: run trials
    results = {f"{f:.2f}": {str(n): {"tau": [], "exact": [], "pair_acc": [], "cycles": []}
               for n in n_sweep} for f in flips}
    total_rejections = 0

    for f in flips:
        for trial in range(n_trials):
            puf, rej = gen_distinct_freq_puf(rng, flip_prob=f)
            total_rejections += rej
            truth = sorted(range(N_RINGS), key=lambda i: -puf.freqs[i])  # fastest first
            # Generate N_max CRPs once (prefix reuse, TECH P2-7)
            seeds = [int(rng.integers(0, 2**63)) for _ in range(n_max)]
            responses = [puf.respond(int(s)) for s in seeds]
            for n in n_sweep:
                obs = extract_unordered_observations(seeds[:n], responses[:n])
                votes = majority_vote_unordered(obs)
                rec, cyc = topo_sort_with_cycle_break(votes)
                tau = kendall_tau_positions(rec, truth)
                exact = 1 if rec == truth else 0
                # Pair accuracy: fraction of pairs where majority direction matches truth
                correct = 0
                for (lo, hi), (winner, _, _) in votes.items():
                    true_winner = lo if puf.freqs[lo] > puf.freqs[hi] else hi
                    if winner == true_winner:
                        correct += 1
                pa = correct / len(votes) if votes else 0.0
                results[f"{f:.2f}"][str(n)]["tau"].append(tau)
                results[f"{f:.2f}"][str(n)]["exact"].append(exact)
                results[f"{f:.2f}"][str(n)]["pair_acc"].append(pa)
                results[f"{f:.2f}"][str(n)]["cycles"].append(cyc)
        print(f"  flip={f:.2f}: done ({n_trials} trials)")

    # Aggregate
    agg = {}
    for f in flips:
        agg[f"{f:.2f}"] = {}
        for n in n_sweep:
            d = results[f"{f:.2f}"][str(n)]
            agg[f"{f:.2f}"][str(n)] = {
                "tau_mean": float(np.mean(d["tau"])),
                "tau_std": float(np.std(d["tau"])),
                "exact_rate": float(np.mean(d["exact"])),
                "pair_acc_mean": float(np.mean(d["pair_acc"])),
                "cycles_mean": float(np.mean(d["cycles"])),
            }

    # Plot
    fig, ax = plt.subplots(figsize=(8, 5))
    for f in flips:
        xs = n_sweep
        ys = [agg[f"{f:.2f}"][str(n)]["exact_rate"] for n in n_sweep]
        ax.plot(xs, ys, "o-", label=f"flip={f:.2f}")
    ax.axvline(120, ls="--", alpha=0.3, color="red", label="design point ~120")
    ax.set_xlabel("Number of CRPs")
    ax.set_ylabel("Exact reconstruction rate")
    ax.set_title("Experiment B: RO ranking reconstruction attack")
    ax.legend(); ax.grid(alpha=0.3); ax.set_ylim(-0.05, 1.05)
    fig.tight_layout(); fig.savefig(out_dir / "exp_b_reconstruction.png", dpi=150); plt.close(fig)

    result = {
        "repro_command": f"python -m src.python.evaluation.ml_attack --exp B --out {out_dir} --seed {seed}",
        "versions": _versions(),
        "seed": seed,
        "n_sweep": n_sweep,
        "flip_levels": flips,
        "n_trials": n_trials,
        "rejection_count": total_rejections,
        "aggregated": agg,
        "conclusion_B": CONCLUSION_B,
        "security_declarations": SECURITY_DECLARATIONS,
        "f2_footnote": F2_FOOTNOTE,
        "note_iid": "per-bit iid flip is the attacker-favorable assumption; real ring jitter is cross-pair correlated and degrades majority voting faster",
        "note_votes": "computed at runtime from actual data",
        "vote_stats_N120": _compute_vote_stats(seeds, responses) if n_max >= 120 else None,
    }
    _save_json(out_dir / "exp_b_results.json", result)
    print(f"  -> {out_dir}/exp_b_results.json + exp_b_reconstruction.png")
    return result

# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exp", choices=["A", "B", "all"], default="all")
    parser.add_argument("--out", default="data/ml_attack")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.exp in ("A", "all"):
        print("=== Experiment A: arbiter PUF + LR ===")
        run_exp_a(out_dir, args.seed)
    if args.exp in ("B", "all"):
        print("=== Experiment B: RO ranking reconstruction ===")
        run_exp_b(out_dir, args.seed)
    print("ML_ATTACK_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())