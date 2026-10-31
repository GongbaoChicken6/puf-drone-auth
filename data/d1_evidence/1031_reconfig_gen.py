# -*- coding: utf-8 -*-
"""D1 无线模块重写配置（通用版）：FU3 / B115200 / <信道>
用法: python 1031_reconfig_gen.py <COM> <CHANNEL 如 C006> <log_path>
前提: SET 已接地。逻辑: 自动探测 AT 会话波特率(115200优先,方式一;9600=方式二出厂)
      -> 写 FU3/B115200/信道 -> 原会话波特率 AT+RX 回读断言（SET接地期间新波特率不生效）
"""
import sys, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import serial

PORT, CH, LOGPATH = sys.argv[1], sys.argv[2], sys.argv[3]
LOG = open(LOGPATH, "a", encoding="utf-8")

def log(s):
    print(s, flush=True)
    LOG.write(s + "\n"); LOG.flush()

def at(ser, cmd, wait=0.4):
    ser.reset_input_buffer()
    ser.write(cmd.encode("ascii"))
    time.sleep(wait)
    r = b""
    t0 = time.time()
    while time.time() - t0 < 0.6:
        n = ser.in_waiting
        if n:
            r += ser.read(n); t0 = time.time()
        else:
            time.sleep(0.05)
    log(f"    {cmd!r} -> {r!r}")
    return r

log(f"=== 重写配置 {PORT} -> {CH} @ {time.strftime('%Y-%m-%d %H:%M:%S')} ===")

session = None
ser = None
for baud in [115200, 9600, 4800, 2400, 1200]:
    try:
        ser = serial.Serial(PORT, baud, timeout=0.3)
    except Exception as e:
        log(f"[FATAL] 打开 {PORT}@{baud} 失败: {e}")
        sys.exit(2)
    time.sleep(0.4)
    r = at(ser, "AT", 0.4)
    if b"OK" in r:
        session = baud
        break
    ser.close(); ser = None

if session is None:
    log(f"[FAIL] {PORT}: 全波特率无 AT 响应（查 SET 接地/模块供电/TX-RX 交叉）")
    sys.exit(1)

log(f"[INFO] {PORT}: AT 会话波特率 = {session}")

okfu = b"OK+FU3" in at(ser, "AT+FU3")
okb  = b"OK+B115200" in at(ser, "AT+B115200")
okc  = (b"OK+" + CH.encode()) in at(ser, "AT+" + CH)
rx = at(ser, "AT+RX", 0.8)
rx_txt = rx.decode("ascii", "replace")
chb = CH.encode()
okrx = ("FU3" in rx_txt) and ("B115200" in rx_txt) and ((("R" + CH) in rx_txt) or (CH in rx_txt))
ser.close()

verdict = okfu and okb and okc and okrx
log(f"[{'PASS' if verdict else 'FAIL'}] {PORT}: FU3={okfu} B115200={okb} {CH}={okc} 回读全对={okrx}")
log(f"AT+RX 回读原文: {rx_txt!r}")
log("提醒: 完成后断开 SET 与 GND（>=80ms 后自动进 115200 透传）")
sys.exit(0 if verdict else 1)
