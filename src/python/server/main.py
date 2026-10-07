"""PC authentication server entry point (REPL) for the PUF drone system.

Runs the B-line server either against a fully simulated in-process drone
terminal (loopback, default -- no hardware needed) or against a real
serial link (pyserial, for the W3 hardware integration).

Usage::

    python -m src.python.server.main --loopback
    python src/python/server/main.py --loopback
    python -m src.python.server.main --port COM3 --baud 115200

REPL commands::

    auth <terminal_id> [n]     run one full authentication round
    spoof <terminal_id>        authenticate using an impostor device
    enroll <terminal_id> [n]   enroll/refresh a device template (n CRPs)
    setkey <terminal_id> <hex> install an explicit Speck64/96 device key
    c2reset <terminal_id>      clear the C2 replay window (terminal
                               power-cycle recovery)
    status                     show sessions, templates and CRP pools
    quit                       exit the server
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Sequence

# ---------------------------------------------------------------------
# Import bootstrap: works both as a module and as a plain script.
# ---------------------------------------------------------------------
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from src.python.server.crp_pool import (  # noqa: E402
        PoolExhaustedError,
        format_pool_summary,
    )
    from src.python.server.hsm import (  # noqa: E402
        DEVICE_KEY_BYTES,
        SpeckHSM,
        hsm_status,
    )
    from src.python.server.protocol import (  # noqa: E402
        CONFIRM_OK,
        HD_NONE,
        RESULT_ERROR,
        RESULT_PASS,
        RESULT_POOL_EMPTY,
        RESULT_REJECT,
        RESULT_REPLAY,
        ProtocolError,
        HFIDAProtocol,
    )
    from src.python.server.template_db import TemplateDB  # noqa: E402
else:
    from .crp_pool import PoolExhaustedError, format_pool_summary
    from .hsm import DEVICE_KEY_BYTES, SpeckHSM, hsm_status
    from .protocol import (
        CONFIRM_OK,
        HD_NONE,
        RESULT_ERROR,
        RESULT_PASS,
        RESULT_POOL_EMPTY,
        RESULT_REJECT,
        RESULT_REPLAY,
        ProtocolError,
        HFIDAProtocol,
    )
    from .template_db import TemplateDB

#: Default per-bit flip probability of the simulated genuine terminal.
#: 2% gives an expected Hamming distance of ~1.3 bit per 64-bit response,
#: comfortably inside the PASS region.
NORMAL_FLIP_PROB = 0.02

_RESULT_NAMES = {
    RESULT_PASS: "PASS",
    RESULT_REJECT: "REJECT",
    RESULT_ERROR: "ERROR (not enrolled / protocol misuse)",
    RESULT_POOL_EMPTY: "REJECT (CRP pool exhausted: re-enroll the device)",
    RESULT_REPLAY: "REJECT (C2 replay suspected; power-cycled terminal? "
                   "run 'c2reset <terminal_id>')",
}


# ---------------------------------------------------------------------
# Simulated drone terminal (loopback transport)
# ---------------------------------------------------------------------
class SimulatedTerminal:
    """Software model of one drone terminal's RO-pairing PUF.

    The device secret is a random 32-byte key; the response to a
    challenge seed is a keyed HMAC-SHA256 digest truncated to 64 bit,
    then perturbed with per-bit flips to model measurement noise.
    """

    #: C2 reset value matching terminal_fsm.v: c2_counter[j] resets to
    #: 8'hA0 + j and every authentication increments each byte bytewise
    #: (no carry propagation), exactly like the RTL counter.
    C2_INIT = bytes(0xA0 + j for j in range(8))

    def __init__(self, terminal_id: int, flip_prob: float = NORMAL_FLIP_PROB) -> None:
        self.terminal_id = terminal_id
        self.secret = secrets.token_bytes(32)
        self.flip_prob = flip_prob
        self._rng = secrets.SystemRandom()
        self._auth_count = 0

    def ideal_response(self, seed: bytes) -> bytes:
        """Noiseless response (deterministic for the device secret)."""
        digest = hmac.new(self.secret, b"resp" + bytes(seed), hashlib.sha256).digest()
        return digest[:8]

    def respond(self, seeds: Sequence[bytes], flip_prob: float | None = None) -> list[bytes]:
        """Respond to challenges with realistic bit-flip noise applied."""
        prob = self.flip_prob if flip_prob is None else flip_prob
        out: list[bytes] = []
        for seed in seeds:
            value = int.from_bytes(self.ideal_response(seed), "big")
            if prob > 0.0:
                for i in range(64):
                    if self._rng.random() < prob:
                        value ^= 1 << i
            out.append(value.to_bytes(8, "big"))
        return out

    def counter_challenge(self) -> bytes:
        """Generate the terminal's counter-challenge C2 (8 bytes).

        Mirrors the RTL contract (terminal_fsm.v): C2 resets to
        0xA0..0xA7 and advances on every authentication, so a replayed
        ACCESS_REQUEST carries a stale C2 that the server's replay
        window rejects.  First authentication after reset therefore
        sends a1 a2 ... a8 (the tb_terminal_fsm golden C2).
        """
        self._auth_count += 1
        return bytes((b + self._auth_count) & 0xFF for b in self.C2_INIT)


class LoopbackTransport:
    """In-process transport holding one SimulatedTerminal per device id."""

    def __init__(self) -> None:
        self._terminals: dict[int, SimulatedTerminal] = {}
        self._rng = secrets.SystemRandom()

    def terminal(self, terminal_id: int) -> SimulatedTerminal:
        """Get (or lazily create) the terminal simulating this device id."""
        tid = int(terminal_id)
        if tid not in self._terminals:
            self._terminals[tid] = SimulatedTerminal(tid)
        return self._terminals[tid]

    def counter_challenge(self, terminal_id: int) -> bytes:
        """C2 generated by the (simulated) terminal."""
        return self.terminal(terminal_id).counter_challenge()

    def respond(
        self,
        terminal_id: int,
        seeds: Sequence[bytes],
        frame: bytes | None = None,
        impostor: bool = False,
        flip_prob: float | None = None,
    ) -> list[bytes]:
        """Terminal answers the challenges; impostor=True answers with a
        different physical device (mutual-exclusion demo for W5)."""
        if impostor:
            impostor_device = SimulatedTerminal(-1 - int(terminal_id))
            return impostor_device.respond(seeds, flip_prob)
        return self.terminal(terminal_id).respond(seeds, flip_prob)


class SerialTransport:
    """Serial transport to a real terminal (pyserial, W3 integration).

    Writes the packed CHALLENGE frame produced by the protocol engine and
    reads back one RESPONSE_R1 frame (12 header/checksum bytes plus 8
    bytes per challenge).  Kept intentionally thin: the wire format is
    owned by HFIDAProtocol.pack/parse.
    """

    def __init__(self, port: str, baud: int = 115200, timeout: float = 3.0) -> None:
        try:
            import serial  # pyserial, optional dependency
        except ImportError as exc:
            raise RuntimeError(
                "pyserial is required for serial mode: pip install pyserial"
            ) from exc
        self.serial = serial.Serial(port, baud, timeout=timeout)
        self.port = port

    def counter_challenge(self, terminal_id: int) -> bytes:
        """The real terminal sends C2 inside MSG_ACCESS_REQUEST; the REPL
        path generates it here until the full receive loop lands (W3)."""
        return secrets.token_bytes(8)

    def respond(
        self,
        terminal_id: int,
        seeds: Sequence[bytes],
        frame: bytes | None = None,
        impostor: bool = False,
        flip_prob: float | None = None,
    ) -> list[bytes]:
        """Send the challenge frame and read the response frame back."""
        if frame is None:
            raise ValueError("serial transport needs the packed challenge frame")
        self.serial.reset_input_buffer()
        self.serial.write(bytes(frame))
        self.serial.flush()
        reply_len = 12 + 8 * len(seeds)
        reply = self.serial.read(reply_len)
        if len(reply) != reply_len:
            raise TimeoutError(
                f"terminal timeout on {self.port}: got {len(reply)}/{reply_len} bytes"
            )
        _msg_id, fields = HFIDAProtocol.parse(reply)
        return fields["r1s"]

    def close(self) -> None:
        """Close the serial port."""
        self.serial.close()


# ---------------------------------------------------------------------
# Device key store (A1: Speck64/96 keys + C2 replay state, persisted)
# ---------------------------------------------------------------------
_DEVICE_KEY_SCHEMA = "puf-drone-auth/device-keys/v1"


class DeviceKeyStore:
    """Per-terminal Speck device keys and C2 replay history (JSON, 0600).

    Two A1 review findings are fixed by this store:

    * keys are generated once and persisted -- previously every server
      run built a fresh random SimulatedHSM secret, so R2 changed after
      each restart and no terminal could ever re-verify the station;
    * the per-terminal C2 replay window survives server restarts
      (P1-2: "replay window = now" while the server kept no C2 state).

    File format (written with owner-only permissions where the OS
    supports them)::

        {"schema": "puf-drone-auth/device-keys/v1",
         "terminals": {"7": {"key_hex": "<24 hex chars>",
                             "c2_history": ["a1a2a3a4a5a6a7a8", ...]}}}
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._keys: dict[int, bytes] = {}
        self._c2: dict[int, list[bytes]] = {}
        # Serializes mutations and atomic saves: unsynchronized concurrent
        # saves would interleave writes to the shared .tmp path (defect
        # review).  RLock because mutators call save() while holding it.
        self._lock = threading.RLock()

    # -- loading / saving ---------------------------------------------------
    def load(self) -> "DeviceKeyStore":
        """Load an existing store; a missing file starts empty.

        Any malformed content raises ValueError carrying the file path
        and terminal id, so a corrupted key store fails loudly at startup
        with actionable context instead of a bare traceback (silent-
        failure review).
        """
        if not self.path.exists():
            return self
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:  # JSONDecodeError is a ValueError
            raise ValueError(f"{self.path}: cannot parse ({exc})") from None
        if not isinstance(data, dict):
            raise ValueError(f"{self.path}: expected a JSON object")
        if data.get("schema") != _DEVICE_KEY_SCHEMA:
            raise ValueError(
                f"{self.path}: unsupported schema {data.get('schema')!r}"
            )
        terminals = data.get("terminals", {})
        if not isinstance(terminals, dict):
            raise ValueError(
                f"{self.path}: 'terminals' must be a JSON object, "
                f"got {type(terminals).__name__}"
            )
        for tid_str, rec in terminals.items():
            if not isinstance(tid_str, str) or tid_str != str(int(tid_str)):
                # Strict canonical form: "1_0"/"+7"/" 9 " must not silently
                # remap to another terminal id (types review TYPES-04).
                raise ValueError(
                    f"{self.path}: terminal id keys must be canonical "
                    f"decimal strings, got {tid_str!r}"
                )
            try:
                tid = int(tid_str)
                key = bytes.fromhex(rec["key_hex"])
                history = [bytes.fromhex(h) for h in rec.get("c2_history", [])]
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"{self.path}: terminal {tid_str!r} has a malformed "
                    f"record ({exc})"
                ) from None
            if len(key) != DEVICE_KEY_BYTES:
                raise ValueError(
                    f"{self.path}: terminal {tid_str} key must be "
                    f"{DEVICE_KEY_BYTES} bytes"
                )
            for c2 in history:
                if len(c2) != 8:
                    raise ValueError(
                        f"{self.path}: terminal {tid_str} c2_history entry "
                        f"must be 8 bytes, got {len(c2)}"
                    )
            self._keys[tid] = key
            self._c2[tid] = history
        return self

    def save(self) -> None:
        """Persist atomically with owner-only permissions on POSIX (0600).

        Windows/NTFS caveat: os.chmod 0600 maps to a read-only bit only,
        with NO ACL restriction -- see the honest declaration in
        project_design.md ("A1 后安全态势") and HANDOFF W4 backlog.

        Serialized by self._lock so concurrent mutations cannot interleave
        writes to the shared .tmp path.
        """
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "schema": _DEVICE_KEY_SCHEMA,
                "terminals": {
                    str(tid): {
                        "key_hex": self._keys[tid].hex(),
                        "c2_history": [c.hex() for c in self._c2.get(tid, [])],
                    }
                    for tid in sorted(self._keys)
                },
            }
            payload = json.dumps(data, indent=2) + "\n"
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(payload)
                os.replace(tmp, self.path)
            except OSError:
                tmp.unlink(missing_ok=True)
                raise
            try:  # enforce on platforms where replace keeps old permissions
                os.chmod(self.path, 0o600)
            except OSError:
                pass  # best effort (e.g. some filesystems)

    # -- key access -----------------------------------------------------------
    def key_for(self, terminal_id: int) -> tuple[bytes, bool]:
        """Return (key, created): the terminal's key, minting a fresh
        CSPRNG 12-byte key and persisting it immediately on first use."""
        tid = int(terminal_id)
        with self._lock:  # read-mint-persist must be one atomic step
            key = self._keys.get(tid)
            if key is not None:
                return key, False
            key = secrets.token_bytes(DEVICE_KEY_BYTES)
            self._keys[tid] = key
            try:
                self.save()
            except OSError:
                # Roll the mint back: a mutation the operator saw fail
                # must never be silently committed by a later save
                # (silent-r2 review R2N2).
                del self._keys[tid]
                raise
            return key, True

    def set_key(self, terminal_id: int, key: bytes) -> None:
        """Install an explicit key (e.g. the W3 FPGA demo key) and persist."""
        if not isinstance(key, (bytes, bytearray)) or len(key) != DEVICE_KEY_BYTES:
            raise ValueError(
                f"device key must be {DEVICE_KEY_BYTES} bytes, got {len(key)}"
            )
        with self._lock:
            tid = int(terminal_id)
            old = self._keys.get(tid)
            self._keys[tid] = bytes(key)
            try:
                self.save()
            except OSError:
                if old is None:
                    del self._keys[tid]
                else:
                    self._keys[tid] = old
                raise  # rollback: never keep a failed mutation (R2N2)

    def all_keys(self) -> dict[int, bytes]:
        """Copy of every known terminal key (for SpeckHSM construction)."""
        with self._lock:  # same discipline as the mutators (types review)
            return dict(self._keys)

    # -- C2 replay history ------------------------------------------------------
    def c2_history(self, terminal_id: int) -> list[bytes]:
        """Copy of one terminal's persisted replay window."""
        with self._lock:
            return list(self._c2.get(int(terminal_id), []))

    def set_c2_history(self, terminal_id: int, c2s: Sequence[bytes]) -> None:
        """Replace and persist one terminal's replay window.

        Like set_key/key_for this auto-persists, so no caller can silently
        lose replay state by forgetting save().  The history is stored
        together with the terminal's key record, so the terminal MUST
        already hold a key -- otherwise save() would drop the window
        (consensus D-7: fail loudly instead).
        """
        tid = int(terminal_id)
        if tid not in self._keys:
            raise ValueError(
                f"{self.path}: terminal {tid} has no key; refusing to "
                f"store a replay window that save() would drop"
            )
        with self._lock:
            tid = int(terminal_id)
            old = self._c2.get(tid)
            self._c2[tid] = list(c2s)
            try:
                self.save()
            except OSError:
                if old is None:
                    del self._c2[tid]
                else:
                    self._c2[tid] = old
                raise  # rollback: never keep a failed mutation (R2N2)

    def clear_c2_history(self, terminal_id: int) -> None:
        """Drop one terminal's replay window and persist the removal."""
        with self._lock:
            tid = int(terminal_id)
            old = self._c2.pop(tid, None)
            try:
                self.save()
            except OSError:
                if old is not None:
                    self._c2[tid] = old
                raise  # rollback: never keep a failed mutation (R2N2)


def _ensure_device_key(
    store: DeviceKeyStore, protocol: HFIDAProtocol, terminal_id: int
) -> None:
    """Make sure an *enrolled* terminal has a Speck device key registered.

    First use mints a fresh 12-byte key with the OS CSPRNG and persists
    it immediately, so R2 stays verifiable across server restarts.  Keys
    are minted only for terminals with an enrolled template and a
    non-negative id (u32 wire domain): a typo like "auth 99" must not
    leave permanent key material in the store (silent-failure review).
    """
    tid = int(terminal_id)
    if tid < 0 or not protocol.templates.has_terminal(tid):
        return
    hsm = protocol.hsm
    if not isinstance(hsm, SpeckHSM) or hsm.has_key(tid):
        return
    key, created = store.key_for(tid)
    hsm.set_key(tid, key)
    if created:
        print(f"[KEY]    terminal {tid}: new Speck64/96 device key "
              f"stored in {store.path}")


def _flush_c2_state(protocol: HFIDAProtocol, store: DeviceKeyStore) -> None:
    """Persist per-terminal C2 replay windows so they survive restarts.

    Persistence failures are downgraded to a warning: this helper runs
    inside finally blocks (cmd_auth / main) where raising would mask the
    original exception and could skip serial-port cleanup (silent-failure
    review P2).
    """
    hsm = protocol.hsm
    if not isinstance(hsm, SpeckHSM):
        return
    try:
        for tid in hsm.terminal_ids():
            store.set_c2_history(tid, protocol.c2_history(tid))
    except OSError as exc:
        print(f"[WARN]   C2 replay-window persistence failed: {exc}")


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
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


def _print_verdict(fields: dict[str, Any], protocol: HFIDAProtocol, tid: int) -> None:
    """Pretty-print a MSG_RESULT field dict."""
    result = fields["result"]
    name = _RESULT_NAMES.get(result, f"RESULT_{result}")
    hd = fields.get("hd", HD_NONE)
    hd_text = "n/a" if hd == HD_NONE else str(hd)
    print(f"  verdict : {name}")
    print(f"  total HD: {hd_text}")
    if result == RESULT_PASS:
        print(f"  R2 (HSM): {fields['r2'].hex()}")
    pool = protocol.pools.get(tid)
    print(f"  pool    : {pool.remaining}/{pool.pool_size} remaining "
          f"({pool.remaining_pct}%)")


# ---------------------------------------------------------------------
# REPL commands
# ---------------------------------------------------------------------
def cmd_enroll(
    protocol: HFIDAProtocol,
    transport: LoopbackTransport | SerialTransport,
    args: Sequence[str],
    measurements: int,
    store: DeviceKeyStore,
) -> None:
    """REPL 'enroll' command: enroll (or refresh) a device template."""
    if not args:
        print("usage: enroll <terminal_id> [n_challenges]")
        return
    tid = int(args[0])
    n = int(args[1]) if len(args) > 1 else 100
    m = max(1, measurements)
    try:
        seeds = protocol.pools.get(tid).reserve(n)
    except PoolExhaustedError as exc:
        print(f"[ERROR] {exc}")
        print("        run 'status' and consider pool maintenance (reset).")
        return
    data: dict[str, list[bytes]] = {seed.hex(): [] for seed in seeds}
    for round_index in range(m):
        for seed, resp in zip(seeds, transport.respond(tid, seeds)):
            data[seed.hex()].append(resp)
    pairs = [(bytes.fromhex(hx), majority_bytes(rs)) for hx, rs in data.items()]
    summary = protocol.templates.enroll(tid, pairs, measurements=data)
    print(f"[ENROLL] terminal {tid}: {summary['n_pairs']} CRPs stored "
          f"(+{summary['added']}), stable bits {summary['stable_bits']}/64 "
          f"({summary['stability_pct']}%) over {m} measurement(s)/challenge")
    pool = protocol.pools.get(tid)
    print(f"[POOL]   {pool.remaining}/{pool.pool_size} challenges remaining "
          f"({pool.remaining_pct}%)")
    # Template exists now, so the enrollment gate in _ensure_device_key
    # passes; minting before this point would key unknown terminals.
    _ensure_device_key(store, protocol, tid)


def cmd_auth(
    protocol: HFIDAProtocol,
    transport: LoopbackTransport | SerialTransport,
    args: Sequence[str],
    store: DeviceKeyStore,
    impostor: bool = False,
) -> None:
    """REPL 'auth'/'spoof' command: run one full authentication round."""
    if not args:
        print("usage: auth <terminal_id>")
        return
    tid = int(args[0])
    label = "SPOOF" if impostor else "AUTH"
    try:
        _ensure_device_key(store, protocol, tid)
        c2 = transport.counter_challenge(tid)
        frame = protocol.on_access_request(tid, c2=c2)
        msg_id, fields = protocol.parse(frame)
        if msg_id == HFIDAProtocol.MSG_RESULT:
            print(f"[{label}] terminal {tid}: refused before challenge: "
                  f"{_RESULT_NAMES.get(fields['result'], fields['result'])}")
            return
        seeds = fields["seeds"]
        print(f"[{label}] terminal {tid}: {len(seeds)} challenges issued "
              f"(frame {len(frame)} B)")
        r1s = transport.respond(tid, seeds, frame=frame, impostor=impostor)
        frame2 = protocol.on_response(tid, r1s)
        msg2, f2 = protocol.parse(frame2)
        if msg2 == HFIDAProtocol.MSG_EXTRA_CHALLENGE:
            print(f"[GRAY]   aggregate score in gray zone; drawing "
                  f"{len(f2['seeds'])} extra challenges")
            r1x = transport.respond(tid, f2["seeds"], frame=frame2, impostor=impostor)
            frame3 = protocol.on_extra_response(tid, r1x)
            msg3, f3 = protocol.parse(frame3)
            _print_verdict(f3, protocol, tid)
            return
        _print_verdict(f2, protocol, tid)
    finally:
        # Persist the widened replay window even on protocol errors, so a
        # crash right after an authentication cannot reopen the replay gap.
        _flush_c2_state(protocol, store)


def cmd_setkey(
    protocol: HFIDAProtocol,
    store: DeviceKeyStore,
    args: Sequence[str],
) -> None:
    """REPL 'setkey': install an explicit Speck64/96 device key (hex).

    Used to align the server with a terminal whose key is already fixed,
    e.g. the W3 FPGA demo device (RTL DEVICE_KEY 96'h13121110_0b0a0908_
    03020100 = hex 0001020308090a0b10111213).
    """
    if len(args) != 2:
        print("usage: setkey <terminal_id> <24-hex-char key>")
        return
    try:
        tid = int(args[0])
        key = bytes.fromhex(args[1])
    except ValueError as exc:
        print(f"[ERROR] bad argument: {exc}")
        return
    if len(key) != DEVICE_KEY_BYTES:
        print(f"[ERROR] key must be {DEVICE_KEY_BYTES} bytes "
              f"({DEVICE_KEY_BYTES * 2} hex chars)")
        return
    if tid < 0:
        print("[ERROR] terminal_id must be non-negative (u32 wire domain)")
        return
    store.set_key(tid, key)
    hsm = protocol.hsm
    if isinstance(hsm, SpeckHSM):
        hsm.set_key(tid, key)
    print(f"[KEY]    terminal {tid}: Speck64/96 device key installed and "
          f"persisted to {store.path}")


def cmd_c2reset(
    protocol: HFIDAProtocol,
    store: DeviceKeyStore,
    args: Sequence[str],
) -> None:
    """REPL 'c2reset': forget a terminal's C2 replay window.

    Recovery path after a genuine terminal power-cycle: its C2 counter
    restarts at the reset value, which the replay window would otherwise
    (correctly, from its point of view) refuse.
    """
    if len(args) != 1:
        print("usage: c2reset <terminal_id>")
        return
    tid = int(args[0])
    protocol.reset_c2_history(tid)
    store.clear_c2_history(tid)
    print(f"[C2]     terminal {tid}: replay window cleared "
          f"(power-cycled terminal may authenticate again)")


def cmd_status(protocol: HFIDAProtocol) -> None:
    """REPL 'status' command: dump sessions, templates and pools."""
    status = protocol.status()
    print("== Sessions ==")
    if status["sessions"]:
        for s in status["sessions"]:
            print(f"  terminal {s['terminal_id']}: state={s['state']} "
                  f"challenges={s['challenges_issued']} "
                  f"scored={s['responses_scored']} hd_sum={s['hd_sum']} "
                  f"decision={s['last_decision']}")
    else:
        print("  (none)")
    print("== Templates ==")
    for t in protocol.templates.status():
        stable = t["stable_bits"]
        stable_text = f"{stable}/64" if stable is not None else "n/a"
        print(f"  terminal {t['terminal_id']}: {t['n_pairs']} CRPs, "
              f"stable {stable_text}")
    print("== CRP pools ==")
    pools = status["pools"]
    print(format_pool_summary(pools) if pools else "  (none)")
    print("== HSM ==")
    print(f"  {hsm_status(protocol.hsm)}")


HELP_TEXT = """commands:
  auth <terminal_id>          authenticate a terminal (full round)
  spoof <terminal_id>         authenticate with an impostor device (demo)
  enroll <terminal_id> [n]    enroll device template (default n=100 CRPs)
  setkey <terminal_id> <hex>  install Speck64/96 device key (24 hex chars)
  c2reset <terminal_id>       clear C2 replay window (power-cycle recovery)
  status                      sessions / templates / CRP pools
  quit                        exit"""


def repl(
    protocol: HFIDAProtocol,
    transport: LoopbackTransport | SerialTransport,
    measurements: int,
    store: DeviceKeyStore,
    input_fn: Callable[[str], str] = input,
) -> int:
    """Run the read-eval-print loop; returns the process exit code."""
    print("PUF drone authentication server")
    print(HELP_TEXT)
    while True:
        try:
            line = input_fn("puf-server> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        parts = line.split()
        cmd, args = parts[0].lower(), parts[1:]
        try:
            if cmd in ("quit", "exit", "q"):
                return 0
            elif cmd == "auth":
                cmd_auth(protocol, transport, args, store, impostor=False)
            elif cmd == "spoof":
                cmd_auth(protocol, transport, args, store, impostor=True)
            elif cmd == "enroll":
                cmd_enroll(protocol, transport, args, measurements, store)
            elif cmd == "setkey":
                cmd_setkey(protocol, store, args)
            elif cmd == "c2reset":
                cmd_c2reset(protocol, store, args)
            elif cmd == "status":
                cmd_status(protocol)
            elif cmd in ("help", "?"):
                print(HELP_TEXT)
            else:
                print(f"unknown command: {cmd}")
                print(HELP_TEXT)
        except (ProtocolError, PoolExhaustedError) as exc:
            print(f"[PROTOCOL ERROR] {exc}")
        except (ValueError, KeyError, OSError) as exc:
            # OSError included so a failing key-store write (disk full,
            # AV/OneDrive lock) degrades to an error line instead of
            # killing the whole REPL (silent-failure review P2).  The
            # type name keeps serial timeouts distinguishable from key
            # store failures (silent-r2 review R2N6).
            print(f"[ERROR] {type(exc).__name__}: {exc}")


def build_parser() -> argparse.ArgumentParser:
    """CLI argument parser for the server entry point."""
    parser = argparse.ArgumentParser(
        prog="puf-server",
        description="PC authentication server for the PUF drone system",
    )
    transport = parser.add_mutually_exclusive_group()
    transport.add_argument(
        "--port", type=str, default=None,
        help="serial port of the terminal radio (e.g. COM3); enables serial mode",
    )
    transport.add_argument(
        "--loopback", action="store_true",
        help="use the in-process simulated terminal (default when --port is absent)",
    )
    parser.add_argument("--baud", type=int, default=115200, help="serial baudrate")
    parser.add_argument(
        "--templates", type=str, default="data/templates/templates.json",
        help="template database JSON path",
    )
    parser.add_argument(
        "--pool-dir", type=str, default="data/crp_datasets/pools",
        help="directory for per-device CRP pool state files",
    )
    parser.add_argument(
        "--pool-size", type=int, default=500,
        help="challenges ever available per device (default 500)",
    )
    parser.add_argument(
        "--measurements", type=int, default=3,
        help="measurements per challenge during enrollment (default 3)",
    )
    parser.add_argument(
        "--device-keys", type=str, default="data/device_keys/device_keys.json",
        help="per-terminal Speck64/96 device key store (JSON, created 0600)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: build the protocol stack and start the REPL."""
    args = build_parser().parse_args(argv)
    templates = TemplateDB(args.templates)
    # A1: Speck64/96 HSM with per-terminal keys persisted in DeviceKeyStore
    # (fixes "fresh random secret every run": R2 now survives restarts and
    # the C2 replay window is rehydrated from the same file).
    store = DeviceKeyStore(args.device_keys).load()
    hsm = SpeckHSM(keys=store.all_keys())
    pools_dir = Path(args.pool_dir)
    if __package__ in (None, ""):
        from src.python.server.crp_pool import CRPPoolRegistry
    else:
        from .crp_pool import CRPPoolRegistry
    pools = CRPPoolRegistry(pools_dir, pool_size=args.pool_size)
    protocol = HFIDAProtocol(templates=templates, hsm=hsm, pools=pools)
    for tid in hsm.terminal_ids():
        protocol.set_c2_history(tid, store.c2_history(tid))
    if args.port:
        try:
            transport: LoopbackTransport | SerialTransport = SerialTransport(
                args.port, baud=args.baud
            )
        except RuntimeError as exc:
            print(f"[ERROR] {exc}")
            return 2
        print(f"[INFO] serial mode on {args.port} @ {args.baud} baud")
    else:
        transport = LoopbackTransport()
        print("[INFO] loopback mode (simulated terminals; no hardware)")
    try:
        return repl(protocol, transport, args.measurements, store)
    finally:
        try:
            _flush_c2_state(protocol, store)
        finally:
            # Nested so the serial port is closed even if persistence
            # somehow raises despite the defensive _flush_c2_state.
            if isinstance(transport, SerialTransport):
                transport.close()


if __name__ == "__main__":
    sys.exit(main())
