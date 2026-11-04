# -*- coding: utf-8 -*-
import json, sys, itertools
sys.path.insert(0, r'D:\puf-drone-auth')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from src.python.evaluation.puf_model import decode_pair_table, N_RINGS

d = json.load(open(r'D:\puf-drone-auth\data\templates\templates.json', encoding='utf-8'))
tids = sorted(d.keys(), key=lambda x: int(x))

def reconstruct(t):
    wins = [0] * N_RINGS
    votes = {}
    for s_hex, r_hex in t.items():
        seed_int = int(s_hex, 16); resp = int(r_hex, 16)
        for r, pairs in enumerate(decode_pair_table(seed_int)):
            for p, (a_, b_) in enumerate(pairs):
                bit = (resp >> (63 - (r * 8 + p))) & 1
                winner = b_ if bit else a_
                wins[winner] += 1
                k = (min(a_, b_), max(a_, b_))
                votes.setdefault(k, {})
                votes[k][winner] = votes[k].get(winner, 0) + 1
    contrad = sum(1 for v in votes.values() if len(v) > 1)
    order = sorted(range(N_RINGS), key=lambda x: -wins[x])
    strict = all(wins[order[i]] > wins[order[i + 1]] for i in range(N_RINGS - 1))
    return order, len(votes), contrad, strict

def response_int(seed_int, rank):
    bits = 0
    for r, pairs in enumerate(decode_pair_table(seed_int)):
        for p, (a_, b_) in enumerate(pairs):
            if rank[b_] > rank[a_]:
                bits |= 1 << (63 - (r * 8 + p))
    return bits

orders = {}
print('== per-tid reconstruction ==')
for tid in tids:
    order, npairs, contrad, strict = reconstruct(d[tid])
    orders[tid] = order
    print(f'tid={tid}: n_seeds={len(d[tid])} unique_pairs={npairs}/120 contradictions={contrad} strict_order={strict}')

rank = {}
for tid, order in orders.items():
    rank[tid] = {ring: N_RINGS - 1 - pos for pos, ring in enumerate(order)}

print()
print('== order-based cross-template mismatch (predict j on i-order) ==')
for i, j in itertools.combinations(tids, 2):
    tot = 0; bits = 0
    for s_hex, r_hex in d[j].items():
        pred = response_int(int(s_hex, 16), rank[i])
        tot += 1; bits += bin(pred ^ int(r_hex, 16)).count('1')
    print(f'order[{i}] predicts tid={j}: mismatch={bits / (tot * 64):.4f} ({bits}/{tot*64})')
