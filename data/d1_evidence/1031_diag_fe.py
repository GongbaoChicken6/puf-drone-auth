# -*- coding: utf-8 -*-
"""0xFE 杂散字节定位实验（2026-10-31 22:53）
T1: COM6 连发两次，只听 COM9（若 0xFE 总在 COM6 发射的载荷前 => COM6 侧发射带前缀）
T2: COM9 连发两次，同时听 COM6 和 COM9 自身（若 0xFE 在 COM9 自己发完后出现在自身 RX => 自发自收回声）
"""
import sys, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import serial

A, B = "COM6", "COM9"
sa = serial.Serial(A, 115200, timeout=0.2)
sb = serial.Serial(B, 115200, timeout=0.2)
time.sleep(0.5)
sa.reset_input_buffer(); sb.reset_input_buffer()

def drain(s, secs=2.0):
    out = b""; t0 = time.time()
    while time.time() - t0 < secs:
        n = s.in_waiting
        if n:
            out += s.read(n); t0 = time.time()
        else:
            time.sleep(0.02)
    return out

print("--- T1: COM6 发, COM9 听 (x2) ---")
sa.write(b"T1_PING_A")
r_self_a = drain(sa, 2); r_b = drain(sb, 2)
print(f"COM6 self after TX#1: {r_self_a.hex()} | COM9 recv: {r_b.hex()}")
sa.write(b"T1_PING_B")
r_self_a2 = drain(sa, 2); r_b2 = drain(sb, 2)
print(f"COM6 self after TX#2: {r_self_a2.hex()} | COM9 recv: {r_b2.hex()}")

print("--- T2: COM9 发, 双侧听 (x2) ---")
sb.write(b"T2_PONG_A")
r_self_b = drain(sb, 2); r_a = drain(sa, 2)
print(f"COM9 self after TX#1: {r_self_b.hex()} | COM6 recv: {r_a.hex()}")
sb.write(b"T2_PONG_B")
r_self_b2 = drain(sb, 2); r_a2 = drain(sa, 2)
print(f"COM9 self after TX#2: {r_self_b2.hex()} | COM6 recv: {r_a2.hex()}")

sa.close(); sb.close()
