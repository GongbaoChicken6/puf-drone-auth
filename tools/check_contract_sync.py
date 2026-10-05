#!/usr/bin/env python3
"""
check_contract_sync.py -- protocol contract drift detector (review B-F6 fix)

Single source of truth = src/python/server/protocol.py.
Regenerates all golden frames from protocol.py and compares them against the
hex vectors in docs/protocol_contract.md section 4. Any one-sided edit fails.

Usage:
    python tools/check_contract_sync.py    # exit 1 on drift
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.python.server.protocol import HFIDAProtocol as H  # noqa: E402


def build_frames():
    """Regenerate the 6 golden frames with the exact inputs from contract S4."""
    p = H(system_id=1, component_id=2)
    p._seq = 0x42
    frames = {}
    frames["ACCESS_REQUEST"] = p.pack(H.MSG_ACCESS_REQUEST, terminal_id=42,
                                      nonce=0xDEADBEEF, c2=bytes(range(8)))
    seeds = [bytes([0xA0 + i] + [i] * 7) for i in range(4)]
    frames["CHALLENGE"] = p.pack(H.MSG_CHALLENGE, seeds=seeds)
    r1s = [bytes([0xB0 + i] + [i] * 7) for i in range(4)]
    frames["RESPONSE_R1"] = p.pack(H.MSG_RESPONSE_R1, r1s=r1s)
    frames["RESULT"] = p.pack(H.MSG_RESULT, result=0, hd=5,
                              r2=bytes([0xC0 + i for i in range(8)]))
    frames["CONFIRM"] = p.pack(H.MSG_CONFIRM, terminal_id=42, status=1)
    es = [bytes([0xD0 + i] + [i] * 7) for i in range(3)]
    frames["EXTRA_CHALLENGE"] = p.pack(H.MSG_EXTRA_CHALLENGE, seeds=es)
    return frames


def contract_vectors():
    """Parse S4 of the contract: '# NAME ... (NB)' header + hex body lines."""
    md = (ROOT / "docs" / "protocol_contract.md").read_text(encoding="utf-8")
    section = md.split("## 4.")[1].split("## 5.")[0]
    out = {}
    name = None
    body = []
    for raw in section.splitlines():
        line = raw.strip()
        hdr = re.match(r"#\s+([A-Z_][A-Z0-9_]*)\b", line)
        if hdr and not line.startswith("#!"):
            if name and body:
                out[name] = bytes.fromhex("".join(body))
            name, body = hdr.group(1), []
            continue
        if name and re.fullmatch(r"(?:[0-9A-Fa-f]{2}[\s]+)+[0-9A-Fa-f]{2}", line):
            body.extend(line.split())
    if name and body:
        out[name] = bytes.fromhex("".join(body))
    return out


def main() -> int:
    gen = build_frames()
    doc = contract_vectors()
    bad = 0
    for name, frame in gen.items():
        want = doc.get(name)
        if want is None:
            print(f"[MISS] {name}: no vector found in contract S4")
            bad += 1
        elif frame != want:
            print(f"[DRIFT] {name}:")
            print(f"  protocol.py : {frame.hex(' ')}")
            print(f"  contract S4 : {want.hex(' ')}")
            bad += 1
        else:
            print(f"[OK]   {name} ({len(frame)}B)")
    if bad:
        print(f"\nDRIFT DETECTED: {bad} mismatch(es) -- update protocol.py AND contract/TB together!")
        return 1
    print("\nCONTRACT SYNC OK: protocol.py == contract S4 (TB golden arrays derive from the same source)")
    return 0


if __name__ == "__main__":
    sys.exit(main())