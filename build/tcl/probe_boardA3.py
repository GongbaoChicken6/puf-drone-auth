"""Repeat CHALLENGE probes with 1/2/4 seeds; check response length consistency."""
import sys, time
sys.path.insert(0, r"D:\puf-drone-auth")
import serial
from src.python.server.protocol import HFIDAProtocol

proto = HFIDAProtocol()
ser = serial.Serial("COM6", 115200, timeout=0.05)

def probe(nseeds, tag):
    seeds = [bytes([i, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77]) for i in range(nseeds)]
    ch = proto.pack(HFIDAProtocol.MSG_CHALLENGE, terminal_id=1, seeds=seeds)
    expect = 12 + 8 * nseeds
    ser.reset_input_buffer()
    ser.write(ch); ser.flush()
    buf = b""; t0 = time.time()
    while time.time() - t0 < 3.0 and len(buf) < expect:
        n = ser.in_waiting
        if n: buf += ser.read(n)
        else: time.sleep(0.005)
    return expect, len(buf), buf.hex()

for nseeds in (1, 2, 4):
    for rep in range(3):
        exp, got, hx = probe(nseeds, nseeds)
        ok = "OK" if got == exp else ("SHORT" if got < exp else "LONG")
        print(f"seeds={nseeds} rep={rep} expect={exp} got={got} {ok} {hx[:96]}", flush=True)
        time.sleep(0.3)
ser.close()
print("PROBE3_DONE", flush=True)
