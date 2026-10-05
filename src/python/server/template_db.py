"""Template storage and Hamming-distance matching for PUF authentication.

Templates are persisted as JSON with the exact layout::

    {"<terminal_id>": {"<seed_hex>": "<response_hex>", ...}, ...}

i.e. one dictionary of challenge/response pairs per terminal, hex-encoded.
A sidecar file (same path with a ".stability.json" suffix) stores the
per-device stable-bit masks produced during enrollment.

The stability analysis reuses the "find stable bits" concept of the
esp32-puf reference project (external/puf-esp32-auth): every bit position
whose observed flip rate across repeated measurements stays under a
threshold is marked stable in a 64-character mask of '0'/'1'.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

#: Width of one PUF response in bits (8 rounds x 8 pair-win bits, W2 spec).
RESPONSE_BITS = 64

#: Default maximum per-bit flip rate for a bit to count as stable (~10%,
#: matching the W2 acceptance criterion for single-path reliability).
DEFAULT_FLIP_THRESHOLD = 0.1

_TEMPLATE_SCHEMA = "puf-drone-auth/templates/v1"


# ----------------------------------------------------------------------
# Value coercion helpers
# ----------------------------------------------------------------------
def coerce_response(value: bytes | bytearray | str | int) -> int:
    """Coerce a 64-bit PUF response into an int (0 .. 2**64-1).

    Accepted inputs: 8 raw bytes, a hex string (with or without "0x"), or
    an integer.  Raises ValueError for anything else or wrong width.
    """
    if isinstance(value, (bytes, bytearray)):
        if len(value) != RESPONSE_BITS // 8:
            raise ValueError(f"response must be 8 bytes, got {len(value)}")
        return int.from_bytes(bytes(value), "big")
    if isinstance(value, str):
        text = value.strip().lower().removeprefix("0x")
        if not text:
            raise ValueError("empty response string")
        return int(text, 16)
    if isinstance(value, int):
        return value
    raise TypeError(f"unsupported response type: {type(value).__name__}")


def coerce_challenge(value: bytes | bytearray | str) -> str:
    """Coerce a 64-bit challenge seed into a lowercase 16-char hex string."""
    if isinstance(value, (bytes, bytearray)):
        if len(value) != 8:
            raise ValueError(f"seed must be 8 bytes, got {len(value)}")
        return bytes(value).hex()
    if isinstance(value, str):
        text = value.strip().lower().removeprefix("0x")
        if len(text) != 16 or any(c not in "0123456789abcdef" for c in text):
            raise ValueError(f"not a 64-bit hex seed: {value!r}")
        return text
    raise TypeError(f"unsupported seed type: {type(value).__name__}")


def hamming_distance_bytes(a: bytes | int, b: bytes | int) -> int:
    """Hamming distance between two 64-bit values (0..64)."""
    va = coerce_response(a)
    vb = coerce_response(b)
    return (va ^ vb).bit_count()


def normalize_pairs(
    pairs: Mapping[Any, Any] | Iterable[Sequence[Any]],
) -> dict[str, str]:
    """Normalize CRP input into a {seed_hex: response_hex} mapping.

    Accepts either a mapping (challenge -> response) or an iterable of
    (challenge, response) tuples.  Challenges and responses may each be
    given as bytes, hex strings or (responses only) ints.
    """
    items: Iterable[Sequence[Any]]
    if isinstance(pairs, Mapping):
        items = [(k, v) for k, v in pairs.items()]
    else:
        items = pairs
    out: dict[str, str] = {}
    for challenge, response in items:
        seed_hex = coerce_challenge(challenge)
        out[seed_hex] = f"{coerce_response(response):016x}"
    return out


# ----------------------------------------------------------------------
# Stability analysis (reuse of the esp32-puf find_stable_bits concept)
# ----------------------------------------------------------------------
def bit_flip_rates(templates: Mapping[str, Any]) -> list[float]:
    """Per-bit flip rate, averaged over challenges.

    Unlike an SRAM PUF (where the same cells are measured repeatedly),
    responses to *different* challenges are statistically unrelated.  The
    flip rate of bit position i is therefore computed per seed over its
    repeated measurements and then averaged across seeds.

    Parameters
    ----------
    templates:
        Mapping seed_hex -> response, where response may be a single value
        (bytes / hex string / int) or a *list* of repeated measurements of
        the same challenge.

    Returns
    -------
    list[float]
        RESPONSE_BITS floats; index 0 corresponds to the MSB (bit 63) of
        the response, matching the mask layout of compute_stability().
    """
    rate_sum = [0.0] * RESPONSE_BITS
    n_seeds = 0
    for response in templates.values():
        samples = response if isinstance(response, (list, tuple)) else [response]
        ones = [0] * RESPONSE_BITS
        total = 0
        for sample in samples:
            value = coerce_response(sample)
            for i in range(RESPONSE_BITS):
                if (value >> (RESPONSE_BITS - 1 - i)) & 1:
                    ones[i] += 1
            total += 1
        if total == 0:
            continue
        n_seeds += 1
        for i in range(RESPONSE_BITS):
            rate_sum[i] += min(ones[i], total - ones[i]) / total
    if n_seeds == 0:
        raise ValueError("no measurements supplied")
    return [r / n_seeds for r in rate_sum]


def compute_stability(
    templates: Mapping[str, Any],
    flip_threshold: float = DEFAULT_FLIP_THRESHOLD,
) -> str:
    """Compute the stable-bit mask for a set of (repeated) measurements.

    This adapts the find_stable_bits concept from the esp32-puf reference
    project (external/puf-esp32-auth/tools) to the 64-bit RO-pairing
    response of this project.

    Parameters
    ----------
    templates:
        Mapping seed_hex -> response, where response is a single value or
        a list of repeated measurements of the same challenge.
    flip_threshold:
        Maximum fraction of measurements a bit may flip (relative to its
        majority value) and still count as stable.  Default 0.1 (10%),
        matching the W2 reliability acceptance criterion.

    Returns
    -------
    str
        RESPONSE_BITS-character string of '1' (stable) and '0' (unstable),
        MSB first, i.e. mask[0] corresponds to response bit 63.
    """
    rates = bit_flip_rates(templates)
    return "".join("1" if r <= flip_threshold else "0" for r in rates)


#: Alias kept for lineage with the esp32-puf reference tooling.
find_stable_bits = compute_stability


# ----------------------------------------------------------------------
# Template database
# ----------------------------------------------------------------------
class TemplateDB:
    """JSON-backed template store with Hamming-distance matching.

    Parameters
    ----------
    path:
        JSON file the templates are persisted to.  The on-disk layout is
        exactly {terminal_id: {seed_hex: response_hex}}.  Stable-bit masks
        are kept in a sidecar file next to it.
    """

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self.templates: dict[str, dict[str, str]] = {}
        self.stability: dict[str, str] = {}
        self.load()

    # -- persistence --------------------------------------------------
    def load(self) -> None:
        """Load templates and stability masks from disk if present."""
        if self.path is not None and self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            # Accept both the plain layout and a versioned wrapper.
            if isinstance(raw, dict) and raw.get("schema") == _TEMPLATE_SCHEMA:
                raw = raw.get("devices", {})
            self.templates = {
                str(tid): dict(pairs) for tid, pairs in raw.items()
            }
        sidecar = self._sidecar_path()
        if sidecar is not None and sidecar.exists():
            self.stability = {
                str(k): str(v)
                for k, v in json.loads(sidecar.read_text(encoding="utf-8")).items()
            }

    def save(self) -> None:
        """Persist templates (and stability masks) to disk as UTF-8 JSON."""
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self.templates, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        sidecar = self._sidecar_path()
        if sidecar is not None:
            sidecar.write_text(
                json.dumps(self.stability, indent=2, sort_keys=True),
                encoding="utf-8",
            )

    def _sidecar_path(self) -> Path | None:
        if self.path is None:
            return None
        return self.path.with_suffix(".stability.json")

    # -- enrollment -----------------------------------------------------
    def enroll(
        self,
        terminal_id: int | str,
        crp_pairs: Mapping[Any, Any] | Iterable[Sequence[Any]],
        measurements: Mapping[str, Sequence[Any]] | None = None,
        flip_threshold: float = DEFAULT_FLIP_THRESHOLD,
    ) -> dict[str, Any]:
        """Enroll (or extend) the template of one terminal.

        Parameters
        ----------
        terminal_id:
            Terminal identifier (stored as its string form in JSON).
        crp_pairs:
            Challenge/response pairs to store.  Mapping or iterable of
            tuples; see normalize_pairs() for accepted value types.
        measurements:
            Optional raw repeated measurements per seed hex used for the
            stability mask; when omitted, the stored pairs themselves are
            analysed (single measurement per seed => all bits "stable").
        flip_threshold:
            Flip-rate cut for the stable-bit mask, see compute_stability().

        Returns
        -------
        dict
            Summary with the number of stored pairs, the stable-bit count
            and the overall stability percentage.
        """
        tid = str(terminal_id)
        pairs = normalize_pairs(crp_pairs)
        device = dict(self.templates.get(tid, {}))
        device.update(pairs)
        self.templates[tid] = device

        source = measurements if measurements is not None else pairs
        try:
            mask = compute_stability(source, flip_threshold)
        except ValueError:
            mask = "1" * RESPONSE_BITS
        self.stability[tid] = mask
        self.save()
        return {
            "terminal_id": tid,
            "n_pairs": len(device),
            "added": len(pairs),
            "stable_bits": mask.count("1"),
            "total_bits": RESPONSE_BITS,
            "stability_pct": round(100.0 * mask.count("1") / RESPONSE_BITS, 1),
        }

    # -- matching ---------------------------------------------------------
    def expected(self, terminal_id: int | str, seed: bytes | str) -> bytes | None:
        """Enrolled response for one seed, or None when unknown."""
        device = self.templates.get(str(terminal_id))
        if device is None:
            return None
        try:
            seed_hex = coerce_challenge(seed)
        except (ValueError, TypeError):
            return None
        resp_hex = device.get(seed_hex)
        return bytes.fromhex(resp_hex) if resp_hex else None

    def _reference_int(self, tid: str) -> int:
        """Majority-vote reference value across a device's responses.

        This implements the simple single-template (W1-style) matching
        mode: without knowing which challenge produced the response, the
        best the database can do is compare against the bit-wise majority
        of every stored response.  The protocol layer always passes the
        seed and therefore uses the exact per-challenge template instead.
        """
        responses = [int(r, 16) for r in self.templates[tid].values()]
        ref = 0
        for i in range(RESPONSE_BITS):
            shift = RESPONSE_BITS - 1 - i
            ones = sum((r >> shift) & 1 for r in responses)
            if ones * 2 > len(responses):  # strict majority, ties -> 0
                ref |= 1 << shift
        return ref

    def hamming_distance(
        self,
        terminal_id: int | str,
        response: bytes | bytearray | str | int,
        seed: bytes | str | None = None,
    ) -> int:
        """Hamming distance between a response and the stored template.

        Parameters
        ----------
        terminal_id:
            Terminal whose template should be used.
        response:
            The 64-bit response under test (bytes, hex string or int).
        seed:
            Optional challenge seed.  When given, the response is compared
            against the exact enrolled response for that seed (the normal
            protocol path).  When omitted, the majority-vote reference of
            the device is used (simple W1-style mode).

        Returns
        -------
        int
            Hamming distance in 0..64.

        Raises
        ------
        KeyError
            If the terminal is not enrolled or the seed has no template.
        """
        tid = str(terminal_id)
        device = self.templates.get(tid)
        if device is None:
            raise KeyError(f"terminal {tid!r} is not enrolled")
        value = coerce_response(response)
        if seed is not None:
            seed_hex = coerce_challenge(seed)
            if seed_hex not in device:
                raise KeyError(f"no template for seed {seed_hex}")
            template_int = int(device[seed_hex], 16)
        else:
            template_int = self._reference_int(tid)
        return (value ^ template_int).bit_count()

    def hamming_distances(
        self,
        terminal_id: int | str,
        seeds: Sequence[bytes | str],
        responses: Sequence[bytes | bytearray | str | int],
    ) -> list[int]:
        """Per-seed Hamming distances for a batch of responses (0..64 each)."""
        if len(seeds) != len(responses):
            raise ValueError("seeds and responses must have equal length")
        return [
            self.hamming_distance(terminal_id, resp, seed=s)
            for s, resp in zip(seeds, responses)
        ]

    # -- introspection -----------------------------------------------------
    def has_terminal(self, terminal_id: int | str) -> bool:
        """True when the terminal has at least one enrolled pair."""
        return str(terminal_id) in self.templates

    def terminals(self) -> list[str]:
        """Sorted list of enrolled terminal ids (string form)."""
        return sorted(self.templates)

    def stable_mask(self, terminal_id: int | str) -> str | None:
        """Stored stable-bit mask for a terminal, or None if not computed."""
        return self.stability.get(str(terminal_id))

    def status(self) -> list[dict[str, Any]]:
        """JSON-serializable summary of every enrolled terminal."""
        out = []
        for tid in self.terminals():
            mask = self.stability.get(tid, "")
            out.append(
                {
                    "terminal_id": tid,
                    "n_pairs": len(self.templates[tid]),
                    "stable_bits": mask.count("1") if mask else None,
                }
            )
        return out
