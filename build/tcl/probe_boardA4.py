"""Repeat 4-seed CHALLENGE probe on COM6; report response length each time."""
import sys, time
sys.path.insert(0, r"D:\puf-drone-auth")
import serial
from src.python.server.protocol import HFIDAProtocol

proto = HFIDAProtocol()
ser = serial.Serial("COM6", 115200, timeout=0.05)
expect = 12 + 8 * 4

for rep in range(6):
    seeds = [bytes([rep, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, i]) for i in range(4)]
    ch = proto.pack(HFIDAProtocol.MSG_CHALLENGE, terminal_id=1, seeds=seeds)
    ser.reset_input_buffer()
    ser.write(ch); ser.flush()
    buf = b""; t0 = time.time()
    while time.time() - t0 < 3.0:
        n = ser.in_waiting
        if n: buf += ser.read(n)
        else: time.sleep(0.005)
        # 短帧提前收尾:帧头够了就能算总数
        if len(buf) >= 2:
            total = 10 + buf[1] + 2
            if len(buf) >= total:
                break
    total_expected = (10 + buf[1] + 2) if len(buf) >= 2 else expect
    print(f"rep={rep} got={len(buf)}B header_len={buf[1] if len(buf)>1 else '-'} "
          f"needed={total_expected} {'OK' if len(buf)==total_expected else 'SHORT'} {buf.hex()[:110]}", flush=True)
    time.sleep(0.5)
ser.close()
print("PROBE4_DONE", flush=True)
