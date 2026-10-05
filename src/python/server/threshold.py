"""Dual-threshold authentication decision with a gray zone.

The server scores a terminal by the Hamming distance (HD) between its
64-bit PUF response and the enrolled template.  Two thresholds carve the
decision space into three regions (design doc, "B line" protocol section):

===== ======================== ===========================================
HD    decision                 rationale
===== ======================== ===========================================
<= 6  PASS   (~9.4% of 64 bit) genuine device noise only
>= 16 REJECT (~25% of 64 bit)  unrelated response, treat as impostor
7..15 GRAY                     borderline: re-test with extra challenges
===== ======================== ===========================================

The gray zone exists so that marginal measurements (thermal drift, voltage
noise) get a second chance instead of a hard reject, while obvious
impostors are rejected in a single round.
"""

from __future__ import annotations

#: Upper Hamming distance still accepted as a genuine device (64-bit response).
TAU_PASS = 6

#: Lower Hamming distance always rejected as an impostor (64-bit response).
TAU_REJECT = 16

# Module-level sanity check: the pass region must lie strictly below the
# reject region, otherwise the gray zone would be empty or inverted.
assert TAU_PASS < TAU_REJECT, (
    f"invalid thresholds: TAU_PASS ({TAU_PASS}) must be strictly smaller "
    f"than TAU_REJECT ({TAU_REJECT})"
)

#: Decision labels returned by decide().
DECISION_PASS = "PASS"
DECISION_REJECT = "REJECT"
DECISION_GRAY = "GRAY"


def decide(hd: int) -> str:
    """Map a single-response Hamming distance to a decision label.

    Parameters
    ----------
    hd:
        Hamming distance between response and template, 0..64.

    Returns
    -------
    str
        "PASS" if hd <= TAU_PASS, "REJECT" if hd >= TAU_REJECT, otherwise
        "GRAY".
    """
    if hd <= TAU_PASS:
        return DECISION_PASS
    if hd >= TAU_REJECT:
        return DECISION_REJECT
    return DECISION_GRAY


def decide_scaled(hd_sum: int, n_responses: int) -> str:
    """Aggregate-scoring variant of decide() for multi-challenge rounds.

    With several 64-bit responses the per-response thresholds scale
    proportionally, which widens the absolute window while keeping the
    per-response statistical resolution identical.  Example with
    TAU_PASS=6 / TAU_REJECT=16:

    * 4 responses (initial round):  PASS <= 24, REJECT >= 64
    * 7 responses (after 3 gray-zone extras): PASS <= 42, REJECT >= 112

    Parameters
    ----------
    hd_sum:
        Sum of per-response Hamming distances.
    n_responses:
        Number of 64-bit responses the sum was computed over (>= 1).

    Returns
    -------
    str
        "PASS" / "REJECT" / "GRAY" according to the scaled thresholds.
    """
    if n_responses < 1:
        raise ValueError("n_responses must be >= 1")
    if hd_sum <= TAU_PASS * n_responses:
        return DECISION_PASS
    if hd_sum >= TAU_REJECT * n_responses:
        return DECISION_REJECT
    return DECISION_GRAY


def gray_zone_width() -> int:
    """Number of integer HD values that fall inside the gray zone (7..15)."""
    return TAU_REJECT - TAU_PASS - 1
