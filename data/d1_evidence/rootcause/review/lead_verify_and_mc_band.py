# -*- coding: utf-8 -*-
"""Lead 复验 + 预登记带宽 MC 立靶（共识修正循环的证据）
A. 复验 EXPERIMENT_LOG 系统级注入两处数字（repro 报告称 ±1%应=0、±5%应=7）
B. 用 tid=1 真实 enrolled 配对表，蒙特卡洛 2000 次「独立随机全序」的轮 HD(4种子) 分布
"""
import json, re, sys, random
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from src.python.evaluation.puf_model import decode_pair_table, N_RINGS

PPR = 8
def hd(x, y): return bin(x ^ y).count("1")

# ---- A. 复验 e_system_matrix ----
t = open(r"D:\puf-drone-auth\data\d1_evidence\rootcause\sim\e_system_matrix.log", encoding="utf-8", errors="replace").read()
blocks = re.split(r"#####\s+", t)
r1s = {}
for b in blocks:
    m = re.match(r"(\w+)\s*", b)
    if not m: continue
    name = m.group(1)
    vals = re.findall(r"INJECT_R1\s+([0-9A-Fa-f]+(?:\s+[0-9A-Fa-f]+)*)", b)
    if vals:
        flat = re.findall(r"[0-9A-Fa-f]{16}", vals[-1])
        if len(flat) >= 4:
            r1s[name] = [int(x, 16) for x in flat[:4]]
print("A. e_system_matrix 复验（各芯片 4×R1 对 base 的 HD）：")
base = r1s.get("base") or r1s.get("chip_base")
for name, arr in sorted(r1s.items()):
    if base and name != "base" and name != "chip_base":
        print(f"   {name}: per-seed={[hd(a,b) for a,b in zip(base,arr)]} total={sum(hd(a,b) for a,b in zip(base,arr))}")

# ---- B. 轮 HD 分布 MC（真实 enrolled 配对表） ----
d = json.load(open(ROOT / "data/templates/templates.json", encoding="utf-8"))
t1 = d["1"]
seeds = [int(s, 16) for s in t1.keys()]
tmpl = [int(r, 16) for r in t1.values()]
def response_int(seed_int, rank):
    bits = 0
    for r, pairs in enumerate(decode_pair_table(seed_int)):
        for p, (a, b) in enumerate(pairs):
            if rank[b] > rank[a]:
                bits |= 1 << (63 - (r * PPR + p))
    return bits
random.seed(1101)
rounds = []
for _ in range(2000):
    idx = random.sample(range(len(seeds)), 4)
    perm = list(range(N_RINGS)); random.shuffle(perm)
    rank2 = [0]*N_RINGS
    for pos, ring in enumerate(perm): rank2[ring] = N_RINGS-1-pos
    tot = sum(hd(response_int(seeds[i], rank2), tmpl[i]) for i in idx)
    rounds.append(tot)
rounds.sort()
n = len(rounds)
print(f"\nB. 独立随机全序 轮HD(4种子x64bit=256) MC x{n}: min={rounds[0]} p5={rounds[n//20]} 中位={rounds[n//2]} p95={rounds[19*n//20]} max={rounds[-1]} 均值={sum(rounds)/n:.1f}")
print(f"   落在 [90,170] 的比例: {sum(1 for x in rounds if 90<=x<=170)/n:.3f}；<64(REJECT线以下)比例: {sum(1 for x in rounds if x<64)/n:.4f}")
print("MC_BAND_OK")
