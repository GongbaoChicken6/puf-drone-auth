"""Raw 8-byte-seed CHALLENGE probe on COM6."""
import sys, time
sys.path.insert(0, r"D:\puf-drone-auth")
import serial
from src.python.server.protocol import HFIDAProtocol

proto = HFIDAProtocol()
ser = serial.Serial("COM6", 115200, timeout=0.05)
print("COM6 opened", flush=True)

seeds = [bytes.fromhex(s) for s in [
    "0011223344556677", "8899aabbccddeeff",
    "1021324354657687", "2031425364758697"]]
ch = proto.pack(HFIDAProtocol.MSG_CHALLENGE, terminal_id=1, seeds=seeds)
print("TX CHALLENGE len=%d %s" % (len(ch), ch.hex()), flush=True)
ser.reset_input_buffer()
ser.write(ch); ser.flush()
buf = b""; t0 = time.time()
while time.time() - t0 < 3.0:
    n = ser.in_waiting
    if n: buf += ser.read(n)
    else: time.sleep(0.005)
print("RX after challenge: %d B %s" % (len(buf), buf.hex() if buf else "(none)"), flush=True)
if len(buf) >= 12:
    try:
        mid, fl = proto.parse(buf[:10 + buf[1] + 2])
        print("  parsed msg=0x%04x" % mid, flush=True)
    except Exception as e:
        print("  parse err", e, flush=True)
ser.close()
print("PROBE2_DONE", flush=True)
