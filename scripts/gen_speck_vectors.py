"""
gen_speck_vectors.py -- Speck64/96 测试向量单源生成器（增强版）

生成 5 类向量到同一个 .mem 文件：
  1. 随机     : 1000 组（seed=20261006，可复现）
  2. 边角     : 全0/全FF/0x55交替/0xAA交替
  3. 单比特游走: 翻转密钥/明文的每个位（定位错误到具体字/轮）
  4. 进位链   : 全1密钥+特殊明文（确定性覆盖 32 位加法器最长进位）
  5. 密钥编排隔离: 两个密钥只差一个字（k0/l0/l1 各一组）

用法：
    python scripts/gen_speck_vectors.py              # 生成
    python scripts/gen_speck_vectors.py --check      # 验证新鲜度
"""

import sys
import os
import random
import struct

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "python", "common"))
from speck import Speck6496, speck_encrypt_reference

SEED = 20261006
NUM_RANDOM = 1000
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "sim", "testvectors")
OUT_FILE = os.path.join(OUT_DIR, "speck_random.mem")

# NSA 官方 KAT（Implementation Guide 1.1 Table 6）
NSA_KAT_KEY = bytes.fromhex("0001020308090a0b10111213")
NSA_KAT_PT = bytes.fromhex("65616e7320466174")
NSA_KAT_CT = bytes.fromhex("6c947541ec52799f")


def to_bus_key(key_bytes: bytes) -> int:
    """key bytes → 96-bit bus value {l1, l0, k0}"""
    k0 = struct.unpack("<I", key_bytes[0:4])[0]
    l0 = struct.unpack("<I", key_bytes[4:8])[0]
    l1 = struct.unpack("<I", key_bytes[8:12])[0]
    return (l1 << 64) | (l0 << 32) | k0


def to_bus_pt(pt_bytes: bytes) -> int:
    """pt bytes → 64-bit bus value {y, x}（NSA 约定）"""
    y = struct.unpack("<I", pt_bytes[0:4])[0]
    x = struct.unpack("<I", pt_bytes[4:8])[0]
    return (y << 32) | x


def compute_ct(key: bytes, pt: bytes) -> int:
    """计算密文并返回 64-bit 总线值"""
    ct = Speck6496(key).encrypt(pt)
    return to_bus_pt(ct)


def gen_all_vectors():
    """生成全部测试向量，返回 (标签, key_bus, pt_bus, ct_bus) 列表"""
    vectors = []
    rng = random.Random(SEED)

    # ---- 1. NSA 官方 KAT ----
    vectors.append(("NSA_KAT", to_bus_key(NSA_KAT_KEY), to_bus_pt(NSA_KAT_PT), to_bus_pt(NSA_KAT_CT)))

    # ---- 2. 边角向量 ----
    edge_cases = [
        ("EDGE_zero_zero", bytes(12), bytes(8)),
        ("EDGE_ff_ff", bytes([0xFF]*12), bytes([0xFF]*8)),
        ("EDGE_zero_ff", bytes(12), bytes([0xFF]*8)),
        ("EDGE_ff_zero", bytes([0xFF]*12), bytes(8)),
        ("EDGE_55_55", bytes([0x55]*12), bytes([0x55]*8)),
        ("EDGE_aa_aa", bytes([0xAA]*12), bytes([0xAA]*8)),
        ("EDGE_seq", bytes(range(12)), bytes(range(0x60, 0x68))),
    ]
    for label, key, pt in edge_cases:
        vectors.append((label, to_bus_key(key), to_bus_pt(pt), compute_ct(key, pt)))

    # ---- 3. 单比特游走（密钥 96 位）----
    base_key = bytes.fromhex("0001020308090a0b10111213")
    base_pt = bytes.fromhex("65616e7320466174")
    for bit in range(96):
        # 构造翻转了第 bit 位的密钥
        mutated = bytearray(base_key)
        byte_idx = bit // 8
        bit_idx = bit % 8
        mutated[byte_idx] ^= (1 << bit_idx)
        mk = bytes(mutated)
        vectors.append((f"WALK_K{bit:03d}", to_bus_key(mk), to_bus_pt(base_pt), compute_ct(mk, base_pt)))

    # ---- 3b. 单比特游走（明文 64 位）----
    for bit in range(64):
        mutated = bytearray(base_pt)
        byte_idx = bit // 8
        bit_idx = bit % 8
        mutated[byte_idx] ^= (1 << bit_idx)
        mp = bytes(mutated)
        vectors.append((f"WALK_P{bit:03d}", to_bus_key(base_key), to_bus_pt(mp), compute_ct(base_key, mp)))

    # ---- 4. 进位链覆盖 ----
    # 全1密钥 + 导致长进位的明文
    carry_cases = [
        ("CARRY_ff_01", bytes([0xFF]*12), bytes([0x01, 0, 0, 0, 0, 0, 0, 0])),
        ("CARRY_ff_7f", bytes([0xFF]*12), bytes([0x7F, 0xFF, 0xFF, 0xFF, 0, 0, 0, 0])),
        ("CARRY_ff_80", bytes([0xFF]*12), bytes([0x80, 0, 0, 0, 0xFF, 0xFF, 0xFF, 0xFF])),
        ("CARRY_k1_ff", bytes([0, 0, 0, 1] + [0xFF]*8), bytes([0xFF]*8)),
    ]
    for label, key, pt in carry_cases:
        vectors.append((label, to_bus_key(key), to_bus_pt(pt), compute_ct(key, pt)))

    # ---- 5. 密钥编排隔离（两个密钥只差一个字）----
    k_base = bytes.fromhex("0001020308090a0b10111213")
    pt_iso = bytes.fromhex("65616e7320466174")
    # 只改 k0（第一个字）
    k0_mod = bytes.fromhex("000102FF08090a0b10111213")
    # 只改 l0（第二个字）
    l0_mod = bytes.fromhex("0001020308090aFF10111213")
    # 只改 l1（第三个字）
    l1_mod = bytes.fromhex("0001020308090a0b101112FF")
    iso_cases = [
        ("ISO_k0_diff", k0_mod, pt_iso),
        ("ISO_l0_diff", l0_mod, pt_iso),
        ("ISO_l1_diff", l1_mod, pt_iso),
    ]
    for label, key, pt in iso_cases:
        vectors.append((label, to_bus_key(key), to_bus_pt(pt), compute_ct(key, pt)))

    # ---- 6. 随机向量 ----
    for i in range(NUM_RANDOM):
        key = bytes(rng.randrange(256) for _ in range(12))
        pt = bytes(rng.randrange(256) for _ in range(8))
        ct_bus = compute_ct(key, pt)
        vectors.append((f"RND{i:04d}", to_bus_key(key), to_bus_pt(pt), ct_bus))

    return vectors


def build_content():
    """Compute vectors + formatted content WITHOUT touching the output file.

    Split out of generate() so --check compares against a pure computation:
    the old check() called generate() (which rewrites the file) and then
    compared against what had just been written -- a tautological PASS that
    also silently destroyed stale evidence (ci_gate review P0).
    """
    os.makedirs(OUT_DIR, exist_ok=True)
    vectors = gen_all_vectors()

    lines = []
    lines.append(f"// Speck64/96 test vectors (seed={SEED})")
    lines.append(f"// Total: {len(vectors)} vectors (KAT + edge + walk + carry + iso + random)")
    lines.append(f"// Generated by gen_speck_vectors.py -- DO NOT EDIT MANUALLY")
    lines.append(f"// Format: key_24hex pt_16hex ct_16hex (bus order {{l1,l0,k0}} / {{y,x}})")

    for label, k, p, c in vectors:
        lines.append(f"{k:024x} {p:016x} {c:016x} // {label}")

    content = "\n".join(lines) + "\n"

    # 统计
    n_kat = sum(1 for v in vectors if v[0].startswith("NSA"))
    n_edge = sum(1 for v in vectors if v[0].startswith("EDGE"))
    n_walk = sum(1 for v in vectors if v[0].startswith("WALK"))
    n_carry = sum(1 for v in vectors if v[0].startswith("CARRY"))
    n_iso = sum(1 for v in vectors if v[0].startswith("ISO"))
    n_rnd = sum(1 for v in vectors if v[0].startswith("RND"))

    return content, vectors


def generate():
    """Generate vectors and WRITE them to the .mem file (report stats)."""
    content, vectors = build_content()
    with open(OUT_FILE, "w") as f:
        f.write(content)

    n_kat = sum(1 for v in vectors if v[0].startswith("NSA"))
    n_edge = sum(1 for v in vectors if v[0].startswith("EDGE"))
    n_walk = sum(1 for v in vectors if v[0].startswith("WALK"))
    n_carry = sum(1 for v in vectors if v[0].startswith("CARRY"))
    n_iso = sum(1 for v in vectors if v[0].startswith("ISO"))
    n_rnd = sum(1 for v in vectors if v[0].startswith("RND"))
    print(f"Generated {len(vectors)} vectors:")
    print(f"  NSA KAT:  {n_kat}")
    print(f"  Edge:     {n_edge}")
    print(f"  Walk:     {n_walk} (96 key + 64 pt)")
    print(f"  Carry:    {n_carry}")
    print(f"  Iso:      {n_iso}")
    print(f"  Random:   {n_rnd}")
    print(f"Output: {OUT_FILE}")
    _cross_impl_check(vectors)
    return content


def _cross_impl_check(vectors):
    """同时验证双实现一致性（生成/检查两条路径共用）"""
    # （原 generate() 尾部的抽检逻辑，见下）
    for label, k_bus, p_bus, c_bus in vectors[:5]:  # 抽检前 5 条
        key_bytes = struct.pack("<III",
            k_bus & 0xFFFFFFFF,        # k0
            (k_bus >> 32) & 0xFFFFFFFF, # l0
            (k_bus >> 64) & 0xFFFFFFFF  # l1
        )
        # 从总线还原字节（注意总线是 {y,x}）
        y_word = (p_bus >> 32) & 0xFFFFFFFF
        x_word = p_bus & 0xFFFFFFFF
        pt_bytes = struct.pack("<II", y_word, x_word)

        ct_class = Speck6496(key_bytes).encrypt(pt_bytes)
        ct_ref = speck_encrypt_reference(key_bytes, pt_bytes)
        assert ct_class == ct_ref, f"Cross-impl mismatch on {label}!"

    print("  Cross-impl check (first 5): PASS")


def check():
    """Freshness check: PURE computation vs on-disk content, never writes.

    The old version regenerated (rewriting the file) before comparing,
    which made the PASS tautological and silently destroyed a stale file
    (ci_gate review P0).  Now a stale file FAILS and is left untouched.
    """
    if not os.path.exists(OUT_FILE):
        print(f"FAIL: {OUT_FILE} does not exist")
        return False
    expected, _ = build_content()  # pure: no file writes, no stat prints
    with open(OUT_FILE, "r") as f:
        actual = f.read()
    if actual == expected:
        print(f"PASS: {OUT_FILE} is up to date ({expected.count(chr(10))-4} vectors)")
        return True
    print(f"FAIL: {OUT_FILE} is stale (run gen_speck_vectors.py to regenerate)")
    return False


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(0 if check() else 1)
    else:
        generate()
