"""HF-IDA protocol state machine and MAVLink v2 framing (server side).

HF-IDA (Hardware-Fingerprint Identification & Authentication) is the
mutual challenge/response protocol of the design doc "B line".  Message
ids start at 0x0090:

====== ================== ==========================================
id     name                direction
====== ================== ==========================================
0x0090 MSG_ACCESS_REQUEST  terminal -> server (carries C2)
0x0091 MSG_CHALLENGE       server -> terminal (4 x 8B seeds, 32B payload)
0x0092 MSG_RESPONSE_R1     terminal -> server (4 x 8B responses, 32B)
0x0093 MSG_RESULT          server -> terminal (verdict + R2)
0x0094 MSG_CONFIRM         terminal -> server (session confirmation)
0x0095 MSG_EXTRA_CHALLENGE server -> terminal (gray zone, 3 x 8B = 24B)
====== ================== ==========================================

Frame budget (design doc P1-R5): the project-imposed MAVLink payload cap
is 32 bytes (44-byte frames).  N_CHALLENGES is therefore 4 (4x8B = 32B,
frame = 10 + 32 + 2 = 44B).  For the same reason the terminal's
counter-challenge C2 travels inside MSG_ACCESS_REQUEST; putting C2 into
MSG_RESPONSE_R1 would need 40 payload bytes and break the identical
uplink budget.

Gray zone: when the aggregate score of the initial round lands between
the scaled thresholds, the server draws N_EXTRA_CHALLENGES (3) additional
seeds and scores the combined 7 responses with proportionally scaled
thresholds (see threshold.decide_scaled).

Framing follows MAVLink v2 (see external/c_library_v2): header minus STX
+ payload + CRC_EXTRA are fed into CRC-16/MCRF4XX (X.25) seeded with
0xFFFF.  The CRC_EXTRA values below are deterministic placeholders until
the hfida.xml dialect is generated in W3; both pack() and parse() use the
same table, so the loop is self-consistent.
"""

from __future__ import annotations

import struct
import threading
from dataclasses import dataclass, field
from typing import Any, Sequence

from .crp_pool import CRPPoolRegistry, PoolExhaustedError
from .hsm import HSM, SimulatedHSM
from .template_db import TemplateDB
from .threshold import DECISION_GRAY, DECISION_PASS, TAU_PASS, TAU_REJECT, decide_scaled

# ----------------------------------------------------------------------
# MAVLink v2 framing constants
# ----------------------------------------------------------------------
MAVLINK_V2_STX = 0xFD
_HEADER_LEN = 10  # STX + len + incompat + compat + seq + sysid + compid + msgid(3)
_CHECKSUM_LEN = 2

#: Project-imposed payload cap (44-byte frames, design doc P1-R5).
MAX_PAYLOAD = 32


def crc16_mcrf4xx(data: bytes, crc: int = 0xFFFF) -> int:
    """CRC-16/MCRF4XX (X.25) as used by MAVLink, matching checksum.h.

    Bit-exact port of crc_accumulate() from external/c_library_v2:
    feed bytes LSB-first, accumulate over the frame bytes, seed 0xFFFF.
    """
    for byte in data:
        tmp = (crc & 0xFF) ^ byte
        tmp = (tmp ^ (tmp << 4)) & 0xFF
        crc = ((crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 0xFFFF
    return crc


#: Result codes carried in MSG_RESULT.
RESULT_PASS = 0
RESULT_REJECT = 1
RESULT_ERROR = 2       # protocol/state error
RESULT_POOL_EMPTY = 3  # CRP pool exhausted: enrollment maintenance needed

#: Sentinel HD value meaning "not applicable".
HD_NONE = 0xFF

#: Session confirm codes carried in MSG_CONFIRM.
CONFIRM_OK = 0
CONFIRM_FAIL = 1


class ProtocolError(RuntimeError):
    """Raised on protocol state violations (unexpected message ordering)."""


@dataclass
class PendingAuth:
    """Book-keeping for one in-flight authentication session."""

    terminal_id: int
    state: str = "CHALLENGED"  # CHALLENGED -> GRAY -> SESSION/IDLE/BLOCKED
    seeds: list[bytes] = field(default_factory=list)
    extra_seeds: list[bytes] = field(default_factory=list)
    hd_sum: int = 0
    n_responses: int = 0
    c2: bytes | None = None
    last_decision: str = DECISION_GRAY

    def n_challenges(self) -> int:
        """Total number of challenges issued so far (initial + extra)."""
        return len(self.seeds) + len(self.extra_seeds)


class HFIDAProtocol:
    """Server-side HF-IDA protocol engine.

    Parameters
    ----------
    templates:
        Template database used for Hamming-distance matching.
    hsm:
        Station HSM backend producing R2 for mutual authentication.
    pools:
        Per-device CRP pool registry (one pool per terminal).
    system_id / component_id:
        MAVLink ids of the ground station auth component.
    """

    # Message ids (design doc, "protocol.py corrected version")
    MSG_ACCESS_REQUEST = 0x0090
    MSG_CHALLENGE = 0x0091
    MSG_RESPONSE_R1 = 0x0092
    MSG_RESULT = 0x0093
    MSG_CONFIRM = 0x0094
    MSG_EXTRA_CHALLENGE = 0x0095

    #: Challenges per authentication round.  4 (not 5): 4x8B = 32B fits the
    #: 44-byte MAVLink frame constraint; 5x8B = 40B would not (P1-R5).
    N_CHALLENGES = 4

    #: Extra challenges drawn when the first round lands in the gray zone.
    N_EXTRA_CHALLENGES = 3

    # Dual thresholds re-exported from threshold.py (single source of truth).
    TAU_PASS = TAU_PASS
    TAU_REJECT = TAU_REJECT

    #: PLACEHOLDER CRC_EXTRA values until the hfida.xml dialect is
    #: generated (W3).  Deterministic and distinct per message id; pack()
    #: and parse() share this table so the link stays self-consistent.
    _CRC_EXTRA: dict[int, int] = {
        MSG_ACCESS_REQUEST: 0x5A,
        MSG_CHALLENGE: 0x5B,
        MSG_RESPONSE_R1: 0x5C,
        MSG_RESULT: 0x5D,
        MSG_CONFIRM: 0x5E,
        MSG_EXTRA_CHALLENGE: 0x5F,
    }

    _MSG_NAMES: dict[int, str] = {
        MSG_ACCESS_REQUEST: "ACCESS_REQUEST",
        MSG_CHALLENGE: "CHALLENGE",
        MSG_RESPONSE_R1: "RESPONSE_R1",
        MSG_RESULT: "RESULT",
        MSG_CONFIRM: "CONFIRM",
        MSG_EXTRA_CHALLENGE: "EXTRA_CHALLENGE",
    }

    def __init__(
        self,
        templates: TemplateDB | None = None,
        hsm: HSM | None = None,
        pools: CRPPoolRegistry | None = None,
        system_id: int = 1,
        component_id: int = 2,
    ) -> None:
        self.templates = templates if templates is not None else TemplateDB()
        self.hsm: HSM = hsm if hsm is not None else SimulatedHSM()
        self.pools = pools if pools is not None else CRPPoolRegistry()
        self.system_id = int(system_id)
        self.component_id = int(component_id)
        # Single lock guards sequence counter, pending sessions, pools and
        # template reads (design doc P1-R7: thread-safe pool access).
        # RLock because handler methods hold it while calling pack(), which
        # takes the sequence counter under the same lock (re-entrant).
        # The CRP pools themselves are protected by their own plain
        # threading.Lock instances (see crp_pool.py).
        self.lock = threading.RLock()
        self._seq: int = 0
        self._pending: dict[int, PendingAuth] = {}

    # ------------------------------------------------------------------
    # Framing
    # ------------------------------------------------------------------
    def _next_seq(self) -> int:
        """Next 8-bit MAVLink sequence number (wraps at 256)."""
        seq = self._seq & 0xFF
        self._seq = (self._seq + 1) & 0xFF
        return seq

    def pack(self, msg_id: int, **kwargs: Any) -> bytes:
        """Serialize keyword arguments into a framed MAVLink v2 message.

        Recognized keyword sets per message id:

        ================ ====================== ==================
        message          payload                keywords
        ================ ====================== ==================
        ACCESS_REQUEST   16B "<II8s"            terminal_id, nonce,
                                                 c2 (8 bytes)
        CHALLENGE        32B (N_CHALLENGES      seeds (4 x 8B)
                          seeds, back to back)
        RESPONSE_R1      24B or 32B             r1s (3 or 4 x 8B)
        RESULT           10B "<BB8s"            result, hd, r2
        CONFIRM          5B "<IB"               status, terminal_id
        EXTRA_CHALLENGE  24B (N_EXTRA seeds)    seeds (3 x 8B)
        ================ ====================== ==================

        Returns
        -------
        bytes
            The complete frame: 10-byte header + payload + 2-byte
            CRC-16/MCRF4XX checksum.  MSG_CHALLENGE frames are exactly
            44 bytes.
        """
        payload = self._build_payload(msg_id, kwargs)
        if len(payload) > MAX_PAYLOAD:
            raise ValueError(
                f"payload for message {self._MSG_NAMES.get(msg_id, hex(msg_id))} "
                f"is {len(payload)} bytes, cap is {MAX_PAYLOAD}"
            )
        with self.lock:
            seq = self._next_seq()
        header = bytes(
            [
                MAVLINK_V2_STX,
                len(payload),
                0,  # incompat flags
                0,  # compat flags
                seq,
                self.system_id & 0xFF,
                self.component_id & 0xFF,
                msg_id & 0xFF,
                (msg_id >> 8) & 0xFF,
                (msg_id >> 16) & 0xFF,
            ]
        )
        crc = crc16_mcrf4xx(header[1:] + payload + bytes([self._crc_extra(msg_id)]))
        return header + payload + struct.pack("<H", crc)

    @classmethod
    def _crc_extra(cls, msg_id: int) -> int:
        """CRC_EXTRA byte for a message id (see class attribute notes)."""
        try:
            return cls._CRC_EXTRA[msg_id]
        except KeyError:
            raise ValueError(f"unknown message id {hex(msg_id)}") from None

    @classmethod
    def msg_name(cls, msg_id: int) -> str:
        """Human-readable name for a message id."""
        return cls._MSG_NAMES.get(msg_id, f"UNKNOWN_{msg_id:#06x}")

    # -- payload builders ------------------------------------------------
    @classmethod
    def _build_payload(cls, msg_id: int, kw: dict[str, Any]) -> bytes:
        """Turn pack() keyword arguments into raw payload bytes."""
        if msg_id == cls.MSG_ACCESS_REQUEST:
            c2 = cls._as_bytes("c2", kw["c2"], 8)
            return struct.pack(
                "<II8s",
                int(kw.get("terminal_id", 0)) & 0xFFFFFFFF,
                int(kw.get("nonce", 0)) & 0xFFFFFFFF,
                c2,
            )
        if msg_id in (cls.MSG_CHALLENGE, cls.MSG_EXTRA_CHALLENGE):
            seeds = cls._as_seed_list(kw["seeds"])
            expected = (
                cls.N_CHALLENGES
                if msg_id == cls.MSG_CHALLENGE
                else cls.N_EXTRA_CHALLENGES
            )
            if len(seeds) != expected:
                raise ValueError(
                    f"{cls.msg_name(msg_id)} expects {expected} seeds, "
                    f"got {len(seeds)}"
                )
            return b"".join(seeds)
        if msg_id == cls.MSG_RESPONSE_R1:
            return b"".join(cls._as_seed_list(kw["r1s"]))
        if msg_id == cls.MSG_RESULT:
            r2 = cls._as_bytes("r2", kw.get("r2", b"\x00" * 8), 8)
            return struct.pack(
                "<BB8s", int(kw.get("result", 0)) & 0xFF,
                int(kw.get("hd", HD_NONE)) & 0xFF, r2,
            )
        if msg_id == cls.MSG_CONFIRM:
            return struct.pack(
                "<IB",
                int(kw.get("terminal_id", 0)) & 0xFFFFFFFF,
                int(kw.get("status", 0)) & 0xFF,
            )
        raise ValueError(f"unknown message id {hex(msg_id)}")

    @staticmethod
    def _as_bytes(name: str, value: Any, length: int) -> bytes:
        """Validate that value is a bytes object of exactly length bytes."""
        if not isinstance(value, (bytes, bytearray)):
            raise TypeError(f"{name} must be bytes, got {type(value).__name__}")
        if len(value) != length:
            raise ValueError(f"{name} must be {length} bytes, got {len(value)}")
        return bytes(value)

    @classmethod
    def _as_seed_list(cls, value: Any) -> list[bytes]:
        """Validate a sequence of 8-byte values (seeds or responses)."""
        if isinstance(value, (bytes, bytearray)):
            raise TypeError("expected a sequence of 8-byte items, got raw bytes")
        items = list(value)
        for item in items:
            cls._as_bytes("seed/r1", item, 8)
        return items

    # -- payload parsers ---------------------------------------------------
    @classmethod
    def parse(cls, frame: bytes) -> tuple[int, dict[str, Any]]:
        """Parse and CRC-check a MAVLink v2 HF-IDA frame.

        Parameters
        ----------
        frame:
            Raw bytes as produced by pack().

        Returns
        -------
        tuple[int, dict]
            Message id plus a field dict mirroring the pack() keywords.

        Raises
        ------
        ValueError
            On truncated frames, bad magic, length mismatch or CRC errors.
        """
        if not isinstance(frame, (bytes, bytearray)):
            raise TypeError("frame must be bytes")
        frame = bytes(frame)
        if len(frame) < _HEADER_LEN + _CHECKSUM_LEN:
            raise ValueError(f"frame too short: {len(frame)} bytes")
        if frame[0] != MAVLINK_V2_STX:
            raise ValueError(f"bad magic byte: {frame[0]:#04x}")
        length = frame[1]
        msg_id = frame[7] | (frame[8] << 8) | (frame[9] << 16)
        expected_len = _HEADER_LEN + length + _CHECKSUM_LEN
        if len(frame) != expected_len:
            raise ValueError(
                f"length mismatch: header says {expected_len}, got {len(frame)}"
            )
        payload = frame[_HEADER_LEN : _HEADER_LEN + length]
        (crc,) = struct.unpack("<H", frame[expected_len - 2 : expected_len])
        calc = crc16_mcrf4xx(frame[1 : _HEADER_LEN] + payload + bytes([cls._crc_extra(msg_id)]))
        if crc != calc:
            raise ValueError(f"CRC mismatch: got {crc:#06x}, computed {calc:#06x}")
        return msg_id, cls._parse_payload(msg_id, payload)

    @classmethod
    def _parse_payload(cls, msg_id: int, payload: bytes) -> dict[str, Any]:
        """Decode payload bytes into named fields."""
        if msg_id == cls.MSG_ACCESS_REQUEST:
            terminal_id, nonce = struct.unpack_from("<II", payload, 0)
            c2 = payload[8:16]
            return {"terminal_id": terminal_id, "nonce": nonce, "c2": c2}
        if msg_id in (cls.MSG_CHALLENGE, cls.MSG_EXTRA_CHALLENGE):
            if len(payload) % 8:
                raise ValueError("seed payload not a multiple of 8 bytes")
            return {"seeds": [payload[i : i + 8] for i in range(0, len(payload), 8)]}
        if msg_id == cls.MSG_RESPONSE_R1:
            if len(payload) % 8:
                raise ValueError("response payload not a multiple of 8 bytes")
            return {"r1s": [payload[i : i + 8] for i in range(0, len(payload), 8)]}
        if msg_id == cls.MSG_RESULT:
            result, hd = struct.unpack_from("<BB", payload, 0)
            return {"result": result, "hd": hd, "r2": payload[2:10]}
        if msg_id == cls.MSG_CONFIRM:
            terminal_id, status = struct.unpack("<IB", payload)
            return {"terminal_id": terminal_id, "status": status}
        raise ValueError(f"unknown message id {hex(msg_id)}")

    # ------------------------------------------------------------------
    # Protocol state machine
    # ------------------------------------------------------------------
    def on_access_request(
        self, terminal_id: int, c2: bytes | None = None, nonce: int = 0
    ) -> bytes:
        """Handle MSG_ACCESS_REQUEST: issue N_CHALLENGES fresh seeds.

        Also serves as the server-initiated entry point (REPL "auth"
        command and unit tests) via its alias start_auth().
        """
        tid = int(terminal_id)
        with self.lock:
            if not self.templates.has_terminal(tid):
                return self.pack(
                    self.MSG_RESULT, result=RESULT_ERROR, hd=HD_NONE
                )
            try:
                seeds = self.pools.get(tid).draw(self.N_CHALLENGES)
            except PoolExhaustedError:
                return self.pack(
                    self.MSG_RESULT, result=RESULT_POOL_EMPTY, hd=HD_NONE
                )
            session = PendingAuth(terminal_id=tid, seeds=list(seeds), c2=c2)
            self._pending[tid] = session
            return self.pack(self.MSG_CHALLENGE, seeds=seeds)

    #: Alias for server-initiated authentication flows.
    start_auth = on_access_request

    def on_response(
        self, terminal_id: int, r1s: Sequence[bytes], c2: bytes | None = None
    ) -> bytes:
        """Handle MSG_RESPONSE_R1: score the initial round of responses.

        The aggregate score is the sum of per-challenge Hamming distances
        checked against thresholds scaled by the number of responses
        (threshold.decide_scaled).  Outcomes:

        * PASS   -> MSG_RESULT with R2 from the HSM (mutual auth)
        * REJECT -> MSG_RESULT with a reject code
        * GRAY   -> MSG_EXTRA_CHALLENGE carrying 3 fresh seeds
        """
        tid = int(terminal_id)
        with self.lock:
            session = self._require_session(tid, "CHALLENGED")
            if len(r1s) != len(session.seeds):
                raise ProtocolError(
                    f"expected {len(session.seeds)} responses, got {len(r1s)}"
                )
            hds = self.templates.hamming_distances(tid, session.seeds, list(r1s))
            session.hd_sum = sum(hds)
            session.n_responses = len(hds)
            if c2 is not None:
                session.c2 = c2
            decision = decide_scaled(session.hd_sum, session.n_responses)
            session.last_decision = decision
            if decision == DECISION_PASS:
                return self._finish_pass(session)
            if decision != DECISION_GRAY:
                return self._finish_reject(session)
            # Gray zone: draw extra challenges for aggregate re-scoring.
            try:
                extra = self.pools.get(tid).draw(self.N_EXTRA_CHALLENGES)
            except PoolExhaustedError:
                session.state = "BLOCKED"
                return self.pack(
                    self.MSG_RESULT, result=RESULT_POOL_EMPTY, hd=HD_NONE
                )
            session.extra_seeds = list(extra)
            session.state = "GRAY"
            return self.pack(self.MSG_EXTRA_CHALLENGE, seeds=extra)

    def on_extra_response(
        self, terminal_id: int, r1s: Sequence[bytes], c2: bytes | None = None
    ) -> bytes:
        """Handle the gray-zone re-test: aggregate scoring over all rounds.

        Combines the pending HD sum of the initial round with the HDs of
        the N_EXTRA_CHALLENGES extra responses and applies the scaled
        thresholds over the total of 7 responses (P1-6 fix).
        """
        tid = int(terminal_id)
        with self.lock:
            session = self._require_session(tid, "GRAY")
            if len(r1s) != len(session.extra_seeds):
                raise ProtocolError(
                    f"expected {len(session.extra_seeds)} extra responses, "
                    f"got {len(r1s)}"
                )
            hds = self.templates.hamming_distances(
                tid, session.extra_seeds, list(r1s)
            )
            session.hd_sum += sum(hds)
            session.n_responses += len(hds)
            if c2 is not None:
                session.c2 = c2
            decision = decide_scaled(session.hd_sum, session.n_responses)
            session.last_decision = decision
            if decision == DECISION_PASS:
                return self._finish_pass(session)
            return self._finish_reject(session)

    def on_confirm(self, terminal_id: int, status: int) -> bytes | None:
        """Handle MSG_CONFIRM: terminal acknowledged the verdict.

        CONFIRM_OK keeps the session alive (state SESSION); anything else
        closes it.  Returns None because the protocol defines no server
        reply after confirmation in W2.
        """
        tid = int(terminal_id)
        with self.lock:
            session = self._pending.get(tid)
            if session is None:
                raise ProtocolError(f"no pending session for terminal {tid}")
            session.state = "SESSION" if status == CONFIRM_OK else "IDLE"
            return None

    # -- internal helpers (call with self.lock held) ---------------------
    def _require_session(self, tid: int, expected_state: str) -> PendingAuth:
        """Fetch the pending session and check its state."""
        session = self._pending.get(tid)
        if session is None:
            raise ProtocolError(f"no pending authentication for terminal {tid}")
        if session.state != expected_state:
            raise ProtocolError(
                f"terminal {tid}: expected state {expected_state}, "
                f"session is {session.state}"
            )
        return session

    def _finish_pass(self, session: PendingAuth) -> bytes:
        """Complete a successful authentication: fetch R2 from the HSM."""
        c2 = session.c2 if session.c2 is not None else b"\x00" * 8
        r2 = self.hsm.respond(c2)
        session.state = "SESSION"
        return self.pack(
            self.MSG_RESULT,
            result=RESULT_PASS,
            hd=min(session.hd_sum, 0xFE),
            r2=r2,
        )

    def _finish_reject(self, session: PendingAuth) -> bytes:
        """Complete a failed authentication."""
        session.state = "BLOCKED"
        return self.pack(
            self.MSG_RESULT,
            result=RESULT_REJECT,
            hd=min(session.hd_sum, 0xFE),
        )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        """JSON-serializable snapshot of sessions and CRP pools."""
        with self.lock:
            sessions = [
                {
                    "terminal_id": s.terminal_id,
                    "state": s.state,
                    "challenges_issued": s.n_challenges(),
                    "responses_scored": s.n_responses,
                    "hd_sum": s.hd_sum,
                    "last_decision": s.last_decision,
                }
                for s in sorted(self._pending.values(), key=lambda x: x.terminal_id)
            ]
        return {"sessions": sessions, "pools": self.pools.status()}
