"""W3 serial receive loop: byte stream -> frames -> HFIDAProtocol dispatch.

This closes the last PC-side gap of verification point 3 (HANDOFF item
"PC 串口通信循环"): the server now *listens* on the wire instead of
doing one-shot polling from the REPL.  The terminal-initiated flow
follows protocol_contract.md §5::

    terminal                                server (this loop)
      |-- ACCESS_REQUEST(tid, nonce, C2) -->|  on_access_request
      |<--------------- CHALLENGE(4 seeds) -|
      |-- RESPONSE_R1(4 x 8B) ------------->|  on_response
      |<------ RESULT / EXTRA_CHALLENGE ----|
      |-- RESPONSE_R1(3 x 8B) ------------->|  on_extra_response
      |<--------------- RESULT -------------|
      |-- CONFIRM(tid, status) ------------>|  on_confirm  <- W3 wiring

Design notes
------------
* FrameSync mirrors the RTL frame_parser discipline (contract §6.1):
  scan for STX, honor LEN, CRC-check, resync on garbage -- radio noise
  must never wedge the loop.
* RESPONSE_R1 frames carry no terminal id (32-byte payload budget,
  protocol.py header note), so the dispatcher attributes them to the
  single pending CHALLENGED/GRAY session.  Concurrent multi-terminal
  authentication on ONE link is reported as ambiguous instead of
  silently misrouted (multi-terminal demos use one link per terminal).
* on_confirm finally has a runtime consumer here (A1 review note):
  CONFIRM_OK counts a completed mutual authentication -- the terminal
  has verified R2 = Speck64/96(K_term, C2) against its own key.
* Handler exceptions never kill the loop (silent-failure review B):
  protocol-state violations are answered on the wire with a RESULT_ERROR
  frame so the terminal leaves its wait state instead of retrying into
  a permanent mutual wait (contract §5: 2 s per wait state); unexpected
  internal errors are recorded as events and also answered with
  RESULT_ERROR.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Callable

from .protocol import (
    CONFIRM_OK,
    HD_NONE,
    MAVLINK_V2_STX,
    MAX_PAYLOAD,
    RESULT_ERROR,
    HFIDAProtocol,
    ProtocolError,
)

#: MAVLink v2 frame overhead on the wire (header + CRC).
_FRAME_OVERHEAD = 12

#: Hard cap on the resync buffer; a healthy stream never gets near it.
_SYNC_BUFFER_CAP = 1024


def _default_event_printer(message: str) -> None:
    import time as _time
    print(f"[WIRE {_time.strftime('%H:%M:%S')}."
          f"{int(_time.monotonic() * 1000) % 1000:03d}] {message}")


class FrameSync:
    """Incremental byte-stream splitter producing complete frames.

    Feed arbitarily chunked bytes (UART grains, TCP segments, test
    fragments) via feed(); get back every complete, CRC-valid frame.
    Garbage between frames is skipped by rescanning for the next STX,
    matching the RTL parser's noise tolerance.
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes | bytearray) -> list[bytes]:
        """Absorb incoming bytes; return the frames completed by them."""
        self._buf += bytes(data)
        frames: list[bytes] = []
        while True:
            # Resync guard: bound memory on a hostile/noisy stream.
            if len(self._buf) > _SYNC_BUFFER_CAP:
                # Keep the newest CAP bytes (a frame in flight may live
                # there); review A-P3 caught the off-by-CAP trim.
                del self._buf[: len(self._buf) - _SYNC_BUFFER_CAP]
            start = self._buf.find(bytes([MAVLINK_V2_STX]))
            if start < 0:
                self._buf.clear()
                break
            if start > 0:
                del self._buf[:start]
            if len(self._buf) < 2:
                break  # header cut between STX and LEN
            length = self._buf[1]
            if length > MAX_PAYLOAD:
                # LEN cannot be valid -> this STX is noise, skip it.
                del self._buf[:1]
                continue
            total = _FRAME_OVERHEAD + length
            if len(self._buf) < total:
                break  # frame still arriving
            candidate = bytes(self._buf[:total])
            try:
                HFIDAProtocol.parse(candidate)
            except ValueError:
                # Bad CRC/magic at this STX -> advance one byte and rescan.
                del self._buf[:1]
                continue
            frames.append(candidate)
            del self._buf[:total]
        return frames


class SerialServer:
    """Dispatch wire frames to the HFIDAProtocol state machine.

    pump(data) is the pure testable core: bytes in, reply frames out,
    every decision recorded as a human-readable event.
    """

    def __init__(
        self,
        protocol: HFIDAProtocol,
        on_event: Callable[[str], None] | None = None,
    ) -> None:
        self.protocol = protocol
        self.sync = FrameSync()
        #: Bounded audit trail: serve_forever is a long-running loop and
        #: events have no consumer there (review B-P2) -- cap the memory.
        self.events: deque[str] = deque(maxlen=1000)
        #: CONFIRM_OK count == completed mutual authentications.
        self.confirmations = 0
        #: CONFIRM with a non-OK status (terminal rejected R2).
        self.rejected_confirms = 0
        self._on_event = on_event if on_event is not None else _default_event_printer

    # -- internals ---------------------------------------------------------
    def _emit(self, message: str) -> None:
        self.events.append(message)
        self._on_event(message)

    @staticmethod
    def _reply_name(reply: bytes) -> str:
        return HFIDAProtocol.msg_name(HFIDAProtocol.parse(reply)[0])

    def handle_frame(self, frame: bytes) -> bytes | None:
        """Route one complete frame; return the reply frame or None."""
        self._emit(f"RXRAW {frame.hex()}")  # DIAGNOSTIC (bring-up)
        msg_id, fields = HFIDAProtocol.parse(frame)
        if msg_id == HFIDAProtocol.MSG_ACCESS_REQUEST:
            return self._handle_access_request(fields)
        if msg_id == HFIDAProtocol.MSG_RESPONSE_R1:
            return self._handle_response(fields["r1s"])
        if msg_id == HFIDAProtocol.MSG_CONFIRM:
            return self._handle_confirm(fields)
        self._emit(
            f"ignored {HFIDAProtocol.msg_name(msg_id)} "
            f"(not expected from a terminal)"
        )
        return None

    def _handle_access_request(self, fields: dict[str, Any]) -> bytes:
        tid = int(fields["terminal_id"])
        c2 = fields["c2"]
        reply = self.protocol.on_access_request(
            tid, c2=c2, nonce=int(fields["nonce"])
        )
        self._emit(
            f"ACCESS_REQUEST tid={tid} nonce={fields['nonce']:#010x} "
            f"c2={c2.hex()} -> {self._reply_name(reply)}"
        )
        return reply

    def _handle_response(self, r1s: list[bytes]) -> bytes | None:
        """RESPONSE_R1 carries no tid: attribute it to the pending session."""
        sessions = {
            int(s["terminal_id"]): s["state"]
            for s in self.protocol.status()["sessions"]
        }
        active = sorted(
            tid for tid, state in sessions.items() if state in ("CHALLENGED", "GRAY")
        )
        if not active:
            self._emit("RESPONSE_R1 without pending challenge -- dropped")
            return None
        if len(active) > 1:
            self._emit(
                f"AMBIGUOUS RESPONSE_R1: sessions {active} share this link "
                f"and the frame carries no terminal id -- dropped"
            )
            return None
        tid = active[0]
        state = sessions[tid]
        handler = (
            self.protocol.on_response
            if state == "CHALLENGED"
            else self.protocol.on_extra_response
        )
        reply = handler(tid, r1s)
        self._emit(
            f"RESPONSE_R1 tid={tid} x{len(r1s)} ({state}) "
            f"-> {self._reply_name(reply)}"
        )
        return reply

    def _handle_confirm(self, fields: dict[str, Any]) -> bytes | None:
        tid = int(fields["terminal_id"])
        status = int(fields["status"])
        self.protocol.on_confirm(tid, status)
        if status == CONFIRM_OK:
            self.confirmations += 1
            self._emit(
                f"CONFIRM tid={tid} OK -- mutual authentication complete "
                f"(terminal verified R2 = Speck(K_term, C2))"
            )
        else:
            self.rejected_confirms += 1
            self._emit(
                f"CONFIRM tid={tid} status={status} -- terminal rejected "
                f"R2, session closed"
            )
        return None

    def _error_frame(self) -> bytes:
        """RESULT_ERROR frame for wire-visible failures (review B-P2)."""
        return self.protocol.pack(
            HFIDAProtocol.MSG_RESULT, result=RESULT_ERROR, hd=HD_NONE
        )

    def pump(self, data: bytes | bytearray) -> list[bytes]:
        """Feed raw link bytes; return the reply frames for them."""
        replies: list[bytes] = []
        for frame in self.sync.feed(data):
            try:
                reply = self.handle_frame(frame)
            except ProtocolError as exc:
                # Answer on the wire: the terminal would otherwise retry
                # the same malformed exchange every 2 s forever.
                self._emit(f"PROTOCOL ERROR: {exc} -> RESULT_ERROR frame")
                replies.append(self._error_frame())
                continue
            except Exception as exc:  # noqa: BLE001 -- loop must survive
                self._emit(
                    f"INTERNAL {type(exc).__name__}: {exc} "
                    f"-> RESULT_ERROR frame (loop survived)"
                )
                replies.append(self._error_frame())
                continue
            if reply is not None:
                replies.append(reply)
        return replies


def serve_forever(
    io: Any,
    protocol: HFIDAProtocol,
    on_event: Callable[[str], None] | None = None,
    stop: Callable[[], bool] | None = None,
    read_size: int = 256,
) -> int:
    """Blocking receive loop over a pyserial-like object.

    io needs .read(n) (timeout-based, returns b'' when idle), .write(),
    .flush() and optionally .in_waiting.  Ctrl-C returns 0 so the REPL
    'serve' command can drop back to the prompt; a dead link (write
    OSError) returns 1 instead of silently killing the process (review
    B-P3).  Partial writes are retried, never silently truncated.
    """
    server = SerialServer(protocol, on_event)

    def _write_all(frame: bytes) -> None:
        view = memoryview(frame)
        while view:
            written = io.write(view)
            if not written:  # file-likes return None on "all accepted"
                break
            view = view[int(written):]
        io.flush()

    try:
        while True:
            if stop is not None and stop():
                return 0
            waiting = int(getattr(io, "in_waiting", 0))
            # Idle reads ask for ONE byte, not read_size: a blocking read(N>1)
            # with a multi-second timeout only returns at the timeout boundary
            # even when a short frame (R1 = 44 B) is already buffered -- which
            # stalled RESULT ~3 s behind R1 and past the board's 2 s window
            # (board B bring-up 2026-10-27, serve 0/10 vs probe 3/3).  With
            # chunk=1 the first byte wakes the loop and in_waiting drains the
            # rest on the next spin.
            chunk = max(1, min(waiting or 1, read_size))
            data = io.read(chunk)
            if not data:
                continue
            for reply in server.pump(data):
                server._emit(f"TXRAW {reply.hex()}")  # DIAGNOSTIC (bring-up)
                try:
                    _write_all(reply)
                except OSError as exc:
                    server._emit(
                        f"LINK WRITE FAILED: {type(exc).__name__}: {exc} "
                        f"-- leaving receive loop"
                    )
                    return 1
    except KeyboardInterrupt:
        return 0
