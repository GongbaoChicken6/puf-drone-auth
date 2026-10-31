# -*- coding: utf-8 -*-
"""D1 无线对验证：双口对发中继测试（动态端口版，2026-10-31）
用法: python 1031_relay_check.py <COM_A> <COM_B> <log_path>
判据: 双向各 ROUNDS 轮，收发字节完全一致 = 信道/波特率/FU3 透传全匹配
"""
import sys, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import serial

A, B = sys.argv[1], sys.argv[2]
LOG = open(sys.argv[3], "w", encoding="utf-8")

def log(s):
    print(s, flush=True)
    LOG.write(s + "\n"); LOG.flush()

log(f"=== 无线对验证 {A} <-> {B} @115200, {time.strftime('%Y-%m-%d %H:%M:%S')} ===")

sa = serial.Serial(A, 115200, timeout=0.2)
sb = serial.Serial(B, 115200, timeout=0.2)
time.sleep(0.5)
sa.reset_input_buffer(); sb.reset_input_buffer()

def drain(s, secs=1.5):
    out = b""; t0 = time.time()
    while time.time() - t0 < secs:
        n = s.in_waiting
        if n:
            out += s.read(n); t0 = time.time()
        else:
            time.sleep(0.05)
    return out

ROUNDS = 5
ok_ab = ok_ba = 0
for i in range(ROUNDS):
    ma = f"PING_R{i}_A2B".encode()
    sa.write(ma)
    r = drain(sb)
    good = (r == ma)
    ok_ab += good
    log(f"[{'PASS' if good else 'FAIL'}] R{i} {A}->{B}: sent {ma!r} recv {r!r}")

    mb = f"PONG_R{i}_B2A".encode()
    sb.write(mb)
    r2 = drain(sa)
    good2 = (r2 == mb)
    ok_ba += good2
    log(f"[{'PASS' if good2 else 'FAIL'}] R{i} {B}->{A}: sent {mb!r} recv {r2!r}")

sa.close(); sb.close()
verdict = (ok_ab == ROUNDS and ok_ba == ROUNDS)
log(f"RESULT: {ok_ab}/{ROUNDS} A->B, {ok_ba}/{ROUNDS} B->A")
log("WIRELESS_PAIR_VERDICT: " + ("GRADUATED (zero error both directions)" if verdict else "FAILED"))
LOG.close()
sys.exit(0 if verdict else 1)
