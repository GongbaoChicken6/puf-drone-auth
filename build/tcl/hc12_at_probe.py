"""Probe each port for HC-12 AT-mode response (SET grounded => responds OK)."""
import sys, time
try:
    import serial
except ImportError:
    print("no pyserial"); sys.exit(1)

PORTS = ["COM6", "COM9", "COM11"]

for p in PORTS:
    for baud in (9600, 115200):
        try:
            s = serial.Serial(p, baud, timeout=0.3)
        except Exception as e:
            print(f"[{p}@{baud}] open fail: {str(e)[:60]}", flush=True)
            continue
        try:
            s.reset_input_buffer()
            s.write(b"AT")
            time.sleep(0.4)
            r = s.read(200)
            s.write(b"AT+RX")
            time.sleep(0.5)
            r2 = s.read(300)
            print(f"[{p}@{baud}] AT -> {r!r} | AT+RX -> {r2!r}", flush=True)
        except Exception as e:
            print(f"[{p}@{baud}] err {e}", flush=True)
        finally:
            s.close()
print("AT_PROBE_DONE", flush=True)
