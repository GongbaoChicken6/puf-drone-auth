"""Hamming distance and weight analysis for PUF measurements (CSV input).

Adapted from external/puf-esp32-auth/tools/analysis/hamming_analysis.py
for this project's data formats:

* input is a measurement CSV with columns (timestamp, hex_value,
  decimal_value) instead of raw hex lines;
* the default response width is 64 bit (RO-pairing response) instead of
  65536 bit (8 KB SRAM);
* a new template comparison mode compares every measurement against an
  enrolled template database (JSON produced by the server);
* plots are always saved to a file, never shown interactively.

Kept from the original tool: the full Hamming distance matrix, the
Hamming weight table/plot, the compare-to-measurement-N mode and the
rolling (consecutive) comparison mode.

Usage examples::

    python hamming_analysis.py -i data.csv -n TERM_01 -c 1
    python hamming_analysis.py -i data.csv -n TERM_01 -r --save roll.png
    python hamming_analysis.py -i data.csv --weight-plot
    python hamming_analysis.py -i data.csv --template templates.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

#: Default number of bits per measurement (64-bit RO-pairing response).
DEFAULT_BITS = 64

_HEX_DIGITS = set("0123456789abcdef")


# ----------------------------------------------------------------------
# Basic helpers
# ----------------------------------------------------------------------
def hex_to_binary(hex_str: str) -> str:
    """Convert a hexadecimal string to a binary string (4 bits per digit)."""
    text = hex_str.strip().lower().removeprefix("0x")
    if not text or any(c not in _HEX_DIGITS for c in text):
        raise ValueError(f"invalid hex string: {hex_str!r}")
    return bin(int(text, 16))[2:].zfill(4 * len(text))


def hamming_distance(s1: str, s2: str) -> int:
    """Hamming distance between two equal-length binary strings."""
    if len(s1) != len(s2):
        raise ValueError(
            f"binary strings must have equal length ({len(s1)} vs {len(s2)})"
        )
    return sum(a != b for a, b in zip(s1, s2))


def hamming_weight(s: str) -> int:
    """Hamming weight of a binary string (number of '1's)."""
    return s.count("1")


def mean(values: Sequence[float]) -> float:
    """Arithmetic mean (pure Python; numpy is not a hard dependency)."""
    return sum(values) / len(values) if values else 0.0


def std(values: Sequence[float]) -> float:
    """Population standard deviation (pure Python)."""
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return (sum((v - m) ** 2 for v in values) / len(values)) ** 0.5


def linear_fit(values: Sequence[float]) -> tuple[float, float]:
    """Least-squares slope/intercept of y=len(values) points (pure Python)."""
    n = len(values)
    if n < 2:
        return 0.0, values[0] if values else 0.0
    xs = list(range(n))
    mx = mean(xs)
    my = mean(values)
    denom = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, values)) / (
        denom if denom else 1.0
    )
    return slope, my - slope * mx


# ----------------------------------------------------------------------
# CSV input (timestamp, hex_value, decimal_value)
# ----------------------------------------------------------------------
def extract_hex_field(fields: Sequence[str]) -> str | None:
    """Pick the hex_value column from a split CSV row.

    Expected layout: timestamp, hex_value, decimal_value -> index 1.  With
    only one or two columns the last field is used.  Returns None when no
    field looks like a hexadecimal value (header rows, malformed rows).
    """
    candidates = (
        [fields[1]] if len(fields) >= 3 else list(fields[-1:])
    )
    for candidate in candidates:
        text = candidate.strip().lower().removeprefix("0x")
        if text and all(c in _HEX_DIGITS for c in text):
            return text
    return None


def read_csv_measurements(path: str | Path) -> list[str]:
    """Read binary measurement strings from a measurement CSV.

    Each data row contributes one measurement (its hex_value column).
    Header rows, blank lines and comment lines are skipped silently.
    """
    binaries: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        hex_value = extract_hex_field(line.split(","))
        if hex_value is None:
            continue
        binaries.append(hex_to_binary(hex_value))
    return binaries


# ----------------------------------------------------------------------
# Output helpers
# ----------------------------------------------------------------------
def print_distance_matrix(distances: list[list[str | None]]) -> None:
    """Print the Hamming distance matrix as a markdown table."""
    n = len(distances)
    header = "| # | " + " | ".join(str(i + 1) for i in range(n)) + " |"
    print(header)
    print("|---" * (n + 1) + "|")
    for i in range(n):
        row = f"| {i + 1} | " + " | ".join(
            distances[i][j] if distances[i][j] is not None else "-"
            for j in range(n)
        ) + " |"
        print(row)


def print_weight_table(name: str, binaries: Sequence[str], total_bits: int) -> None:
    """Print per-measurement Hamming weights as a markdown table."""
    print("\n| Device | Ones | Zeros | Weight (%) |")
    print("|--------|------|-------|------------|")
    for i, bits in enumerate(binaries):
        weight = hamming_weight(bits)
        weight_pct = round(weight / total_bits * 100, 2)
        print(f"| {name}_{i + 1} | {weight} | {total_bits - weight} | {weight_pct} |")


def save_plot(
    values: Sequence[float],
    plot_type: str,
    device_name: str,
    save_path: str | Path,
    ylabel: str = "Hamming Distance (%)",
    title: str | None = None,
) -> None:
    """Save a metric-over-measurements plot to a PNG file (never shown).

    matplotlib is imported lazily so the non-plot modes work without it.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")  # headless: always save, never show
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise SystemExit(
            "[ERROR] matplotlib is required for plots: pip install matplotlib"
        ) from exc

    titles = {
        "compare": "Hamming Distance to Reference Measurement",
        "rolling": "Hamming Distance Between Consecutive Measurements",
        "weight": "Hamming Weight Over Time",
        "template": "Hamming Distance to Enrolled Template",
    }
    plt.figure(figsize=(14, 6))
    x = list(range(len(values)))
    plt.plot(x, values, color="#000000", marker="o", markersize=3)
    if plot_type == "weight":
        slope, intercept = linear_fit(values)
        plt.plot(x, [slope * xi + intercept for xi in x], label=f"Linear fit (slope={slope:.4f})",
                 color="red", linestyle="--", linewidth=2)
        plt.legend(loc="best")
    plt.xlabel("Measurement Index")
    plt.ylabel(ylabel)
    plt.title(title or f"{titles.get(plot_type, plot_type)} | Device: {device_name}")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"[INFO] Plot saved to: {save_path}")


# ----------------------------------------------------------------------
# Analysis modes
# ----------------------------------------------------------------------
def analyze_compare(binaries: Sequence[str], ref_index: int, bits: int,
                    name: str, save: str | None) -> None:
    """Compare all measurements to measurement number ref_index (1-based)."""
    distances = [
        round(hamming_distance(binaries[ref_index], b) / bits * 100, 2)
        for i, b in enumerate(binaries)
        if i != ref_index
    ]
    print(f"[STATS] Average distance: {mean(distances):.2f}% "
          f"(+/- {std(distances):.2f}%)")
    if save:
        save_plot(distances, "compare", name, save)


def analyze_rolling(binaries: Sequence[str], bits: int, name: str,
                    save: str | None) -> None:
    """Compare each measurement to its predecessor."""
    distances = [
        round(hamming_distance(binaries[i], binaries[i - 1]) / bits * 100, 2)
        for i in range(1, len(binaries))
    ]
    print(f"[STATS] Average distance: {mean(distances):.2f}% "
          f"(+/- {std(distances):.2f}%)")
    if save:
        save_plot(distances, "rolling", name, save)


def analyze_weight(binaries: Sequence[str], bits: int, name: str,
                   save: str | None) -> None:
    """Analyze the Hamming weight distribution across measurements."""
    weights = [round(hamming_weight(b) / bits * 100, 2) for b in binaries]
    print(f"[STATS] Average weight: {mean(weights):.2f}% "
          f"(+/- {std(weights):.2f}%)")
    print("[STATS] Expected: ~50% for an unbiased response")
    if save:
        save_plot(weights, "weight", name, save, ylabel="Hamming Weight (%)")


def analyze_matrix(binaries: Sequence[str], bits: int) -> None:
    """Compute and print the full pairwise Hamming distance matrix."""
    n = len(binaries)
    distances: list[list[str | None]] = [
        [None if i != j else "-" for j in range(n)] for i in range(n)
    ]
    for i in range(n):
        for j in range(i + 1, n):
            dist = round(hamming_distance(binaries[i], binaries[j]) / bits * 100, 2)
            distances[i][j] = str(dist)
            distances[j][i] = str(dist)
    print("\nHamming Distance Matrix (%):")
    print_distance_matrix(distances)


def analyze_template(
    binaries: Sequence[str],
    template_path: str,
    terminal_id: str | None,
    bits: int,
    name: str,
    save: str | None,
) -> int:
    """Compare every measurement against an enrolled template database.

    The template file uses the server layout {terminal_id: {seed_hex:
    response_hex}}.  With --terminal-id the responses of that terminal
    are used, otherwise the file must contain exactly one terminal.  Each
    measurement is matched against every stored response of the terminal
    and the minimum distance is reported (best-matching CRP).

    Returns 0 on success, 1 on usage errors.
    """
    data = json.loads(Path(template_path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and data.get("schema", "").startswith("puf-drone-auth"):
        data = data.get("devices", data)
    if terminal_id is None:
        if len(data) != 1:
            print(f"[ERROR] template file has {len(data)} terminals; "
                  f"pass --terminal-id one of: {sorted(data)}")
            return 1
        terminal_id = next(iter(data))
    if terminal_id not in data:
        print(f"[ERROR] terminal {terminal_id!r} not found in template file")
        return 1
    templates = [hex_to_binary(r) for r in data[terminal_id].values()]
    if not templates:
        print(f"[ERROR] terminal {terminal_id!r} has no stored responses")
        return 1

    print(f"[INFO] Comparing {len(binaries)} measurements against "
          f"{len(templates)} template response(s) of terminal {terminal_id}")
    print("\n| Measurement | Min HD | Min HD (%) | Best match |")
    print("|-------------|--------|------------|------------|")
    distances: list[float] = []
    for i, bits_str in enumerate(binaries):
        per_cr = [hamming_distance(bits_str, t) for t in templates]
        best = min(range(len(per_cr)), key=lambda k: per_cr[k])
        distances.append(round(per_cr[best] / bits * 100, 2))
        print(f"| {i + 1} | {per_cr[best]} | {distances[-1]} | CRP #{best + 1} |")

    print(f"\n[STATS] Average min distance: {mean(distances):.2f}% "
          f"(+/- {std(distances):.2f}%)")
    print("[STATS] Genuine device expected: <= "
          f"{round(6 / bits * 100, 1)}% (TAU_PASS=6); "
          f"impostor expected ~50%")
    if save:
        save_plot(distances, "template", name, save)
    return 0


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Analyze PUF measurements (CSV) using Hamming distance/weight",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python hamming_analysis.py -i data.csv -n TERM_01 -c 1
  python hamming_analysis.py -i data.csv -n TERM_01 -r --save roll.png
  python hamming_analysis.py -i data.csv --weight-plot
  python hamming_analysis.py -i data.csv --template templates.json --terminal-id 1
  python hamming_analysis.py -i data.csv        (full distance matrix)
        """,
    )
    parser.add_argument("-i", "--input", required=True,
                        help="input CSV (timestamp,hex_value,decimal_value)")
    parser.add_argument("-n", "--name", default="Unknown",
                        help="name/id of the measured device")
    parser.add_argument("-c", "--compare", type=int, default=None,
                        help="compare all measurements to measurement N (1-based)")
    parser.add_argument("-r", "--rolling", action="store_true",
                        help="compare each measurement to the previous one")
    parser.add_argument("--weight-plot", action="store_true",
                        help="plot Hamming weight across measurements")
    parser.add_argument("-w", "--weight-table", action="store_true",
                        help="print Hamming weight table")
    parser.add_argument("--template", type=str, default=None,
                        help="template JSON for HD-vs-template comparison mode")
    parser.add_argument("--terminal-id", type=str, default=None,
                        help="terminal id inside the template file")
    parser.add_argument("--bits", type=int, default=DEFAULT_BITS,
                        help=f"bits per measurement (default {DEFAULT_BITS})")
    parser.add_argument("--save", type=str, default=None,
                        help="save plot to this file (plots are never shown)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; returns a process exit code."""
    args = parse_arguments(argv)
    print(f"[INFO] Reading measurements from: {args.input}")
    try:
        binaries = read_csv_measurements(args.input)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] {exc}")
        return 1
    print(f"[INFO] Loaded {len(binaries)} measurements")
    if not binaries:
        print("[ERROR] No measurements found in file")
        return 1

    total_bits = len(binaries[0])
    if total_bits != args.bits:
        print(f"[WARNING] Expected {args.bits} bits, found {total_bits} bits")
        print(f"[INFO] Using {total_bits} bits for calculations")
    else:
        total_bits = args.bits

    # Plot modes always produce a file (never an interactive window):
    # derive a default save path from the input name when --save is absent.
    if args.save is None:
        if args.template:
            mode = "template"
        elif args.weight_plot:
            mode = "weight"
        elif args.rolling:
            mode = "rolling"
        elif args.compare is not None:
            mode = "compare"
        else:
            mode = None
        if mode is not None:
            inp = Path(args.input)
            args.save = str(inp.with_name(f"{inp.stem}_{mode}.png"))

    if args.template:
        return analyze_template(binaries, args.template, args.terminal_id,
                                total_bits, args.name, args.save)
    if args.compare is not None:
        ref = args.compare - 1
        if ref < 0 or ref >= len(binaries):
            print(f"[ERROR] Compare index {args.compare} out of bounds "
                  f"(1-{len(binaries)})")
            return 1
        print(f"[INFO] Comparing all measurements to measurement #{args.compare}")
        analyze_compare(binaries, ref, total_bits, args.name, args.save)
    elif args.rolling:
        print("[INFO] Computing rolling Hamming distances...")
        analyze_rolling(binaries, total_bits, args.name, args.save)
    elif args.weight_plot:
        print("[INFO] Computing Hamming weights...")
        analyze_weight(binaries, total_bits, args.name, args.save)
    elif args.weight_table:
        print_weight_table(args.name, binaries, total_bits)
    else:
        print("[INFO] Computing full Hamming distance matrix...")
        analyze_matrix(binaries, total_bits)
    return 0


if __name__ == "__main__":
    sys.exit(main())
