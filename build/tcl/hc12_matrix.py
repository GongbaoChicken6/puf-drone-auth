"""HC-12 full-direction loopback matrix at 115200 and 9600."""
import sys, time
try:
    import serial
except ImportError:
    print("no pyserial"); sys.exit(1)

PORTS = ["COM6", "COM9", "COM11"]
BAUDS = [115200, 9600]

for baud in BAUDS:
    print(f"\n########## baud {baud} ##########", flush=True)
    for txp in PORTS:
        others = [p for p in PORTS if p != txp]
        try:
            tx = serial.Serial(txp, baud, timeout=0.05)
        except Exception as e:
            print(f"TX {txp}: open fail {str(e)[:50]}", flush=True); continue
        rxs = {}
        for p in others:
            try: rxs[p] = serial.Serial(p, baud, timeout=0.05)
            except Exception as e: print(f"RX {p}: open fail {str(e)[:50]}", flush=True)
        time.sleep(0.15)
        for s in list(rxs.values()) + [tx]:
            try: s.reset_input_buffer()
            except Exception: pass
        payload = (txp + "-PING-").encode()
        tx.write(payload); tx.flush()
        t0 = time.time(); got = {p: b"" for p in rxs}
        while time.time() - t0 < 2.0:
            for p, s in rxs.items():
                n = s.in_waiting
                if n: got[p] += s.read(n)
            time.sleep(0.01)
        summary = ", ".join(f"{p}:{len(d)}B" for p, d in got.items()) or "(no open rx)"
        print(f"TX {txp} -> {summary}", flush=True)
        for s in list(rxs.values()) + [tx]:
            try: s.close()
            except Exception: pass
print("\nMATRIX_DONE", flush=True)
