import serial, time
port, baud = "COM6", 115200
s = serial.Serial(port, baud, timeout=0.2)
time.sleep(0.3)
s.reset_input_buffer()
payload = bytes(range(32))
s.write(payload)
t0 = time.time()
echo = bytearray()
while time.time() - t0 < 3.0 and len(echo) < 32:
    d = s.read(64)
    if d: echo += d
s.close()
print("SENT   :", payload.hex(' '))
print("ECHO   :", bytes(echo).hex(' '))
print("RESULT :", "LINKE_LOOPBACK_OK" if bytes(echo) == payload else f"MISMATCH got {len(echo)} bytes")
