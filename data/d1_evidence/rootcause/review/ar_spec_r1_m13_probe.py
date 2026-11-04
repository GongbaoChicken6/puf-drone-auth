# -*- coding: utf-8 -*-
import json, sys, itertools
sys.path.insert(0, r'D:\puf-drone-auth')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from src.python.evaluation.puf_model import decode_pair_table, N_RINGS

d = json.load(open(r'D:\puf-drone-auth\data\templates\templates.json', encoding='utf-8'))
print('TIDS:', sorted(d.keys(), key=lambda x: int(x)))
for tid, t in d.items():
    resp_ints = [int(r, 16) for r in t.values()]
    uni = sum(bin(v).count('1') for v in resp_ints) / (len(resp_ints) * 64)
    print(f'tid={tid}: n_seeds={len(t)} uniformity={uni:.4f}')

tids = sorted(d.keys(), key=lambda x: int(x))
print()
print('== cross-tid shared seeds ==')
for a, b in itertools.combinations(tids, 2):
    shared = set(d[a]) & set(d[b])
    tag = ''
    if shared:
        hds = [bin(int(d[a][s], 16) ^ int(d[b][s], 16)).count('1') for s in shared]
        tag = f' HD_shared_mean={sum(hds)/len(hds)/64:.4f} (n={len(hds)})'
    print(f'{a} vs {b}: shared={len(shared)}{tag}')

print()
print('== rank-order reconstruction per tid (win-count, like v3) ==')
for tid in tids:
    t = d[tid]
    wins = [0] * N_RINGS
    dirvotes = {}
    ok = True
    try:
        for s_hex, r_hex in t.items():
            seed_int = int(s_hex, 16); resp = int(r_hex, 16)
            for r, pairs in enumerate(decode_pair_table(seed_int)):
                for p, (a_, b_) in enumerate(pairs):
                    bit = (resp >> (63 - (r * 8 + p))) & 1
                    winner = b_ if bit else a_
                    wins[winner] += 1
                    k = (min(a_, b_), max(a_, b_))
                    cur = dirvotes.get(k, winner)
                    if cur != winner: ok = False
        order = sorted(range(N_RINGS), key=lambda x: -wins[x])
        n_pairs_obs = len(dirvotes)
        strict = all(wins[order[i]] > wins[order[i+1]] for i in range(N_RINGS-1))
        print(f'tid={tid}: pairs_observed={n_pairs_obs}/120 contradictions={not ok} strict_win_order={strict}')
        print(f'   order={order}')
    except Exception as e:
        print(f'tid={tid}: ERROR {e}')
