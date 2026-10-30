# -*- coding: utf-8 -*-
import sys; sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import serial, time

PORT, AT_BAUD = sys.argv[1], int(sys.argv[2])
ser = serial.Serial(PORT, AT_BAUD, timeout=0.3)
time.sleep(0.4)
ser.reset_input_buffer()

def cmd(s, expect_ok=True, wait=0.8):
    ser.reset_input_buffer()
    ser.write(s)
    time.sleep(wait)
    r = b""
    t0 = time.time()
    while time.time() - t0 < 0.5:
        n = ser.in_waiting
        if n: r += ser.read(n); t0 = time.time()
        else: time.sleep(0.05)
    status = "PASS" if (not expect_ok or b"OK" in r) else "FAIL"
    print(f"[{status}] {s!r} -> {r!r}")
    return b"OK" in r

ok = True
ok &= cmd(b"AT")
ok &= cmd(b"AT+FU3")
if AT_BAUD != 115200:
    ok &= cmd(b"AT+B115200")
ok &= cmd(b"AT+C006")
# 回读验证（波特率可能已变，重新开 115200）
ser.close()
time.sleep(0.3)
ser2 = serial.Serial(PORT, 115200, timeout=0.3)
time.sleep(0.4)
ser2.reset_input_buffer()
ser2.write(b"AT+RX")
time.sleep(0.6)
r = b""
t0 = time.time()
while time.time() - t0 < 1.0:
    n = ser2.in_waiting
    if n: r += ser2.read(n); t0 = time.time()
    else: time.sleep(0.05)
ser2.close()
print(f"AT+RX@115200 -> {r!r}")
all_ok = (b"B115200" in r and b"RC006" in r and b"FU3" in r)
print(f"PARAMS_CORRECT: {all_ok}")
print(f"OVERALL: {'PASS' if ok and all_ok else 'FAIL'}")