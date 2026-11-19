"""Check whether the 36-byte RESPONSE has a valid CRC over 24-byte payload."""
import sys
sys.path.insert(0, r"D:\puf-drone-auth")
from src.python.server.protocol import HFIDAProtocol
try:
    from src.python.server.mavlink_frame import crc16_x25
except Exception:
    crc16_x25 = None
proto = HFIDAProtocol()
raw = bytes.fromhex("fd200000050102920000b0a4d83f3b7d1fdab081d05bd33966f1b825f03d339d8533f8a5")
print("len:", len(raw), "header_len_field:", raw[1], "msgid:", raw[7:10].hex())
# 帧结构: fd len incompat compat seq sys comp msgid(3) payload(len) crc(2)
payload = raw[10:-2]
crc_rx = raw[-2:]
print("payload bytes:", len(payload), payload.hex())
print("crc in frame:", crc_rx.hex())
if crc16_x25:
    for name, body in (("over header[1:]+payload24", None),):
        pass
    # 常见口径: len..end-of-payload
    c_short = crc16_x25(raw[1:34])
    print("crc over bytes[1:34] (len..24B payload):", hex(c_short))
    # 若板子按4个响应算CRC(32字节payload), 我们缺8字节, 无法直接验
else:
    print("crc16_x25 not importable")
