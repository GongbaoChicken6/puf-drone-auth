"""W4 PUF response-semantics golden model (contract S8 / W4 design book S1).

Bit-exact Python mirror of the RTL pairing pipeline::

    seed  --(challenge_decode.v: LFSR + Fisher-Yates)-->  pair_table
    freqs[16] --(pairwise compare)-->  64-bit R1

Both sides of the system (RTL testbenches and the PC server) derive
their expectations from THIS module, so semantic drift fails CI instead
of silently splitting the two implementations.

Frozen semantics (mirror of challenge_decode.v, do not change one side):
  * LFSR: Fibonacci x^64+x^63+x^61+x^60+1, LEFT shift, feedback into
    bit 0, fb = s[63]^s[62]^s[60]^s[59]; draw = state[63:56] taken
    BEFORE the 8 advancing steps ("xian qu shu hou yiwei").
  * Per swap i = 15..1: d = draw; LFSR advances 8 steps;
    j = d % (i + 1)  (RTL restoring division == Python % for d>=0);
    swap order[i] <-> order[j]; order starts as identity [0..15]
    (ORDER_INIT nibble i = i).
  * Round word (64 bit): nibble i = order[i] (i=0 lowest nibble);
    byte p = (order[2p+1] << 4) | order[2p]; pair p = (A=order[2p],
    B=order[2p+1]).
  * Register image: 512-bit value = sum(round_word << (64 * r)) --
    round 0 lives in the LOWEST 64 bits, exactly like pair_table_reg.
  * Response: bit(r, p) = 1 iff freq[B] > freq[A] else 0 (ties -> 0);
    R1[63 - 8r - p] = bit(r, p); serialize big-endian (byte 0 first).
"""

from __future__ import annotations

import secrets
from typing import Iterable, Sequence

N_RINGS = 16
N_ROUNDS = 8
PAIRS_PER_ROUND = 8
RESPONSE_BITS = 64
RESPONSE_BYTES = 8

_MASK64 = (1 << 64) - 1

#: W2 counter magnitude (ro_array 1 ms window, /32 divided rings).
DEFAULT_FREQ_MIN = 3100
DEFAULT_FREQ_MAX = 9600

#: Frozen cross-check seeds (contract S8 / tb_challenge_decode golden).
GOLDEN_SEED_A = 0xC0FF_EEBE_EF12_3456   # = tb SEED_FIX, continuity
GOLDEN_SEED_B = 0x0F1E_2D3C_4B5A_6978
GOLDEN_SEED_C = 0xFEED_FACE_CAFE_BABE


def _as_seed_int(seed: bytes | bytearray | int) -> int:
    if isinstance(seed, (bytes, bytearray)):
        if len(seed) != 8:
            raise ValueError(f"seed must be 8 bytes, got {len(seed)}")
        return int.from_bytes(bytes(seed), "big")
    value = int(seed)
    if not 0 <= value <= _MASK64:
        raise ValueError("seed out of 64-bit range")
    return value


def _lfsr_step(state: int) -> int:
    """One Fibonacci LFSR step: left shift, feedback into bit 0."""
    fb = ((state >> 63) ^ (state >> 62) ^ (state >> 60) ^ (state >> 59)) & 1
    return ((state << 1) | fb) & _MASK64


def decode_pair_table(seed: bytes | bytearray | int) -> list[list[tuple[int, int]]]:
    """Decode one seed into 8 rounds x 8 (ring_A, ring_B) pairs.

    Deterministic and side-effect free; mirrors challenge_decode.v
    bit-for-bit (see module docstring for the frozen semantics).
    """
    lfsr = _as_seed_int(seed)
    rounds: list[list[tuple[int, int]]] = []
    for _round in range(N_ROUNDS):
        order = list(range(N_RINGS))
        for i in range(N_RINGS - 1, 0, -1):
            draw = (lfsr >> 56) & 0xFF          # take d = state[63:56] first
            for _ in range(8):                  # then advance 8 steps
                lfsr = _lfsr_step(lfsr)
            j = draw % (i + 1)                  # == RTL restoring division
            order[i], order[j] = order[j], order[i]
        rounds.append(
            [(order[2 * p], order[2 * p + 1]) for p in range(PAIRS_PER_ROUND)]
        )
    return rounds


def pair_table_int(seed: bytes | bytearray | int) -> int:
    """512-bit register image exactly as the RTL holds it.

    Round r occupies bits [64r +: 64]; the big-endian hex string of this
    value is what tb_challenge_decode and contract S8 freeze.
    """
    value = 0
    for r, pairs in enumerate(decode_pair_table(seed)):
        word = 0
        for p, (ring_a, ring_b) in enumerate(pairs):
            # byte p lives at bits [8p +: 8] of the round word -- the
            # first pair is the LOWEST byte (RTL indexing), not the MSB
            # (cross-check lesson: left-shift packing mirrored it).
            word |= ((ring_b << 4) | ring_a) << (8 * p)
        value |= word << (64 * r)
    return value


def pair_table_hex(seed: bytes | bytearray | int) -> str:
    """128 lowercase hex chars, MSB first (round 7 ... round 0)."""
    return f"{pair_table_int(seed):0128x}"


class ROPairingPUF:
    """Software model of one device's RO-pairing PUF (W4 B5a semantics).

    The device secret is its 16-ring frequency vector; the response to a
    challenge seed is the 64-bit pairwise-comparison vector derived from
    decode_pair_table(seed) and the current (possibly noisy) freqs.

    freqs=None mints a CSPRNG vector in the W2 counter magnitude; an
    injected random source (any random.Random-like) makes tests
    deterministic; flip_prob applies per-response-bit measurement noise
    (same noise model as the loopback SimulatedTerminal).
    """

    def __init__(
        self,
        freqs: Sequence[int] | None = None,
        flip_prob: float = 0.0,
        rng: secrets.SystemRandom | object | None = None,
    ) -> None:
        self.rng = rng if rng is not None else secrets.SystemRandom()
        if freqs is None:
            self.freqs = [
                self.rng.randint(DEFAULT_FREQ_MIN, DEFAULT_FREQ_MAX)
                for _ in range(N_RINGS)
            ]
        else:
            self.freqs = [int(f) for f in freqs]
            if len(self.freqs) != N_RINGS:
                raise ValueError(f"freqs must have {N_RINGS} entries")
        if not 0.0 <= float(flip_prob) <= 1.0:
            raise ValueError(f"flip_prob must be in [0,1], got {flip_prob}")
        self.flip_prob = float(flip_prob)

    def ideal(self, seed: bytes | bytearray | int) -> bytes:
        """Noiseless 64-bit response (deterministic for this device)."""
        bits = 0
        for r, pairs in enumerate(decode_pair_table(seed)):
            for p, (ring_a, ring_b) in enumerate(pairs):
                if self.freqs[ring_b] > self.freqs[ring_a]:
                    bits |= 1 << (RESPONSE_BITS - 1 - (r * PAIRS_PER_ROUND + p))
        return bits.to_bytes(RESPONSE_BYTES, "big")

    def respond(self, seed: bytes | bytearray | int) -> bytes:
        """Response with per-bit measurement noise (flip_prob)."""
        value = int.from_bytes(self.ideal(seed), "big")
        if self.flip_prob > 0.0:
            for i in range(RESPONSE_BITS):
                if self.rng.random() < self.flip_prob:
                    value ^= 1 << i
        return value.to_bytes(RESPONSE_BYTES, "big")

    def measure(self, jitter_pct: float = 0.0, scale: float = 1.0) -> list[int]:
        """Perturbed frequency vector (temperature / voltage hook).

        Returns a NEW list (self.freqs untouched): symmetric jitter of
        +/- jitter_pct percent around each scaled frequency, rounded and
        clamped to >= 1.  Used by reliability experiments and the W5
        temperature curves; not part of the frozen wire semantics.
        """
        if scale <= 0:
            raise ValueError(f"scale must be > 0, got {scale}")
        out: list[int] = []
        for f in self.freqs:
            scaled = float(f) * float(scale)
            if jitter_pct > 0.0:
                scaled *= 1.0 + self.rng.uniform(-jitter_pct, jitter_pct) / 100.0
            out.append(max(1, int(round(scaled))))
        return out

    def with_freqs(self, freqs: Iterable[int]) -> "ROPairingPUF":
        """Clone this device at a perturbed operating point (e.g. hot)."""
        return ROPairingPUF(freqs=freqs, flip_prob=self.flip_prob, rng=self.rng)
