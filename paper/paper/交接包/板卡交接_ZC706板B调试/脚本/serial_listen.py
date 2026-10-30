import serial, time, sys
port, baud, dur = "COM6", 115200, 300
out = r"D:\文件\ssssssss\FPGA\_tmp\serial_capture.bin"
log = r"D:\文件\ssssssss\FPGA\_tmp\serial_capture.txt"
s = serial.Serial(port, baud, timeout=1)
buf = bytearray()
t0 = time.time()
with open(log, "w", encoding="utf-8") as f:
    f.write(f"listening {port}@{baud} for {dur}s\n")
    while time.time() - t0 < dur:
        data = s.read(256)
        if data:
            buf += data
            f.write(f"[{time.time()-t0:7.2f}s] {len(data)}B HEX: {data.hex(' ')}\n")
            f.flush()
    f.write(f"TOTAL {len(buf)} bytes\n")
s.close()
print(f"DONE total={len(buf)} bytes")
