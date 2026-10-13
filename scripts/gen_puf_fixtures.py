#!/usr/bin/env python3
"""gen_puf_fixtures.py -- PUF golden fixture generator (W4-P1).

--golden  prints the three frozen cross-check seeds' pair tables as
          Verilog localparams and contract-style hex blocks (used to
          freeze tb_challenge_decode additions and contract S8).

W4-P2 will extend this script with --tb-mem to emit the .mem response
fixtures the RTL testbenches consume.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import random

from src.python.evaluation.puf_model import (  # noqa: E402
    DEFAULT_FREQ_MAX,
    DEFAULT_FREQ_MIN,
    GOLDEN_SEED_A,
    GOLDEN_SEED_B,
    GOLDEN_SEED_C,
    N_RINGS,
    ROPairingPUF,
    pair_table_hex,
)

#: tb_puf_path 专用第 4 种子（首轮 4 种子 = A/B/C/D）
GOLDEN_SEED_D = 0x1234_5678_9ABC_DEF0


def golden() -> int:
    seeds = [("A", GOLDEN_SEED_A), ("B", GOLDEN_SEED_B), ("C", GOLDEN_SEED_C)]
    for tag, seed in seeds:
        hx = pair_table_hex(seed)
        raw = bytes.fromhex(hx)
        print(f"# SEED_{tag} = 64'h{seed:016X}")
        print(f"localparam [511:0] GOLDEN_TBL_{tag} = 512'h{hx.upper()};")
        print(f"# PUF_SEED_{tag}")
        for i in range(0, 64, 16):
            print("  " + " ".join(f"{b:02X}" for b in raw[i:i + 16]))
        print()
    return 0


def tb_mem() -> int:
    """Write the deterministic TB frequency fixture consumed by ro_array_sim.

    Fixed master seed => the same 16 frequencies everywhere (RTL TBs, PC
    tests, interop harness): reproducibility beats realism in simulation.
    """
    rng = random.Random(0x0044_3450)  # "W4PUF" master seed (deterministic)
    freqs = sorted(rng.sample(range(DEFAULT_FREQ_MIN, DEFAULT_FREQ_MAX + 1), N_RINGS))
    out = ROOT / "sim" / "testvectors" / "puf_tb_freqs.mem"
    out.write_text("\n".join(f"{f:04X}" for f in freqs) + "\n", encoding="ascii")
    print(f"wrote {out} (16 freqs, deterministic master seed)")
    print("freqs:", " ".join(str(f) for f in freqs))
    return 0


def tb_resp() -> int:
    """Print the R1 golden bytes tb_puf_path checks (puf_model at the
    fixture frequencies).  Single source: the same .mem ro_array_sim loads."""
    mem = ROOT / "sim" / "testvectors" / "puf_tb_freqs.mem"
    freqs = [int(line.strip(), 16) for line in mem.read_text().split() if line.strip()]
    puf = ROPairingPUF(freqs=freqs)
    for tag, seed in (("A", GOLDEN_SEED_A), ("B", GOLDEN_SEED_B),
                      ("C", GOLDEN_SEED_C), ("D", GOLDEN_SEED_D)):
        print(f"localparam [63:0] R1_SEED_{tag} = 64'h{int.from_bytes(puf.ideal(seed), 'big'):016X};")
    return 0


def check() -> int:
    """Freshness gate (review D-P2): the on-disk .mem must match what
    --tb-mem would regenerate, and the R1 constants in tb_puf_path.v
    must match what --tb-resp would produce.  Exit 1 on drift."""
    import tempfile
    bad = 0
    # .mem freshness
    rng = random.Random(0x0044_3450)
    freqs = sorted(rng.sample(range(DEFAULT_FREQ_MIN, DEFAULT_FREQ_MAX + 1), N_RINGS))
    expected = "\n".join(f"{f:04X}" for f in freqs) + "\n"
    mem = ROOT / "sim" / "testvectors" / "puf_tb_freqs.mem"
    actual = mem.read_text(encoding="ascii") if mem.exists() else ""
    if actual != expected:
        print(f"[DRIFT] {mem.name}: on-disk != regenerated")
        print(f"  expected first line: {expected.splitlines()[0]}")
        print(f"  actual   first line: {actual.splitlines()[0] if actual else '(missing)'}")
        bad += 1
    else:
        print(f"[OK]   {mem.name} fresh ({len(freqs)} freqs)")
    # R1 constants in tb_puf_path.v
    tb = (ROOT / "sim" / "tb" / "tb_puf_path.v").read_text(encoding="utf-8")
    puf = ROPairingPUF(freqs=freqs)
    for tag, seed in (("A", GOLDEN_SEED_A), ("B", GOLDEN_SEED_B),
                      ("C", GOLDEN_SEED_C), ("D", GOLDEN_SEED_D)):
        want = f"R1_SEED_{tag} = 64'h{int.from_bytes(puf.ideal(seed), 'big'):016X}"
        if want not in tb:
            print(f"[DRIFT] tb_puf_path.v missing/mismatched: {want}")
            bad += 1
        else:
            print(f"[OK]   R1_SEED_{tag} matches puf_model")
    return 1 if bad else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", action="store_true",
                        help="print frozen pair-table fixtures")
    parser.add_argument("--tb-mem", action="store_true",
                        help="write sim/testvectors/puf_tb_freqs.mem (ro_array_sim)")
    parser.add_argument("--tb-resp", action="store_true",
                        help="print tb_puf_path golden R1 bytes (from puf_model at fixture freqs)")
    parser.add_argument("--check", action="store_true",
                        help="freshness gate: .mem + tb_puf_path R1 constants vs puf_model")
    args = parser.parse_args()
    if args.golden:
        return golden()
    if args.tb_mem:
        return tb_mem()
    if args.tb_resp:
        return tb_resp()
    if args.check:
        return check()
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
