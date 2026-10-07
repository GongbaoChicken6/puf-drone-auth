"""Hardware Security Module interface for the ground-station server.

Architecture (design doc section 0.5): the base station authenticates
itself *back* to the drone.  When a terminal passes the PUF check, the
server forwards the terminal's counter-challenge C2 to the station HSM
(PUF instance 0 on the ZC702 demo board) which answers with an 8-byte
response R2; the terminal verifies R2 against the station template it
stored read-only during enrollment.

W2 scope: :class:SimulatedHSM provides random-but-deterministic software
responses (keyed HMAC-SHA256 PRF) so the full protocol can be exercised
before hardware exists.  :class:SerialHSM is the UART transport that will
talk to the real instance-0 hardware later; it is intentionally minimal
and is only activated when a serial port is configured.

A1 (Speck64/96): :class:`SpeckHSM` replaces the HMAC PRF as the R2
generator.  R2 = Speck64/96(K_terminal, C2) with a per-terminal 12-byte
key, matching the RTL core (src/rtl/common/speck64_96.v) bit-for-bit so
the drone terminal verifies R2 by recomputing the cipher over its own
stored device key.  The 8 C2 bytes feed the cipher exactly as they
travel on the wire and the ciphertext serializes y before x (the NSA
convention frozen in docs/protocol_contract.md).  SimulatedHSM is kept
for the legacy station-PUF enroll() path.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from pathlib import Path
from typing import Any

try:  # package mode (src.python.server.hsm)
    from ..common.speck import Speck6496
except ImportError:  # pragma: no cover - direct script sys.path bootstrap
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from src.python.common.speck import Speck6496

#: Response length in bytes (64-bit R2, design spec data-path table).
RESPONSE_BYTES = 8

#: Challenge seed length in bytes (64-bit).
SEED_BYTES = 8

#: Speck64/96 device-key length in bytes (96-bit key = PUF stable-bit budget).
DEVICE_KEY_BYTES = 12

_HSM_SCHEMA = "puf-drone-auth/hsm-secret/v1"


def _prf(secret: bytes, data: bytes, out_len: int = RESPONSE_BYTES) -> bytes:
    """Keyed deterministic PRF: HMAC-SHA256(secret, data) truncated to out_len."""
    return hmac.new(secret, data, hashlib.sha256).digest()[:out_len]


class HSM:
    """Abstract base for station-side HSM backends."""

    def respond(self, c2: bytes, terminal_id: int | None = None) -> bytes:
        """Answer a terminal counter-challenge C2 with an 8-byte R2.

        terminal_id lets key-per-terminal backends (:class:`SpeckHSM`)
        select the matching device key; single-key backends
        (SimulatedHSM/SerialHSM) ignore it.  CONTRACT (types review
        TYPES-01): a per-terminal backend MUST treat terminal_id=None as
        a missing precondition and raise KeyError; callers on the
        authentication path always supply a concrete terminal id, so
        "None is accepted by the signature" only means "meaningless for
        single-key backends", never "valid for keyed ones".
        """
        raise NotImplementedError

    def enroll(self, n_challenges: int = 100) -> dict[bytes, bytes]:
        """Collect n_challenges CRP pairs from the HSM's own PUF instance."""
        raise NotImplementedError


class SimulatedHSM(HSM):
    """Software simulation of the station HSM (W2 deliverable).

    The instance secret is drawn once from the OS CSPRNG; afterwards every
    response is a deterministic keyed hash of the challenge.  "Random but
    deterministic": responses look random and are reproducible for the
    lifetime of the secret, which can be persisted to JSON and reloaded.

    Parameters
    ----------
    secret:
        32-byte key.  When omitted a fresh secret is generated with
        secrets.token_bytes (never the "random" module).
    """

    def __init__(self, secret: bytes | None = None) -> None:
        if secret is not None and len(secret) < 16:
            raise ValueError("secret must be at least 16 bytes")
        self.secret = secret if secret is not None else secrets.token_bytes(32)

    # -- HSM interface ---------------------------------------------------
    def respond(self, c2: bytes, terminal_id: int | None = None) -> bytes:
        """Return the deterministic 8-byte R2 for counter-challenge c2.

        terminal_id is accepted for interface symmetry and ignored: this
        legacy backend serves every terminal from one instance secret.
        """
        if not isinstance(c2, (bytes, bytearray)) or len(c2) == 0:
            raise ValueError("c2 must be a non-empty bytes object")
        return _prf(self.secret, bytes(c2))

    def enroll(self, n_challenges: int = 100) -> dict[bytes, bytes]:
        """Generate n_challenges CRP pairs {seed: response} from the PRF."""
        if n_challenges < 1:
            raise ValueError("n_challenges must be >= 1")
        pairs: dict[bytes, bytes] = {}
        rng = secrets.SystemRandom()
        while len(pairs) < n_challenges:
            seed = rng.randbytes(SEED_BYTES)
            if seed in pairs:
                continue
            pairs[seed] = _prf(self.secret, seed)
        return pairs

    # -- secret persistence ------------------------------------------------
    def save_secret(self, path: str | Path) -> None:
        """Persist the secret to JSON so R2 values survive a restart."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '{"schema": "%s", "secret_hex": "%s"}'
            % (_HSM_SCHEMA, self.secret.hex()),
            encoding="utf-8",
        )

    @classmethod
    def load_secret(cls, path: str | Path) -> "SimulatedHSM":
        """Rebuild an instance from a previously persisted secret file."""
        raw = Path(path).read_text(encoding="utf-8")
        import json

        data = json.loads(raw)
        return cls(secret=bytes.fromhex(data["secret_hex"]))


class SpeckHSM(HSM):
    """Station HSM computing R2 = Speck64/96(K_terminal, C2) (A1).

    Replaces the W2 HMAC-SHA256 PRF: the drone terminal now verifies R2
    by running the same cipher it carries in RTL (speck64_96.v) over its
    stored device key, which makes the mutual-authentication step
    symmetric and hardware-checkable.

    Keys are per-terminal (12 bytes, one Speck6496 instance each).  The
    terminal enrolled with key K expects R2 == Speck(K, C2) for the
    counter-challenge C2 it sent, so the server must register the same
    key the terminal holds (via DeviceKeyStore persistence or the REPL
    "setkey" command in main.py).

    Byte order matches terminal_fsm.v bit-for-bit: the 8 C2 bytes feed
    the cipher as transmitted (bytes[0:4] -> y word, bytes[4:8] -> x
    word, little-endian) and the ciphertext serializes y before x.  The
    W3 demo values are key 0001020308090a0b10111213 (RTL parameter
    96'h13121110_0b0a0908_03020100), first-auth C2 a1..a8 and R2
    7b45b0545e59aa94.
    """

    def __init__(self, keys: dict[int, bytes] | None = None) -> None:
        self._keys: dict[int, bytes] = {}
        self._ciphers: dict[int, Speck6496] = {}
        for tid, key in (keys or {}).items():
            self.set_key(tid, key)

    # -- key management ---------------------------------------------------
    def set_key(self, terminal_id: int, key: bytes) -> None:
        """Install (or replace) one terminal's 12-byte Speck device key."""
        if not isinstance(key, (bytes, bytearray)) or len(key) != DEVICE_KEY_BYTES:
            got = len(key) if isinstance(key, (bytes, bytearray)) else type(key).__name__
            raise ValueError(f"device key must be {DEVICE_KEY_BYTES} bytes, got {got}")
        tid = int(terminal_id)
        self._keys[tid] = bytes(key)
        self._ciphers[tid] = Speck6496(bytes(key))

    def has_key(self, terminal_id: int) -> bool:
        """True when this terminal's device key has been registered."""
        return int(terminal_id) in self._keys

    def terminal_ids(self) -> list[int]:
        """Sorted ids of every terminal holding a registered key."""
        return sorted(self._keys)

    # -- HSM interface ---------------------------------------------------
    def respond(self, c2: bytes, terminal_id: int | None = None) -> bytes:
        """Return R2 = Speck(K_terminal, C2) (8 bytes).

        Raises
        ------
        KeyError
            When terminal_id is missing or holds no registered key: an
            unkeyed terminal must never be served a bogus R2.
        """
        if not isinstance(c2, (bytes, bytearray)) or len(c2) != RESPONSE_BYTES:
            raise ValueError(f"c2 must be exactly {RESPONSE_BYTES} bytes")
        if terminal_id is None:
            raise KeyError("SpeckHSM needs terminal_id for per-terminal key selection")
        cipher = self._ciphers.get(int(terminal_id))
        if cipher is None:
            raise KeyError(
                f"terminal {terminal_id} has no Speck device key "
                f"(register one via DeviceKeyStore or SpeckHSM.set_key)"
            )
        return cipher.encrypt(bytes(c2))

    def enroll(self, n_challenges: int = 100) -> dict[bytes, bytes]:
        """Not supported: Speck verification is symmetric re-computation.

        The terminal checks R2 by encrypting C2 with its own key, so no
        station-side CRP enrollment is involved.  Station-PUF enrollment
        remains a SimulatedHSM/SerialHSM (W2/W4) feature.
        """
        raise NotImplementedError(
            "SpeckHSM.enroll: R2 verification is symmetric Speck re-computation"
        )


class SerialHSM(HSM):
    """UART transport to the real station HSM (ZC702 PUF instance 0).

    Wire protocol matches the W2 data path: the PC writes the raw 8-byte
    challenge and reads back the raw 8-byte response.  This backend is a
    thin placeholder for the hardware integration week (W3+); pyserial is
    imported lazily so the rest of the package never requires it.
    """

    def __init__(self, port: str, baud: int = 115200, timeout: float = 1.0) -> None:
        try:
            import serial  # pyserial
        except ImportError as exc:  # pragma: no cover - env dependent
            raise RuntimeError(
                "pyserial is required for SerialHSM: pip install pyserial"
            ) from exc
        self.serial = serial.Serial(port, baud, timeout=timeout)
        self.port = port
        self.baud = baud

    def respond(self, c2: bytes, terminal_id: int | None = None) -> bytes:
        """Send C2 to the HSM over UART and read the 8-byte R2 back.

        terminal_id is accepted for interface symmetry and ignored: the
        hardware instance holds exactly one device key.
        """
        if len(c2) != SEED_BYTES:
            raise ValueError(f"c2 must be {SEED_BYTES} bytes, got {len(c2)}")
        self.serial.reset_input_buffer()
        self.serial.write(bytes(c2))
        self.serial.flush()
        r2 = self.serial.read(RESPONSE_BYTES)
        if len(r2) != RESPONSE_BYTES:
            raise TimeoutError(f"HSM timeout on {self.port}: got {len(r2)} bytes")
        return bytes(r2)

    def enroll(self, n_challenges: int = 100) -> dict[bytes, bytes]:
        """Collect CRP pairs from the hardware instance, one frame each."""
        pairs: dict[bytes, bytes] = {}
        rng = secrets.SystemRandom()
        while len(pairs) < n_challenges:
            seed = rng.randbytes(SEED_BYTES)
            if seed in pairs:
                continue
            pairs[seed] = self.respond(seed)
        return pairs

    def close(self) -> None:
        """Close the underlying serial port."""
        self.serial.close()

    def __del__(self) -> None:  # best-effort cleanup
        try:
            self.close()
        except Exception:
            pass


def hsm_status(hsm: HSM) -> dict[str, Any]:
    """Small JSON-serializable description of an HSM backend."""
    if isinstance(hsm, SpeckHSM):
        return {
            "backend": "speck64/96",
            "terminals_with_keys": len(hsm.terminal_ids()),
        }
    if isinstance(hsm, SimulatedHSM):
        return {"backend": "simulated", "secret_bits": len(hsm.secret) * 8}
    if isinstance(hsm, SerialHSM):
        return {"backend": "serial", "port": hsm.port, "baud": hsm.baud}
    return {"backend": type(hsm).__name__}
