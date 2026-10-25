#!/usr/bin/env python3
"""golden_compare.py - compare measured output against a golden reference.

Works fully OFF the board: golden comparison is a host-side concern.
Supports numeric CSV (with or without header), whitespace-separated
number vectors, and raw binary via --dtype/--shape (needs numpy only for
the binary mode; CSV mode is stdlib-only).

Verdict rules (hard gates, do not weaken to make it green):
  PASS  : every comparable cell within tolerance
  FAIL  : any cell outside tolerance, or row/column count mismatch
  Count mismatches are FAIL, not warning - silent truncation is exactly
  what this script exists to catch.

Usage:
    python golden_compare.py --got out.csv --golden ref.csv \
        [--rtol 1e-5] [--atol 1e-6] [--md-out cmp.md] [--json-out cmp.json]
    python golden_compare.py --got out.bin --golden ref.bin --binary \
        --dtype float32 --shape 1024

Exit codes: 0 PASS, 1 FAIL, 2 usage/data error.

License: MIT. Part of the generic PYNQ skill package.
"""
import argparse
import csv
import json
import sys
from datetime import datetime, timezone


def load_csv_numbers(path):
    """Load a CSV of numbers. Returns (headers|None, rows of floats|str)."""
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample)
            has_header = csv.Sniffer().has_header(sample)
        except csv.Error:
            dialect, has_header = csv.excel, False
        rows = list(csv.reader(f, dialect))
    if not rows:
        raise ValueError(f"{path}: empty file")
    headers = None
    if has_header:
        headers = rows[0]
        rows = rows[1:]
    parsed = []
    for r in rows:
        if not r or all(c.strip() == "" for c in r):
            continue
        out = []
        for c in r:
            c = c.strip()
            if c in ("", "nan", "NaN"):
                out.append(float("nan"))
            else:
                out.append(float(c))  # raises on non-numeric -> caller reports
        parsed.append(out)
    return headers, parsed


def load_vector(path):
    """Whitespace/ newline separated single-column-ish number vectors."""
    with open(path, encoding="utf-8", errors="replace") as f:
        toks = f.read().split()
    return [float(t) for t in toks]


def load_binary(path, dtype, shape, numpy_path="numpy"):
    import importlib
    np = importlib.import_module(numpy_path)
    a = np.fromfile(path, dtype=np.dtype(dtype))
    if shape:
        a = a.reshape(shape)
    return a


def within(got, ref, rtol, atol):
    import math
    if math.isnan(ref) and math.isnan(got):
        return True
    return abs(got - ref) <= atol + rtol * abs(ref)


def compare_tables(got, ref, rtol, atol):
    """got/ref: list of rows (lists of floats). Returns report dict."""
    mismatch_shape = None
    n_rows_g, n_rows_r = len(got), len(ref)
    if n_rows_g != n_rows_r:
        mismatch_shape = f"rows: got {n_rows_g}, golden {n_rows_r}"
    cols_g = {len(r) for r in got}
    cols_r = {len(r) for r in ref}
    if not mismatch_shape and cols_g != cols_r:
        mismatch_shape = (f"columns: got {sorted(cols_g)}, "
                          f"golden {sorted(cols_r)}")

    n_cmp = n_bad = 0
    worst = None
    bad_cells = []
    for i in range(min(n_rows_g, n_rows_r)):
        for j in range(min(len(got[i]), len(ref[i]))):
            g, r = got[i][j], ref[i][j]
            ok = within(g, r, rtol, atol)
            n_cmp += 1
            err = abs(g - r)
            if not ok:
                n_bad += 1
                if len(bad_cells) < 50:
                    bad_cells.append({"row": i, "col": j,
                                      "got": g, "golden": r})
            if worst is None or err > worst["abs_err"]:
                worst = {"row": i, "col": j, "got": g, "golden": r,
                         "abs_err": err}
    verdict = "PASS" if (n_bad == 0 and not mismatch_shape) else "FAIL"
    return {
        "verdict": verdict,
        "cells_compared": n_cmp,
        "cells_failed": n_bad,
        "shape_mismatch": mismatch_shape,
        "worst_abs_error": None if worst is None else worst["abs_err"],
        "worst_cell": worst,
        "first_bad_cells": bad_cells,
        "tolerance": {"rtol": rtol, "atol": atol},
    }


def md_report(rep, got_path, golden_path):
    w = rep["worst_cell"] or {}
    lines = [
        "# golden_compare report", "",
        f"- utc: {rep['utc']}",
        f"- got: `{got_path}`",
        f"- golden: `{golden_path}`",
        f"- tolerance: rtol={rep['tolerance']['rtol']} "
        f"atol={rep['tolerance']['atol']}",
        f"- cells compared: {rep['cells_compared']}",
        f"- cells failed: {rep['cells_failed']}",
        f"- shape mismatch: {rep['shape_mismatch'] or 'none'}",
        f"- worst |err|: {rep['worst_abs_error']} at "
        f"row={w.get('row')} col={w.get('col')} "
        f"(got={w.get('got')} golden={w.get('golden')})",
        "",
        f"## Verdict: **{rep['verdict']}**", "",
    ]
    if rep["first_bad_cells"]:
        lines += ["| row | col | got | golden |", "|---|---|---|---|"]
        for c in rep["first_bad_cells"][:20]:
            lines.append(f"| {c['row']} | {c['col']} | {c['got']} | "
                         f"{c['golden']} |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(
        description="Compare measured output to a golden reference")
    ap.add_argument("--got", required=True)
    ap.add_argument("--golden", required=True)
    ap.add_argument("--binary", action="store_true",
                    help="raw binary compare (needs numpy)")
    ap.add_argument("--dtype", default="float32",
                    help="numpy dtype for --binary")
    ap.add_argument("--shape", default=None,
                    help="e.g. 1024 or 4,256 for --binary")
    ap.add_argument("--rtol", type=float, default=1e-5)
    ap.add_argument("--atol", type=float, default=1e-6)
    ap.add_argument("--md-out")
    ap.add_argument("--json-out")
    args = ap.parse_args()

    try:
        if args.binary:
            shape = None
            if args.shape:
                shape = tuple(int(x) for x in args.shape.split(","))
            got = load_binary(args.got, args.dtype, shape)
            ref = load_binary(args.golden, args.dtype, shape)
            if got.shape != ref.shape:
                rep = {"verdict": "FAIL", "cells_compared": 0,
                       "cells_failed": -1,
                       "shape_mismatch":
                           f"got {got.shape} vs golden {ref.shape}",
                       "worst_abs_error": None, "worst_cell": None,
                       "first_bad_cells": []}
                rep["tolerance"] = {"rtol": args.rtol, "atol": args.atol}
            else:
                import numpy as np
                diff = np.abs(got.astype(np.float64) -
                              ref.astype(np.float64))
                bad = ~(np.isnan(got) & np.isnan(ref)) & \
                    (diff > args.atol + args.rtol * np.abs(ref))
                idx = np.argwhere(bad)
                rep = {"verdict": "FAIL" if idx.size else "PASS",
                       "cells_compared": int(got.size),
                       "cells_failed": int(idx.size),
                       "shape_mismatch": None,
                       "worst_abs_error": float(diff.max()),
                       "worst_cell": ({"row": int(idx[0][0]),
                                       "col": int(idx[0][1])}
                                      if idx.size else None),
                       "first_bad_cells": [
                           {"row": int(i), "col": int(j), "got": float(got[i, j]),
                            "golden": float(ref[i, j])}
                           for i, j in idx[:20]],
                       "tolerance": {"rtol": args.rtol,
                                     "atol": args.atol}}
                if got.ndim == 1:  # keep report honest for 1-D data
                    for c in rep["first_bad_cells"]:
                        c["index"] = c.pop("row")
                        c.pop("col", None)
        else:
            try:
                _, got_rows = load_csv_numbers(args.got)
                _, ref_rows = load_csv_numbers(args.golden)
            except ValueError:
                got_rows = [load_vector(args.got)]
                ref_rows = [load_vector(args.golden)]
            rep = compare_tables(got_rows, ref_rows, args.rtol, args.atol)
    except (ValueError, OSError) as e:
        print(f"[ERROR] {e}")
        sys.exit(2)

    rep["utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"cells compared : {rep['cells_compared']}")
    print(f"cells failed   : {rep['cells_failed']}")
    print(f"shape mismatch : {rep['shape_mismatch'] or 'none'}")
    print(f"worst |err|    : {rep['worst_abs_error']}")
    print(f"[VERDICT] {rep['verdict']}")
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(rep, f, indent=2)
    if args.md_out:
        with open(args.md_out, "w", encoding="utf-8") as f:
            f.write(md_report(rep, args.got, args.golden))
    sys.exit(0 if rep["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
