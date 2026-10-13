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

from src.python.evaluation.puf_model import (  # noqa: E402
    GOLDEN_SEED_A,
    GOLDEN_SEED_B,
    GOLDEN_SEED_C,
    pair_table_hex,
)


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", action="store_true",
                        help="print frozen pair-table fixtures")
    args = parser.parse_args()
    if args.golden:
        return golden()
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
