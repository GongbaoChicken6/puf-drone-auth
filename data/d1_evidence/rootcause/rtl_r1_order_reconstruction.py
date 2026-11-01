# -*- coding: utf-8 -*-
"""RTL 根因·决定性数值验证：模板 100 CRP 反推 16 环频率全序（rootcause 第5视角）
问题：响应位是否 = f(挑战种子, 单一固定环序)？
方法：
  A. 镜像 puf_model.py / challenge_decode.v 的冻结语义，把每个 seed 解成 8x8 对 (A,B)
  B. 响应位=1 <=> freq[B]>freq[A] -> 收集 6400 个二元比较，检验能否由一个全序一致解释
  C. 用反推出的全序正向复算模板，逐位比对；再用日志(1101)里 3 组在线挑战种子
     正向预测 R1，与板上实测 R1 比 HD
只读 templates.json 与证据日志；产物仅打印（本脚本即证据，可复跑）。
【已废弃 2026-11-01 auto-review】以 rtl_r1_order_reconstruction_v3.py 为准：本 v1 第 114 行实测 R1 字面量抄录损坏（66 hex 字符，重跑该轮 HD=97 与 v3 官方解帧/服务器 RESULT=3 矛盾）；全序反推部分与 v3 一致，仍可参考。
"""
import json, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

N_RINGS, N_ROUNDS, PPR = 16, 8, 8
MASK64 = (1 << 64) - 1

def lfsr_step(s):
    fb = ((s >> 63) ^ (s >> 62) ^ (s >> 60) ^ (s >> 59)) & 1
    return ((s << 1) | fb) & MASK64

def decode_pairs(seed_int):
    """镜像 challenge_decode.v：每轮 Fisher-Yates，pair p=(order[2p],order[2p+1])"""
    lfsr = seed_int
    rounds = []
    for _ in range(N_ROUNDS):
        order = list(range(N_RINGS))
        for i in range(N_RINGS - 1, 0, -1):
            draw = (lfsr >> 56) & 0xFF
            for _ in range(8):
                lfsr = lfsr_step(lfsr)
            j = draw % (i + 1)
            order[i], order[j] = order[j], order[i]
        rounds.append([(order[2 * p], order[2 * p + 1]) for p in range(PPR)])
    return rounds

def response_bits(seed_int, rank):
    """rank[r]：环 r 的频率名次（越大越快）。bit(r,p)=1 <=> freq[B]>freq[A]"""
    bits = 0
    for r, pairs in enumerate(decode_pairs(seed_int)):
        for p, (a, b) in enumerate(pairs):
            if rank[b] > rank[a]:
                bits |= 1 << (63 - (r * PPR + p))
    return bits

def hd(x, y):
    return bin(x ^ y).count("1")

d = json.load(open(r"D:\puf-drone-auth\data\templates\templates.json", encoding="utf-8"))
t1 = d["1"]
seeds = sorted(t1.keys())
print(f"A. tid=1 模板：{len(seeds)} CRP")

# ---- B. 收集比较观测 ----
obs = {}   # (a,b) a<b -> {'ab':n_ab(说 a>b 的次数), 'ba':n_ba}
one_ratio_bits = 0
total_bits = 0
for s_hex in seeds:
    seed_int = int(s_hex, 16)
    resp = int(t1[s_hex], 16)
    for r, pairs in enumerate(decode_pairs(seed_int)):
        for p, (a, b) in enumerate(pairs):
            bit = (resp >> (63 - (r * PPR + p))) & 1
            one_ratio_bits += bit
            total_bits += 1
            k = (min(a, b), max(a, b))
            obs.setdefault(k, {"ab": 0, "ba": 0})
            if bit:  # freq[b] > freq[a]
                if a < b: obs[k]["ba"] += 1   # b>a，即大号快
                else:    obs[k]["ab"] += 1   # (a>b 时 a 是大号？注意) —— 见下修正
            else:      # freq[a] >= freq[b]
                if a < b: obs[k]["ab"] += 1
                else:    obs[k]["ba"] += 1
# 上面分支化简后等价于：obs 记录"较大环号更快"与"较小环号更快"的票数
contradictions = sum(1 for k, v in obs.items() if v["ab"] > 0 and v["ba"] > 0)
mismatch_votes = sum(min(v["ab"], v["ba"]) for v in obs.values())
total_votes = sum(v["ab"] + v["ba"] for v in obs.values())
print(f"B. 比较观测：{total_votes} 次，覆盖 {len(obs)}/{N_RINGS*(N_RINGS-1)//2} 个无序环对")
print(f"   1 比例：{one_ratio_bits/total_bits:.4f}（0.5=均衡）")
print(f"   矛盾对数（同对两方向都有票）：{contradictions}，矛盾票占比：{mismatch_votes/total_votes:.5f}")

# ---- C. 构造支配图 -> 全序（矛盾票按多数决） ----
# rank 简单求法：净胜场排序（每对赢的环得 1）
wins = [0] * N_RINGS
for (a, b), v in obs.items():  # a<b
    # ab 票数=小号快，ba 票数=大号快
    if v["ba"] > v["ab"]: wins[b] += 1
    else:                 wins[a] += 1
order = sorted(range(N_RINGS), key=lambda x: -wins[x])
rank = [0] * N_RINGS
for pos, ring in enumerate(order):
    rank[ring] = N_RINGS - 1 - pos  # 最快环 rank=15
print(f"C. 反推全序（快->慢）：{order}")
print(f"   净胜场：{[wins[r] for r in order]}（若与 15,13,11,... 一致=全序成立）")

# ---- D. 用该全序正向复算 100 CRP，逐位比 HD ----
tot_hd = 0
worst = 0
per_hd = []
for s_hex in seeds:
    seed_int = int(s_hex, 16)
    pred = response_bits(seed_int, rank)
    h = hd(pred, int(t1[s_hex], 16))
    per_hd.append(h); tot_hd += h; worst = max(worst, h)
print(f"D. 全序正向复算 100 CRP：总 HD={tot_hd}，最大单 CRP HD={worst}（0=模板可被单一全序完全解释）")

# ---- E. 日志在线轮正向预测 ----
# (挑战帧载荷种子, 实测 R1 载荷) 取自 1101 log TXRAW 0x0091 / RXRAW 0x0092
wire = [
    ("e60cc4d56170bae4b16cd3e699d114939a2232770703934bc979f436b3433221b84d",
     "99a8e6a42c9412ce0f11b66f26b3ab96d86d365aaa35591644136554cbaa1336"),
    ("e0e5477db8b8577f36942ad08f3419effa7c726f6490ba55d4606289d23f6be56af5",
     "268edfa0af3024c904cfb24adc35725bb297399bd5a1373e451b741ace692b92d2"),
    ("3fd12d05091d83b5e79b894a0033447af3811dbdf3b953ef8c14d32d6aad66526fbd",
     "535ab24b19d175551c30413a99d110bd1efdabaf27bcf886986f102c61626742c0"),
]
print("E. 1101 日志 3 轮在线验证（模板全序 vs 板上实测 R1）：")
for i, (chal_hex, r1_hex) in enumerate(wire):
    chal = bytes.fromhex(chal_hex)
    r1_meas = bytes.fromhex(r1_hex)
    tot = 0
    per = []
    for s_i in range(4):
        seed_int = int.from_bytes(chal[8*s_i:8*s_i+8], "big")
        pred = response_bits(seed_int, rank).to_bytes(8, "big")
        h = hd(int.from_bytes(pred, "big"), int.from_bytes(r1_meas[8*s_i:8*s_i+8], "big"))
        per.append(h); tot += h
    print(f"   轮{i+1}: 每 seed HD={per}，总 HD={tot}")
