# -*- coding: utf-8 -*-
import sys; sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import serial, time

A, B = "COM6", "COM11"
sa = serial.Serial(A, 115200, timeout=0.2)
sb = serial.Serial(B, 115200, timeout=0.2)
time.sleep(0.5)
sa.reset_input_buffer(); sb.reset_input_buffer()

def drain(s, secs=2.0):
    out = b""
    t0 = time.time()
    while time.time() - t0 < secs:
        n = s.in_waiting
        if n:
            out += s.read(n); t0 = time.time()
        else:
            time.sleep(0.05)
    return out

msg_a = b"PING_FROM_COM6_HELLO_AIR"
msg_b = b"PONG_FROM_COM11_ACK"

# A -> B
sa.write(msg_a)
r1 = drain(sb)
print(f"A({A}) sent: {msg_a}")
print(f"B({B}) recv: {r1!r}  => {"PASS" if r1 == msg_a else "FAIL"}")

# B -> A
sb.write(msg_b)
r2 = drain(sa)
print(f"B({B}) sent: {msg_b}")
print(f"A({A}) recv: {r2!r}  => {"PASS" if r2 == msg_b else "FAIL"}")

sa.close(); sb.close()
ok = (r1 == msg_a and r2 == msg_b)
print("WIRELESS_LINK_VERDICT:", "GRADUATED" if ok else "FAILED")