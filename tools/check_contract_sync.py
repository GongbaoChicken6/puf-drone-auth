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

from src.python.evaluation.puf_model import (  # noqa: E402
    GOLDEN_SEED_A,
    GOLDEN_SEED_B,
    GOLDEN_SEED_C,
    pair_table_int,
)
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
    # A1 golden RESULT frame (section 4.1 / tb_level3 result_gold): first-auth
    # R2 = Speck(W3 demo key, C2=a1..a8) = 7b45b0545e59aa94 at seq 0x50.
    p._seq = 0x50
    frames["RESULT_A1_GOLDEN"] = p.pack(
        H.MSG_RESULT, result=0, hd=5,
        r2=bytes.fromhex("7b45b0545e59aa94"))
    return frames


def contract_vectors():
    """Parse S4 of the contract: '# NAME ... (NB)' header + hex body lines.

    NOTE (gate_audit GATE-02): the scan region ends at the SECOND
    occurrence of the substring "## 4." -- which today is inside the
    "### 4.1" heading, purely by coincidence.  Renaming that heading
    would silently widen the scan into section 4.1 prose; keep the
    "### 4.x" numbering or anchor the split on full-line headings.
    """
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


def build_puf_tables():
    """W4 S8: regenerate the three frozen pair tables from puf_model."""
    out = {}
    for name, seed in (
        ("PUF_SEED_A", GOLDEN_SEED_A),
        ("PUF_SEED_B", GOLDEN_SEED_B),
        ("PUF_SEED_C", GOLDEN_SEED_C),
    ):
        out[name] = pair_table_int(seed).to_bytes(64, "big")
    return out


def contract_puf_vectors():
    """Parse S8 golden blocks with the same shape as contract_vectors()."""
    md = (ROOT / "docs" / "protocol_contract.md").read_text(encoding="utf-8")
    if "## 8." not in md:
        return {}
    section = md.split("## 8.")[1].split("\n## ")[0]
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
    gen = {**build_frames(), **build_puf_tables()}
    doc = {**contract_vectors(), **contract_puf_vectors()}
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
    # Reverse direction (gate_audit GATE-01): vectors that live only in the
    # contract with no protocol.py generator are drift too -- they look like
    # contract to a reader but are invisible to every forward check.
    for name in sorted(set(doc) - set(gen)):
        print(f"[ORPHAN] {name}: in contract but no generator in build_frames()")
        bad += 1
    if bad:
        print(f"\nDRIFT DETECTED: {bad} mismatch(es) -- update protocol.py AND contract/TB together!")
        return 1
    print("\nCONTRACT SYNC OK: protocol.py + puf_model == contract S4 + S8 "
          "(TB golden arrays are manually mirrored -- this tool does not read them)")
    return 0


if __name__ == "__main__":
    sys.exit(main())