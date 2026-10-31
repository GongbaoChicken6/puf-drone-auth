# -*- coding: utf-8 -*-
"""D1 A对毕业测试（容错判据版，2026-10-31 22:54）
已知现象: CH340 侧模块发射后有 1 字节 0xFE 自回声（供电毛刺，FPGA 解析器 S_SEARCH 态静默容忍）
判据: 剥离杂散 0xFE 后载荷必须逐字节完好; 统计严格/容错双判据
"""
import sys, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import serial

A, B = "COM6", "COM9"
LOG = open(sys.argv[1], "w", encoding="utf-8")
def log(s):
    print(s, flush=True)
    LOG.write(s + "\n"); LOG.flush()

log(f"=== A对毕业测试(容错判据) {A} <-> {B} @115200, {time.strftime('%H:%M:%S')} ===")
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
            time.sleep(0.02)
    return out

ROUNDS = 10
strict_ab = tol_ab = strict_ba = tol_ba = echo_cnt = 0
for i in range(ROUNDS):
    ma = f"GRAD_PING_R{i}".encode()
    sa.write(ma)
    r = drain(sb)
    s_ok = (r == ma)
    t_ok = (r.replace(b"\xfe", b"") == ma)
    strict_ab += s_ok; tol_ab += t_ok; echo_cnt += r.count(0xFE)
    log(f"R{i} {A}->{B}: {r.hex()} strict={s_ok} tolerant={t_ok}")

    mb = f"GRAD_PONG_R{i}".encode()
    sb.write(mb)
    r2 = drain(sa)
    s2 = (r2 == mb); t2 = (r2.replace(b"\xfe", b"") == mb)
    strict_ba += s2; tol_ba += t2; echo_cnt += r2.count(0xFE)
    log(f"R{i} {B}->{A}: {r2.hex()} strict={s2} tolerant={t2}")

sa.close(); sb.close()
log(f"RESULT: A->B strict {strict_ab}/{ROUNDS} tolerant {tol_ab}/{ROUNDS} | B->A strict {strict_ba}/{ROUNDS} tolerant {tol_ba}/{ROUNDS} | 杂散0xFE共 {echo_cnt} 个")
verdict = (tol_ab == ROUNDS and tol_ba == ROUNDS)
log("WIRELESS_PAIR_VERDICT: " + ("GRADUATED (双向载荷零误码, 容忍已知0xFE自回声)" if verdict else "FAILED"))
LOG.close()
sys.exit(0 if verdict else 1)
