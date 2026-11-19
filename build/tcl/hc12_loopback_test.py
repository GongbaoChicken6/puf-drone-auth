"""HC-12 air-link self test: TX from COM6, RX on COM9/COM11 at several bauds."""
import sys, time

try:
    import serial
except ImportError:
    print("no pyserial"); sys.exit(1)

TX_PORT = "COM6"
RX_PORTS = ["COM9", "COM11"]
BAUDS = [115200, 9600]
PAYLOAD = b"\xfdHC12TEST12345"

for baud in BAUDS:
    print(f"\n=== baud {baud} ===", flush=True)
    rxs = {}
    for p in RX_PORTS:
        try:
            rxs[p] = serial.Serial(p, baud, timeout=0.05)
        except Exception as e:
            print(f"  {p} open fail: {str(e)[:60]}")
    try:
        tx = serial.Serial(TX_PORT, baud, timeout=0.05)
    except Exception as e:
        print(f"  {TX_PORT} open fail: {str(e)[:60]}")
        for s in rxs.values(): s.close()
        continue
    for s in list(rxs.values()) + [tx]:
        try: s.reset_input_buffer()
        except Exception: pass
    time.sleep(0.2)
    tx.write(PAYLOAD); tx.flush()
    print(f"  TX {TX_PORT} -> {PAYLOAD!r}", flush=True)
    t0 = time.time()
    got = {p: b"" for p in rxs}
    while time.time() - t0 < 3.0:
        for p, s in rxs.items():
            n = s.in_waiting
            if n:
                got[p] += s.read(n)
        time.sleep(0.01)
    for p, d in got.items():
        print(f"  RX {p}: {len(d)}B {d!r}", flush=True)
    for s in list(rxs.values()) + [tx]:
        try: s.close()
        except Exception: pass
print("\nLOOPBACK_TEST_DONE", flush=True)
