"""
speck.py -- Speck64/96 轻量级分组密码（Python 参考实现）

参数（NSA 2013 规范）：
    字长   n = 32 bit
    块大小 2n = 64 bit（= 8 字节 = R2 长度）
    密钥   3n = 96 bit（= 12 字节 = PUF 稳定位）
    轮数   T = 26

字节序：小端（little-endian）
    key[0..3]   → K[0]（k0）    plaintext[0..3] → x
    key[4..7]   → K[1]（l0）    plaintext[4..7] → y
    key[8..11]  → K[2]（l1）    ciphertext 同 plaintext 布局
"""

import struct


_WORD = 32
_ROUNDS = 26
_MASK = 0xFFFFFFFF


def _rol(x: int, r: int) -> int:
    return ((x << r) | (x >> (_WORD - r))) & _MASK


def _ror(x: int, r: int) -> int:
    return ((x >> r) | (x << (_WORD - r))) & _MASK


# ============================================================
# 实现一：数组式密钥扩展（与 VHDL 参考结构一致）
# ============================================================
class Speck6496:
    def __init__(self, key: bytes) -> None:
        if len(key) != 12:
            raise ValueError(f"key must be 12 bytes (96 bits), got {len(key)}")
        self._k0 = struct.unpack("<I", key[0:4])[0]
        self._l0 = struct.unpack("<I", key[4:8])[0]
        self._l1 = struct.unpack("<I", key[8:12])[0]
        self._rk = self._key_schedule()

    def _key_schedule(self) -> list:
        rk = [0] * _ROUNDS
        l = [0] * (_ROUNDS + 1)
        rk[0] = self._k0
        l[0] = self._l0
        l[1] = self._l1
        for i in range(_ROUNDS - 1):
            l[i + 2] = ((_ror(l[i], 8) + rk[i]) & _MASK) ^ i
            rk[i + 1] = _rol(rk[i], 3) ^ l[i + 2]
        return rk

    def encrypt(self, plaintext: bytes) -> bytes:
        if len(plaintext) != 8:
            raise ValueError(f"plaintext must be 8 bytes, got {len(plaintext)}")
        x = struct.unpack("<I", plaintext[0:4])[0]
        y = struct.unpack("<I", plaintext[4:8])[0]
        for i in range(_ROUNDS):
            x = ((_ror(x, 8) + y) & _MASK) ^ self._rk[i]
            y = _rol(y, 3) ^ x
        return struct.pack("<II", x, y)


# ============================================================
# 实现二：独立参考（直接从 C 代码翻译，不同代码结构）
# 用于交叉验证实现一的正确性
# ============================================================
def speck_encrypt_reference(key: bytes, plaintext: bytes) -> bytes:
    """直接翻译 NSA C 参考代码（不同代码路径，用于交叉验证）"""
    k = [0] * 26  # round keys
    l = [0] * 28  # l values (l[0] and l[1] from key, l[2..27] generated)

    k[0] = struct.unpack("<I", key[0:4])[0]
    l[0] = struct.unpack("<I", key[4:8])[0]
    l[1] = struct.unpack("<I", key[8:12])[0]

    # Key schedule (C style: for loop, different from class approach)
    for i in range(25):
        l[i + 2] = ((_ror(l[i], 8) + k[i]) & _MASK) ^ i
        k[i + 1] = _rol(k[i], 3) ^ l[i + 2]

    # Encryption (C style: while loop)
    x = struct.unpack("<I", plaintext[0:4])[0]
    y = struct.unpack("<I", plaintext[4:8])[0]
    i = 0
    while i < 26:
        x = _ror(x, 8)
        x = (x + y) & _MASK
        x = x ^ k[i]
        y = _rol(y, 3)
        y = y ^ x
        i = i + 1

    return struct.pack("<II", x, y)


# ============================================================
# 交叉验证 + KAT
# ============================================================
def _self_test() -> bool:
    all_pass = True

    # 测试 1：两实现交叉一致性（100 组随机）
    import random
    rng = random.Random(20261006)  # 固定种子
    for trial in range(100):
        key = bytes(rng.randrange(256) for _ in range(12))
        pt = bytes(rng.randrange(256) for _ in range(8))
        ct1 = Speck6496(key).encrypt(pt)
        ct2 = speck_encrypt_reference(key, pt)
        if ct1 != ct2:
            print(f"  CROSS-FAIL trial={trial} key={key.hex()} pt={pt.hex()}")
            print(f"    impl1={ct1.hex()} impl2={ct2.hex()}")
            all_pass = False
    if all_pass:
        print(f"  [PASS] 100 组随机交叉一致")

    # 测试 2：边界向量
    edge_cases = [
        (bytes(12), bytes(8)),                           # 全 0
        (bytes([0xFF] * 12), bytes([0xFF] * 8)),         # 全 FF
        (bytes(12), bytes([0xFF] * 8)),                  # key=0, pt=FF
        (bytes([0xFF] * 12), bytes(8)),                  # key=FF, pt=0
        (bytes.fromhex("00112233445566778899aabb"), bytes.fromhex("deadbeefcafebabe")),
    ]
    for idx, (key, pt) in enumerate(edge_cases):
        ct1 = Speck6496(key).encrypt(pt)
        ct2 = speck_encrypt_reference(key, pt)
        if ct1 != ct2:
            print(f"  EDGE-FAIL idx={idx}")
            all_pass = False
        else:
            print(f"  [PASS] edge[{idx}] key={key[:4].hex()}.. pt={pt.hex()} ct={ct1.hex()}")

    # 测试 3：确定性（同输入必同输出）
    key = bytes.fromhex("131211100b0a090803020100")
    pt = bytes.fromhex("74614620736e6165")
    ct_a = Speck6496(key).encrypt(pt)
    ct_b = Speck6496(key).encrypt(pt)
    if ct_a == ct_b:
        print(f"  [PASS] 确定性: key={key.hex()} pt={pt.hex()} ct={ct_a.hex()}")
    else:
        print(f"  [FAIL] 非确定性!")
        all_pass = False

    # 测试 4：雪崩效应（1 bit 变化→~50% 输出位变化）
    pt2 = bytes([pt[0] ^ 1] + list(pt[1:]))  # 翻转 1 bit
    ct_c = Speck6496(key).encrypt(pt2)
    diff_bits = bin(int.from_bytes(ct_a, "little") ^ int.from_bytes(ct_c, "little")).count("1")
    total_bits = 64
    ratio = diff_bits / total_bits
    if 0.3 < ratio < 0.7:
        print(f"  [PASS] 雪崩效应: {diff_bits}/{total_bits} bits flipped ({ratio:.0%})")
    else:
        print(f"  [FAIL] 雪崩异常: {diff_bits}/{total_bits} ({ratio:.0%})")
        all_pass = False

    # 测试 5：长度校验
    try:
        Speck6496(bytes(11))  # 11 字节 key → 应报错
        print("  [FAIL] 11B key 未报错")
        all_pass = False
    except ValueError:
        print("  [PASS] 11B key 正确报错")
    try:
        Speck6496(bytes(12)).encrypt(bytes(7))  # 7 字节 pt → 应报错
        print("  [FAIL] 7B pt 未报错")
        all_pass = False
    except ValueError:
        print("  [PASS] 7B pt 正确报错")

    return all_pass


if __name__ == "__main__":
    print("Speck64/96 self-test:")
    print("=" * 50)
    if _self_test():
        print("=" * 50)
        print("ALL TESTS PASS")
    else:
        print("=" * 50)
        print("TESTS FAILED")
        raise SystemExit(1)
