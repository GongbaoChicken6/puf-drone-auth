# -*- coding: utf-8 -*-
"""HC-12 出厂验收 + 参数配置脚本 v2（auto-review 修正版）
用法：python hc12_config.py COM6
接线（全程 SET 接 GND，上电前接好）：
  USB-TTL 3V3 -> VCC   USB-TTL GND -> GND（模块 GND 有 2/7/8 三个引脚，任一均可）
  USB-TTL TX  -> RXD   USB-TTL RX  -> TXD   （交叉，手册 5.5）
  SET -> 任一空闲 GND 点（模块 7/8 脚补焊的针 / 面包板地轨均可）
"""
import sys, time
import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM6"
LOG = open("hc12_config_log.txt", "w", encoding="utf-8")

def log(s):
    print(s, flush=True)
    LOG.write(s + "\n"); LOG.flush()

def drain(ser):
    out = b""
    t0 = time.time()
    while time.time() - t0 < 0.8:
        n = ser.in_waiting
        if n:
            out += ser.read(n)
            t0 = time.time()
        else:
            time.sleep(0.05)
    return out

def at(ser, cmd, expect, note=""):
    ser.reset_input_buffer()
    ser.write(cmd.encode("ascii"))  # HC-12 AT 指令：大写、不带回车换行
    time.sleep(0.35)
    r = drain(ser)
    ok = expect.encode() in r
    log(f"[{'PASS' if ok else 'FAIL'}] {cmd!r} -> {r!r}  {note}")
    return ok, r

log(f"=== HC-12 配置 {PORT} @ {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
log("提示：方式二（SET 先接地再上电）进入 AT 固定为 9600,N,1（手册 6.1）")

# 第一阶段：9600 冒烟（手册 6.2：出厂默认 9600 / FU3 / C001）
ser = serial.Serial(PORT, 9600, timeout=0.5)
time.sleep(0.6)
ok1, _ = at(ser, "AT", "OK", "AT 冒烟")
if not ok1:
    log("!! 无响应：查 1)TX/RX 是否交叉 2)SET 是否已接 GND 3)COM 号")
    sys.exit(1)

# 第二阶段：目标参数（真正必要的是 B115200；FU3/C001 为显式确认，防模块曾被改过）
okfu, _ = at(ser, "AT+FU3", "OK+FU3", "透传模式 FU3")
okb, _ = at(ser, "AT+B115200", "OK+B115200", "波特率 115200（掉电保存）")
ser.close()

# 第三阶段：115200 复验 + 信道 + 读回断言（手册 6.3.7：AT+RX 分行返回各参数）
ser = serial.Serial(PORT, 115200, timeout=0.5)
time.sleep(0.5)
ok2, _ = at(ser, "AT", "OK", "115200 下 AT 复验")
if not ok2:
    log("115200 复验无响应 -> 回退 9600 验证参数是否已保存（手册：退出设置状态才生效）")
    ser.close()
    ser = serial.Serial(PORT, 9600, timeout=0.5)
    time.sleep(0.4)
    okb2, rb = at(ser, "AT+RB", "OK+B115200", "回退读波特率")
    ok2 = okb2
else:
    okb2 = True
okc, _ = at(ser, "AT+C001", "OK+C001", "信道 001（两块一致）")
okrx, rx = at(ser, "AT+RX", "OK", "读回全部参数（证据）")
rx_txt = rx.decode("ascii", "replace")
okrx = ("OK+FU3" in rx_txt) and ("OK+B115200" in rx_txt) and (("OK+RC001" in rx_txt) or ("OK+C001" in rx_txt))  # 实测读回带 R 前缀
log(f"AT+RX 断言 FU3/B115200/C001 全含: {okrx}")
ser.close()
LOG.close()

verdict = all([ok1, okfu, okb, ok2, okc, okrx])
print()
print("结论：", "配置完成且验收全过 PASS" if verdict else "存在 FAIL 项，看上面日志")
print("日志已存 hc12_config_log.txt")
print("完成后必做：断开 SET 与 GND（>=80ms 后自动进 115200 透传）；")
print("            如需再进 AT：退出后至少等 200ms 再拉低 SET（手册 6.1 注）")
print("            两块模块都要各跑一遍本脚本，参数完全一致")
