"""mavlink_fwd.py —— finals-demo-drone 加分项:标准 MAVLink v2 双向转发器。

让真 QGroundControl(或任何 GCS)经 UDP 直连本演示系统的"无人机":
  出站(hub tap → UDP):HEARTBEAT 1Hz / ATTITUDE 10Hz / LOCAL_POSITION_NED 5Hz
    / STATUSTEXT(解锁/上锁/拒绝) / COMMAND_ACK —— 消息与 CRC_EXTRA 全按
    MAVLink common.xml 官方口径(CRC_EXTRA 由 XML 定义串现算,测试对官方
    公布值逐一断言)。
  入站(UDP → DroneSim):COMMAND_LONG → 飞控指令映射
    400 arm/disarm · 22 takeoff(launch) · 21 land · 20 rtl · 16 waypoint
    (param5/6/7 → 本地北/东/高度米,演示口径)。认证门控由 DroneSim.command
    统一裁决:未认证 → COMMAND_ACK(TEMPORARILY_REJECTED) + STATUSTEXT。

设计要点(与 DroneSim 同纪律):
  * 零 I/O 可测:send_fn / clock / sleeper 全注入,tests 直驱不发真包;
  * stop() 生命周期,桥 shutdown 挂钩;
  * 不碰线上 HF-IDA 帧与 RTL —— 纯站端演示层(设计 §9 诚实边界不变)。
启动(真 UDP,默认目标 QGC 常用 14550):
    web_bridge.py ... --mavlink-udp            # 127.0.0.1:14550
    web_bridge.py ... --mavlink-udp 192.168.x.x:14550
"""
from __future__ import annotations

import math
import socket
import sys
import struct
import threading
import time
from queue import Empty, Queue

# --------------------------------------------------------------------------
# CRC-16/MCRF4XX(MAVLink 标准校验;check "123456789" = 0x6F91)
# --------------------------------------------------------------------------
def crc16_mcrf4xx(data: bytes, crc: int = 0xFFFF) -> int:
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc >> 1) ^ 0x8408) if (crc & 1) else (crc >> 1)
    return crc


# --------------------------------------------------------------------------
# 标准消息定义(common.xml 子集):字段序/类型必须逐字一致 —— CRC_EXTRA
# 与载荷布局都依赖它。CRC_EXTRA 由官方算法现算:名字 + " 类型 字段名"…,
# 测试对官方公布值断言(HEARTBEAT=50/ATTITUDE=39/…),五值全中即证算法正确。
# --------------------------------------------------------------------------
_STATUSTEXT_LEN = 50

# 消息常量全部取自**官方生成器** pymavlink 2.4.50(2026-11-13 提取,
# 载荷 wire 序见各 struct 调用):HEARTBEAT <IBBBBB(9B,含 custom_mode);
# ATTITUDE / LOCAL_POSITION_NED <Iffffff(28B);STATUSTEXT sev+char[50](51B);
# COMMAND_ACK <HB(3B 核心段,兼容最佳);COMMAND_LONG <fffffffHBBB(33B)。
# 测试做官方解码器交叉验证(pymavlink 缺席时 importorskip 降级)。
_MSG_ID = {"HEARTBEAT": 0, "ATTITUDE": 30, "LOCAL_POSITION_NED": 32,
           "STATUSTEXT": 253, "COMMAND_ACK": 77, "COMMAND_LONG": 76}
_CRC_X = {"HEARTBEAT": 50, "ATTITUDE": 39, "LOCAL_POSITION_NED": 185,
          "STATUSTEXT": 83, "COMMAND_ACK": 143, "COMMAND_LONG": 152}

# MAV_RESULT / MAV_SEVERITY / MAV_CMD(common 官方枚举;content-review R1:
# 凭记忆写的 8/2 是错的,以下为 pymavlink 2.4.50 本机实测值)
ACCEPTED, TEMP_REJ, DENIED, UNSUPPORTED = 0, 1, 2, 3
SEV_ALERT, SEV_NOTICE = 1, 5
MAV_CMD = {"NAV_WAYPOINT": 16, "RTL": 20, "LAND": 21, "TAKEOFF": 22,
           "ARM_DISARM": 400}


def pack_v2(msg_name: str, payload: bytes, seq: int, sysid: int = 1,
            compid: int = 1) -> bytes:
    """标准 MAVLink v2 帧(与 HF-IDA 私有帧同链路不同 ID 空间,互不干扰)。"""
    mid = _MSG_ID[msg_name]
    head = bytes([0xFD, len(payload), 0, 0, seq & 0xFF, sysid, compid,
                  mid & 0xFF, (mid >> 8) & 0xFF, (mid >> 16) & 0xFF])
    crc = crc16_mcrf4xx(head[1:] + payload)
    crc = crc16_mcrf4xx(bytes([_CRC_X[msg_name]]), crc)
    return head + payload + bytes([crc & 0xFF, crc >> 8])


def _parse_spec(spec: str) -> tuple[str, int]:
    """解析 [HOST:]PORT。裸端口(如 "14550")= 127.0.0.1:14550。
    (排障教训回归锚:此前 partition 写法把裸端口当主机名,sendto 变 DNS
    查询伪装成死锁——tests/test_mavlink_fwd.py 钉死三种形态。)"""
    if ":" in spec:
        host, port = spec.split(":", 1)
    else:
        host, port = "127.0.0.1", spec
    return (host or "127.0.0.1", int(port or 14550))


def start_udp(hub, drone, spec: str, bind_host: str = "0.0.0.0") -> "MavlinkForwarder":
    """真 UDP 引导(桥 --mavlink-udp):单 socket 双向——发往 GCS 目标地址,
    GCS 的回包按 UDP 语义回到同一 ephemeral 端口,读线程喂 feed_inbound。
    QGC 侧:Application Settings→Comm Links→UDP→监听 <port> 即可直连。
    双串口攻击演示拓扑中,真基站侧 = web_bridge --serial-port COM6(见
    tools/attack/fake_result_attack.py docstring)。"""
    addr = _parse_spec(spec)          # 裸端口当主机名的老 bug 见 _parse_spec 注释
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((bind_host, 0))
    # Windows UDP 实测坑(2026-11-13 定案,三组对照实验):unconnected
    # sendto 在"ICMP unreachable 错误被 recvfrom 消费后"会永久阻塞(本机
    # Python 3.13 无 SIO_UDP_CONNRESET 可抑制);**connected UDP 完全免疫**
    # (connect 后 send/recv,消费 ConnectionResetError 后连发无碍,复现脚本
    # 验证 5/5)。GCS 回包恰来自所连对端(QGC 监听口),路由不受影响。
    sock.setblocking(False)
    sock.connect(addr)

    fail = [0]                        # 连续失败计数(content-review P3:黑洞留痕)

    def send_fn(frame: bytes) -> None:
        try:
            sock.send(frame)
            fail[0] = 0
        except OSError:
            fail[0] += 1               # BlockingIOError 丢帧无害;连败才告警
            if fail[0] == 20:          # 节流:目标不可达/QGC 未起时每 20 帧一条
                try:
                    hub.publish("server.log", {
                        "level": "warn",
                        "msg": f"mavlink-udp: 20 consecutive send failures to "
                               f"{addr[0]}:{addr[1]} (QGC not listening?)"})
                except Exception:
                    pass

    def recv_fn() -> bytes:
        return sock.recv(512)          # 非阻塞;空/ICMP 由 _loop 统一容错

    fwd = MavlinkForwarder(hub, drone, send_fn=send_fn, recv_fn=recv_fn,
                           on_stop=sock.close)
    fwd.start()
    return fwd


class MavlinkForwarder:
    """hub tap(drone.* 事件)↔ UDP 的双向转发。零 I/O 可测(send/clock 注入)。"""

    SYSID, COMPID = 1, 1

    def __init__(self, hub, drone, send_fn=None, target="127.0.0.1:14550",
                 clock=time.monotonic, recv_fn=None, on_stop=None, tid=None):
        self._drone = drone
        # 演示终端绑定(content-review P1):None=自动跟随(首个出站事件绑定,
        # 之后跟随最近解锁 tid 改绑);入站指令发往绑定 tid。此前硬编码 tid=1
        # 与演示终端空间(7/9/99)失配 → QGC 指令恒 AUTH_REQUIRED 自相矛盾。
        self._tid = tid
        self._send_fn = send_fn          # 真模式: lambda frame: sock.sendto(frame, addr)
        self._recv_fn = recv_fn          # 真模式: lambda: sock.recvfrom(512)[0](非阻塞)
        self._on_stop = on_stop
        self.target = target
        self._clock = clock
        self._tap: Queue = hub.add_tap()
        self._stop = threading.Event()
        self._seq = 0
        self._boot = clock()
        self._pos_acc = 0.0
        self._last_unlocked: bool | None = None
        self._inbuf = bytearray()
        self._th = threading.Thread(target=self._loop, name="mavlink-fwd",
                                    daemon=True)

    # ---- 生命周期 ----
    def start(self) -> None:
        self._th.start()

    def stop(self) -> None:
        self._stop.set()

    # ---- 出站 ----
    def _emit(self, name: str, payload: bytes) -> None:
        frame = pack_v2(name, payload, self._seq, self.SYSID, self.COMPID)
        self._seq = (self._seq + 1) & 0xFF
        if self._send_fn is not None:
            self._send_fn(frame)

    def _ms(self) -> int:
        return int((self._clock() - self._boot) * 1000)

    def _heartbeat(self) -> None:
        # type=MAV_TYPE_QUADROTOR(2) autopilot=INVALID(8) base_mode=0
        # system_status=MAV_STATE_ACTIVE(4) mavlink_version=3
        # (wire 序 <IBBBBB:MAVLink v2 大字段优先重排,custom_mode uint32 在最前)
        self._emit("HEARTBEAT", struct.pack("<IBBBBB", 0, 2, 8, 0, 4, 3))

    def _accept_out(self, p: dict) -> bool:
        """出站 tid 过滤:未绑定先绑,绑定后只放行本 tid(多终端防串台)。"""
        if self._tid is None:
            self._tid = p.get("terminal_id")
        return p.get("terminal_id") == self._tid

    def _on_drone_attitude(self, p: dict) -> None:
        if not self._accept_out(p):
            return
        d2r = math.pi / 180.0
        self._emit("ATTITUDE", struct.pack("<Iffffff", self._ms(),
            p["roll"] * d2r, p["pitch"] * d2r, p["yaw"] * d2r, 0.0, 0.0, 0.0))
        # LOCAL_POSITION_NED 5Hz 节流(与 attitude 同源,坐标 NED:z 取 -alt)
        self._pos_acc += 0.1
        if self._pos_acc >= 0.2 - 1e-9:
            self._pos_acc = 0.0
            self._emit("LOCAL_POSITION_NED", struct.pack(
                "<Iffffff", self._ms(), p["x"], p["y"], -p["alt"],
                p["vx"], p["vy"], -p["vz"]))

    def _on_drone_state(self, p: dict) -> None:
        unlocked = bool(p.get("unlocked"))
        if unlocked:
            self._tid = p.get("terminal_id")   # 跟随最近解锁的演示终端
        if not self._accept_out(p):
            return
        if unlocked != self._last_unlocked:
            self._last_unlocked = unlocked
            text = ("PUF auth PASS: flight unlocked"
                    if unlocked else "flight locked (auth lost or manual lock)")
            sev = SEV_NOTICE if unlocked else SEV_ALERT
            raw = text[:_STATUSTEXT_LEN - 1].encode("utf-8")[:_STATUSTEXT_LEN - 1]
            self._emit("STATUSTEXT", bytes([sev]) + raw.ljust(_STATUSTEXT_LEN, b"\0"))

    def _on_drone_reject(self, p: dict) -> None:
        if not self._accept_out(p):
            return
        raw = (f"cmd {p.get('cmd')} rejected: {p.get('reason')}"
               )[:_STATUSTEXT_LEN - 1].encode("utf-8")[:_STATUSTEXT_LEN - 1]
        self._emit("STATUSTEXT", bytes([SEV_ALERT]) + raw.ljust(_STATUSTEXT_LEN, b"\0"))

    # ---- 入站(COMMAND_LONG → DroneSim) ----
    _CMD_MAP = {
        MAV_CMD["TAKEOFF"]: lambda p: ("launch", {}),
        MAV_CMD["LAND"]: lambda p: ("land", {}),
        MAV_CMD["RTL"]: lambda p: ("rtl", {}),
        MAV_CMD["ARM_DISARM"]: lambda p:
            ("arm" if p[0] > 0.5 else "disarm", {}),
        # param5/param6 → 本地北/东(米);0/0 是合法目标(回原点上空),
        # 不做 truthy 兜底(content-review P3:原注释与索引错位且 (0,0) 不可达)
        MAV_CMD["NAV_WAYPOINT"]: lambda p: ("goto", {"x": p[4], "y": p[5]}),
    }

    def feed_inbound(self, data: bytes) -> None:
        """喂入 GCS 侧字节(真模式=UDP recv;测试直驱)。v1(0xFE)/v2(0xFD)
        都收:现代 QGC 走 v2,官方生成器/老 GCS 常出 v1,白赚一层兼容。"""
        self._inbuf.extend(data)
        while True:
            while self._inbuf and self._inbuf[0] not in (0xFD, 0xFE):
                self._inbuf.pop(0)
            if len(self._inbuf) < 2:
                return
            total = (10 if self._inbuf[0] == 0xFD else 6) + self._inbuf[1] + 2
            if len(self._inbuf) < total:
                return
            frame = bytes(self._inbuf[:total])
            del self._inbuf[:total]
            self._handle_frame(frame)

    def _handle_frame(self, frame: bytes) -> None:
        v2 = frame[0] == 0xFD
        mid = ((frame[7] | (frame[8] << 8) | (frame[9] << 16)) if v2
               else frame[5])
        if mid != _MSG_ID["COMMAND_LONG"] or frame[1] != 33:
            return                       # 只消费 COMMAND_LONG(其余忽略)
        head_end, payload = (10, frame[10:43]) if v2 else (6, frame[6:39])
        name = "COMMAND_LONG"
        crc = crc16_mcrf4xx(frame[1:head_end] + payload)
        crc = crc16_mcrf4xx(bytes([_CRC_X[name]]), crc)
        if crc != (frame[-2] | (frame[-1] << 8)):
            return                       # 坏帧静默(GCS 端会重试)
        params = struct.unpack("<7fHBBB", payload)
        self._dispatch(params)

    def _dispatch(self, params) -> None:
        cmd = params[7]
        m = self._CMD_MAP.get(cmd)
        if m is None:
            self._ack(cmd, UNSUPPORTED)
            return
        # 入站绑定:显式 tid > 出站已绑定 > DroneSim 当前解锁 tid > 1
        if self._tid is None:
            unlocked = self._drone.unlocked_tids()
            self._tid = unlocked[0] if unlocked else 1
        op, extra = m(params[0:7])
        # TAKEOFF 状态感知(R2 实测):ARMED 后须发 takeoff(launch 源态仅 LANDED),
        # QGC 标准 ARM→TAKEOFF 序列在 ARMED 态点 launch 必 409
        if cmd == MAV_CMD["TAKEOFF"]:
            op = "takeoff" if self._drone.state_of(self._tid) == "ARMED" else "launch"
        r = self._drone.command(self._tid, op, extra.get("x"),
                                extra.get("y"), extra.get("alt"))
        self._ack(cmd, ACCEPTED if r.get("ok") else TEMP_REJ)

    def _ack(self, cmd: int, result: int) -> None:
        self._emit("COMMAND_ACK", struct.pack("<HB", cmd, result))

    # ---- 主循环(tap 出站事件 + 1Hz 心跳 + 入站字节) ----
    def _loop(self) -> None:
        """单线程事件循环:tap 出站事件 + GCS 入站非阻塞轮询 + 1Hz 心跳。
        入站与出站共用同一 socket —— Windows Winsock 实测(2026-11-13):
        多线程并发访问同一 UDP socket(一读一写)会在 sendto 上死锁;
        单线程轮询彻底免疫,10Hz 轮询对 GCS 指令延迟 <100ms。"""
        last_hb = 0.0
        while not self._stop.is_set():
            try:
                try:
                    env = self._tap.get(timeout=0.1)
                    etype, pl = env.get("type"), env.get("payload") or {}
                    if etype == "drone.attitude":
                        self._on_drone_attitude(pl)
                    elif etype == "drone.state":
                        self._on_drone_state(pl)
                    elif etype == "drone.reject":
                        self._on_drone_reject(pl)
                except Empty:
                    pass
                if self._recv_fn is not None:        # GCS 入站(非阻塞,收尽)
                    while True:
                        try:
                            self.feed_inbound(self._recv_fn())
                        except (BlockingIOError, ConnectionResetError):
                            break                      # 空/ICMP 回声:本轮收完
                        except OSError:
                            break
                now = self._clock()
                if now - last_hb >= 1.0:  # HEARTBEAT 1Hz
                    last_hb = now
                    self._heartbeat()
            except Exception as exc:       # 线程防线(content-review P3,同 drone_sim)
                sys.stderr.write(f"mavlink-fwd loop error (recovered): {exc!r}\n")
                time.sleep(0.1)
        if self._on_stop is not None:
            self._on_stop()               # 循环退出后关 socket(绝无并发)
