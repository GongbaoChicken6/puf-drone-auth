#!/usr/bin/env python3
"""mc_hd_curve.py -- ROOTCAUSE Monte Carlo: HD(chipB, chipA) vs per-ring silicon
mismatch magnitude, using the frozen golden model puf_model (bit-exact with RTL
per tb_puf_path). Base freq vector = repo fixture sim/testvectors/puf_tb_freqs.mem
(spread 3330..9507, mimicking the W1-measured on-board 3x RO spread).
Response set = the 4 golden challenge seeds A/B/C/D (256 bits, one board round).
"""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]   # data/d1_evidence/rootcause/sim -> 仓库根
sys.path.insert(0, str(ROOT))
from src.python.evaluation.puf_model import ROPairingPUF, decode_pair_table  # noqa: E402

mem = (ROOT / "sim" / "testvectors" / "puf_tb_freqs.mem").read_text().split()
base = [int(x, 16) for x in mem]
seeds = [0xC0FF_EEBE_EF12_3456, 0x0F1E_2D3C_4B5A_6978,
         0xFEED_FACE_CAFE_BABE, 0x1234_5678_9ABC_DEF0]

def responses(freqs):
    p = ROPairingPUF(freqs=freqs)
    return [int.from_bytes(p.ideal(s), "big") for s in seeds]

def hd(a, b):
    return sum(bin(x ^ y).count("1") for x, y in zip(a, b))

r_base = responses(base)
print("base freqs:", base)
print("base R1:", " ".join(f"{x:016x}" for x in r_base))

print("\n=== differential per-ring mismatch (chipB = base x (1+U(-k,k)%)) ===")
for k in (0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0):
    rng = random.Random(20261101)
    hds = []
    for _ in range(300):
        f2 = [max(1, round(f * (1 + rng.uniform(-k, k) / 100))) for f in base]
        hds.append(hd(r_base, responses(f2)))
    hds.sort()
    print(f"k={k:5.2f}%  mean HD={sum(hds)/len(hds):6.1f}/256  "
          f"min={hds[0]}  median={hds[len(hds)//2]}  max={hds[-1]}")

print("\n=== common-mode (all rings scaled, mismatch=0) ===")
for s in (1.05, 1.10, 0.90):
    f2 = [round(f * s) for f in base]
    print(f"scale={s}: HD={hd(r_base, responses(f2))}")

print("\n=== matched array (all rings equal counts) ===")
r_m = responses([5200] * 16)
print("R1:", " ".join(f"{x:016x}" for x in r_m), " HD vs base =", hd(r_base, r_m))
for s in (1.05, 0.95):
    r_m2 = responses([round(5200 * s)] * 16)
    print(f"matched x{s}: HD vs matched = {hd(r_m, r_m2)}  (chip-independent constant response)")

print("\n=== pair-gap structure of the base fixture (why small mismatch cannot flip bits) ===")
gaps = []
for s in seeds:
    for rnd in decode_pair_table(s):
        for a, b in rnd:
            gaps.append(abs(base[a] - base[b]) / max(base[a], base[b]) * 100)
gaps.sort()
n = len(gaps)
print(f"256 compared pairs: relative gap min={gaps[0]:.2f}%  p25={gaps[n//4]:.1f}%  "
      f"median={gaps[n//2]:.1f}%  p75={gaps[3*n//4]:.1f}%  max={gaps[-1]:.1f}%")
print(f"pairs with relative gap < 1%: {sum(1 for g in gaps if g < 1)} / 256")
print(f"pairs with relative gap < 2%: {sum(1 for g in gaps if g < 2)} / 256")
print(f"pairs with relative gap < 5%: {sum(1 for g in gaps if g < 5)} / 256")
