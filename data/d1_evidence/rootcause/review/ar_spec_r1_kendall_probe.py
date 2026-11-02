# -*- coding: utf-8 -*-
import json, sys, itertools, random
sys.path.insert(0, r'D:\puf-drone-auth')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from src.python.evaluation.puf_model import decode_pair_table, N_RINGS

d = json.load(open(r'D:\puf-drone-auth\data\templates\templates.json', encoding='utf-8'))
tids = sorted(d.keys(), key=lambda x: int(x))

def reconstruct(t):
    wins = [0] * N_RINGS
    for s_hex, r_hex in t.items():
        seed_int = int(s_hex, 16); resp = int(r_hex, 16)
        for r, pairs in enumerate(decode_pair_table(seed_int)):
            for p, (a_, b_) in enumerate(pairs):
                bit = (resp >> (63 - (r * 8 + p))) & 1
                wins[b_ if bit else a_] += 1
    return sorted(range(N_RINGS), key=lambda x: -wins[x])

def agreement(o1, o2):
    r1 = {ring: pos for pos, ring in enumerate(o1)}
    r2 = {ring: pos for pos, ring in enumerate(o2)}
    same = sum(1 for a_, b_ in itertools.combinations(range(N_RINGS), 2)
               if (r1[a_] < r1[b_]) == (r2[a_] < r2[b_]))
    return same / 120.0

orders = {tid: reconstruct(d[tid]) for tid in tids}
print('== real-template pairwise Kendall agreement ==')
for a, b in itertools.combinations(tids, 2):
    print(f'  {a} vs {b}: {agreement(orders[a], orders[b]):.4f}')

random.seed(20261102)
base = list(range(N_RINGS))
ags = []
for _ in range(2000):
    o1 = random.sample(base, N_RINGS); o2 = random.sample(base, N_RINGS)
    ags.append(agreement(o1, o2))
ags.sort()
import statistics
print()
print(f'== MC 2000 random order pairs: mean={statistics.mean(ags):.4f} stdev={statistics.stdev(ags):.4f} max={ags[-1]:.4f} p999={ags[int(0.999*len(ags))-1]:.4f}')
print(f'   gaussian sigma=sqrt(0.25/120)={0.5/ (120**0.5):.4f}; P(ag>0.75) empirical = {sum(1 for a in ags if a > 0.75)}/{len(ags)}')

o = orders['1']
pos = {ring: i for i, ring in enumerate(o)}
print()
print('== clone simulation on tid=1 order ==')
print(f'  original order: {o}')
i79 = pos[9]
clone = list(o); clone[i79 - 1], clone[i79] = clone[i79], clone[i79 - 1]  # swap adjacent 7/9
print(f'  swap {{7,9}} (adjacent): agreement={agreement(o, clone):.4f} (=119/120)')
for k, (x, y) in enumerate([(4, 11), (12, 8), (14, 6)]):
    c = list(o); px, py = pos[x], pos[y]
    c[px], c[py] = c[py], c[px]
    print(f'  swap non-adjacent {{{x},{y}}}: agreement={agreement(o, c):.4f}')
