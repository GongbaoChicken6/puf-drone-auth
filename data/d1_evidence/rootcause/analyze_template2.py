# -*- coding: utf-8 -*-
"""模板取证 v2：tid=1（真板）响应位统计 + 与演示tid对照 + 响应-挑战相关性"""
import json, sys, itertools
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

path = r"D:\puf-drone-auth\data\templates\templates.json"
d = json.load(open(path, encoding="utf-8"))

def bits(x, n=64):
    if isinstance(x, str):
        x = int(x, 16)
    return [(x >> (n - 1 - i)) & 1 for i in range(n)]

def hd(a, b):
    return sum(1 for x, y in zip(a, b) if x != y)

for tid in ["1", "7", "9", "55", "99"]:
    t = d[tid]
    chs = sorted(t.keys())
    resp_raw = [t[c] for c in chs]
    print(f"\n===== tid={tid}: {len(chs)} CRPs, 响应样例: {str(resp_raw[0])[:60]}")
    # 响应可能是 hex 字符串 / int / list——统一转位
    try:
        rb = [bits(r) for r in resp_raw]
    except Exception as e:
        print("  位转换失败:", e, "原始类型:", type(resp_raw[0])); continue
    ones = sum(sum(b) for b in rb) / (len(rb) * 64)
    print(f"  1 比例: {ones:.3f}（0.5=均衡）")
    # 两两 HD 分布（抽样全对）
    pairs = list(itertools.combinations(range(len(rb)), 2))
    hds = [hd(rb[i], rb[j]) for i, j in pairs]
    hds.sort()
    n = len(hds)
    print(f"  响应间两两HD: n={n} min={hds[0]} p25={hds[n//4]} 中位={hds[n//2]} p75={hds[3*n//4]} max={hds[-1]} 均值={sum(hds)/n:.1f}（64位随机期望32）")
    uniq = len(set(tuple(b) for b in rb))
    print(f"  不同响应个数: {uniq}/{len(rb)}")
    # 响应 vs 挑战 的 HD（查 response 是否 = 挑战本身的简单变换）
    cb = [bits(int(c, 16)) for c in chs]
    xh = [hd(cb[i], rb[i]) for i in range(len(chs))]
    xh.sort()
    print(f"  挑战-响应HD: min={xh[0]} 中位={xh[len(xh)//2]} max={xh[-1]}（若恒0/恒64=直接变换）")
    # 逐位一致性：跨挑战每个响应位的翻转率（若某些位从不变化=弱熵位）
    flip = [sum(rb[k][i] for k in range(len(rb))) / len(rb) for i in range(64)]
    stuck0 = sum(1 for f in flip if f == 0.0); stuck1 = sum(1 for f in flip if f == 1.0)
    print(f"  跨挑战恒0位: {stuck0}, 恒1位: {stuck1}, 翻转率范围: {min(flip):.2f}~{max(flip):.2f}")
