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
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from pathlib import Path
from typing import Any

#: Response length in bytes (64-bit R2, design spec data-path table).
RESPONSE_BYTES = 8

#: Challenge seed length in bytes (64-bit).
SEED_BYTES = 8

_HSM_SCHEMA = "puf-drone-auth/hsm-secret/v1"


def _prf(secret: bytes, data: bytes, out_len: int = RESPONSE_BYTES) -> bytes:
    """Keyed deterministic PRF: HMAC-SHA256(secret, data) truncated to out_len."""
    return hmac.new(secret, data, hashlib.sha256).digest()[:out_len]


class HSM:
    """Abstract base for station-side HSM backends."""

    def respond(self, c2: bytes) -> bytes:
        """Answer a terminal counter-challenge C2 with an 8-byte R2."""
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
    def respond(self, c2: bytes) -> bytes:
        """Return the deterministic 8-byte R2 for counter-challenge c2."""
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

    def respond(self, c2: bytes) -> bytes:
        """Send C2 to the HSM over UART and read the 8-byte R2 back."""
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
    if isinstance(hsm, SimulatedHSM):
        return {"backend": "simulated", "secret_bits": len(hsm.secret) * 8}
    if isinstance(hsm, SerialHSM):
        return {"backend": "serial", "port": hsm.port, "baud": hsm.baud}
    return {"backend": type(hsm).__name__}
