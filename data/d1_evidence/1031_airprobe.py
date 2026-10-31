# -*- coding: utf-8 -*-
"""D1 无线下行探测：从 COM6(C001) 向空中打测试字节，判断板侧模块是否收得到
用法: python 1031_airprobe.py <COM_TX> <COM_SNIFF>
观察: 板上 DS9 是否随发射节奏闪（闪=下行通: 模块供电/信道/RXD->pin5 接线全对）
同时监听 COM_SNIFF(C006) 检测串台
"""
import sys, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import serial

TX, SNIFF = sys.argv[1], sys.argv[2]
stx = serial.Serial(TX, 115200, timeout=0.2)
ssn = serial.Serial(SNIFF, 115200, timeout=0.2)
time.sleep(0.4)
stx.reset_input_buffer(); ssn.reset_input_buffer()

print(f"=== 下行探测: {TX} 每秒发一帧 x10，盯板侧 DS9 ===", flush=True)
sniff_all = b""
for i in range(10):
    stx.write(f"AIRPROBE_R{i}_X".encode())
    print(f"[{time.strftime('%H:%M:%S')}] burst {i} 已发射", flush=True)
    time.sleep(1.0)
    if ssn.in_waiting:
        sniff_all += ssn.read(ssn.in_waiting)

# 收尾：再等1秒收尾包
t0 = time.time()
while time.time() - t0 < 1.0:
    if ssn.in_waiting:
        sniff_all += ssn.read(ssn.in_waiting); t0 = time.time()
    else:
        time.sleep(0.05)

stx.close(); ssn.close()
print(f"串台检测（{SNIFF}/C006 收到）: {sniff_all.hex() if sniff_all else '(空,正常)'}", flush=True)
