"""Inter-device Hamming distance analysis (uniqueness check).

Adapted from external/puf-esp32-auth/tools/analysis/compare_devices.py
for this project's CSV measurement format.  Unlike the original (which
compared only the first measurement of each device), this version reads
*all* measurements of every device file:

* off-diagonal cells average the Hamming distance over every cross pair
  of measurements (device A measurement i vs device B measurement j);
* diagonal cells report the intra-device distance (reliability) whenever
  a device file contains more than one measurement;
* cells are reported as "mean% +/- std%".

Inter-device distance close to 50% indicates good uniqueness.

Input: a directory with one CSV per device (columns: timestamp,
hex_value, decimal_value).

Usage::

    python compare_devices.py -d data/w1_readings/
    python compare_devices.py -d data/w1_readings/ --first-only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from src.python.evaluation.hamming_analysis import (
        hamming_distance,
        mean,
        read_csv_measurements,
        std,
    )
else:
    from .hamming_analysis import (
        hamming_distance,
        mean,
        read_csv_measurements,
        std,
    )


def read_device(path: Path) -> list[str]:
    """Read all measurements (binary strings) from one device CSV."""
    return read_csv_measurements(path)


def pairwise_stats(set_a: Sequence[str], set_b: Sequence[str], bits: int) -> tuple[float, float, int] | None:
    """Mean/std of HD% across every cross pair of two measurement sets.

    Returns None when either set is empty.
    """
    if not set_a or not set_b:
        return None
    distances = [
        hamming_distance(a, b) / bits * 100.0 for a in set_a for b in set_b
    ]
    return mean(distances), std(distances), len(distances)


def intra_stats(measurements: Sequence[str], bits: int) -> tuple[float, float] | None:
    """Mean/std of HD% between all measurement pairs of one device."""
    n = len(measurements)
    if n < 2:
        return None
    distances = [
        hamming_distance(measurements[i], measurements[j]) / bits * 100.0
        for i in range(n)
        for j in range(i + 1, n)
    ]
    return mean(distances), std(distances)


def print_distance_table(
    names: Sequence[str],
    cells: list[list[str | None]],
) -> None:
    """Print the inter-device distance matrix as a markdown table."""
    header = "| Device | " + " | ".join(names) + " |"
    print(header)
    print("|---" * (len(names) + 1) + "|")
    for i, name in enumerate(names):
        row = f"| {name} | " + " | ".join(
            cells[i][j] if cells[i][j] is not None else "-" for j in range(len(names))
        ) + " |"
        print(row)


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Compare PUF measurements from different devices (CSV)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  python compare_devices.py -d ./measurements/

Directory structure:
  measurements/
    +-- term_01.csv
    +-- term_02.csv
    +-- term_03.csv
        """,
    )
    parser.add_argument("-d", "--directory", required=True,
                        help="directory containing one measurement CSV per device")
    parser.add_argument("--first-only", action="store_true",
                        help="use only the first measurement per device "
                             "(esp32-puf compatibility mode)")
    parser.add_argument("--bits", type=int, default=64,
                        help="bits per measurement (default 64)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; returns a process exit code."""
    args = parse_arguments(argv)
    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"[ERROR] Directory not found: {directory}")
        return 1

    files = sorted(
        f for f in directory.iterdir()
        if f.is_file() and not f.name.startswith(".") and f.suffix.lower() == ".csv"
    )
    if len(files) < 2:
        print(f"[ERROR] Need at least 2 device CSV files, found {len(files)}")
        return 1
    print(f"[INFO] Found {len(files)} device files")

    names: list[str] = []
    sets: list[list[str]] = []
    bit_length = args.bits
    for path in files:
        try:
            measurements = read_device(path)
        except (OSError, ValueError) as exc:
            print(f"[WARNING] Skipping unreadable file {path.name}: {exc}")
            continue
        if not measurements:
            print(f"[WARNING] Skipping empty file: {path.name}")
            continue
        if args.first_only:
            measurements = measurements[:1]
        names.append(path.name)
        sets.append(measurements)
        bit_length = len(measurements[0])
        print(f"[INFO] {path.name}: {len(measurements)} measurement(s)")

    if len(names) < 2:
        print("[ERROR] Not enough valid device files")
        return 1
    if bit_length != args.bits:
        print(f"[WARNING] Expected {args.bits} bits, using {bit_length} bits")

    n = len(names)
    cells: list[list[str | None]] = [[None] * n for _ in range(n)]
    inter_values: list[float] = []
    for i in range(n):
        for j in range(n):
            if i == j:
                intra = intra_stats(sets[i], bit_length)
                cells[i][j] = (
                    f"{intra[0]:.2f} +/- {intra[1]:.2f}" if intra else "-"
                )
                continue
            stats = pairwise_stats(sets[i], sets[j], bit_length)
            if stats is None:
                cells[i][j] = "-"
                continue
            avg, dev, _pairs = stats
            cells[i][j] = f"{avg:.2f} +/- {dev:.2f}"
            if i < j:
                inter_values.append(avg)

    print("\nInter-Device Hamming Distance Matrix (%):")
    print("(off-diagonal: uniqueness, ~50% expected; diagonal: intra-device"
          " reliability)\n")
    print_distance_table(names, cells)

    if inter_values:
        avg = mean(inter_values)
        print(f"\n[STATS] Average inter-device distance: {avg:.2f}% "
              f"(min {min(inter_values):.2f}%, max {max(inter_values):.2f}%)")
        print("[STATS] Expected for good PUF: ~50%")
        if avg < 40:
            print("[WARNING] Low inter-device distance - devices may not be unique enough!")
        elif avg > 60:
            print("[WARNING] High inter-device distance - check for systematic bias")
        else:
            print("[OK] Inter-device distance looks good!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
