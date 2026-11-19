"""Raw multi-port sniffer: capture any bytes on PC-side serial ports."""
import sys, time, threading

PORTS = ["COM6", "COM9", "COM11"]
BAUD = 115200
DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
OUT = r"D:\puf-drone-auth\build\logs\raw_sniff.log"

try:
    import serial
except ImportError:
    print("no pyserial"); sys.exit(1)

log_lock = threading.Lock()
f = open(OUT, "w", encoding="utf-8")

def log(msg):
    with log_lock:
        print(msg, flush=True)
        f.write(msg + "\n"); f.flush()

def listen(port_name):
    try:
        ser = serial.Serial(port_name, BAUD, timeout=0.05)
    except Exception as e:
        log(f"[{port_name}] OPEN FAIL: {str(e)[:80]}")
        return
    log(f"[{port_name}] listening @{BAUD} for {DUR:.0f}s")
    t0 = time.time()
    total = 0
    while time.time() - t0 < DUR:
        try:
            n = ser.in_waiting
        except Exception as e:
            log(f"[{port_name}] lost: {e}")
            break
        if n:
            data = ser.read(n)
            total += len(data)
            log(f"[{port_name}] +{len(data)}B @{time.time()-t0:.2f}s: {data.hex()}")
        else:
            time.sleep(0.005)
    log(f"[{port_name}] done, total {total} bytes")
    ser.close()

threads = [threading.Thread(target=listen, args=(p,), daemon=True) for p in PORTS]
for t in threads: t.start()
for t in threads: t.join(timeout=DUR + 5)
f.close()
print("SNIFF_DONE", flush=True)
