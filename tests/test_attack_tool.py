"""N8(finals-demo) attack tool tests -- fake RESULT race injection.

CI-safe:FakeResultAttacker 零 I/O(pack/send/sleep/clock 全注入),
不连串口、不起线程、无网络。Run: python -m pytest tests/test_attack_tool.py -q
"""

import sys
import unittest
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.python.server.protocol import HFIDAProtocol
from tools.attack.fake_result_attack import (
    DEFAULT_FAKE_R2, FakeResultAttacker, FrameSync, MSG_RESPONSE_R1,
    build_rogue_burst)

_P = HFIDAProtocol()


def transcript(rounds: int = 1) -> bytes:
    """一轮(或多轮)认证上行流:ACCESS_REQUEST + RESPONSE_R1。"""
    parts = []
    for _ in range(rounds):
        parts.append(_P.pack(HFIDAProtocol.MSG_ACCESS_REQUEST,
                             terminal_id=1, c2=bytes.fromhex("a1a2a3a4a5a6a7a8")))
        parts.append(_P.pack(MSG_RESPONSE_R1, r1s=[bytes(8)] * 4))
    return b"".join(parts)


def make(**kw):
    sent: list[bytes] = []
    logs: list[str] = []
    atk = FakeResultAttacker(send=sent.append,
                             log=logs.append,
                             sleeper=lambda s: None,      # 零等待
                             clock=lambda: 0.0,
                             **kw)
    return atk, sent, logs


class TestRaceInjection(unittest.TestCase):
    def test_injects_valid_fake_result_on_response_r1(self):
        atk, sent, logs = make()
        atk.feed(transcript())
        self.assertEqual(len(sent), 1)
        mid, fields = HFIDAProtocol.parse(sent[0])        # 注入帧是真协议可解析的
        self.assertEqual(HFIDAProtocol.msg_name(mid), "RESULT")
        self.assertEqual(fields["result"], 0)             # 假 PASS
        self.assertEqual(fields["r2"], DEFAULT_FAKE_R2)   # 错 R2(按构造)

    def test_exactly_once_per_round_and_rearm(self):
        atk, sent, _ = make()
        atk.feed(transcript(rounds=1))
        atk.feed(transcript(rounds=1))                     # 第二轮:ACCESS_REQUEST 重武装
        self.assertEqual(atk.injected_rounds, 2)

    def test_same_round_double_r1_injects_once(self):
        """content-review P2:删 disarm-on-inject 后原测试仍绿——同轮第二个
        R1(板子重传)必须不再注入,否则半双工碰撞概率翻倍。"""
        atk, sent, _ = make()
        stream = transcript(rounds=1)
        atk.feed(stream)
        atk.feed(_P.pack(MSG_RESPONSE_R1, r1s=[bytes(8)] * 4))  # 同轮第二个 R1
        self.assertEqual(atk.injected_rounds, 1)                 # disarm 生效
        self.assertFalse(atk.armed)

    def test_passive_mode_never_injects(self):
        atk, sent, _ = make(mode="passive")
        atk.feed(transcript())
        self.assertEqual(sent, [])
        self.assertEqual(atk.heard_frames, 2)              # 监听仍在工作

    def test_noise_partial_frames_resync(self):
        atk, sent, _ = make()
        stream = b"\x00\xffgarbage" + transcript()
        stream = stream[:-3]                                # 截断尾帧
        atk.feed(stream)
        self.assertEqual(sent, [])                          # 帧未完整:不触发
        atk.feed(transcript())                              # 完整一轮:恢复触发
        self.assertEqual(len(sent), 1)
        self.assertGreater(atk.sync.noise, 0)               # 噪声被计数量丢弃


class TestSimulateMode(unittest.TestCase):
    """content-review P3:--simulate 排练路径与退出码契约零覆盖。"""

    def test_simulate_race_returns_zero(self):
        from tools.attack.fake_result_attack import main
        self.assertEqual(main(["--simulate", "--mode", "race"]), 0)

    def test_simulate_passive_returns_zero(self):
        from tools.attack.fake_result_attack import main
        self.assertEqual(main(["--simulate", "--mode", "passive"]), 0)


class TestFrameSync(unittest.TestCase):
    def test_stx_noise_dropped_and_batched(self):
        fs = FrameSync()
        good = _P.pack(MSG_RESPONSE_R1, r1s=[bytes(8)] * 4)
        got = fs.feed(b"\x12\x34" + good[:5])
        self.assertEqual(got, [])
        got = fs.feed(good[5:] + b"\xab" + good)          # 补齐 + 一次完整重放
        self.assertEqual(len(got), 2)
        self.assertEqual(got[0][0], MSG_RESPONSE_R1)


class TestInjectNowAndDelay(unittest.TestCase):
    def test_inject_now_frame_parses(self):
        atk, sent, _ = make()
        frame = atk.inject_now()
        self.assertEqual(sent[-1], frame)
        mid, fields = HFIDAProtocol.parse(frame)
        self.assertEqual(fields["r2"], DEFAULT_FAKE_R2)

    def test_delay_honored_and_lag_recorded(self):
        slept: list[float] = []
        sent2: list[bytes] = []
        t = [1.0]
        atk = FakeResultAttacker(send=sent2.append, r2_fake=DEFAULT_FAKE_R2,
                                 delay_s=0.05,
                                 sleeper=lambda s: (slept.append(s), t.__setitem__(0, t[0] + s)),
                                 clock=lambda: t[0])
        atk.feed(transcript())
        self.assertEqual(slept, [0.05])                     # 延迟真的 sleep 了
        self.assertEqual(atk.injected_rounds, 1)            # 注入真发生了
        self.assertEqual(len(sent2), 1)
        self.assertAlmostEqual(atk.last_inject_lag_s, 0.05)  # 递增 clock:lag≈delay




class TestRogueBurst(unittest.TestCase):
    """N10 伪基站接入演示帧组(零 I/O,只验构造与解析回读)。"""

    def test_default_burst_two_frames(self):
        burst = build_rogue_burst()
        self.assertEqual([n for n, _ in burst],
                         ["banner_fake_result_0x0093",
                          "rogue_access_request_0x0090"])
        mid, fl = HFIDAProtocol.parse(burst[0][1])
        self.assertEqual(mid, 0x0093)
        self.assertEqual(fl["result"], 0)          # PASS 伪装
        self.assertEqual(fl["r2"], DEFAULT_FAKE_R2)
        mid2, fl2 = HFIDAProtocol.parse(burst[1][1])
        self.assertEqual(mid2, 0x0090)
        self.assertEqual(fl2["terminal_id"], 77)   # 未注册 tid
        self.assertEqual(len(fl2["c2"]), 8)

    def test_no_banner_custom_tid_c2(self):
        burst = build_rogue_burst(tid=7, banner=False, c2=bytes(range(8)))
        self.assertEqual(len(burst), 1)
        mid, fl = HFIDAProtocol.parse(burst[0][1])
        self.assertEqual(mid, 0x0090)
        self.assertEqual(fl["terminal_id"], 7)
        self.assertEqual(fl["c2"], bytes(range(8)))

    def test_c2_random_each_call(self):
        a = build_rogue_burst(banner=False)[0][1]
        b = build_rogue_burst(banner=False)[0][1]
        self.assertNotEqual(a, b)                  # c2 每次随机→不触发真站重放窗

    def test_bad_c2_rejected(self):
        with self.assertRaises(ValueError):
            build_rogue_burst(c2=b"\x00" * 7)


if __name__ == "__main__":
    unittest.main()

