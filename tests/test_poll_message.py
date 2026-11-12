"""N3/N4(finals-demo) station-side tests -- AUTH_POLL message + contract vector.

Covers the python half of:
  * N4 AUTH_POLL(0x0097): pack/parse roundtrip, payload length validation,
    CRC_EXTRA distinctness, and the contract S4 golden vector byte-match.
  * N3 CONFIRM status field: protocol.parse returns status at payload[4]
    ("<IB" layout) -- the invariant the bridge confirm-wait fix relies on
    (reading payload[0] would alias the tid LSB as status for tid=1).

Run from the repository root::

    python -m pytest tests/test_poll_message.py -q
"""

import sys
import unittest
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.python.server.protocol import HFIDAProtocol

_P = HFIDAProtocol()

GOLDEN_POLL_HEX = "FD080000480102970000" "2A000000" "EFBEADDE" "5567"


class TestAuthPoll(unittest.TestCase):
    def test_pack_parse_roundtrip(self):
        f = _P.pack(HFIDAProtocol.MSG_AUTH_POLL,
                    terminal_id=42, nonce=0xDEADBEEF)
        mid, fl = HFIDAProtocol.parse(f)
        self.assertEqual(mid, 0x0097)
        self.assertEqual(fl["terminal_id"], 42)
        self.assertEqual(fl["nonce"], 0xDEADBEEF)
        self.assertEqual(len(f), 20)  # 10 head + 8 payload + 2 CRC

    def test_contract_golden_vector_byte_match(self):
        # 与 docs/protocol_contract.md §4 AUTH_POLL 向量**逐字节全等**(seq 固定
        # 0x48,与 check_contract_sync.build_frames 同构造)。
        p = HFIDAProtocol(system_id=1, component_id=2)
        p._seq = 0x48
        f = p.pack(HFIDAProtocol.MSG_AUTH_POLL,
                   terminal_id=42, nonce=0xDEADBEEF)
        self.assertEqual(f.hex().upper(), GOLDEN_POLL_HEX.replace(" ", ""))

    def test_msg_name_and_crc_extra_registered(self):
        self.assertEqual(HFIDAProtocol.msg_name(0x0097), "AUTH_POLL")
        self.assertEqual(HFIDAProtocol._CRC_EXTRA[0x0097], 0x60)
        # CRC_EXTRA 全表无重复(每消息唯一,parse 侧防混淆的前提)
        vals = list(HFIDAProtocol._CRC_EXTRA.values())
        self.assertEqual(len(vals), len(set(vals)))

    def test_parse_rejects_wrong_length(self):
        good = _P.pack(HFIDAProtocol.MSG_AUTH_POLL, terminal_id=1, nonce=2)
        bad_body = good[10:-2] + b"\x00"       # 9B 载荷(应 8B)
        # 帧头 len 位改成 9 + 追加 1 字节,CRC 保持原值 -> parse 必须拒绝
        bad = good[:1] + bytes([len(bad_body)]) + good[2:10] + bad_body + good[-2:]
        with self.assertRaises(Exception):
            HFIDAProtocol.parse(bad)


class TestConfirmStatusLayout(unittest.TestCase):
    """N3: bridge confirm 修复所依赖的协议层不变量。"""

    def test_status_is_payload4_not_payload0(self):
        # tid=1,status=0:按载荷[0]读会把 tid LSB(=1)当 status 误判 FAIL
        f = _P.pack(HFIDAProtocol.MSG_CONFIRM, terminal_id=1, status=0)
        mid, fl = HFIDAProtocol.parse(f)
        self.assertEqual(mid, 0x0094)
        self.assertEqual(fl["terminal_id"], 1)
        self.assertEqual(fl["status"], 0)
        raw_payload = f[10:-2]
        self.assertEqual(raw_payload[0], 1)   # tid LSB -- 不是 status
        self.assertEqual(raw_payload[4], 0)   # status 在 payload[4]

    def test_confirm_fail_roundtrip(self):
        f = _P.pack(HFIDAProtocol.MSG_CONFIRM, terminal_id=7, status=1)
        _, fl = HFIDAProtocol.parse(f)
        self.assertEqual(fl["status"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
