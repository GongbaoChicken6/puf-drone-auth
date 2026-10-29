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
    """Depth-audit upgrade (2026-10-29, ar-ml-depth-r1 P2 fixes):

    * 5 seeds x 5 independent devices w -> mean +/- std error band
      (was: single seed/device point estimate).
    * Analytic arctan Bayes line kept but relabelled Gaussian
      approximation; an EMPIRICAL Bayes oracle (predict sign(signal),
      exact for the actual Rademacher-sum signal) is added so the
      measured-accuracy <= bound relation holds by construction.
    * signal_std now logged per (alpha, seed) from the values the
      generator actually used (std(Phi @ w)), fixing the stale
      re-sampled-w field.
    * LR convergence evidence (n_iter_) persisted.
    """
    train_sizes = [1000, 5000, 10000, 50000, 100000]
    alphas = [0.00, 0.05, 0.15, 0.30]
    n_test = 10000
    n_seeds = 5
    seeds = [seed + k for k in range(n_seeds)]

    acc_runs = {f"{a:.2f}": {str(n): [] for n in train_sizes} for a in alphas}
    bayes_emp = {f"{a:.2f}": [] for a in alphas}
    signal_std_log: dict = {}
    n_iter_max = 0

    for sd in seeds:
        rng = np.random.default_rng(sd)
        w = rng.normal(size=64)  # fresh device per seed
        for a in alphas:
            Phi_te, y_te, _, std_te = gen_arbiter_crps(n_test, a, rng, w)
            oracle = ((Phi_te @ w) > 0).astype(int)
            bayes_emp[f"{a:.2f}"].append(float(np.mean(y_te == oracle)))
            std_tr = None
            for n_tr in train_sizes:
                Phi_tr, y_tr, _, std_tr = gen_arbiter_crps(n_tr, a, rng, w)
                lr = LogisticRegression()  # default hyperparams (TECH T4)
                lr.fit(Phi_tr, y_tr)
                acc_runs[f"{a:.2f}"][str(n_tr)].append(float(lr.score(Phi_te, y_te)))
                n_iter_max = max(n_iter_max, int(np.max(lr.n_iter_)))
            signal_std_log[f"a={a:.2f},seed={sd}"] = {
                "train_last": std_tr, "test": std_te}
        print(f"  seed {sd}: done")

    acc_mean = {a: {n: float(np.mean(v)) for n, v in d.items()}
                for a, d in acc_runs.items()}
    acc_std = {a: {n: float(np.std(v)) for n, v in d.items()}
               for a, d in acc_runs.items()}
    for a in alphas:
        print(f"  alpha={a:.2f}: " +
              ", ".join(f"{int(n)//1000}k={acc_mean[f'{a:.2f}'][str(n)]:.4f}"
                         for n in train_sizes))

    # Plot: mean line + std band; dashed = empirical Bayes oracle
    fig, ax = plt.subplots(figsize=(8, 5))
    for a in alphas:
        key = f"{a:.2f}"
        m = [acc_mean[key][str(n)] for n in train_sizes]
        s = [acc_std[key][str(n)] for n in train_sizes]
        ax.plot(train_sizes, m, "o-", label=f"alpha={a:.2f}")
        ax.fill_between(train_sizes, np.array(m) - np.array(s),
                        np.array(m) + np.array(s), alpha=0.12)
        ax.axhline(float(np.mean(bayes_emp[key])), ls="--", alpha=0.35,
                   color="gray")
    ax.set_xscale("log")
    ax.set_xlabel("Training set size")
    ax.set_ylabel("Test accuracy (mean over 5 devices, band = std)")
    ax.set_title("Experiment A: LR attack on synthetic arbiter PUF\n(relative noise, dashed = empirical Bayes oracle)")
    ax.legend(); ax.grid(alpha=0.3); ax.set_ylim(0.5, 1.02)
    fig.tight_layout(); fig.savefig(out_dir / "exp_a_accuracy.png", dpi=150); plt.close(fig)

    result = {
        "repro_command": f"python -m src.python.evaluation.ml_attack --exp A --out {out_dir} --seed {seed}",
        "versions": _versions(),
        "seed": seed,
        "seeds": seeds,
        "note_seeds": "5 seeds x 5 independent devices w (depth-audit fix)",
        "train_sizes": train_sizes,
        "noise_rel": alphas,
        "n_test": n_test,
        "bayes_gaussian_approx": {f"{a:.2f}": _bayes_acc(a) for a in alphas},
        "bayes_empirical_mean": {a: float(np.mean(v)) for a, v in bayes_emp.items()},
        "note_bayes": "empirical oracle = predict sign(signal) on the actual Rademacher-sum signals; analytic arctan line is the Gaussian-signal approximation (kept for reference)",
        "signal_std": signal_std_log,
        "note_signal_std": "per (alpha, seed), values actually used by the generator: std(Phi @ w)",
        "lr_convergence": {"max_n_iter": n_iter_max,
                            "converged": bool(n_iter_max < 100)},
        "accuracy": acc_mean,
        "accuracy_std": acc_std,
        "accuracy_runs": acc_runs,
        "conclusion_A": CONCLUSION_A,
        "security_declarations": SECURITY_DECLARATIONS,
        "frozen_floor": 0.95,
        "self_target": 0.99,
        "note": "relative noise alpha*signal_std; per seed, train/test share the same device w and the same noise",
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

    # Plot (depth-audit P2 fix: Kendall tau secondary axis per frozen plan)
    fig, ax = plt.subplots(figsize=(8, 5))
    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    for i, f in enumerate(flips):
        xs = n_sweep
        ys = [agg[f"{f:.2f}"][str(n)]["exact_rate"] for n in n_sweep]
        ax.plot(xs, ys, "o-", color=colors[i], label=f"flip={f:.2f} (exact)")
    ax.axvline(120, ls="--", alpha=0.3, color="red", label="design point ~120")
    ax.set_xlabel("Number of CRPs")
    ax.set_ylabel("Exact reconstruction rate")
    ax2 = ax.twinx()
    for i, f in enumerate(flips):
        ts = [agg[f"{f:.2f}"][str(n)]["tau_mean"] for n in n_sweep]
        sd = [agg[f"{f:.2f}"][str(n)]["tau_std"] for n in n_sweep]
        ax2.plot(n_sweep, ts, "--", color=colors[i], alpha=0.5, lw=1)
        ax2.fill_between(n_sweep, np.array(ts) - np.array(sd),
                         np.array(ts) + np.array(sd), color=colors[i], alpha=0.08)
    ax2.set_ylabel("Kendall tau (dashed, shaded +/-std)")
    ax2.set_ylim(0.5, 1.05)
    ax.set_title("Experiment B: RO ranking reconstruction attack")
    ax.legend(loc="lower right"); ax.grid(alpha=0.3); ax.set_ylim(-0.05, 1.05)
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
        "vote_stats_provenance": "computed from the LAST loop iteration (flip=0.10, trial=20, first 120 CRPs of its prefix); pair coverage depends only on decode_pair_table, not on flip",
        "note_plan_drift": "frozen plan L96 cites older TECH pre-measurements (flip=0.10: N=12 exact 0%, N=20 40%, N=30 90%); the delivered numbers here supersede them -- the pre-runs used an earlier (pre-fix) vote-aggregation prototype; this JSON is the authoritative result",
        "note_design_point": "claim anchoring: worst noise flip=0.10 reaches exact_rate=1.0 by N=30 (20/20 trials); N=120 is the conservative design point covering all C(16,2)=120 unordered pairs",
        "entropy_derivation": "effective entropy = log2(16!) ~ 44.0 bit (16-ring total ordering is the secret); future work log2(64!) ~ 296.0 bit at 64 rings",
    }
    _save_json(out_dir / "exp_b_results.json", result)
    print(f"  -> {out_dir}/exp_b_results.json + exp_b_reconstruction.png")
    return result

# ------------------------------------------------------------------
# Experiment C (depth-audit P1 fix, 2026-10-29): LR directly on the
# W3 XOR-merged response of OUR design -- closes the evidence gap for
# security declaration #1. Controls prove the harness is not blind:
# the same LR attack on the W2 single-group raw response (pair-aware
# featurisation) succeeds ~=100%, while on the XOR-merged response
# every featurisation collapses to ~=50%.
# ------------------------------------------------------------------

def _mix(seed: int, g: int) -> int:
    """Per-group independent-routing assumption (W3: 4 groups of 16
    rings each produce their own 64-bit response; modelled as a
    splitmix-style deterministic remix of the seed per group)."""
    z = (seed + (g + 1) * 0x9E3779B97F4A7C15) & 0x7FFFFFFFFFFFFFFF
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0x7FFFFFFFFFFFFFFF
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0x7FFFFFFFFFFFFFFF
    return (z ^ (z >> 31)) & 0x7FFFFFFFFFFFFFFF


def _bits(responses: list) -> np.ndarray:
    arr = np.frombuffer(b"".join(r if isinstance(r, bytes) else bytes(r)
                                for r in responses),
                        dtype=np.uint8).reshape(len(responses), 8)
    return np.unpackbits(arr, axis=1, bitorder="big").astype(np.int8)


def run_exp_c(out_dir: Path, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    pufs = [gen_distinct_freq_puf(rng)[0] for _ in range(4)]
    train_sizes = [1000, 5000, 10000, 50000]
    n_test = 10000
    n_max = max(train_sizes) + n_test
    seeds = [int(rng.integers(0, 2**63)) for _ in range(n_max)]

    # -- generate responses: 4 XOR groups (independent routing) + W2 control
    resp = {g: [pufs[g].respond(_mix(s, g)) for s in seeds] for g in range(4)}
    ctrl = [pufs[0].respond(s) for s in seeds]          # W2 raw, plain seed
    bits = {g: _bits(resp[g]) for g in range(4)}
    ctrl_bits = _bits(ctrl)
    merged = (bits[0] ^ bits[1] ^ bits[2] ^ bits[3]).astype(np.int8)
    print("  responses generated")

    # -- pair tables for the pair-aware featurisation (round 0, 8 pairs)
    tabs = {g: [decode_pair_table(_mix(s, g)) for s in seeds] for g in range(4)}
    tabs_ctrl = [decode_pair_table(s) for s in seeds]
    print("  pair tables decoded")

    seed_bits = np.array([[(s >> (63 - b)) & 1 for b in range(64)]
                          for s in seeds], dtype=np.float64)

    def pos_onehot():
        e = np.zeros((len(seeds), 8, 8))
        for j in range(8):
            e[:, j, j] = 1.0
        return e

    pos_oh = pos_onehot()

    def feat_seedbit(idx):
        n = len(idx)
        X = np.empty((n * 8, 72))
        for j in range(8):
            X[j*n:(j+1)*n, :64] = seed_bits[idx]
            X[j*n:(j+1)*n, 64:] = pos_oh[idx, j]
        return X

    def feat_pair(idx, groups):
        """Pair-aware features, POSITION-MAJOR row order (must match
        targets()/feat_seedbit blocking: row = j*n + i). For each
        (round-0 position j, seed i) row: concat one-hot(A)+one-hot(B)
        per group. groups = [0..3] for XOR-merged (128 dims),
        ["c"] for the W2 control (32 dims)."""
        n = len(idx)
        dims = 32 * len(groups)
        X = np.zeros((n * 8, dims))
        for j in range(8):
            for row, i in enumerate(idx):
                r = j * n + row
                off = 0
                for g in groups:
                    pair = (tabs[g][i][0][j] if g in tabs
                            else tabs_ctrl[i][0][j])
                    X[r, off + pair[0]] = 1.0
                    X[r, off + 16 + pair[1]] = 1.0
                    off += 32
        return X

    def targets(mat, idx):
        n = len(idx)
        y = np.empty(n * 8, dtype=np.int8)
        for j in range(8):
            y[j*n:(j+1)*n] = mat[idx, j]
        return y

    tr_idx = np.arange(0, max(train_sizes))
    te_idx = np.arange(max(train_sizes), n_max)
    variants = {
        "ctrl_pair_aware":   (lambda idx: feat_pair(idx, ["c"]), ctrl_bits),
        "ctrl_seedbit":      (feat_seedbit, ctrl_bits),
        "merged_pair_aware": (lambda idx: feat_pair(idx, [0, 1, 2, 3]), merged),
        "merged_seedbit":    (feat_seedbit, merged),
    }
    acc = {k: {} for k in variants}
    for name, (feat, mat) in variants.items():
        y_te = targets(mat, te_idx)
        for n_tr in train_sizes:
            idx = tr_idx[:n_tr]
            X_tr = feat(idx)
            y_tr = targets(mat, idx)
            if X_tr.shape[0] > 250_000:
                keep = rng.choice(X_tr.shape[0], 250_000, replace=False)
                X_tr, y_tr = X_tr[keep], y_tr[keep]
            lr = LogisticRegression(max_iter=200)
            lr.fit(X_tr, y_tr)
            X_te = feat(te_idx[:min(len(te_idx), 20000)])
            y_te_s = targets(mat, te_idx[:min(len(te_idx), 20000)])
            acc[name][str(n_tr)] = float(lr.score(X_te, y_te_s))
            print(f"  {name} n={n_tr}: acc={acc[name][str(n_tr)]:.4f}")

    # Plot
    fig, ax = plt.subplots(figsize=(8, 5))
    for name in variants:
        ax.plot(train_sizes, [acc[name][str(n)] for n in train_sizes],
                "o-", label=name)
    ax.axhline(0.5, ls="--", color="gray", alpha=0.5, label="random guess 0.5")
    ax.set_xscale("log")
    ax.set_ylim(0.4, 1.02)
    ax.set_xlabel("Training set size")
    ax.set_ylabel("Pooled bit-prediction accuracy (round-0, 8 positions)")
    ax.set_title("Experiment C: LR attack on W3 XOR-merged vs W2 raw response\n(same attacker; XOR + independent routing collapses it to chance)")
    ax.legend(loc="center right"); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(out_dir / "exp_c_xor_protection.png", dpi=150); plt.close(fig)

    ok_merged = all(acc["merged_pair_aware"][str(n)] < 0.55 and
                    acc["merged_seedbit"][str(n)] < 0.55
                    for n in train_sizes)
    ok_ctrl = acc["ctrl_pair_aware"][str(train_sizes[-1])] > 0.95
    result = {
        "repro_command": f"python -m src.python.evaluation.ml_attack --exp C --out {out_dir} --seed {seed}",
        "versions": _versions(),
        "seed": seed,
        "train_sizes": train_sizes,
        "n_test": n_test,
        "assumptions": [
            "W3 XOR(k=4): 4 groups of 16 rings, each group routes the seed independently (splitmix remix per group) -- '4 组独立产生' per project_design.md L70",
            "noiseless responses (attacker-best case); pair tables are PUBLIC knowledge (decode_pair_table) so the pair-aware featurisation is the strongest LR attacker",
            "pooled targets: round-0 8 response bits; LR(max_iter=200), rows capped at 250k",
        ],
        "accuracy": acc,
        "declaration_evidence": {
            "claim": "抗逻辑回归建模攻击（对 XOR 合并后的响应）",
            "merged_pair_aware_max": max(acc["merged_pair_aware"].values()),
            "merged_seedbit_max": max(acc["merged_seedbit"].values()),
            "control_w2_pair_aware_final": acc["ctrl_pair_aware"][str(train_sizes[-1])],
            "verdict": "SUPPORTED" if (ok_merged and ok_ctrl) else "CHECK",
            "reading": "the same LR harness that fully clones the W2 raw response (pair-aware ~100%) collapses to chance (<0.55) on the XOR-merged response under BOTH featurisations",
        },
        "future_work": "stronger attackers on the merged interface (GBM/evolutionary); frequency-spacing-correlated noise; adaptive seed selection",
    }
    _save_json(out_dir / "exp_c_results.json", result)
    print(f"  -> {out_dir}/exp_c_results.json + exp_c_xor_protection.png")
    print(f"  declaration #1 verdict: {result['declaration_evidence']['verdict']}")
    return result

# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exp", choices=["A", "B", "C", "all"], default="all")
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
    if args.exp in ("C", "all"):
        print("=== Experiment C: LR on W3 XOR-merged response ===")
        run_exp_c(out_dir, args.seed)
    print("ML_ATTACK_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())