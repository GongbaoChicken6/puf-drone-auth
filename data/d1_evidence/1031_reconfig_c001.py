# -*- coding: utf-8 -*-
"""D1 无线模块重写配置（A对）：FU3 / B115200 / C001
用法: python 1031_reconfig_c001.py <COM> <log_path>
前提: SET 已接地（上电前接地=AT固定9600/方式二；上电后接地=AT走已配波特率/方式一）
逻辑: 自动探测 AT 会话波特率(115200优先) -> 写 FU3/B115200/C001 -> 原会话波特率 AT+RX 回读断言
教训依据: SET 接地期间新波特率不生效，验证须在原会话波特率读（10-30 配置会话结论）
"""
import sys, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import serial

PORT = sys.argv[1]
LOG = open(sys.argv[2], "a", encoding="utf-8")

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

log(f"=== 重写配置 {PORT} @ {time.strftime('%Y-%m-%d %H:%M:%S')} ===")

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
    log(f"[FAIL] {PORT}: 全波特率无 AT 响应（查 SET 接地/模块供电/TX-RX 交叉/是否真有模块）")
    sys.exit(1)

log(f"[INFO] {PORT}: AT 会话波特率 = {session}")

okfu = b"OK+FU3" in at(ser, "AT+FU3")
if session == 115200:
    okb = b"OK+B115200" in at(ser, "AT+B115200")
else:
    okb = b"OK+B115200" in at(ser, "AT+B115200")  # 保存后仍以当前会话波特率应答
okc = b"OK+C001" in at(ser, "AT+C001")
rx = at(ser, "AT+RX", 0.8)
rx_txt = rx.decode("ascii", "replace")
okrx = ("FU3" in rx_txt) and ("B115200" in rx_txt) and (("RC001" in rx_txt) or ("C001" in rx_txt))
ser.close()

verdict = okfu and okb and okc and okrx
log(f"[{'PASS' if verdict else 'FAIL'}] {PORT}: FU3={okfu} B115200={okb} C001={okc} 回读全对={okrx}")
log(f"AT+RX 回读原文: {rx_txt!r}")
log("提醒: 完成后断开 SET 与 GND（>=80ms 后自动进 115200 透传）")
sys.exit(0 if verdict else 1)
