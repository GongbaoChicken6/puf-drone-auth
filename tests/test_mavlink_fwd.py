"""finals-demo-drone MAVLink forwarder tests(QGC 直连加分项)。

CI-safe:核心用例零 I/O(send_fn/clock 注入);官方解码器交叉验证在
pymavlink 可导入时执行(importorskip 降级——常跑机已装 pymavlink 2.4.50)。
Run: python -m pytest tests/test_mavlink_fwd.py -q
"""

import math
import struct
import sys
import unittest
from pathlib import Path
from queue import Queue

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web.bridge.drone_sim import DroneSim
from web.bridge.mavlink_fwd import (
    _MSG_ID, MavlinkForwarder, crc16_mcrf4xx, pack_v2)


class FakeHub:
    def __init__(self):
        self.taps = []

    def add_tap(self):
        q = Queue()
        self.taps.append(q)
        return q

    def publish(self, etype, payload):
        pass


def make_fwd(sent=None, drone=None):
    hub = FakeHub()
    sim = drone or DroneSim(hub, autostart=False)
    t = [0.0]
    fwd = MavlinkForwarder(hub, sim,
                           send_fn=(sent if sent is not None else []).append,
                           clock=lambda: t[0])
    return fwd, sim, hub, t


class TestParseSpec(unittest.TestCase):
    """content-review P2:裸端口解析曾是真实 bug(端口当主机名→DNS 伪装死锁)。"""

    def test_three_forms(self):
        from web.bridge.mavlink_fwd import _parse_spec
        self.assertEqual(_parse_spec("14550"), ("127.0.0.1", 14550))
        self.assertEqual(_parse_spec("192.168.1.5:14550"), ("192.168.1.5", 14550))
        self.assertEqual(_parse_spec(":14550"), ("127.0.0.1", 14550))


class TestCrcAndFrames(unittest.TestCase):
    def test_crc16_mcrf4xx_check_value(self):
        # 标准校验向量:CRC-16/MCRF4XX("123456789") = 0x6F91
        self.assertEqual(crc16_mcrf4xx(b"123456789"), 0x6F91)

    def test_frame_shape_heartbeat(self):
        f = pack_v2("HEARTBEAT", struct.pack("<IBBBBB", 0, 2, 8, 0, 4, 3), 0)
        self.assertEqual(len(f), 21)          # 10 头 + 9 载荷 + 2 CRC
        self.assertEqual(f[0], 0xFD)
        self.assertEqual(f[1], 9)
        self.assertEqual(f[7], 0)             # msgid 0

    def test_mav_result_enums_are_official(self):
        """content-review P2:TEMP_REJ 曾凭记忆写 8,官方=1——用 pymavlink 钉死。"""
        import web.bridge.mavlink_fwd as M
        self.assertEqual(M.TEMP_REJ, 1)
        self.assertEqual(M.ACCEPTED, 0)
        self.assertEqual(M.DENIED, 2)
        self.assertEqual(M.UNSUPPORTED, 3)
        try:
            from pymavlink import mavutil
        except ImportError:
            self.skipTest("pymavlink 未安装")
        E = mavutil.mavlink
        self.assertEqual(M.TEMP_REJ, E.MAV_RESULT_TEMPORARILY_REJECTED)
        self.assertEqual(M.ACCEPTED, E.MAV_RESULT_ACCEPTED)
        self.assertEqual(M.DENIED, E.MAV_RESULT_DENIED)
        self.assertEqual(M.UNSUPPORTED, E.MAV_RESULT_UNSUPPORTED)
        self.assertEqual(M.SEV_ALERT, E.MAV_SEVERITY_ALERT)

    def test_crc_extra_constants_are_official(self):
        # 取自 pymavlink 2.4.50 官方生成器(gen 提取,2026-11-13)
        from web.bridge.mavlink_fwd import _CRC_X
        self.assertEqual(_CRC_X["HEARTBEAT"], 50)
        self.assertEqual(_CRC_X["ATTITUDE"], 39)
        self.assertEqual(_CRC_X["LOCAL_POSITION_NED"], 185)
        self.assertEqual(_CRC_X["STATUSTEXT"], 83)
        self.assertEqual(_CRC_X["COMMAND_ACK"], 143)
        self.assertEqual(_CRC_X["COMMAND_LONG"], 152)

    def test_official_decoder_cross_validation(self):
        """官方 pymavlink 解码器必须能解我们打包的全部出站帧。"""
        try:
            from pymavlink import mavutil
        except ImportError:
            self.skipTest("pymavlink 未安装(交叉验证降级)")
        dec = mavutil.mavlink.MAVLink(None, srcSystem=255)
        m = dec.parse_char(pack_v2(
            "ATTITUDE", struct.pack("<Iffffff", 12345, .1, -.2, 3., 0, 0, 0), 7))
        self.assertEqual(m.get_type(), "ATTITUDE")
        self.assertAlmostEqual(m.roll, 0.1, places=6)
        self.assertAlmostEqual(m.pitch, -0.2, places=6)
        self.assertAlmostEqual(m.yaw, 3.0, places=6)
        self.assertEqual(m.time_boot_ms, 12345)
        h = dec.parse_char(pack_v2(
            "HEARTBEAT", struct.pack("<IBBBBB", 0, 2, 8, 0, 4, 3), 8))
        self.assertEqual((h.type, h.autopilot, h.system_status, h.mavlink_version),
                         (2, 8, 4, 3))
        p = dec.parse_char(pack_v2(
            "LOCAL_POSITION_NED", struct.pack("<Iffffff", 9, 1.5, -2., -3., 0, 0, 0), 9))
        self.assertEqual((p.x, p.y, p.z), (1.5, -2.0, -3.0))
        st = dec.parse_char(pack_v2(
            "STATUSTEXT", bytes([5]) + b"hello".ljust(50, b"\x00"), 10))
        self.assertEqual(st.severity, 5)
        self.assertTrue(st.text.startswith("hello"))
        ack = dec.parse_char(pack_v2("COMMAND_ACK", struct.pack("<HB", 22, 0), 11))
        self.assertEqual((ack.command, ack.result), (22, 0))


class TestOutboundEvents(unittest.TestCase):
    def _drain(self, fwd, hub):
        while True:
            try:
                env = hub.taps[0].get_nowait()
            except Exception:
                return
            etype, pl = env.get("type"), env.get("payload") or {}
            if etype == "drone.attitude":
                fwd._on_drone_attitude(pl)
            elif etype == "drone.state":
                fwd._on_drone_state(pl)
            elif etype == "drone.reject":
                fwd._on_drone_reject(pl)

    def test_attitude_and_position_out(self):
        sent = []
        fwd, sim, hub, _ = make_fwd(sent)
        att = {"roll": 10.0, "pitch": -5.0, "yaw": 90.0,
               "x": 1.0, "y": 2.0, "alt": 3.0,
               "vx": 0, "vy": 0, "vz": 0, "state": "HOVER", "terminal_id": 1}
        fwd._on_drone_attitude(att)      # 第 1 帧:ATTITUDE(位置 5Hz 起始相位)
        fwd._on_drone_attitude(att)      # 第 2 帧:ATTITUDE + LOCAL_POSITION_NED
        kinds = [f[7] | (f[8] << 8) for f in sent]
        # 5Hz 节流序列(content-review P3:两 ATTITUDE + 一 POSITION,精确钉死)
        self.assertEqual(kinds, [_MSG_ID["ATTITUDE"], _MSG_ID["ATTITUDE"],
                                 _MSG_ID["LOCAL_POSITION_NED"]])
        self.assertIn(_MSG_ID["ATTITUDE"], kinds)
        self.assertIn(_MSG_ID["LOCAL_POSITION_NED"], kinds)
        # 数值映射(content-review P2:deg→rad 因子与 NED z=-alt 符号此前零断言)
        try:
            from pymavlink import mavutil
        except ImportError:
            self.skipTest("pymavlink 未安装")
        dec = mavutil.mavlink.MAVLink(None, srcSystem=255)
        att = [f for f in sent if (f[7] | (f[8] << 8)) == 30]
        m = dec.parse_char(att[0])
        self.assertAlmostEqual(m.roll, math.radians(10.0), places=5)
        self.assertAlmostEqual(m.pitch, math.radians(-5.0), places=5)
        self.assertAlmostEqual(m.yaw, math.radians(90.0), places=5)
        pos = [f for f in sent if (f[7] | (f[8] << 8)) == 32]
        p2 = dec.parse_char(pos[0])
        self.assertAlmostEqual(p2.z, -3.0, places=4)         # NED:z = -alt
        self.assertAlmostEqual(p2.x, 1.0, places=4)

    def test_outbound_filters_other_tids(self):
        """content-review P1 回归:绑定后其他 tid 的出站事件不转发。"""
        sent = []
        fwd, sim, hub, _ = make_fwd(sent)
        fwd._on_drone_state({"terminal_id": 7, "unlocked": True})   # 绑定 7
        fwd._on_drone_attitude({"terminal_id": 9, "roll": 1.0, "pitch": 0.0,
                                "yaw": 0.0, "x": 0.0, "y": 0.0, "alt": 0.0,
                                "vx": 0, "vy": 0, "vz": 0, "state": "HOVER"})
        kinds = [f[7] | (f[8] << 8) for f in sent]
        self.assertNotIn(_MSG_ID["ATTITUDE"], kinds)                # tid9 被滤掉

    def test_unlock_emits_statustext_once(self):
        sent = []
        fwd, sim, hub, _ = make_fwd(sent)
        fwd._on_drone_state({"terminal_id": 1, "unlocked": True})
        fwd._on_drone_state({"terminal_id": 1, "unlocked": True})   # 去抖
        st = [f for f in sent if (f[7] | (f[8] << 8)) == _MSG_ID["STATUSTEXT"]]
        self.assertEqual(len(st), 1)

    def test_reject_emits_alert_statustext(self):
        """content-review P3:承诺三腿(解锁/上锁/拒绝)的拒绝腿零测。"""
        sent = []
        fwd, sim, hub, _ = make_fwd(sent)
        fwd._on_drone_state({"terminal_id": 1, "unlocked": True})   # 绑定
        fwd._on_drone_reject({"terminal_id": 1, "cmd": "launch",
                              "reason": "AUTH_REQUIRED"})
        st = [f for f in sent if (f[7] | (f[8] << 8)) == 253
              and f[10] == 1]        # severity=ALERT(1),排除解锁的 NOTICE(5)
        self.assertEqual(len(st), 1)

    def test_heartbeat_emits_valid_frame(self):
        """名实相符(content-review P2:原 periodic 测试名不符实——1Hz 周期
        由 live smoke HEARTBEAT×9 把关,本测试钉帧本身的有效性)。"""
        sent = []
        fwd, sim, hub, t = make_fwd(sent)
        t[0] = 5.0                     # boot 后 5s
        fwd._heartbeat()
        hb = [f for f in sent if (f[7] | (f[8] << 8)) == 0]
        self.assertEqual(len(hb), 1)
        try:
            from pymavlink import mavutil
        except ImportError:
            self.skipTest("pymavlink 未安装")
        dec = mavutil.mavlink.MAVLink(None, srcSystem=255)
        m = dec.parse_char(hb[0])
        self.assertEqual((m.type, m.autopilot, m.system_status, m.mavlink_version),
                         (2, 8, 4, 3))


class TestInboundCommands(unittest.TestCase):
    def _official_command_long(self, command, **params):
        """用官方生成器打包 COMMAND_LONG(v1 帧也行,feed 双收)。"""
        try:
            from pymavlink import mavutil
        except ImportError:
            self.skipTest("pymavlink 未安装")
        import inspect
        cls = mavutil.mavlink.mavlink_map[76]
        sig = [p for p in inspect.signature(cls.__init__).parameters
               if p != "self"]
        kw = {p: 0 for p in sig}
        kw.update(target_system=1, target_component=1, command=command,
                  confirmation=0, **params)
        return cls(**kw).pack(mavutil.mavlink.MAVLink(None, srcSystem=255))

    def test_tid_follows_unlocked_terminal(self):
        """content-review P1 回归:入站指令跟随解锁 tid(非硬编码 1)。"""
        sent = []
        fwd, sim, hub, _ = make_fwd(sent)
        sim._on_event("verdict", {"terminal_id": 7, "result": 0})   # 演示终端 7
        fwd.feed_inbound(self._official_command_long(22))
        # _dispatch 自动绑定:无出站事件时从 DroneSim 解锁 tid 推断
        self.assertEqual(sim._st[7].state, "TAKEOFF")
        self.assertNotIn(1, sim._st)                                # tid=1 未被触碰

    def test_takeoff_dispatch(self):
        sent = []
        fwd, sim, hub, _ = make_fwd(sent)
        sim._on_event("verdict", {"terminal_id": 1, "result": 0})   # 解锁
        fwd.feed_inbound(b"\x00noise" + self._official_command_long(22))
        self.assertEqual(sim._st[1].state, "TAKEOFF")
        ack = [f for f in sent if (f[7] | (f[8] << 8)) == 77]
        self.assertEqual(len(ack), 1)
        cmd, result = struct.unpack("<HB", ack[0][10:13])
        self.assertEqual((cmd, result), (22, 0))          # ACCEPTED

    def test_locked_takeoff_temporarily_rejected(self):
        sent = []
        fwd, sim, hub, _ = make_fwd(sent)                 # 未认证
        fwd.feed_inbound(self._official_command_long(22))
        self.assertEqual(sim._st[1].state, "LANDED")      # 未起飞
        ack = [f for f in sent if (f[7] | (f[8] << 8)) == 77]
        cmd, result = struct.unpack("<HB", ack[0][10:13])
        self.assertEqual(result, 1)                       # TEMPORARILY_REJECTED(官方=1)

    def test_inbound_v2_frame_branch(self):
        """content-review P2:官方生成器产 v1 帧,v2 分支(现代 QGC 真路径)
        此前零覆盖——pack_v2 自产 v2 帧回灌(出站/入站 CRC 同源)。"""
        sent = []
        fwd, sim, hub, _ = make_fwd(sent)
        sim._on_event("verdict", {"terminal_id": 1, "result": 0})
        payload = struct.pack("<7fHBBB", 0, 0, 0, 0, 0, 0, 0, 22, 1, 1, 0)
        fwd.feed_inbound(pack_v2("COMMAND_LONG", payload, 0))
        self.assertEqual(sim._st[1].state, "TAKEOFF")   # v2 帧走了 v2 分支

    def test_waypoint_params_map_to_goto(self):
        sent = []
        fwd, sim, hub, _ = make_fwd(sent)
        sim._on_event("verdict", {"terminal_id": 1, "result": 0})
        sim.command(1, "launch")
        for _ in range(80):                               # 直驱到 HOVER
            with sim._lk:
                for tid, st in list(sim._st.items()):
                    sim._step(tid, st, 0.05)
        fwd.feed_inbound(self._official_command_long(16, param5=5.0, param6=-2.0))
        self.assertEqual(sim._st[1].state, "MOVE")
        self.assertEqual(sim._st[1].wp, (5.0, -2.0))

    def test_remaining_command_mappings(self):
        """content-review P3:5 命令只测了 2,补 arm/land/rtl/unknown。"""
        sent = []
        fwd, sim, hub, _ = make_fwd(sent)
        sim._on_event("verdict", {"terminal_id": 1, "result": 0})
        # arm(param1>0.5)
        fwd.feed_inbound(self._official_command_long(400, param1=1.0))
        self.assertEqual(sim._st[1].state, "ARMED")
        # takeoff(ARMED 态 → 状态感知映射为 takeoff 而非 launch)
        fwd.feed_inbound(self._official_command_long(22))
        for _ in range(80):                    # 直驱到 HOVER
            with sim._lk:
                for tid, st in list(sim._st.items()):
                    sim._step(tid, st, 0.05)
        # rtl
        fwd.feed_inbound(self._official_command_long(20))
        self.assertEqual(sim._st[1].state, "RTL")
        # land
        fwd.feed_inbound(self._official_command_long(21))
        self.assertEqual(sim._st[1].state, "LAND")
        # unknown command → UNSUPPORTED(3)
        fwd.feed_inbound(self._official_command_long(999))
        acks = [f for f in sent if (f[7] | (f[8] << 8)) == 77]
        cmd, result = struct.unpack("<HB", acks[-1][10:13])
        self.assertEqual((cmd, result), (999, 3))

    def test_bad_crc_silently_dropped(self):
        sent = []
        fwd, sim, hub, _ = make_fwd(sent)
        sim._on_event("verdict", {"terminal_id": 1, "result": 0})
        raw = bytearray(self._official_command_long(22))
        raw[-1] ^= 0xFF                                   # 破坏 CRC
        fwd.feed_inbound(bytes(raw))
        self.assertEqual(sim._st[1].state, "LANDED")
        self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
