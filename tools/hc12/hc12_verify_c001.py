# -*- coding: utf-8 -*-
"""hc12_verify_c001.py -- 只读校验 HC-12 是否已是 C001/115200/FU3（不写参数）。

用法: python hc12_verify_c001.py COMx
接线: SET 在上电前接地（方式二），AT 会话固定 9600,N,1（手册 6.1）。
判据: AT 回 OK + AT+RX 回读同时含 FU3 / B115200 / RC001（读回带 R 前缀）。
"""
import sys, time
import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else 'COM6'

def drain(ser, quiet=0.6):
    out = b''
    t0 = time.time()
    while time.time() - t0 < quiet:
        n = ser.in_waiting
        if n:
            out += ser.read(n)
            t0 = time.time()
        else:
            time.sleep(0.05)
    return out

def at(ser, cmd, quiet=0.5):
    ser.reset_input_buffer()
    ser.write(cmd.encode('ascii'))
    time.sleep(0.30)
    return drain(ser, quiet)

ok_session = None
for baud in (9600, 115200):
    try:
        ser = serial.Serial(PORT, baud, timeout=0.5)
    except Exception as e:
        print('OPEN_FAIL', baud, e)
        continue
    time.sleep(0.6)
    r = at(ser, 'AT')
    if b'OK' in r:
        ok_session = baud
        print('AT_SESSION_OK baud=%d raw=%r' % (baud, r))
        rx = at(ser, 'AT+RX', quiet=1.2)
        ser.close()
        txt = rx.decode('ascii', 'replace')
        print('AT_RX_RAW:', repr(txt))
        has_fu  = ('FU3' in txt)
        has_baud= ('B115200' in txt) or ('RB115200' in txt)
        has_ch  = ('RC001' in txt) or ('C001' in txt)
        verdict = has_fu and has_baud and has_ch
        print('VERIFY_%s fu3=%s baud115200=%s ch001=%s (session=%d)'
              % ('PASS' if verdict else 'FAIL', has_fu, has_baud, has_ch, baud))
        if not verdict:
            print('建议: 运行 hc12_config_c001.py %s 写入 C001/115200/FU3' % PORT)
        sys.exit(0 if verdict else 1)
    ser.close()

print('VERIFY_FAIL 无 AT 响应(SET 是否上电前接地? TX/RX 是否交叉?)')
sys.exit(1)
