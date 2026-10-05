# -*- coding: utf-8 -*-
"""protocol.py / crp_pool.py 伪代码可行性与时序安全检查（审查证据）"""
import random
import sys
import threading

# ========== 1. protocol.py 调用签名冲突（terminal_id 传给了 count） ==========
print("=" * 60)
print("[1] protocol.py: self.pool.draw(terminal_id, count=5) 签名冲突")
print("=" * 60)

class PoolExhausted(Exception):
    pass

class CRPPool:
    """crp_pool.py 伪代码的忠实实现"""
    def __init__(self, device_id: int, size: int = 500):
        self.device_id = device_id
        self.used: set = set()
        self.pool: list = [bytes([i & 0xFF]) * 8 for i in range(size)]

    def draw(self, count: int = 5) -> list:
        available = set(range(len(self.pool))) - self.used
        if len(available) < count:
            raise PoolExhausted(f"remaining {len(available)}, need {count}")
        chosen = random.sample(list(available), count)
        self.used.update(chosen)
        return [self.pool[i] for i in chosen]

    @property
    def remaining_pct(self) -> float:
        return 1 - len(self.used) / len(self.pool)

pool = CRPPool(1)
try:
    terminal_id = 42
    pool.draw(terminal_id, count=5)     # <-- 文档 protocol.py 3.2 的原样调用
    print("  未报错（意外）")
except TypeError as e:
    print(f"  复现成功 -> TypeError: {e}")

# ========== 2. draw() 线程安全（多终端并发共享同一 pool） ==========
print()
print("=" * 60)
print("[2] crp_pool.py: draw() 无锁并发 -> 挑战重复发放")
print("=" * 60)
sys.setswitchinterval(1e-6)             # 压缩 GIL 切换间隔，放大 check-then-act 竞态

max_dups = 0
for trial in range(20):
    shared = CRPPool(0, size=500)
    issued = []
    lock = threading.Lock()
    def worker():
        for _ in range(15):
            try:
                cs = shared.draw(5)
            except PoolExhausted:
                return
            with lock:
                issued.extend(cs)
    ts = [threading.Thread(target=worker) for _ in range(8)]
    for t in ts: t.start()
    for t in ts: t.join()
    dups = len(issued) - len(set(issued))
    max_dups = max(max_dups, dups)
print(f"  20 轮并发实验（8 线程 x 15 次 x 5 挑战）：最大重复发放挑战数 = {max_dups}")
print("  注：这是 check-then-act 竞态（available 计算与 used 更新之间无锁）")

# ========== 3. 双阈值 + 灰区可达性 ==========
print()
print("=" * 60)
print("[3] protocol.py: 灰区分支可达性依赖常量排序（文档未定义）")
print("=" * 60)
def classify(score, TP, TR, GL, GH):
    if score < TP:
        return "reject(HD too high)"
    if score > TR:
        return "reject(HD too low)"
    if GL < score < GH:
        return "gray(extra challenge)"
    return "pass"

# 假设 1：常量排序正确 TP <= GL < GH <= TR
TP, TR, GL, GH = 0.30, 0.60, 0.40, 0.50
print(f"  排序正确 (TP={TP},GL={GL},GH={GH},TR={TR}):")
for s in (0.10, 0.35, 0.45, 0.55, 0.70):
    print(f"    score={s:.2f} -> {classify(s, TP, TR, GL, GH)}")
# 假设 2：灰区下界低于放行阈值（常见的直觉定义法）
TP, TR, GL, GH = 0.30, 0.60, 0.20, 0.50
print(f"  排序错误 (TP={TP},GL={GL},GH={GH},TR={TR}): score=0.45 -> {classify(0.45, TP, TR, GL, GH)}")
print(f"    score=0.25 -> {classify(0.25, TP, TR, GL, GH)} (本应加测，被直接放行)")

# ========== 4. HF-IDA 五帧延迟预算 ==========
print()
print("=" * 60)
print("[4] HF-IDA 五帧延迟预算（433MHz SiK 电台，57600 串口 / 64kbps 空中）")
print("=" * 60)
baud = 57600
frame_bytes = 44
t_serial_ms = frame_bytes * 10 / baud * 1000
print(f"  串口侧单最大帧: {frame_bytes}B x 10bit / {baud}bps = {t_serial_ms:.3f} ms")
print(f"  5 帧串口合计: {5*t_serial_ms:.2f} ms")
air_bits = (4 + 2 + 44) * 8
for oh, tag in ((1.0, "无ECC"), (1.5, "ECC~50%")):
    t_air_ms = air_bits * oh / 64000 * 1000
    print(f"  空中侧单帧({tag}): {t_air_ms:.2f} ms -> 5 帧 {5*t_air_ms:.1f} ms")
print(f"  空中传播(10km, 光速): {10000/3e5*1000:.1f} ms  (可忽略)")
print()
print(f"  MSG_CHALLENGE 载荷 = 5 种子 x 8B = {5*8}B，文档自限载荷 <= 32B -> 超限: {5*8 > 32}")
print(f"  超限帧实际长度 = 10 + {5*8} + 2 = {10+5*8+2}B > 44B 自限帧长")
