import sys, struct, random
sys.path.insert(0, r'D:\puf-drone-auth\src\python\common')
from speck import Speck6496

def to_w(kb, pb):
    k0, l0, l1 = struct.unpack('<III', kb)
    x, y = struct.unpack('<II', pb)
    return (l1 << 64) | (l0 << 32) | k0, (y << 32) | x

def ct_w(ctb):
    x, y = struct.unpack('<II', ctb)
    return (y << 32) | x

print('--- vectors hardcoded in tb_speck.v (verify golden values) ---')
for name, kb, pb in [
    ('KAT ', bytes.fromhex('131211100b0a090803020100'), bytes.fromhex('74614620736e6165')),
    ('ZERO', bytes(12), bytes(8)),
    ('FF  ', bytes([0xFF]*12), bytes([0xFF]*8)),
]:
    ki, pi = to_w(kb, pb)
    print('%s key_in=0x%024x pt_in=0x%016x exp_ct=0x%016x' % (name, ki, pi, ct_w(Speck6496(kb).encrypt(pb))))

print('--- golden vectors for MISSING tests (alternating / carry-chain / key-schedule isolation) ---')
for name, kb, pb in [
    ('ALT5 ', bytes.fromhex('555555555555555555555555'), bytes.fromhex('5555555555555555')),
    ('ALTA ', bytes.fromhex('aaaaaaaaaaaaaaaaaaaaaaaa'), bytes.fromhex('aaaaaaaaaaaaaaaa')),
    ('CARRY', bytes.fromhex('ffffffffffffffffffffffff'), bytes.fromhex('0000000000000001')),
    ('CARRY2', bytes.fromhex('000000010000000000000000'), bytes.fromhex('ffffffffffffffff')),
    ('ONEK ', bytes.fromhex('000000000000000000000001'), bytes(8)),
    ('KSW1 ', bytes.fromhex('00000000131211100b0a0908'), bytes.fromhex('74614620736e6165')),
]:
    ki, pi = to_w(kb, pb)
    print('%s key_in=0x%024x pt_in=0x%016x exp_ct=0x%016x' % (name, ki, pi, ct_w(Speck6496(kb).encrypt(pb))))

print('--- first 5 seeded-random vectors (seed 20261006) for the T4 .mem file ---')
rng = random.Random(20261006)
for i in range(5):
    kb = bytes(rng.randrange(256) for _ in range(12))
    pb = bytes(rng.randrange(256) for _ in range(8))
    ki, pi = to_w(kb, pb)
    print('RND%03d key_in=0x%024x pt_in=0x%016x exp_ct=0x%016x' % (i, ki, pi, ct_w(Speck6496(kb).encrypt(pb))))
