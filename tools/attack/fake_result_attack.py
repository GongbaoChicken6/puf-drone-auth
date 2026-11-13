#!/usr/bin/env python3
"""fake_result_attack.py —— N8(finals-demo) 伪基站竞速注入演示工具。

信道模型(HC-12 半双工广播,433MHz 同频):攻击者电台与真基站同配 C001,
听得见信道上的一切,也能随时注入。演示剧本(FEATURES §2 N8):

    真站发起认证 → 板子回 RESPONSE_R1(0x0092)
      → 本工具【零延迟】注入"PASS + 伪 R2"的 RESULT(0x0093)
      → 板端 R2 失配(双向认证识破) → CONFIRM_FAIL 上报(N3) → BLOCKED 双亮
      → 真站随后到场的真 RESULT 已无主;站端 IDS 听到注入帧红警(N2),
        并收到终端 CONFIRM_FAIL → 矛盾关联告警(base.spoof.suspected)

竞速依据:真站 R1→RESULT 之间有 ~0.2s 节奏延迟 + HD 计算(web_bridge
_auth_round),零延迟注入必先到场。半双工碰撞(注入撞上板子发送尾字节,
两帧互毁被 CRC 丢弃)是已知风险——重跑一次本脚本即可(备选剧本)。

用法(真信道,需 pyserial):
    python tools/attack/fake_result_attack.py --port COM9            # 竞速模式
    python tools/attack/fake_result_attack.py --port COM9 --passive  # 只监听(讲"攻击者在听")
    python tools/attack/fake_result_attack.py --port COM9 --inject-now  # 空闲注入一帧(单演 Tier0 IDS)
HC-12 同频配置用 tools/hc12 现成脚本。仅供本作品决赛演示,信道上无真实密钥
(伪 R2 按构造就是错的)。

CI-safe:核心类 FakeResultAttacker 不做任何 I/O(串口/时间都注入),
tests/test_attack_tool.py 直驱验证。运行入口 main() 才 import pyserial。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.python.server.protocol import HFIDAProtocol  # noqa: E402

STX = 0xFD
MSG_ACCESS_REQUEST = HFIDAProtocol.MSG_ACCESS_REQUEST   # 0x0090 term->server
MSG_RESPONSE_R1 = HFIDAProtocol.MSG_RESPONSE_R1         # 0x0092 term->server
MSG_RESULT = HFIDAProtocol.MSG_RESULT                   # 0x0093 server->term
RESULT_PASS = 0

DEFAULT_FAKE_R2 = bytes.fromhex("deadbeefcafe0110")      # 按构造就是错 R2


class FrameSync:
    """最小 MAVLink v2 帧同步器(字节流 → 完整帧列表)。

    与板端 frame_parser.v 同规则:非 STX 字节静默丢弃(噪声容忍);
    帧长 = 10 头 + LEN + 2 CRC。不做 CRC 校验(监听用途,坏帧也能计数)。
    """

    def __init__(self) -> None:
        self.buf = bytearray()
        self.noise = 0

    def feed(self, data: bytes) -> list[tuple[int, bytes]]:
        """返回本批完整的 (msg_id, frame_bytes) 列表。"""
        out: list[tuple[int, bytes]] = []
        self.buf.extend(data)
        while True:
            # 丢掉 STX 之前的噪声字节
            while self.buf and self.buf[0] != STX:
                self.buf.pop(0)
                self.noise += 1
            if len(self.buf) < 2:
                break
            total = 10 + self.buf[1] + 2
            if len(self.buf) < total:
                break
            frame = bytes(self.buf[:total])
            del self.buf[:total]
            msg_id = frame[7] | (frame[8] << 8) | (frame[9] << 16)
            out.append((msg_id, frame))
        return out


class FakeResultAttacker:
    """状态机:armed --RESPONSE_R1--> 注入伪 RESULT --> disarmed;
    disarmed --ACCESS_REQUEST(新一轮认证)--> re-arm。"""

    def __init__(self, pack_fn=HFIDAProtocol().pack, send=None,
                 r2_fake: bytes = DEFAULT_FAKE_R2, mode: str = "race",
                 delay_s: float = 0.0, log=None, sleeper=time.sleep,
                 clock=time.monotonic):
        self._pack = pack_fn
        self._send = send or (lambda frame: None)
        self._log = log or (lambda msg: print(f"[{time.strftime('%H:%M:%S')}] {msg}",
                                              file=sys.stderr))
        self._sleep = sleeper
        self._clock = clock
        self.r2_fake = r2_fake
        self.mode = mode                    # race | passive
        self.delay_s = delay_s
        self.armed = True
        self.injected_rounds = 0
        self.heard_frames = 0
        self.sync = FrameSync()
        self.last_inject_lag_s: float | None = None

    # ---- 入口:喂串口字节(攻击者听到的一切) ----
    def feed(self, data: bytes) -> None:
        for msg_id, frame in self.sync.feed(data):
            self._on_frame(msg_id, frame)

    def _on_frame(self, msg_id: int, frame: bytes) -> None:
        self.heard_frames += 1
        name = HFIDAProtocol.msg_name(msg_id)
        self._log(f"heard {name} ({len(frame)}B) {frame.hex()[:32]}…")
        if msg_id == MSG_ACCESS_REQUEST:
            if not self.armed:
                self._log("new auth round → re-arm")
            self.armed = True
            return
        if msg_id == MSG_RESPONSE_R1 and self.armed and self.mode == "race":
            self._inject(frame)

    # ---- 注入:伪 RESULT(PASS + 错 R2) ----
    def _inject(self, trigger: bytes) -> None:
        t0 = self._clock()
        if self.delay_s > 0:
            self._sleep(self.delay_s)
        fake = self._pack(MSG_RESULT, result=RESULT_PASS, hd=5, r2=self.r2_fake)
        self._send(fake)
        self.injected_rounds += 1
        self.armed = False
        self.last_inject_lag_s = self._clock() - t0
        self._log(f">>> INJECT fake RESULT (PASS + r2={self.r2_fake.hex()}) "
                  f"triggered by RESPONSE_R1, lag={self.last_inject_lag_s * 1000:.1f}ms")

    def inject_now(self) -> bytes:
        """空闲单帧注入(演示 Tier0 IDS:站端不该收到的方向帧)。"""
        fake = self._pack(MSG_RESULT, result=RESULT_PASS, hd=5, r2=self.r2_fake)
        self._send(fake)
        self.injected_rounds += 1
        self._log(f">>> INJECT-NOW idle fake RESULT {fake.hex()}")
        return fake


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--port", required=True, help="攻击者电台串口(如 COM9)")
    p.add_argument("--baud", type=int, default=115_200)
    p.add_argument("--r2-hex", default=DEFAULT_FAKE_R2.hex(),
                   help="伪 R2(8B hex,默认按构造即错)")
    p.add_argument("--mode", choices=["race", "passive"], default="race")
    p.add_argument("--delay-ms", type=float, default=0.0,
                   help="注入延迟(演示'竞速'用,默认 0)")
    p.add_argument("--inject-now", action="store_true",
                   help="启动即注入一帧(单演 Tier0 IDS)后退出")
    p.add_argument("--simulate", action="store_true",
                   help="不连串口,回放内置演示字节流(排练用,零硬件)")
    args = p.parse_args(argv)

    r2 = bytes.fromhex(args.r2_hex)
    if len(r2) != 8:
        p.error("--r2-hex must be 8 bytes")

    sent: list[bytes] = []
    atk = FakeResultAttacker(send=sent.append, r2_fake=r2, mode=args.mode,
                             delay_s=args.delay_ms / 1000.0)

    if args.simulate:                       # 零硬件排练:回放一轮真认证字节流
        proto = HFIDAProtocol()
        c2 = bytes.fromhex("a1a2a3a4a5a6a7a8")
        stream = b"".join([
            b"\x00noise\xff", proto.pack(HFIDAProtocol.MSG_ACCESS_REQUEST,
                                   terminal_id=1, c2=c2),
            proto.pack(HFIDAProtocol.MSG_CHALLENGE,
                       seeds=[bytes(8)] * 4),
            proto.pack(HFIDAProtocol.MSG_RESPONSE_R1,
                       r1s=[bytes(8)] * 4),
        ])
        atk.feed(stream)
        print(f"[SIMULATE] heard={atk.heard_frames} injected={atk.injected_rounds}")
        for f in sent:
            mid, fields = HFIDAProtocol.parse(f)
            print(f"[SIMULATE] sent msg={HFIDAProtocol.msg_name(mid)} {fields}")
        return 0 if (args.mode == "passive" or atk.injected_rounds == 1) else 1

    try:
        import serial  # 仅真信道需要
    except ImportError:
        print("pyserial not installed: pip install pyserial (或先用 --simulate)",
              file=sys.stderr)
        return 2

    atk._send = lambda frame: None           # 换真发送
    with serial.Serial(args.port, args.baud, timeout=0.1) as ser:
        def send(frame: bytes) -> None:
            ser.write(frame)
            ser.flush()
        atk._send = send
        if args.inject_now:
            atk.inject_now()
            return 0
        print(f"[ATTACK] sniffing {args.port}@{args.baud} mode={args.mode} "
              f"r2={r2.hex()} — Ctrl+C 退出", file=sys.stderr)
        try:
            while True:
                chunk = ser.read(256)
                if chunk:
                    atk.feed(chunk)
        except KeyboardInterrupt:
            print(f"[ATTACK] stop. heard={atk.heard_frames} "
                  f"injected={atk.injected_rounds} noise={atk.sync.noise}",
                  file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
