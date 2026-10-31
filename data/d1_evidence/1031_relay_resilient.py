# -*- coding: utf-8 -*-
"""D1 韧性版对发测试：记录 USB 适配器中途失联事件（2026-10-31 23:07）
现象: COM9(CH340) 在模块发射后报 ClearCommError PermissionError(5)，疑似适配器被电流尖峰拉重启
设计: 每次收发都捕获异常; 失联后按 VID:PID 动态找回端口(防漂移)重开; 统计失联事件与时机
用法: python 1031_relay_resilient.py <ROUNDS> <log>
"""
import sys, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import serial
import serial.tools.list_ports as lp

ROUNDS = int(sys.argv[1])
LOG = open(sys.argv[2], "w", encoding="utf-8")

def log(s):
    print(s, flush=True)
    LOG.write(s + "\n"); LOG.flush()

def ts():
    return time.strftime("%H:%M:%S.") + f"{int(time.time()*1000)%1000:03d}"

def find_by_vid(vidpid):
    for p in lp.comports():
        if vidpid in (p.hwid or ""):
            return p.device
    return None

def open_port(name, vidpid):
    for attempt in range(6):
        port = find_by_vid(vidpid) or name
        try:
            s = serial.Serial(port, 115200, timeout=0.2)
            time.sleep(0.4)
            s.reset_input_buffer()
            if port != name:
                log(f"[{ts()}] [NOTE] {name} 漂移到 {port}，已改用")
            return s, port
        except Exception as e:
            log(f"[{ts()}] [REOPEN] {port} 第{attempt+1}次失败: {type(e).__name__}: {e}")
            time.sleep(1.5)
    return None, None

deaths = {"A": 0, "B": 0}
sa, pa = open_port("COM6", "1A86:8012")
sb, pb = open_port("COM9", "1A86:7523")
log(f"=== 韧性对发 {pa} <-> {pb} x{ROUNDS} @ {ts()} ===")

def drain(side, secs=1.5):
    s = sa if side == "A" else sb
    out = b""
    t0 = time.time()
    while time.time() - t0 < secs:
        try:
            n = s.in_waiting
        except Exception as e:
            deaths[side] += 1
            raise RuntimeError(f"PORT_DEATH {side} RX: {type(e).__name__}")
        if n:
            try:
                out += s.read(n)
                t0 = time.time()
            except Exception as e:
                deaths[side] += 1
                raise RuntimeError(f"PORT_DEATH {side} RD: {type(e).__name__}")
        else:
            time.sleep(0.03)
    return out

def write(side, data):
    s = sa if side == "A" else sb
    try:
        s.write(data)
    except Exception as e:
        deaths[side] += 1
        raise RuntimeError(f"PORT_DEATH {side} TX: {type(e).__name__}")

def revive(side):
    global sa, sb
    log(f"[{ts()}] [REVIVE] {side} 侧尝试复活...")
    try:
        (sa if side == "A" else sb).close()
    except Exception:
        pass
    time.sleep(2.0)
    s, port = open_port("COM6" if side == "A" else "COM9",
                        "1A86:8012" if side == "A" else "1A86:7523")
    if s is None:
        return False
    if side == "A": sa = s
    else: sb = s
    log(f"[{ts()}] [REVIVE] {side} 侧复活于 {port}")
    return True

ok_ab = ok_ba = 0
for i in range(ROUNDS):
    ma = f"PING_R{i}".encode()
    try:
        write("A", ma)
        r = drain("B")
        log(f"[{ts()}] R{i} A->B: {r.hex()} {'PASS' if r == ma else 'FAIL'}")
        ok_ab += (r == ma)
    except RuntimeError as e:
        log(f"[{ts()}] R{i} A->B 异常: {e}")
        if not revive("B"):
            log("B 侧无法复活，终止")
            break
    mb = f"PONG_R{i}".encode()
    try:
        write("B", mb)
        r2 = drain("A")
        log(f"[{ts()}] R{i} B->A: {r2.hex()} {'PASS' if r2 == mb else 'FAIL'}")
        ok_ba += (r2 == mb)
    except RuntimeError as e:
        log(f"[{ts()}] R{i} B->A 异常: {e}")
        if not revive("A"):
            log("A 侧无法复活，终止")
            break

try: sa.close()
except Exception: pass
try: sb.close()
except Exception: pass
log(f"RESULT: A->B {ok_ab}/{ROUNDS}, B->A {ok_ba}/{ROUNDS}, 失联事件 A={deaths['A']} B={deaths['B']}")
sys.exit(0 if (ok_ab == ROUNDS and ok_ba == ROUNDS and deaths["A"] == 0 and deaths["B"] == 0) else 1)
