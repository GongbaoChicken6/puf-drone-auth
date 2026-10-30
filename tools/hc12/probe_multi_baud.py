# -*- coding: utf-8 -*-
import sys; sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import serial, time
PORT = sys.argv[1]
for baud in [115200, 9600, 4800, 1200, 2400]:
    try:
        ser = serial.Serial(PORT, baud, timeout=0.3)
        time.sleep(0.3)
        ser.reset_input_buffer()
        ser.write(b"AT+RX")
        time.sleep(0.6)
        r = b""
        t0 = time.time()
        while time.time() - t0 < 0.8:
            n = ser.in_waiting
            if n: r += ser.read(n); t0 = time.time()
            else: time.sleep(0.05)
        ser.close()
        if r:
            print(f"{PORT}@{baud} AT+RX -> {r!r}")
            if b"OK+" in r:
                print(f"FOUND_AT @{baud}")
                break
        else:
            print(f"{PORT}@{baud} -> (empty)")
    except Exception as e:
        print(f"{PORT}@{baud} -> ERROR {e}")