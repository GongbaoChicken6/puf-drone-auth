"""
test_r2_nonlinearity.py -- 线性金丝雀：R2 = Speck64/96(K, C2) 不可被线性拟合

A1 动机：被替换的旧 R2 方案（~C2）是 C2 的仿射函数——持有少量 (C2, R2)
对的攻击者可线性外推任意 C2 对应的 R2，"基站证明"退化为可预测值。
本金丝雀在固定密钥下系统搜索线性结构，任一命中即 FAIL：

  [C0] 负对照   : 对仿射 (~C2)、宽扇入 GF(2) 线性、xor-tree 折叠三类退化，
                   金丝雀必须全部抓获（自证有效；C4 对完全线性映射零漏检）
  [C1] 位平衡   : R2 每个输出位 ~ Bernoulli(1/2)，偏差 <= 4σ（二项）
  [C2] 一阶相关 : 全部 64x64 (输入位 i, 输出位 j) 的 |corr(i,j)| 上界
  [C3] 二阶奇偶 : 输入位对奇偶 (c_i XOR c_k) 对每个输出位的 |corr| 上界
  [C4] 精确线性 : 对每个输出位做 GF(2) 高斯消元，判定其是否为输入位的
                   完全仿射函数（N=256 样本 > 65 未知量；完全线性映射
                   无论扇入宽度必然残差为零 -> FAIL，零假阳性漏检）

阈值（Bonferroni 校正的多重比较界）：对无结构密码 corr ~ N(0, 1/sqrt(N))，
  C1 位平衡     : |偏差| <= 4σ  （64 次比较，族错误率 ~4.1e-3）
  C2 一阶相关   : |corr| <= 5σ   （4096 次比较，族错误率 ~2.3e-3；界=0.3125@N=256）
  C3 二阶奇偶   : |corr| <= 6σ   （~129k 次比较，族错误率 ~2.5e-4；界=0.3750@N=256）
各界相对期望最大值（约 2.9/4.1/4.9σ）留有余量（C3 实测典型 ~5.0σ，边际 1σ，
固定种子下结果完全确定）；检测边界（诚实声明）：能抓 = 任意完全线性/仿射映射
（含宽扇入/CRC 类）、对角仿射、1 轮 Speck 饱和；抓不住 = >=2 轮的轮数削减
（其弱点是差分/密钥恢复类，不表现为 N=256 的一/二阶位相关）与高阶非线性结构。

用法：
    python scripts/test_r2_nonlinearity.py     # exit 0 = PASS, 1 = FAIL
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "python", "common"))
from speck import Speck6496

SEED = 20261007          # 固定种子：可复现且无 flaky
N = 256                  # 每密钥样本数（bitmask 列宽）
ORDER1_SIGMA = 5.0       # C2 阈值：4096 次比较的 Bonferroni 界
ORDER2_SIGMA = 6.0       # C3 阈值：~129k 次比较的 Bonferroni 界
BALANCE_SIGMA = 4.0      # C1 平衡阈值（σ 数）
KEYS = [
    ("W3-demo(NSA public)", bytes.fromhex("0001020308090a0b10111213")),
    ("fixed-random", bytes.fromhex("7d11a9c3f004be58629a8e2d")),
]


def corr(a: int, b: int) -> float:
    """两个 N 位 bitmask 列的 Pearson 相关（±1 编码 agree/disagree）。"""
    dis = (a ^ b).bit_count()
    return (N - 2 * dis) / N


def sample_columns(cipher, rng):
    """采样 N 组 (C2, R2)，返回 64 个输入位列 + 64 个输出位列（bitmask）。"""
    in_cols = [0] * 64
    out_cols = [0] * 64
    for s in range(N):
        ci = int.from_bytes(rng.randbytes(8), "little")
        ri = int.from_bytes(cipher.encrypt(ci.to_bytes(8, "little")), "little")
        for p in range(64):
            if (ci >> p) & 1:
                in_cols[p] |= 1 << s
            if (ri >> p) & 1:
                out_cols[p] |= 1 << s
    return in_cols, out_cols


def check_balance(out_cols):
    """[C1] 每输出位的 1-比例偏离 1/2 不超过 BALANCE_SIGMA 个二项 σ。"""
    worst = 0.0
    sigma = N ** 0.5 / 2  # Bernoulli(1/2) 的 N 样本计数标准差
    for q in range(64):
        z = abs(out_cols[q].bit_count() - N / 2) / sigma
        worst = max(worst, z)
    return worst


def check_order1(in_cols, out_cols):
    """[C2] max |corr(输入位 i, 输出位 j)|。仿射结构（含旧 ~C2）此处饱和到 1。"""
    worst, at = 0.0, None
    for p in range(64):
        cp = in_cols[p]
        for q in range(64):
            c = abs(corr(cp, out_cols[q]))
            if c > worst:
                worst, at = c, (p, q)
    return worst, at


def check_order2(in_cols, out_cols):
    """[C3] max |corr(c_i XOR c_k, 输出位 j)|——捕获二阶异或类线性结构。"""
    worst, at = 0.0, None
    for p in range(64):
        for k in range(p + 1, 64):
            par = in_cols[p] ^ in_cols[k]
            for q in range(64):
                c = abs(corr(par, out_cols[q]))
                if c > worst:
                    worst, at = c, (p, k, q)
    return worst, at


def gf2_span_contains(basis_masks, target: int) -> bool:
    """True iff target (an N-bit column) lies in the GF(2) span of the masks.

    basis_masks: list of N-bit ints; reduced on the fly to a pivot basis
    (highest set bit as pivot).  Exact test -- no statistics involved.
    """
    basis = {}  # pivot_bit -> mask
    for m in basis_masks:
        cur = m
        while cur:
            piv = cur.bit_length() - 1
            if piv in basis:
                cur ^= basis[piv]
            else:
                basis[piv] = cur
                break
    for piv in sorted(basis, reverse=True):
        if (target >> piv) & 1:
            target ^= basis[piv]
    return target == 0


def check_exact_linear(in_cols, out_cols):
    """[C4] Is any output bit an exact GF(2)-affine function of the inputs?

    With N samples > 65 unknowns (64 input bits + constant), an exact
    linear/affine relation leaves zero residual -- catches wide-fan-in
    GF(2) maps (CRC-like) that correlation checks cannot see.  Returns
    the number of linear output bits (0 = good).
    """
    basis_masks = list(in_cols) + [(1 << N) - 1]  # inputs + constant-1
    hits = 0
    for q in range(64):
        if gf2_span_contains(basis_masks, out_cols[q]):
            hits += 1
    return hits


def _columns_from_map(fn, rng):
    """Build (in_cols, out_cols) by sampling a 64->64 bit map fn."""
    in_cols = [0] * 64
    out_cols = [0] * 64
    for s in range(N):
        ci = rng.getrandbits(64)
        ri = fn(ci)
        for p in range(64):
            if (ci >> p) & 1:
                in_cols[p] |= 1 << s
            if (ri >> p) & 1:
                out_cols[p] |= 1 << s
    return in_cols, out_cols


def negative_control() -> int:
    """[C0] Three degenerate maps must ALL be caught -- canary self-proof.

    Affine ~C2 saturates order-1 correlation; wide-fan-in GF(2) linear
    and xor-tree fold ESCAPE C1-C3 (proven in review) but cannot escape
    the exact C4 linearity test.  Returns count of maps NOT caught.
    """
    rng = random.Random(SEED ^ 0xC0)
    caught = 0
    # (a) diagonal affine: ~C2 (the replaced W3 scheme)
    ic, oc = _columns_from_map(lambda v: v ^ ((1 << 64) - 1), rng)
    c1, _ = check_order1(ic, oc)
    if c1 > 0.99 or check_exact_linear(ic, oc) == 64:
        caught += 1
    # (b) wide-fan-in GF(2) linear map (CRC/LFSR-like realistic regression)
    rows = [rng.getrandbits(64) | 1 for _ in range(64)]
    ic, oc = _columns_from_map(lambda v: _gf2_apply(rows, v), rng)
    if check_exact_linear(ic, oc) == 64:
        caught += 1
    # (c) xor-tree fold: all 8 output bytes identical (byte 0 XOR of all)
    ic, oc = _columns_from_map(_xor_tree, rng)
    if check_exact_linear(ic, oc) == 64:
        caught += 1
    return 3 - caught  # escaped count (0 = all caught, as required)


def _gf2_apply(rows, v: int) -> int:
    out = 0
    for j, r in enumerate(rows):
        out |= (bin(r & v).count("1") & 1) << j
    return out


def _xor_tree(v: int) -> int:
    b = v.to_bytes(8, "big")
    x = b[0] ^ b[1] ^ b[2] ^ b[3] ^ b[4] ^ b[5] ^ b[6] ^ b[7]
    return int.from_bytes(bytes([x] * 8), "big")


def main() -> int:
    b1 = ORDER1_SIGMA / N ** 0.5
    b2 = ORDER2_SIGMA / N ** 0.5
    print("R2 nonlinearity canary (linear structure search)")
    print(f"  N={N} samples/key, bounds: order1 {ORDER1_SIGMA:.0f}s={b1:.4f} "
          f"order2 {ORDER2_SIGMA:.0f}s={b2:.4f}")
    escaped = negative_control()
    print(f"  [C0] negative controls (affine / wide-fan-in GF(2) / xor-tree): "
          f"{3 - escaped}/3 caught")
    if escaped:
        print(f"  [C0 FAIL] {escaped} degenerate map(s) escaped -- harness broken")
        return 1
    print("  [C0 PASS] all three linear degenerations are caught")

    ok = True
    for name, key in KEYS:
        # Per-key independent sample stream (review: sharing one C2 set
        # across keys couples the two checks to a single sample draw).
        rng = random.Random(SEED ^ int.from_bytes(key[0:8], "little"))
        cipher = Speck6496(key)
        in_cols, out_cols = sample_columns(cipher, rng)
        bal = check_balance(out_cols)
        c1, at1 = check_order1(in_cols, out_cols)
        c2, at2 = check_order2(in_cols, out_cols)
        lin = check_exact_linear(in_cols, out_cols)
        print(f"  key={name}: balance {bal:.2f}s (<= {BALANCE_SIGMA:.0f}s) | "
              f"order1 {c1:.4f} @bit{at1[0]}->{at1[1]} | "
              f"order2 {c2:.4f} @({at2[0]},{at2[1]})->{at2[2]} | "
              f"exact-linear bits {lin}/64")
        if bal > BALANCE_SIGMA:
            print(f"    [C1 FAIL] bit balance beyond {BALANCE_SIGMA:.0f} sigma")
            ok = False
        if c1 > b1:
            print(f"    [C2 FAIL] first-order correlation exceeds {b1:.4f}")
            ok = False
        if c2 > b2:
            print(f"    [C3 FAIL] second-order parity correlation exceeds {b2:.4f}")
            ok = False
        if lin:
            print(f"    [C4 FAIL] {lin} output bit(s) are exact affine "
                  f"functions of C2 -- R2 is linearly predictable")
            ok = False
    print("CANARY " + ("PASS: no affine/GF(2)-linear structure detected; "
                       "order-1/2 bit correlations within noise bounds"
                       if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
