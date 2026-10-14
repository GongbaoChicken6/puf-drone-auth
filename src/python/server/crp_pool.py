"""Thread-safe challenge pool management for the PUF drone authentication server.

Every enrolled terminal owns a dedicated CRPPool instance (design doc
P1-R6).  A PUF's response to a challenge cannot be predicted, so the pool
only ever hands out challenges whose response has been *measured* during
enrollment:

* :meth:`CRPPool.reserve` (enrollment path) mints fresh CSPRNG seeds and
  registers them as available once the terminal's responses are stored in
  the template database;
* :meth:`CRPPool.draw` (authentication path) hands out available seeds
  without replacement, guaranteeing no challenge is ever used twice for
  the same device (anti-replay);
* exhausting the pool raises :class:`PoolExhaustedError`, which per the
  project risk table triggers a re-enrollment maintenance window.

All randomness comes from :class:`secrets.SystemRandom` (CSPRNG); the
"random" module is deliberately not used anywhere in this package.  All
state mutations are guarded by :class:`threading.Lock` (design doc
P1-R7).  Both the available and used seed sets are persisted to a JSON
file after every mutation, so pool state survives server restarts.

Design reference: docs/project_design.md, section "B line".
"""

from __future__ import annotations

import json
import os
import secrets
import threading
from pathlib import Path
from typing import Any, Iterable, Sequence

#: Default number of challenges ever available per device (configurable).
DEFAULT_POOL_SIZE = 500

#: Length of one challenge seed in bytes (64-bit, see design spec data path).
SEED_BYTES = 8

_POOL_SCHEMA = "puf-drone-auth/crp-pool/v2"


class PoolExhaustedError(RuntimeError):
    """Raised when a draw requests more challenges than remain in the pool.

    Per the project risk table, pool exhaustion (< 20% remaining) triggers a
    re-enrollment maintenance window; the caller is expected to catch this
    exception and start that workflow.
    """


class CRPPool:
    """Per-device pool of single-use 64-bit challenge seeds.

    Parameters
    ----------
    terminal_id:
        Numeric terminal identifier this pool belongs to.
    pool_size:
        Maximum number of challenges ever available for this device
        (default DEFAULT_POOL_SIZE = 500).  If a state file already
        exists it records the committed pool size, which then wins over
        the constructor argument.
    state_path:
        Optional JSON file persisting the available/used seed sets after
        every mutation.  When the file exists it is loaded at
        construction so pool state survives server restarts.
    """

    def __init__(
        self,
        terminal_id: int,
        pool_size: int = DEFAULT_POOL_SIZE,
        state_path: str | os.PathLike[str] | None = None,
    ) -> None:
        if pool_size <= 0:
            raise ValueError("pool_size must be a positive integer")
        self.terminal_id = int(terminal_id)
        self.pool_size = int(pool_size)
        self.state_path = Path(state_path) if state_path is not None else None
        self._rng = secrets.SystemRandom()  # CSPRNG, NOT the random module
        self._lock = threading.Lock()
        self._available: set[str] = set()
        self._used: set[str] = set()
        self._load()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def _load(self) -> None:
        """Load the persisted available/used seed sets, if any."""
        if self.state_path is None or not self.state_path.exists():
            return
        raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        self._available = {str(s).lower() for s in raw.get("available", [])}
        self._used = {str(s).lower() for s in raw.get("used", [])}
        saved_size = int(raw.get("pool_size", self.pool_size))
        if saved_size > 0:
            # The persisted value is the committed capacity for this device.
            self.pool_size = saved_size

    def _persist_locked(self) -> None:
        """Atomically persist pool state.  Caller must hold the lock."""
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "schema": _POOL_SCHEMA,
            "terminal_id": self.terminal_id,
            "pool_size": self.pool_size,
            "available": sorted(self._available),
            "used": sorted(self._used),
        }
        tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, self.state_path)

    # ------------------------------------------------------------------
    # Enrollment path: mint and register new challenges
    # ------------------------------------------------------------------
    def add(self, seeds: Iterable[bytes | str]) -> int:
        """Register seeds as drawable challenges (enrollment replenishment).

        Call this with the seeds whose responses were just measured and
        stored in the template database.  Returns the number of seeds
        actually added (already-known seeds do not count).
        """
        added = 0
        with self._lock:
            for seed in seeds:
                key = seed.hex() if isinstance(seed, (bytes, bytearray)) else str(seed).lower()
                if key in self._available:
                    continue
                if len(self._available) >= self.pool_size:
                    raise PoolExhaustedError(
                        f"CRP pool for terminal {self.terminal_id}: capacity "
                        f"{self.pool_size} reached; raise pool_size or reset"
                    )
                self._available.add(key)
                added += 1
            self._persist_locked()
        return added

    def reserve(self, count: int) -> list[bytes]:
        """Mint count fresh CSPRNG seeds and register them as available.

        Used by the enrollment flow: the returned seeds are sent to the
        terminal, their responses are stored as templates, and the seeds
        become drawable for later authentications (they are *not* marked
        used by reserving).
        """
        if count < 1:
            raise ValueError("count must be >= 1")
        with self._lock:
            if len(self._available) + count > self.pool_size:
                raise PoolExhaustedError(
                    f"CRP pool for terminal {self.terminal_id}: reserving "
                    f"{count} would exceed capacity {self.pool_size} "
                    f"({len(self._available)} already available)"
                )
            minted: list[bytes] = []
            while len(minted) < count:
                seed = self._rng.randbytes(SEED_BYTES)
                key = seed.hex()
                if key in self._available or key in self._used:
                    continue  # collision (probability ~ 2^-64): redraw
                self._available.add(key)
                minted.append(seed)
            self._persist_locked()
            return minted

    # ------------------------------------------------------------------
    # Authentication path
    # ------------------------------------------------------------------
    def draw(self, count: int = 1) -> list[bytes]:
        """Atomically draw count available challenges (without replacement).

        The draw is all-or-nothing: if fewer than count eligible challenges
        remain, nothing is consumed and PoolExhaustedError is raised.  The
        used set is persisted to JSON before returning.

        Parameters
        ----------
        count:
            Number of challenges to draw (must be >= 1).

        Returns
        -------
        list[bytes]
            count seeds, each exactly SEED_BYTES bytes, chosen uniformly
            at random (without replacement) from the enrolled-unused set
            via secrets.SystemRandom.
        """
        if count < 1:
            raise ValueError("count must be >= 1")
        with self._lock:
            eligible = self._available - self._used
            if count > len(eligible):
                raise PoolExhaustedError(
                    f"CRP pool for terminal {self.terminal_id}: requested "
                    f"{count} challenges, only {len(eligible)} of "
                    f"{self.pool_size} remain (enroll to replenish)"
                )
            picked = self._rng.sample(sorted(eligible), count)
            self._used.update(picked)
            self._persist_locked()
            return [bytes.fromhex(key) for key in picked]

    def release(self, seeds: list[bytes] | tuple[bytes, ...]) -> int:
        """Roll back seeds minted by reserve() when enrollment aborted.

        review B-P1: reserve() puts freshly minted seeds straight into
        the drawable set.  If the enrollment exchange dies halfway
        (serial timeout, Ctrl-C), those seeds have no template entry and
        drawing one later would blow up scoring.  Removes the given
        seeds from the available set again (used seeds are kept -- they
        were genuinely consumed) and persists.  Returns how many were
        actually removed.
        """
        keys = [bytes(s).hex() for s in seeds]
        with self._lock:
            removed = 0
            for key in keys:
                if key in self._available and key not in self._used:
                    self._available.discard(key)
                    removed += 1
            if removed:
                self._persist_locked()
            return removed

    def unuse(self, seeds: list[bytes] | tuple[bytes, ...]) -> int:
        """Return drawn-but-unconsumed seeds to the drawable set.

        W4-P4 T4 staging-release semantics (review B-P2 F5): draw() marks
        seeds used **permanently**, so a failed authentication burns the
        challenge for good.  An attacker flooding ACCESS_REQUEST therefore
        drains the pool even through the rate limiter (~90s to empty a
        100-seed pool at 10/min).  This rolls a *failed* session's draw
        back, so the pool only shrinks on successful authentications.

        Contrast release(), which removes never-enrolled seeds from the
        available set (enrollment abort path) -- different direction.

        Returns how many seeds were actually returned.
        """
        keys = [bytes(s).hex() for s in seeds]
        with self._lock:
            returned = 0
            for key in keys:
                if key in self._used:
                    self._used.discard(key)
                    returned += 1
            if returned:
                self._persist_locked()
            return returned

    def _remaining_nolock(self) -> int:
        """Remaining (enrolled, unused) challenge count.  Lock required."""
        return len(self._available - self._used)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    @property
    def remaining(self) -> int:
        """Number of challenges still drawable in this pool."""
        with self._lock:
            return self._remaining_nolock()

    @property
    def remaining_pct(self) -> int:
        """Remaining capacity as an integer percentage in 0..100.

        Note: returns an integer 0-100 (e.g. 87), *not* a 0-1 float.
        """
        with self._lock:
            if self.pool_size <= 0:
                return 0
            return int(round(self._remaining_nolock() * 100.0 / self.pool_size))

    @property
    def used_count(self) -> int:
        """Number of challenges already consumed by this device."""
        with self._lock:
            return len(self._used)

    @property
    def available_count(self) -> int:
        """Number of enrolled challenges currently registered."""
        with self._lock:
            return len(self._available)

    def status(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot of the pool state."""
        with self._lock:
            remaining = self._remaining_nolock()
            return {
                "terminal_id": self.terminal_id,
                "pool_size": self.pool_size,
                "available": len(self._available),
                "used": len(self._used),
                "remaining": remaining,
                "remaining_pct": int(round(remaining * 100.0 / self.pool_size))
                if self.pool_size > 0
                else 0,
                "state_file": str(self.state_path) if self.state_path else None,
            }

    def reset(self) -> None:
        """Clear both the available and used sets (re-enrollment path).

        WARNING: after reset the pool can only hand out challenges again
        once a fresh enrollment replenishes it.
        """
        with self._lock:
            self._available.clear()
            self._used.clear()
            self._persist_locked()


class CRPPoolRegistry:
    """Registry that manages one CRPPool per terminal device."""

    def __init__(
        self,
        state_dir: str | os.PathLike[str] = "data/crp_datasets/pools",
        pool_size: int = DEFAULT_POOL_SIZE,
    ) -> None:
        self.state_dir = Path(state_dir)
        self.pool_size = int(pool_size)
        self._lock = threading.Lock()
        self._pools: dict[int, CRPPool] = {}

    def get(self, terminal_id: int) -> CRPPool:
        """Return the pool for terminal_id, creating it on first use."""
        tid = int(terminal_id)
        with self._lock:
            pool = self._pools.get(tid)
            if pool is None:
                pool = CRPPool(
                    terminal_id=tid,
                    pool_size=self.pool_size,
                    state_path=self.state_dir / f"pool_{tid}.json",
                )
                self._pools[tid] = pool
            return pool

    def remove(self, terminal_id: int) -> None:
        """Drop the in-memory pool instance (state file is kept on disk)."""
        with self._lock:
            self._pools.pop(int(terminal_id), None)

    def reset(self, terminal_id: int) -> None:
        """Reset the pool of one device (see CRPPool.reset)."""
        self.get(terminal_id).reset()

    def status(self) -> list[dict[str, Any]]:
        """Snapshot of every pool known to this registry."""
        with self._lock:
            pools = list(self._pools.values())
        return [pool.status() for pool in sorted(pools, key=lambda p: p.terminal_id)]

    def terminals(self) -> list[int]:
        """Sorted list of terminal ids that have pools."""
        with self._lock:
            return sorted(self._pools)


def format_pool_summary(pools: Sequence[dict[str, Any]]) -> str:
    """Render a registry status snapshot as a human-readable table."""
    lines = ["terminal    used  remaining   left %"]
    for p in pools:
        lines.append(
            f"{p['terminal_id']:>10} {p['used']:>6} {p['remaining']:>10} "
            f"{p['remaining_pct']:>7}"
        )
    return "\n".join(lines)
