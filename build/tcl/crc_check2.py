import sys
sys.path.insert(0, r"D:\puf-drone-auth")
from src.python.server.protocol import HFIDAProtocol, crc16_mcrf4xx
proto = HFIDAProtocol()
raw = bytes.fromhex("fd200000050102920000b0a4d83f3b7d1fdab081d05bd33966f1b825f03d339d8533f8a5")
msgid = 0x0092
extra = proto._crc_extra(msgid)
crc_rx = int.from_bytes(raw[-2:], "little")
# 口径A: 24字节负载(帧内实际)
a = crc16_mcrf4xx(raw[1:34] + bytes([extra]))
# 口径B: 32字节负载(头部声明), 但只有24 -> 无法
print("crc extra:", hex(extra))
print("crc over [1:34]+extra =", hex(a), "frame crc =", hex(crc_rx), "MATCH" if a == crc_rx else "NO")
# 若尾部8字节丢失, 真实帧应是 44B; 用现有24B payload算不匹配说明帧自身CRC覆盖了别的长度
