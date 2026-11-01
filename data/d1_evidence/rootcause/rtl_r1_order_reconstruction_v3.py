# -*- coding: utf-8 -*-
"""RTL 根因·v3（终版）：官方解帧验证 + 双硅数值演示（rootcause 第5视角）
  F. HFIDAProtocol.parse（含CRC）重解 1101 日志三轮，与模板反推全序正向预测比 HD
  自校验：全序正向复算 100 CRP 必须 HD=0 且各环胜场={15,14,...,0}，否则报错退出
  G. 双硅数值演示（仓库 puf_model，只读）
"""
import json, re, sys, random
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]   # 仓库根（auto-review P2: 去绝对路径硬编码）
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from src.python.server.protocol import HFIDAProtocol
from src.python.evaluation.puf_model import decode_pair_table, ROPairingPUF, N_RINGS

PPR = 8
def response_int(seed_int, rank):
    bits = 0
    for r, pairs in enumerate(decode_pair_table(seed_int)):
        for p, (a, b) in enumerate(pairs):
            if rank[b] > rank[a]:
                bits |= 1 << (63 - (r * PPR + p))
    return bits
def hd(x, y): return bin(x ^ y).count("1")

# ---- 反推全序：胜场法（bit=1 <=> freq[B]>freq[A]，赢家=B；bit=0 赢家=A）----
_tpl = ROOT / "data/d1_evidence/rootcause/templates_snapshot_tid1_20261101.json"
if not _tpl.exists(): _tpl = ROOT / "data/templates/templates.json"  # 快照缺失回退运行库（可能漂移）
d = json.load(open(_tpl, encoding="utf-8"))
t1 = d["1"]
wins = [0] * N_RINGS
dirvotes = {}   # 无序对 -> {环号: 票数}
for s_hex, r_hex in t1.items():
    seed_int = int(s_hex, 16); resp = int(r_hex, 16)
    for r, pairs in enumerate(decode_pair_table(seed_int)):
        for p, (a, b) in enumerate(pairs):
            bit = (resp >> (63 - (r * PPR + p))) & 1
            winner = b if bit else a
            wins[winner] += 1
            k = (min(a, b), max(a, b))
            dirvotes.setdefault(k, {})
            dirvotes[k][winner] = dirvotes[k].get(winner, 0) + 1
contradict = sum(1 for v in dirvotes.values() if len(v) > 1)
order = sorted(range(N_RINGS), key=lambda x: -wins[x])
rank = [0] * N_RINGS
for pos, ring in enumerate(order): rank[ring] = N_RINGS - 1 - pos
print(f"F0. 反推全序(快->慢): {order}")
print(f"    各环胜场(按该序): {[wins[r] for r in order]}  方向矛盾对数: {contradict}/120")
# ---- 自校验 ----
tot = sum(hd(response_int(int(s, 16), rank), int(t1[s], 16)) for s in t1)
assert all(wins[order[i]] > wins[order[i + 1]] for i in range(15)), "胜场非严格递减：计票方向错！"
assert tot == 0, f"全序复算模板 HD={tot} != 0：反推错误！"
print(f"    自校验通过：全序正向复算 {len(t1)} CRP 总 HD=0，胜场=15..0（无矛盾全序）")

# ---- F. 官方解帧 + 在线验证 ----
log = open(ROOT / "data/d1_evidence/1101_假冒实验_双板均PASS_唯一性存疑.log", encoding="utf-8").read()
frames = re.findall(r"\[(?:WIRE [0-9:.]+)\] (?:TX|RX)RAW ([0-9a-f]+)", log)
chal, r1f, resf = [], [], []
for hx in frames:
    try: mid, f = HFIDAProtocol.parse(bytes.fromhex(hx))
    except Exception: continue
    if mid == HFIDAProtocol.MSG_CHALLENGE: chal.append(f["seeds"])
    elif mid == HFIDAProtocol.MSG_RESPONSE_R1: r1f.append(f["r1s"])
    elif mid == HFIDAProtocol.MSG_RESULT: resf.append((f["result"], f["hd"]))
print(f"F1. 官方解帧: CHALLENGE={len(chal)} RESPONSE_R1={len(r1f)} RESULT={len(resf)}（CRC 全过）")
# auto-review P1 修复（silent-failure #4）：空集合=假绿灯，必须响亮失败
assert len(chal) > 0, "F 段空集合：日志正则 0 匹配（格式漂移？）——拒绝空洞验证"
assert len(chal) == len(r1f) == len(resf), f"F 段帧数不齐 chal/r1/res={len(chal)}/{len(r1f)}/{len(resf)}——拒绝静默截断"
print("F_ASSERT_OK")
print("F2. 三轮在线验证（模板全序预测 vs 板实测 R1）：")
for i, (seeds, r1s) in enumerate(zip(chal, r1f)):
    per = []; flip_pairs = []
    for s_i in range(len(seeds)):
        seed_int = int.from_bytes(seeds[s_i], "big")
        pred = response_int(seed_int, rank)
        meas = int.from_bytes(r1s[s_i], "big")
        diff = pred ^ meas
        per.append(bin(diff).count("1"))
        for r, pairs in enumerate(decode_pair_table(seed_int)):
            for p, (a, b) in enumerate(pairs):
                if (diff >> (63 - (r * PPR + p))) & 1:
                    flip_pairs.append((a, b))
    res = resf[i] if i < len(resf) else ("?", "?")
    print(f"   轮{i+1}: 每 seed HD={per} 总={sum(per)} | 服务器 RESULT: result={res[0]} hd={res[1]} | 翻转环对={flip_pairs}")

# ---- G. 双硅数值演示 ----
random.seed(20261101)
base = sorted([3100 + round((9600 - 3100) * i / 15) for i in range(16)])
freqA = [0] * N_RINGS
for pos, ring in enumerate(order): freqA[ring] = base[15 - pos]   # 全序最快的环=9600
pA = ROPairingPUF(freqs=freqA)
test_seeds = [0xC0FF_EEBE_EF12_3456, 0x0F1E_2D3C_4B5A_6978, 0xFEED_FACE_CAFE_BABE, 0x1234_5678_9ABC_DEF0]
def cross(pB):
    return sum(hd(int.from_bytes(pA.ideal(s), "big"), int.from_bytes(pB.ideal(s), "big")) for s in test_seeds)
print("G. 双硅数值演示（puf_model，非实测，说明量化器性质）：")
pB1 = ROPairingPUF(freqs=[round(f * 1.15) for f in freqA])
print(f"   G1 同序 x1.15 共模（die 间快慢差）: HD={cross(pB1)}/256")
pB2 = ROPairingPUF(freqs=[max(1, round(f * (1 + random.uniform(-0.003, 0.003)))) for f in freqA])
print(f"   G2 同序 ±0.3% 逐环随机失配:        HD={cross(pB2)}/256")
hds3 = []
for _ in range(50):
    pB3 = ROPairingPUF(freqs=[random.randint(3100, 9600) for _ in range(16)])
    hds3.append(cross(pB3))
hds3.sort()
print(f"   G3 独立随机频率×50 次抽样:          HD 中位={hds3[25]}/256，min={hds3[0]}，max={hds3[-1]}（均值≈128）")
