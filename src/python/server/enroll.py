"""Device enrollment over any transport (registration-semantics pairing).

Implements the "注册流程 (P1-6)" sketch from docs/project_design.md as
real code.  The rule recorded in HANDOFF (W3/W4 boundary): enrollment
MUST use the same response semantics as the terminal it will later
authenticate -- the loopback simulator here, the real W3 device through
SerialTransport or the serial server later.  Enrolling with one
semantics and authenticating with another makes every PUF score fail
against the wrong reference (always-REJECT), which looks like a
protocol bug but is an enrollment bug.

Wire constraint honored here: a CHALLENGE frame carries exactly
N_CHALLENGES seeds (32-byte payload budget), so the requested challenge
count is rounded up to a multiple of it.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

from .crp_pool import PoolExhaustedError  # noqa: F401  (re-exported for callers)
from .protocol import HFIDAProtocol


def majority_bytes(responses: Sequence[bytes]) -> bytes:
    """Bit-wise majority vote across repeated 8-byte responses (ties -> 0)."""
    n = len(responses)
    if n == 0:
        raise ValueError("no responses to vote on")
    values = [int.from_bytes(r, "big") for r in responses]
    out = 0
    for i in range(64):
        if sum((v >> i) & 1 for v in values) * 2 > n:
            out |= 1 << i
    return out.to_bytes(8, "big")


def _chunks(seq: Sequence[bytes], size: int) -> list[list[bytes]]:
    return [list(seq[i : i + size]) for i in range(0, len(seq), size)]


def enroll_device(
    protocol: HFIDAProtocol,
    transport: Any,
    terminal_id: int,
    n_challenges: int = 100,
    measurements: int = 3,
    on_progress: Callable[[int, int, int, int], None] | None = None,
) -> dict[str, Any]:
    """Enroll (or refresh) one terminal's template through a transport.

    transport must expose respond(terminal_id, seeds, frame=...) with the
    semantics of the terminal being enrolled (LoopbackTransport,
    SerialTransport, or the wire terminal of the serial-server tests).

    on_progress(batch, batches, round, rounds) fires per measurement
    round for UI hooks.  Returns the template summary plus metadata.
    Raises PoolExhaustedError when the CRP pool cannot supply the seeds.
    """
    tid = int(terminal_id)
    rounds = max(1, int(measurements))
    per_frame = int(HFIDAProtocol.N_CHALLENGES)
    n = max(per_frame, int(n_challenges))
    n += (-n) % per_frame  # every wire exchange is one full CHALLENGE frame

    seeds = protocol.pools.get(tid).reserve(n)
    data: dict[str, list[bytes]] = {}
    try:
        batches = _chunks(seeds, per_frame)
        for index, batch in enumerate(batches):
            frame = protocol.pack(HFIDAProtocol.MSG_CHALLENGE, seeds=batch)
            for round_index in range(rounds):
                if on_progress is not None:
                    on_progress(index + 1, len(batches), round_index + 1, rounds)
                for seed, resp in zip(
                    batch, transport.respond(tid, batch, frame=frame)
                ):
                    data.setdefault(seed.hex(), []).append(resp)
    except BaseException:
        # review B-P1: seeds minted by reserve() but never measured must
        # not stay drawable (they have no template entry); roll them back
        # and re-raise the original failure (Ctrl-C included).
        protocol.pools.get(tid).release(seeds)
        raise

    pairs = [
        (bytes.fromhex(hex_seed), majority_bytes(responses))
        for hex_seed, responses in data.items()
    ]
    summary = protocol.templates.enroll(tid, pairs, measurements=data)
    return {
        "summary": summary,
        "measurements": rounds,
        "n_challenges": len(seeds),
    }
