"""VIO ratio-to-bit quantizer for W1 measurement data (B-line adapter).

The W1 stage measures a ring-oscillator frequency ratio with the 32-bit
VIO counter.  This module turns a stream of ratio readings into binary
response strings using simple threshold judgment (design doc, P1-9
"hamming_analysis adapter layer"): a reading strictly above the center
value maps to bit '1', a reading at or below maps to '0'.

From W2 onward the FPGA returns full 64-bit responses directly and this
quantizer is no longer part of the authentication path; it stays as an
evaluation tool for W1 datasets.

CSV input format (matches the measurement logger)::

    timestamp,hex_value,decimal_value

The decimal column is preferred; the hex column is the fallback.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from pathlib import Path
from typing import Sequence


def estimate_center(readings: Sequence[float]) -> float:
    """Estimate the theoretical center value as the median of readings.

    The median is robust against the (symmetric) noise tails of the VIO
    ratio counter and is the default center when the user does not supply
    one.
    """
    if not readings:
        raise ValueError("no readings supplied")
    return float(statistics.median(readings))


def ratio_to_bits(
    readings: Sequence[float],
    center_value: float,
    n_bits: int = 64,
) -> list[str]:
    """Quantize ratio readings into binary strings via threshold judgment.

    W1 rule: reading > center_value -> '1', else '0' (design doc P1-9).
    Readings are chunked into groups of n_bits; each group becomes one
    binary string, so len(readings) // n_bits strings are returned and a
    partial trailing remainder is discarded (it cannot form a full-width
    response word).

    Parameters
    ----------
    readings:
        VIO ratio counter readings (decimal values).
    center_value:
        Threshold separating bit '1' from bit '0'.
    n_bits:
        Number of bits per output word (default 64, W2 response width).

    Returns
    -------
    list[str]
        Binary strings, each exactly n_bits characters long.
    """
    if n_bits < 1:
        raise ValueError("n_bits must be >= 1")
    words: list[str] = []
    for start in range(0, len(readings) - n_bits + 1, n_bits):
        chunk = readings[start : start + n_bits]
        words.append("".join("1" if r > center_value else "0" for r in chunk))
    return words


def majority_vote(bit_strings: Sequence[str]) -> str:
    """Per-position majority vote across equal-length binary strings.

    Ties resolve to '0'.  Used to fold repeated measurements of the same
    challenge into one robust response word before further analysis.
    """
    if not bit_strings:
        raise ValueError("no bit strings supplied")
    length = len(bit_strings[0])
    if any(len(s) != length for s in bit_strings):
        raise ValueError("all bit strings must have equal length")
    half = len(bit_strings) / 2.0
    return "".join(
        "1" if sum(s[i] == "1" for s in bit_strings) > half else "0"
        for i in range(length)
    )


def bits_to_hex(bits: str) -> str:
    """Convert a binary string to a hex string (zero-padded to nibbles)."""
    if not bits or any(c not in "01" for c in bits):
        raise ValueError("bits must be a non-empty string of 0/1")
    padded = bits.zfill((len(bits) + 3) // 4 * 4)
    return f"{int(padded, 2):x}"


def hamming_weight(bits: str) -> int:
    """Number of '1' characters in a binary string."""
    return bits.count("1")


def read_readings_csv(path: str | Path) -> list[float]:
    """Read VIO ratio readings from a measurement CSV.

    Column preference: decimal_value (index 2), then hex_value (index 1),
    then the first column.  Header rows and comment lines are skipped.
    """
    readings: list[float] = []
    with open(path, "r", encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle):
            if not row or not any(field.strip() for field in row):
                continue
            fields = [f.strip() for f in row]
            if fields[0].startswith("#"):
                continue
            value: float | None = None
            for index in (2, 1, 0):
                if index >= len(fields):
                    continue
                text = fields[index].lower().removeprefix("0x")
                try:
                    value = float(int(text, 16)) if index == 1 else float(text)
                except ValueError:
                    continue
                break
            if value is None:
                continue  # header or malformed row
            readings.append(value)
    if not readings:
        raise ValueError(f"no readings found in {path}")
    return readings


def parse_center(spec: str, readings: Sequence[float]) -> float:
    """Resolve the --center CLI value ('auto' or a number)."""
    if spec.strip().lower() == "auto":
        return estimate_center(readings)
    return float(spec)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for the quantizer."""
    parser = argparse.ArgumentParser(
        description="Quantize VIO ratio readings (CSV) into bit streams"
    )
    parser.add_argument("-i", "--input", required=True, help="input CSV file")
    parser.add_argument(
        "--center", default="auto",
        help="threshold center value, or 'auto' for the median (default)",
    )
    parser.add_argument(
        "--bits", type=int, default=64, help="bits per response word (default 64)"
    )
    args = parser.parse_args(argv)

    try:
        readings = read_readings_csv(args.input)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] {exc}")
        return 1
    center = parse_center(args.center, readings)
    words = ratio_to_bits(readings, center, args.bits)
    discarded = len(readings) - len(words) * args.bits

    print(f"[INFO] {len(readings)} readings from {args.input}")
    print(f"[INFO] center value = {center}")
    if not words:
        print(f"[ERROR] need at least {args.bits} readings for one word")
        return 1
    print(f"[INFO] produced {len(words)} x {args.bits}-bit word(s)"
          + (f" ({discarded} trailing readings discarded)" if discarded else ""))
    weights = []
    for i, word in enumerate(words):
        weight = hamming_weight(word)
        weights.append(weight)
        print(f"word {i + 1}: {bits_to_hex(word)}  weight {weight}/{args.bits} "
              f"({100.0 * weight / args.bits:.1f}%)")
    mean = sum(weights) / len(weights)
    print(f"[STATS] mean Hamming weight {mean / args.bits * 100:.1f}% "
          f"(random expectation ~50%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
