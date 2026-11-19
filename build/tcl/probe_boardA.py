"""Raw CHALLENGE probe on COM6: does board A answer RESPONSE_R1?"""
import sys, time
sys.path.insert(0, r"D:\puf-drone-auth")
sys.path.insert(0, r"D:\puf-drone-auth\web\bridge")
import serial
from src.python.server.protocol import HFIDAProtocol

proto = HFIDAProtocol()
ser = serial.Serial("COM6", 115200, timeout=0.05)
print("COM6 opened", flush=True)

# 1) AUTH_POLL -> expect ACCESS_REQUEST
ser.reset_input_buffer()
fr = proto.pack(HFIDAProtocol.MSG_AUTH_POLL, terminal_id=1, nonce=time.time_ns() & 0xFFFFFFFF)
ser.write(fr); ser.flush()
print("TX AUTH_POLL", fr.hex(), flush=True)
buf = b""; t0 = time.time()
while time.time() - t0 < 3.0:
    n = ser.in_waiting
    if n: buf += ser.read(n)
    else: time.sleep(0.005)
print("RX after poll:", len(buf), "B", buf.hex() if buf else "(none)", flush=True)
if len(buf) >= 12:
    try:
        mid, fl = proto.parse(buf[:28])
        print("  parsed msg=0x%04x tid=%s c2=%s" % (mid, fl.get("terminal_id"), fl.get("c2", b"").hex()), flush=True)
    except Exception as e:
        print("  parse err", e, flush=True)

# 2) CHALLENGE with 4 seeds (like the bridge)
seeds = [bytes.fromhex(s) for s in [
    "00112233445566778899aabbccddeeff",
    "102132435465768798a9baccbdcedeff",
    "2031425364758697a8b9cadbecfd0e1f",
    "30415263748596a7b8c9dae bfc0d1e2f".replace(" ", ""),
]]
try:
    ch = proto.pack(HFIDAProtocol.MSG_CHALLENGE, terminal_id=1, seeds=seeds)
except Exception as e:
    print("challenge build err:", e, flush=True)
    # fallback: 16-byte seeds?
    seeds = [b"\x00" * 16 for _ in range(4)]
    ch = proto.pack(HFIDAProtocol.MSG_CHALLENGE, terminal_id=1, seeds=seeds)
print("TX CHALLENGE", ch.hex(), flush=True)
ser.reset_input_buffer()
ser.write(ch); ser.flush()
buf2 = b""; t0 = time.time()
while time.time() - t0 < 3.0:
    n = ser.in_waiting
    if n: buf2 += ser.read(n)
    else: time.sleep(0.005)
print("RX after challenge:", len(buf2), "B", buf2.hex() if buf2 else "(none)", flush=True)
ser.close()
print("PROBE_DONE", flush=True)
