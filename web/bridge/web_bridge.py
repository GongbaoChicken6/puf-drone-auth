#!/usr/bin/env python3
"""web_bridge.py — PUF 无人机认证 · 前端桥接层(全 Python 标准库,零 pip 依赖)。

设计依据:《web/前端探索报告.md》v1.1 §8(外部契约冻结:REST 端点 §8.2 /
SSE 信封与 12 型事件 §8.3 / 终端侧代演口径 §8.1)。与报告 §8.1 的唯一偏差
(团队拍板,理由见 web/README.md):本文件位于 web/bridge/ 而非
src/python/server/,使前端模块可整体拷入组员仓库而**零改动其任何现有文件**;
启动时以 sys.path 引导复用组员 server 包的公共 API(与 main.py 脚本模式同一先例)。

用法(合并后在组员仓库根目录):
    python web/bridge/web_bridge.py --loopback --open

开发态(本工作区;组员仓库严格只读、运行态数据全落本地沙箱):
    python web/bridge/web_bridge.py --repo-root <组员仓库> --data-dir web/.dev-data --loopback

冒烟自检(不起 HTTP,跑完即退出;退出码表达成败):
    python web/bridge/web_bridge.py --repo-root <仓库> --data-dir web/.dev-data --once s1
    ... --once s2|s3|s4|s5|s6|s7|golden

架构:
    浏览器(web/dist 静态页) ←SSE /api/events + POST /api/*─ 本桥接
      ├─ 复用 src/python/server 公共 API(HFIDAProtocol / LoopbackTransport /
      │   enroll_device / TemplateDB / DeviceKeyStore / CRPPoolRegistry /
      │   threshold / SpeckHSM)与 src/python/common/speck.py
      ├─ 终端侧三帧(ACCESS_REQUEST / RESPONSE_R1 / CONFIRM)与 R2 复算验证在
      │   loopback 下由本桥接「代演」(§8.1);帧事件标 source="simulated-terminal"
      └─ 场景 S1–S7 只调公共 API 与真实算法,不改判定逻辑、不杜撰数据
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import secrets as _secrets
import sys
import threading
import time
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Empty, Queue
from typing import Any

# finals-demo-drone:站端无人机演示层(纯展示仿真,零 RTL/线上协议改动)。
# ⚠ 既有测试用 importlib.spec_from_file_location 加载本文件(test_channel_ids.py
# L29-39 一带),sys.path 不含本目录——必须先注入再 import,否则 ModuleNotFoundError
# 且 CI 全量 pytest 必挂(协调点①,2026-11-12)。
_BRIDGE_DIR = Path(__file__).resolve().parent
if str(_BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_DIR))
from drone_sim import DroneSim
from mavlink_fwd import start_udp as _mavlink_start_udp

VERSION = "0.1.0"

# ---- 冻结常量(docs/protocol_contract.md §4.1 / threshold.py 实读口径) ----
W3_DEMO_KEY_HEX = "0001020308090a0b10111213"   # W3 演示密钥(NSA KAT,安全=零)
C2_GOLDEN_HEX = "a1a2a3a4a5a6a7a8"             # 终端复位后首次认证的 C2
GOLDEN_R2_HEX = "7b45b0545e59aa94"             # Speck(W3 key, C2=a1..a8) §4.1
GOLDEN_TID = 42                                # §4 黄金帧所用 terminal_id
GRAY_FLIP_PROB = 0.13                          # S4 灰区加测(§8.2: 0.13–0.15)
POOL_SCHEMA = "puf-drone-auth/crp-pool/v2"
STATE_SCHEMA = "puf-drone-auth/web-bridge/v2"   # Phase A A2:freqs(ROPairingPUF)取代 secret_hex
SSE_PING_S = 15                                # §8.4:每 15s 发 ": ping" 心跳
QUEUE_CAP = 256                                # 单客户端事件队列上限

RESULT_NAMES = {0: "PASS", 1: "REJECT", 2: "ERROR", 3: "POOL_EMPTY", 4: "REPLAY"}
AUTH_MODES = ("normal", "spoof", "replay", "gray", "evilbase")

# docs/protocol_contract.md §4 的 7 条黄金帧(逐字节,静态真实)。
# 文件可读时按 §4 现场解析;不可读时用本表兜底(交付后 docs/ 一定在)。
GOLDEN_FRAMES_FALLBACK: list[dict[str, str]] = [
    {"name": "ACCESS_REQUEST", "note": "tid=42 nonce=0xDEADBEEF c2=000102...07 (28B)",
     "hex": "FD1000004201029000002A000000EFBEADDE00010203040506073AD2"},
    {"name": "CHALLENGE", "note": "seq=0x43 seeds=A0 00*7 / A1 01*7 / A2 02*7 / A3 03*7 (44B)",
     "hex": "FD200000430102910000A000000000000000A1010101010101"
            "01A202020202020202A3030303030303F2F7"},
    {"name": "RESPONSE_R1", "note": "seq=0x44 (44B)",
     "hex": "FD200000440102920000B000000000000000B1010101010101"
            "01B202020202020202B3030303030303A715"},
    {"name": "RESULT", "note": "pass hd=5 r2=C0..C7 (22B)",
     "hex": "FD0A00004501029300000005C0C1C2C3C4C5C6C7A5D2"},
    {"name": "CONFIRM", "note": "tid=42 status=1 (17B)",
     "hex": "FD0500004601029400002A0000000178F4"},
    {"name": "EXTRA_CHALLENGE", "note": "seq=0x47 (36B)",
     "hex": "FD180000470102950000D000000000000000D1010101"
            "01010101D2020202020202027A9F"},
    {"name": "RESULT_A1_GOLDEN", "note": "seq=0x50 result=PASS hd=5 r2=Speck(W3 key,C2=a1..a8) (22B)",
     "hex": "FD0A000050010293000000057B45B0545E59AA94FF1D"},
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def console_utf8() -> None:
    """Windows GBK 控制台兜底:输出流切 UTF-8(pythonw 下静默跳过)。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:
            pass


# ============================================================
# §1 SSE Hub —— 信封 {seq,ts,type,payload};无回放缓冲(§8.4:重连走
# /api/status 全量重同步);慢客户端丢最旧,连续两次滞后则断开(poison)
# ============================================================
class SSEHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seq = 0
        self._clients: dict[int, Queue] = {}
        self._next_cid = 0
        self._laggy: set[int] = set()
        self._taps: list[Queue] = []      # finals-demo-drone:站内消费者引出线

    def subscribe(self) -> tuple[int, Queue]:
        q: Queue = Queue(maxsize=QUEUE_CAP)
        with self._lock:
            cid = self._next_cid
            self._next_cid += 1
            self._clients[cid] = q
            self._laggy.discard(cid)
            return cid, q

    def unsubscribe(self, cid: int) -> None:
        with self._lock:
            self._clients.pop(cid, None)
            self._laggy.discard(cid)

    def add_tap(self) -> Queue:
        """finals-demo-drone:内部事件引出线(DroneSim 等站内消费者)。

        复用 publish 的锁与丢旧保新策略;不入 SSE 客户端计数。tap 消费者
        不得在回调内再 publish(锁递归)——DroneSim 在自己线程出队后发布。
        """
        q: Queue = Queue(maxsize=512)   # 设计 §3.1 口径(独立于 SSE 客户端 QUEUE_CAP)
        with self._lock:
            self._taps.append(q)
        return q

    def publish(self, etype: str, payload: dict) -> int:
        with self._lock:
            self._seq += 1
            env = {"seq": self._seq, "ts": now_iso(), "type": etype, "payload": payload}
            dead: list[int] = []
            for cid, q in self._clients.items():
                try:
                    q.put_nowait(env)
                    self._laggy.discard(cid)
                except Exception:  # queue.Full
                    if cid in self._laggy:      # 第二次连续滞后 -> 断开
                        dead.append(cid)
                        continue
                    self._laggy.add(cid)
                    try:                        # 丢最旧,塞最新
                        q.get_nowait()
                        q.put_nowait(env)
                    except Exception:
                        pass
            for cid in dead:
                q = self._clients.pop(cid, None)
                self._laggy.discard(cid)
                if q is not None:
                    try:
                        q.put_nowait(None)      # poison:SSE 循环退出
                    except Exception:
                        pass
            for q in self._taps:               # finals-demo-drone:站内 tap
                try:
                    q.put_nowait(env)
                except Exception:              # queue.Full:丢最旧保最新(同客户端策略)
                    try:
                        q.get_nowait(); q.put_nowait(env)
                    except Exception:
                        pass
            return self._seq

    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    def current_seq(self) -> int:
        with self._lock:
            return self._seq


# ============================================================
# §2 数据目录与桥接自有状态
#   组员仓库 data/ 在开发态保持只读;一切运行态落 --data-dir。
#   web_bridge_state.json 持久化代演终端的 PUF secret —— SimulatedTerminal
#   的 secret 是每进程随机的(main.py:122 secrets.token_bytes),不持久化则
#   重启后旧模板必失配、S1 全部 REJECT。
# ============================================================
def templates_sig(templates: Any, tid: int) -> str:
    """模板表的指纹 —— 只取该 tid 的**种子集合**,不取响应值。

    取种子集合而非文件字节:模板表在注册流程里会被重写,但若种子集合没变,已量出的
    HD 序列就仍然有效(HD 由种子经器件算出,与表里的响应列无关)。按文件字节做校验
    会在每次无害重写后误弃样本,反而逼出一堆无谓的现场重采。
    同一函数的两个调用方(tools/sample_hd.py 与桥接)必须给出一致结果,故两侧共用
    此实现而不是各写一份 —— 签名对不上会导致样本被静默弃用,且没有任何报错。
    """
    rows = (templates.templates.get(str(tid)) or {}) if templates is not None else {}
    h = hashlib.sha256()
    h.update(f"tid={tid}|n={len(rows)}|".encode("utf-8"))
    for seed in sorted(rows):
        h.update(seed.lower().encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()[:16]


def freqs_sig(freqs: Any) -> str:
    """器件指纹(ROPairingPUF 的 16 环频率向量)—— 与 tools/sample_hd.py 共用一份
    实现(理由同 templates_sig:两侧各写一份,签名对不上会导致样本被静默弃用且
    毫无报错)。

    规范(Phase A A3,两侧逐字面一致):
        sha256("freqs-v1:" + ",".join(str(int(f)) for f in freqs)) 取前 16 位十六
        进制;不含 auth_count。只暴露哈希,不下发频率向量本身:它回答的是
    「落盘样本量测的那个器件,还是现在这个器件吗」。状态文件被删或重建后
    SimulatedTerminal 会重新随机 freqs,而种子集合可以一字未改 —— 此时单看模板
    签名会判定样本仍然有效,于是页面继续展示一对已经无意义的谱。
    """
    try:
        parts = ",".join(str(int(f)) for f in freqs)
    except Exception:
        return ""
    return hashlib.sha256(("freqs-v1:" + parts).encode("utf-8")).hexdigest()[:16]


@dataclass
class DataDir:
    root: Path

    @property
    def templates_json(self) -> Path: return self.root / "templates" / "templates.json"
    @property
    def pools_dir(self) -> Path: return self.root / "crp_datasets" / "pools"
    @property
    def device_keys_json(self) -> Path: return self.root / "device_keys" / "device_keys.json"
    @property
    def state_json(self) -> Path: return self.root / "web_bridge_state.json"
    @property
    def hd_sample_json(self) -> Path: return self.root / "viz" / "hd_sample.json"

    def mkdir_all(self) -> None:
        self.templates_json.parent.mkdir(parents=True, exist_ok=True)
        self.pools_dir.mkdir(parents=True, exist_ok=True)
        self.device_keys_json.parent.mkdir(parents=True, exist_ok=True)

    def read_hd_sample(self) -> tuple[str, dict[str, Any]] | None:
        """读 tools/sample_hd.py 的落盘样本 → (templates_sig, payload)。

        只读、不迁移、不修复:文件坏了/半截(采样中途被 Ctrl+C 打断)就当作不存在,
        退回现场采样。宁可不省那点时间,也不能让 V1 拿到半组数据 —— 缺一半样本的
        直方图看上去和完整的一样,而分离度已经错了。
        """
        try:
            raw = json.loads(self.hd_sample_json.read_text(encoding="utf-8"))
            sig = str(raw["templates_sig"])
            if not raw.get("intra") or not raw.get("inter"):
                return None
            return sig, raw
        except (OSError, ValueError, KeyError, TypeError):
            return None


def prewrite_small_pool(pools_dir: Path, tid: int, size: int) -> None:
    """S5 小池(§8.1):预写 pool_<tid>.json 桩,schema v2、pool_size=<size>。

    CRPPool._load 里「已提交的 pool_size 优先于构造参数」,故必须在
    CRPPoolRegistry 首次构造该池**之前**落盘。available 留空 —— 真实种子
    由注册流程 reserve() 铸出并随即具备模板表项;预先塞入无模板的种子会
    让后续 draw() 抽到它时 hamming_distances 抛 KeyError(报告 §8.1 原文
    「seeds 由 secrets 生成」在此实现为「容量预设 + reserve 铸种子」)。
    """
    path = pools_dir / f"pool_{tid}.json"
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema": POOL_SCHEMA, "terminal_id": int(tid), "pool_size": int(size),
        "available": [], "used": [],
    }, indent=2), encoding="utf-8")


class BridgeState:
    """web_bridge_state.json:{terminals:{tid:{freqs,auth_count}}}(v2)。

    Phase A A2:v1 记录的是 secret_hex —— ROPairingPUF 重构后该属性已不存在,
    v1 器件无法重建。加载时显式校验 schema:v1 一律视为空(不复活半套旧状态),
    并记下 legacy_tids 供 RealApp 在 TemplateDB/CRPPoolRegistry 构造前级联清理。
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.terminals: dict[int, dict[str, Any]] = {}
        self.legacy_tids: set[int] = set()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except Exception:
            print(f"[WARN] bridge state unreadable, starting fresh: {path}")
            return
        if data.get("schema") != STATE_SCHEMA:
            self.legacy_tids = {int(t) for t in (data.get("terminals") or {})}
            if self.legacy_tids:
                print(f"[WARN] bridge state schema {data.get('schema')!r} != {STATE_SCHEMA};"
                      f" legacy terminals {sorted(self.legacy_tids)} will be purged")
            return
        for tid_s, rec in data.get("terminals", {}).items():
            if isinstance(rec, dict) and rec.get("freqs"):
                self.terminals[int(tid_s)] = rec

    def save(self) -> None:
        data = json.dumps({"schema": STATE_SCHEMA,
                           "terminals": {str(t): r for t, r in self.terminals.items()}},
                          indent=2)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        # Windows 上 os.replace 偶发 WinError 5(杀软/索引器瞬时持有句柄)。
        # 重试几次;仍失败则降级为警告 —— 落盘失败只影响「重启后能否免注册」,
        # 不该让整轮认证/注册失败(否则 run.error 会盖掉正常判定)。
        for attempt in range(4):
            try:
                tmp.write_text(data, encoding="utf-8")
                tmp.replace(self.path)
                return
            except OSError as exc:
                if attempt == 3:
                    print(f"[WARN] bridge state save failed ({exc}); terminal "
                          f"secrets may not survive a restart", file=sys.stderr)
                    return
                time.sleep(0.05 * (attempt + 1))


# ============================================================
# §3 懒加载组员 server 包(--mock 完全不 import,组员仓库可缺席)
# ============================================================
def resolve_repo_root(arg: str | None) -> Path:
    root = Path(arg).resolve() if arg else Path(__file__).resolve().parents[2]
    if not (root / "src" / "python" / "server" / "protocol.py").exists():
        raise SystemExit(
            f"[ERROR] repo root invalid (no src/python/server/protocol.py): {root}\n"
            f"        pass --repo-root <puf-drone-auth path>")
    return root


class _Mods:
    """组员 server 包的公共 API 命名空间(实读签名,勿凭记忆增删)。"""
    Speck6496: Any
    PoolExhaustedError: Any
    enroll_device: Any
    SpeckHSM: Any
    hsm_status: Any
    LoopbackTransport: Any
    SimulatedTerminal: Any
    DeviceKeyStore: Any
    ensure_device_key: Any
    flush_c2_state: Any
    HFIDAProtocol: Any
    ProtocolError: Any
    TemplateDB: Any
    CRPPoolRegistry: Any
    TAU_PASS: int
    TAU_REJECT: int
    ROPairingPUF: Any


def load_server_modules(repo_root: Path) -> _Mods:
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from src.python.common.speck import Speck6496
    from src.python.server.crp_pool import CRPPoolRegistry, PoolExhaustedError
    from src.python.server.enroll import enroll_device
    from src.python.server.hsm import SpeckHSM, hsm_status
    from src.python.server.main import (DeviceKeyStore, LoopbackTransport,
                                        SimulatedTerminal, _ensure_device_key,
                                        _flush_c2_state)
    from src.python.evaluation.puf_model import ROPairingPUF
    from src.python.server.protocol import HFIDAProtocol, ProtocolError
    from src.python.server.template_db import TemplateDB
    from src.python.server.threshold import TAU_PASS, TAU_REJECT

    m = _Mods()
    m.Speck6496, m.PoolExhaustedError, m.enroll_device = Speck6496, PoolExhaustedError, enroll_device
    m.SpeckHSM, m.hsm_status = SpeckHSM, hsm_status
    m.LoopbackTransport, m.SimulatedTerminal = LoopbackTransport, SimulatedTerminal
    m.DeviceKeyStore = DeviceKeyStore
    # main.py 的两个模块级辅助函数(cmd_auth / main 的清理路径同一对):
    # 代演链路必须复用它们,否则设备密钥与 C2 重放窗不会持久化。
    m.ensure_device_key, m.flush_c2_state = _ensure_device_key, _flush_c2_state
    m.HFIDAProtocol, m.ProtocolError = HFIDAProtocol, ProtocolError
    m.TemplateDB, m.CRPPoolRegistry = TemplateDB, CRPPoolRegistry
    m.TAU_PASS, m.TAU_REJECT = TAU_PASS, TAU_REJECT
    m.ROPairingPUF = ROPairingPUF            # B2:reliability 模型曲线(measure/with_freqs)
    return m


# ============================================================
# §4 终端侧代演(§8.1:pack 三帧 + Speck 复算验证 R2,全公共 API)
# ============================================================
class TerminalProxy:
    """loopback 下的「无人机终端」:三帧构造与终端侧 R2 验证(§4.1/§5⑥)。"""

    def __init__(self, mods: _Mods, protocol, store) -> None:
        self.mods, self.protocol, self.store = mods, protocol, store

    def access_request_frame(self, tid: int, c2: bytes, nonce: int) -> bytes:
        return self.protocol.pack(self.mods.HFIDAProtocol.MSG_ACCESS_REQUEST,
                                  terminal_id=tid, nonce=nonce, c2=c2)

    def response_frame(self, r1s: list[bytes]) -> bytes:
        return self.protocol.pack(self.mods.HFIDAProtocol.MSG_RESPONSE_R1, r1s=r1s)

    def confirm_frame(self, tid: int, status: int) -> bytes:
        return self.protocol.pack(self.mods.HFIDAProtocol.MSG_CONFIRM,
                                  terminal_id=tid, status=status)

    def verify_r2(self, tid: int, c2: bytes, r2_received: bytes) -> bool:
        """终端用自身 DEVICE_KEY 重算 Speck64/96(K,C2),与帧中 R2 逐字节比对
        (§4.1「终端侧 R2 验证」:精确比对,非 HD 比对)。"""
        key, _created = self.store.key_for(tid)
        return self.mods.Speck6496(key).encrypt(c2) == r2_received


class MeasurementProxyTransport:
    """包装 LoopbackTransport.respond,旁路捕获原始多次测量(/api/viz/measurements,
    V4 数据源);零改服务器。enroll_device 只要求 respond(tid, batch, frame=frame)。"""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.captured: dict[int, dict[str, list[str]]] = {}   # tid → seed_hex → [resp_hex]
        self._capture_tid: int | None = None

    def begin_capture(self, tid: int) -> None:
        self._capture_tid = int(tid)
        self.captured.setdefault(int(tid), {})

    def respond(self, terminal_id, seeds, frame=None, impostor=False, flip_prob=None):
        out = self.inner.respond(terminal_id, seeds, frame=frame,
                                 impostor=impostor, flip_prob=flip_prob)
        if self._capture_tid == int(terminal_id) and not impostor:
            bucket = self.captured.setdefault(int(terminal_id), {})
            for seed, resp in zip(seeds, out):
                bucket.setdefault(seed.hex(), []).append(resp.hex())
        return out

    def measurements_of(self, tid: int | None) -> list[dict[str, Any]]:
        if tid is None:
            return []
        return [{"seed": s, "samples": v}
                for s, v in self.captured.get(int(tid), {}).items()]

    def __getattr__(self, name):  # counter_challenge / terminal 等透传
        return getattr(self.inner, name)


# ============================================================
# §5 编排器 —— 单工作线程串行化一切协议写操作(protocol._pending 按 tid
# 键控,同终端并发会互踩);复刻 cmd_auth 调用序列(§8.1)
# ============================================================
@dataclass
class DemoTerminal:
    tid: int
    pool_size: int


@dataclass
class Job:
    kind: str                      # auth/enroll/c2reset/setkey/demo_reset/bootstrap/viz_hd
    tid: int | None = None
    mode: str = "normal"
    n: int = 100
    measurements: int = 3         # N5 enroll_real: 每 CRP 的测量轮数(多数表决)
    key_hex: str | None = None
    fresh: bool = False            # 注册前清空该终端模板与池(重注册语义)
    run_id: str | None = None      # 由提交方预生成,REST 返回值与事件流一致
    done: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: str | None = None


class Orchestrator:
    def __init__(self, app: "RealApp") -> None:
        self.app = app
        self.q: Queue = Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="orchestrator", daemon=True)
        self._cached_c2: dict[int, bytes] = {}     # S3 重放素材:最近一次 PASS 的 C2
        self._run_no = 0
        self._run_lock = threading.Lock()

    def start(self) -> None: self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3)

    def next_run_id(self) -> str:
        with self._run_lock:
            self._run_no += 1
            return f"r{self._run_no}"

    # ---- 代理到 app,减少 self.app. 噪音 ----
    @property
    def hub(self): return self.app.hub
    @property
    def mods(self) -> _Mods: return self.app.mods
    @property
    def protocol(self): return self.app.protocol
    @property
    def transport(self) -> MeasurementProxyTransport: return self.app.transport
    @property
    def store(self): return self.app.store
    @property
    def proxy(self) -> TerminalProxy: return self.app.proxy
    @property
    def P(self): return self.mods.HFIDAProtocol

    # ---------- 工作循环:协议状态的唯一写者 ----------
    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                job = self.q.get(timeout=0.5)
            except Empty:
                continue
            try:
                # N5 enroll_real 带自定义 runner(串口握手逻辑在 enroll_real.py);
                # 旧分发按 kind 拼方法名,会忽略 _runner 直接 AttributeError。
                _runner = getattr(job, "_runner", None)
                if _runner is not None:
                    job.result = _runner()
                else:
                    job.result = getattr(self, f"_do_{job.kind}")(job)
            except Exception as exc:  # noqa: BLE001 —— 兜底成 run.error,进程不倒
                job.error = f"{type(exc).__name__}: {exc}"
                self.hub.publish("run.error", {
                    "run_id": job.run_id or self.next_run_id(),
                    "stage": job.kind, "error": job.error,
                    # 2026-10-29: terminal_id lets the frontend reset the
                    # terminal's enrolling flag (spinner stuck otherwise)
                    "terminal_id": job.tid})
            finally:
                job.done.set()

    def submit(self, job: Job) -> Job:
        self.q.put(job)
        return job

    def submit_sync(self, job: Job, timeout: float = 30.0) -> Job:
        """同步提交。**注意(P2-2 fix)**:超时仅放弃等待——Job 已入队,必然执行,
        其副作用(store.set_key/hsm.set_key/pool reset 等)稍后照常落盘。调用方
        不应将超时误读为「操作失败且已回滚」;真正需要原子性的操作(如 setkey)
        应在下一轮 Job 中查状态确认,而非依赖超时返回值。"""
        self.q.put(job)
        if not job.done.wait(timeout):
            job.error = job.error or "orchestrator timeout (job still queued; side effects will apply)"
        return job

    # ---------- 事件构造(§8.3 逐字段) ----------
    def _emit_frame(self, run_id: str, tid: int, msg_id: int, frame: bytes,
                    outgoing: bool) -> None:
        self.hub.publish("frame.tx" if outgoing else "frame.rx", {
            "run_id": run_id, "terminal_id": tid, "msg_id": msg_id,
            "name": self.P.msg_name(msg_id), "hex": frame.hex(), "len": len(frame),
            "dir": "server->term" if outgoing else "term->server",
            "source": "simulated-terminal",
        })

    def _emit_session(self, tid: int) -> None:
        for s in self.protocol.status()["sessions"]:
            if s["terminal_id"] == tid:
                self.hub.publish("session.update", s)
                return

    def _pool_payload(self, tid: int) -> dict:
        if tid not in self.protocol.pools.terminals():   # 避免为未知终端造池文件
            return {"remaining": 0, "pool_size": 0, "pct": 0}
        st = self.protocol.pools.get(tid).status()
        return {"remaining": st["remaining"], "pool_size": st["pool_size"],
                "pct": st["remaining_pct"]}

    def _next_c2(self, tid: int) -> bytes:
        """取一个不在本终端重放窗内的新 C2。

        代演终端的计数器每进程从 0 重新开始(SimulatedTerminal 只持久化 secret,
        见 §2),所以重启后必须逐值跳过窗内历史。窗口由 protocol 持有,步长 1、
        窗宽 128,故至多 C2_REPLAY_WINDOW+32 次必然离开。返回的即本轮实际使用
        的值 —— 不预先「占位」,避免一次多余的递增落回窗内。
        """
        window = set(self.protocol.c2_history(tid))
        for _ in range(self.P.C2_REPLAY_WINDOW + 32):
            c2 = self.transport.counter_challenge(tid)
            if c2 not in window:
                return c2
        raise RuntimeError(f"tid={tid}: no C2 outside the replay window")

    def _emit_verdict(self, run_id: str, tid: int, fields: dict,
                      hd_per: list[int]) -> None:
        result = int(fields["result"])
        n_resp = len(hd_per)
        payload = {
            "run_id": run_id, "terminal_id": tid, "result": result,
            "result_name": RESULT_NAMES.get(result, str(result)),
            "n_responses": n_resp,
            "hd": int(fields.get("hd", 0xFF)),
            "hd_per_response": hd_per,
            "pool": self._pool_payload(tid),
            # 桥接按本轮 n_responses 以 threshold.decide_scaled 口径下发,
            # 前端不硬编码 TAU(§8.3 verdict 行)。
            "thresholds": {
                "tau_pass": self.mods.TAU_PASS, "tau_reject": self.mods.TAU_REJECT,
                "scaled_pass": self.mods.TAU_PASS * max(n_resp, 1),
                "scaled_reject": self.mods.TAU_REJECT * max(n_resp, 1),
            },
        }
        if result == 0 and "r2" in fields:          # r2 仅 PASS 下发
            payload["r2"] = fields["r2"].hex()
        self.hub.publish("verdict", payload)
        if result == 4:                             # §8.3:verdict 的别名事件
            self.hub.publish("replay.reject",
                             {"run_id": run_id, "terminal_id": tid, "result": 4})

    # ---------- S1/S2/S3/S4/S7:认证编排(复刻 cmd_auth) ----------
    def _do_auth(self, job: Job) -> str:
        tid = int(job.tid or 0)
        mode = job.mode
        run_id = job.run_id or self.next_run_id()
        self.hub.publish("server.log", {
            "level": "info", "msg": f"auth start tid={tid} mode={mode} run={run_id}"})
        # 守卫:真板终端(模板经串口实板注入)不能走 loopback 仿真认证 ——
        # SimulatedTerminal 的 PUF 与真板是两套硬件,响应必然失配(HD≈50%),
        # 表现为「点认证通过却显示指纹匹配未通过」的误导性 REJECT。
        # 真板认证只能由板子主动发起(SW7 → RealSerialListener._auth)。
        # 例外:mode=replay 放行 —— 重放在 C2 窗检查阶段即被拒,不消耗挑战池、
        # 不请求任何指纹响应,判定语义对真板诚实;这正是「攻击者重发录制帧」的入口。
        # 注意:on_access_request 的限流令牌在 C2 检查*之前*扣除——重放点击与真板实轮
        # 共享每分钟配额,连点多次后真板会被限流(这本身是抗滥用语义,但须知晓)。
        if mode != "replay" and int(tid) in getattr(self.app, "real_serial_tids", set()):
            why = (f"tid={tid} 为真板终端:loopback 仿真无法复现其实板指纹,"
                   f"已拦截本轮认证(避免误导性 REJECT)。演示请改用演示终端(7/9),"
                   f"真板认证请按 SW7 由板子发起(REAL-LIVE)。")
            self.hub.publish("server.log", {"level": "warn", "msg": why})
            self.hub.publish("run.error", {
                "run_id": run_id, "stage": "auth", "error": why,
                "terminal_id": tid})
            self._emit_verdict(run_id, tid, {"result": 2, "hd": 0xFF}, [])
            return run_id
        real_tids = getattr(self.app, "real_serial_tids", set())
        if mode == "replay" and int(tid) in real_tids:
            self.hub.publish("server.log", {"level": "info",
                "msg": f"replay tid={tid}: 重放尝试与真板实轮共享限流配额(各扣 1 令牌/次)"})
        try:
            if mode == "replay" and int(tid) in real_tids:
                pass  # 真板重放路径:绝不铸钥/不建仿真终端,仅走 C2 窗口拒绝
            else:
                self.mods.ensure_device_key(self.store, self.protocol, tid)
            if mode == "replay":
                c2 = self._replay_c2(tid)
            else:
                c2 = self._next_c2(tid)

            frame, fields, msg_id = self._open_round(run_id, tid, c2)
            if msg_id == self.P.MSG_RESULT:      # ERROR / REPLAY / POOL_EMPTY
                self._emit_frame(run_id, tid, msg_id, frame, outgoing=True)
                self._emit_verdict(run_id, tid, fields, [])
                self._emit_session(tid)
                return run_id

            if mode == "gray":
                # S4:flip 提升若未入灰区则整轮重试(≤3),每轮都是真实协议往返
                for _ in range(3):
                    entered, _ = self._auth_round(run_id, tid, mode, frame, fields, c2)
                    if entered:
                        return run_id
                    self.hub.publish("server.log", {
                        "level": "info",
                        "msg": f"gray retry tid={tid}: first round not in gray zone"})
                    c2 = self._next_c2(tid)
                    frame, fields, msg_id = self._open_round(run_id, tid, c2)
                    if msg_id == self.P.MSG_RESULT:
                        self._emit_frame(run_id, tid, msg_id, frame, outgoing=True)
                        self._emit_verdict(run_id, tid, fields, [])
                        return run_id
                return run_id

            self._auth_round(run_id, tid, mode, frame, fields, c2)
            return run_id
        finally:
            self.mods.flush_c2_state(self.protocol, self.store)
            # persist_terminal 会经 transport.inner.terminal() 惰性创建随机仿真终端并把
            # 伪造指纹落盘——真板 tid 绝不允许走这条路。
            if int(tid) not in real_tids:
                self.app.persist_terminal(tid)

    def _open_round(self, run_id: str, tid: int, c2: bytes):
        """代演 ACCESS_REQUEST → on_access_request → 解析返回帧。"""
        ar = self.proxy.access_request_frame(tid, c2, _secrets.randbits(32))
        self._emit_frame(run_id, tid, self.P.MSG_ACCESS_REQUEST, ar, outgoing=False)
        frame = self.protocol.on_access_request(tid, c2=c2)
        msg_id, fields = self.protocol.parse(frame)
        return frame, fields, msg_id

    def _auth_round(self, run_id: str, tid: int, mode: str,
                    frame: bytes, fields: dict, c2: bytes) -> tuple[bool, str]:
        """一轮 CHALLENGE→RESPONSE→(EXTRA→RESPONSE)→RESULT→(代演 CONFIRM)。
        返回 (本轮是否进入灰区分叉, run_id)。"""
        # P2-1(fix):gray 模式的 flip_prob=0.13 会永久突变共享器件的 _puf.flip_prob
        # (main.py:156-159 的单线程假设被桥接多场景打破)。轮末显式恢复到默认,
        # 否则后续 S1 normal 期望 HD≈8.3>TAU_PASS,会意外进灰区甚至 REJECT。
        _saved_flip = None
        if mode == "gray":
            try:
                _saved_flip = self.transport.inner.terminal(tid)._puf.flip_prob
            except Exception:
                pass
        try:
            return self._auth_round_inner(run_id, tid, mode, frame, fields, c2)
        finally:
            if _saved_flip is not None:
                try:
                    self.transport.inner.terminal(tid)._puf.flip_prob = _saved_flip
                except Exception:
                    pass

    def _auth_round_inner(self, run_id: str, tid: int, mode: str,
                          frame: bytes, fields: dict, c2: bytes) -> tuple[bool, str]:
        seeds = fields["seeds"]
        self._emit_frame(run_id, tid, self.P.MSG_CHALLENGE, frame, outgoing=True)
        r1s = self.transport.respond(
            tid, seeds, frame=frame, impostor=(mode == "spoof"),
            flip_prob=(GRAY_FLIP_PROB if mode == "gray" else None))
        hd_per = self.protocol.templates.hamming_distances(tid, seeds, list(r1s))
        self._emit_frame(run_id, tid, self.P.MSG_RESPONSE_R1,
                         self.proxy.response_frame(r1s), outgoing=False)
        frame2 = self.protocol.on_response(tid, r1s)
        msg2, f2 = self.protocol.parse(frame2)

        entered_gray = False
        if msg2 == self.P.MSG_EXTRA_CHALLENGE:
            entered_gray = True
            self._emit_frame(run_id, tid, msg2, frame2, outgoing=True)
            self.hub.publish("gray.extra", {
                "run_id": run_id, "terminal_id": tid,
                "seeds": [s.hex() for s in f2["seeds"]], "n": len(f2["seeds"])})
            # 加测轮不加 flip(终端真实噪声语义);总判定由协议 decide_scaled 给出
            r1x = self.transport.respond(tid, f2["seeds"], frame=frame2,
                                         impostor=(mode == "spoof"))
            hd_per = hd_per + self.protocol.templates.hamming_distances(
                tid, f2["seeds"], list(r1x))
            self._emit_frame(run_id, tid, self.P.MSG_RESPONSE_R1,
                             self.proxy.response_frame(r1x), outgoing=False)
            frame2 = self.protocol.on_extra_response(tid, r1x)
            msg2, f2 = self.protocol.parse(frame2)

        if mode == "evilbase" and int(f2["result"]) == 0:
            # S7:基站侧判定 PASS,但发给终端的 RESULT 中 R2 被篡改(翻首字节)。
            # 终端以自身密钥复算 Speck(K,C2) 发现不一致 → 不发 CONFIRM(§5⑥),
            # 链路被终端主动断开。confirm.done(status=1) 是给 UI 的「终端侧
            # BLOCKED」信号(§6.3),不是终端真的发了 CONFIRM_FAIL 帧。
            evil_r2 = bytes([f2["r2"][0] ^ 0xFF]) + f2["r2"][1:]
            evil_frame = self.protocol.pack(self.P.MSG_RESULT,
                                            result=f2["result"], hd=f2["hd"], r2=evil_r2)
            self._emit_frame(run_id, tid, msg2, evil_frame, outgoing=True)
            self._emit_verdict(run_id, tid, f2, hd_per)
            self.hub.publish("confirm.done", {
                "run_id": run_id, "terminal_id": tid, "status": 1,
                "verified_r2": self.proxy.verify_r2(tid, c2, evil_r2)})
            self._emit_session(tid)
            return entered_gray, run_id

        self._emit_frame(run_id, tid, msg2, frame2, outgoing=True)
        self._emit_verdict(run_id, tid, f2, hd_per)
        self._emit_session(tid)

        if int(f2["result"]) == 0 and "r2" in f2:      # PASS → 代演终端握手
            verified = self.proxy.verify_r2(tid, c2, f2["r2"])
            self._emit_frame(run_id, tid, self.P.MSG_CONFIRM,
                             self.proxy.confirm_frame(tid, 0), outgoing=False)
            self.protocol.on_confirm(tid, 0)
            self.hub.publish("confirm.done", {
                "run_id": run_id, "terminal_id": tid,
                "status": 0, "verified_r2": verified})
            if mode == "normal" and verified:
                self._cached_c2[tid] = c2            # S3 重放素材
        return entered_gray, run_id

    def _replay_c2(self, tid: int) -> bytes:
        """S3:复用「旧 C2」。无素材时先诚实跑一次 S1(需要先有捕获)。"""
        if tid in self._cached_c2:
            return self._cached_c2[tid]
        # 真板 tid 的重放素材:串口实轮的 C2 已进协议重放窗(c2_history 即窗内集),
        # 取最近一个 —— 等价于「攻击者重发刚录制的真实 ACCESS_REQUEST」。
        hist = self.protocol.c2_history(tid)
        if hist:
            c2 = hist[-1]
            self.hub.publish("server.log", {
                "level": "info",
                "msg": f"replay tid={tid}: reusing captured real C2 {c2.hex()} "
                       f"(from serial round, inside replay window)"})
            return c2
        if int(tid) in getattr(self.app, "real_serial_tids", set()):
            raise RuntimeError(f"replay tid={tid}: 真板尚无已捕获 C2 —— 请先在真板上按 SW7 "
                               f"完成一轮真实认证,再发起重放演示")
        self.hub.publish("server.log", {
            "level": "info",
            "msg": f"replay tid={tid}: no captured C2 yet; running one normal auth first"})
        self._do_auth(Job(kind="auth", tid=tid, mode="normal",
                          run_id=self.next_run_id()))
        if tid not in self._cached_c2:
            raise RuntimeError("cannot capture a C2 to replay")
        return self._cached_c2[tid]

    # ---------- S6 注册(公共函数 enroll_device,进度经 server.log) ----------
    def _do_poll(self, job: Job) -> dict:
        """N4(finals-demo): AUTH_POLL 下发(遥控 SW7)。auto-review R2 P1 修复:
        handler 必须住在本 Orchestrator 上——分发是 getattr(self, "_do_poll")。
        R2 P2 修复:与 _auth 的串口写互斥(serial_bus_lock)+认证忙拒 +
        先写后发(时间线不出现未发出的帧,同早 RESULT 纪律)。"""
        tid = int(job.tid)
        app = self.app
        if getattr(app, "auth_in_progress", False):
            raise RuntimeError("auth in progress -- poll rejected; "
                               "retry after the current round completes")
        # finals-demo-N6: 按 tid 路由监听器(多口模式防 poll 打错板;单口/旧
        # 测试 SimpleNamespace 无此方法时走原单引用路径,行为不变)
        ln = (app.resolve_listener(tid) if hasattr(app, "resolve_listener")
              else getattr(app, "serial_listener", None))
        if ln is None or not getattr(ln, "running", False):
            raise RuntimeError(
                "poll requires real-serial mode (--serial-port): "
                "loopback/mock has no board to wake; multi-port mode needs "
                "--tid-port (or a queued SW7 entry) to locate this tid's port")
        nonce = time.time_ns() & 0xFFFFFFFF
        frame = self.protocol.pack(
            self.P.MSG_AUTH_POLL, terminal_id=tid, nonce=nonce)
        base = getattr(app, "last_access_request_ts", 0.0)
        with app.serial_bus_lock:
            ln.ser.write(frame); ln.ser.flush()
        # 写成功才发事件(证据纪律:见 _auth 早 RESULT 路径注释)
        self.hub.publish("poll.sent",
                         {"run_id": job.run_id, "terminal_id": tid, "nonce": nonce})
        self.hub.publish("frame.tx", {
            "run_id": job.run_id, "terminal_id": tid,
            "msg_id": self.P.MSG_AUTH_POLL, "name": "AUTH_POLL",
            "hex": frame.hex(), "len": len(frame),
            "dir": "server->term", "source": "real-terminal"})
        # 3s 内板子应回 ACCESS_REQUEST(经 RealSerialListener._auth 全链);
        # 无响应多为阻断态(按 SW13)或链路断
        t0 = time.time()
        while time.time() - t0 < 3.0:
            if getattr(app, "last_access_request_ts", 0.0) > base:
                return {"polled": True, "tid": tid}
            time.sleep(0.02)
        raise RuntimeError(
            "no ACCESS_REQUEST within 3s after AUTH_POLL -- terminal may be "
            "BLOCKED (press SW13 then retry) or the link is down")

    def _do_enroll(self, job: Job) -> str:
        tid = int(job.tid or 0)
        run_id = job.run_id or self.next_run_id()
        # 守卫:真板终端的模板/池来自实板串口注入,loopback 重注册会先用仿真
        # 终端重测并覆盖真板数据(_do_enroll 下方 pool.reset + templates 清空),
        # 属于不可逆的数据污染 —— 直接拒绝。
        if int(tid) in getattr(self.app, "real_serial_tids", set()):
            why = (f"enroll tid={tid} 已拒绝:真板终端的模板与池来自实板注入,"
                   f"loopback 重注册会用仿真数据将其覆盖。需要重注册请在真板上操作。")
            self.hub.publish("server.log", {"level": "warn", "msg": why})
            self.hub.publish("run.error", {
                "run_id": run_id, "stage": "enroll", "error": why,
                "terminal_id": tid})
            return run_id
        pool = self.protocol.pools.get(tid)
        want = max(1, int(job.n))
        if job.fresh or pool.available_count + want > pool.pool_size:
            # 池容量是「历史可用上限」而非当前余额(crp_pool 文档),已注册过的
            # 终端再补种子必然越界 —— 这就是风险表里的「重注册维护窗口」。
            # 重注册 = 换一组新挑战重测,故池与模板段一并作废:旧配对的种子已
            # 不可抽,留着只会虚增 n_pairs 并污染 V3 模板矩阵(TemplateDB 无
            # 删除 API,经其公开 templates/stability 接口清空该终端段)。
            refill = not job.fresh
            self.hub.publish("server.log", {
                "level": "warn",
                "msg": f"enroll tid={tid}: "
                       + ("full re-enroll (pool+templates cleared)" if not refill else
                          f"pool maintenance window ({pool.available_count}/"
                          f"{pool.pool_size} available); refilling to capacity")})
            pool.reset()
            self.protocol.templates.templates[str(tid)] = {}
            self.protocol.templates.stability.pop(str(tid), None)
            if refill:
                want = pool.pool_size
        self.hub.publish("server.log", {
            "level": "info", "msg": f"enroll start tid={tid} n={want} run={run_id}"})
        self.transport.begin_capture(tid)
        step = max(1, want // 4 // 8)       # 进度日志节流:每轮最多约 8 条

        def progress(batch, batches, rnd, rounds):
            if batch % step == 0 or batch == batches:
                self.hub.publish("server.log", {
                    "level": "info",
                    "msg": f"enroll tid={tid} batch {batch}/{batches} round {rnd}/{rounds}"})

        result = self.mods.enroll_device(
            self.protocol, self.transport, tid, n_challenges=want,
            measurements=self.app.args.measurements, on_progress=progress)
        s = result["summary"]
        if result["n_challenges"] != want:
            self.hub.publish("server.log", {
                "level": "info",
                "msg": f"enroll tid={tid}: n rounded {want} -> {result['n_challenges']}"})
        # Phase A A4:注册即按 provisionkey 语义装机 —— K 由终端 PUF 派生
        # (SimulatedTerminal.derived_key,与 REPL provisionkey 同源),不再随机
        # 铸钥;显式 /api/setkey 仍可覆盖(W3 演示密钥/黄金 R2 场景用)。
        # (_do_auth 内的 ensure_device_key 保留为兜底:已装机时本就是 no-op。)
        key = self.transport.inner.terminal(tid).derived_key
        self.store.set_key(tid, key)
        hsm = self.protocol.hsm
        if isinstance(hsm, self.mods.SpeckHSM):
            hsm.set_key(tid, key)
        self.hub.publish("server.log", {
            "level": "info",
            "msg": f"provisionkey tid={tid}: device key derived from terminal PUF"})
        self.hub.publish("enroll.done", {
            "terminal_id": tid, "n_pairs": s["n_pairs"], "added": s["added"],
            "stable_bits": s["stable_bits"], "stability_pct": s["stability_pct"],
            "pool": self._pool_payload(tid)})
        self.app.persist_terminal(tid)
        return run_id

    # ---------- 维护命令(与 REPL cmd_c2reset / cmd_setkey 同法) ----------
    def _do_c2reset(self, job: Job) -> bool:
        tid = int(job.tid or 0)
        self.protocol.reset_c2_history(tid)
        self.store.clear_c2_history(tid)
        self._cached_c2.pop(tid, None)
        self.hub.publish("server.log", {"level": "info",
                                        "msg": f"c2 replay window cleared tid={tid}"})
        return True

    def _do_setkey(self, job: Job) -> bool:
        tid = int(job.tid or 0)
        if int(tid) in getattr(self.app, "real_serial_tids", set()):
            # 不阻断(重烧板后的重新对钥依赖此入口),但必须留下显眼审计痕迹:
            # 真板密钥被覆盖会直接导致后续 PASS 轮 R2 全错、CONFIRM 永不出现。
            self.hub.publish("server.log", {
                "level": "warn",
                "msg": f"setkey tid={tid}: 真板终端设备密钥被显式覆盖 —— 若非有意重对钥,"
                      f"请立即恢复,否则真板 CONFIRM 将失败"})
        key = bytes.fromhex(job.key_hex or W3_DEMO_KEY_HEX)
        self.store.set_key(tid, key)
        hsm = self.protocol.hsm
        if isinstance(hsm, self.mods.SpeckHSM):
            hsm.set_key(tid, key)
        self.hub.publish("server.log", {
            "level": "info",
            "msg": f"device key installed tid={tid} ({len(key)}B)"
                   + ("" if job.key_hex else " [W3 demo key]")})
        return True

    def _do_demo_reset(self, job: Job) -> bool:
        tid = int(job.tid or 0)
        # 守卫:demo_reset 会先删 pool_{tid}.json 并重置 C2 历史,再走 fresh enroll——
        # 对真板 tid 前半段就已不可逆破坏实板池源文件(RealSerialListener 的注入源),
        # 必须在一切动作之前拒绝。
        if int(tid) in getattr(self.app, "real_serial_tids", set()):
            why = (f"demo_reset tid={tid} 已拒绝:该终端为真板终端,重置会删除其实板"
                   f"挑战池文件并清空重放记录(不可逆)。S5 重演请用演示终端(7/9/88)。")
            self.hub.publish("server.log", {"level": "warn", "msg": why})
            self.hub.publish("run.error", {"run_id": self.next_run_id(), "stage": "demo_reset",
                                            "error": why, "terminal_id": tid})
            return False
        """S5 重演:清小池演示终端状态并按小池容量重新注册(§8.1)。"""
        tid = int(job.tid or 0)
        self.protocol.pools.remove(tid)
        (self.app.data.pools_dir / f"pool_{tid}.json").unlink(missing_ok=True)
        demo = next((d for d in self.app.args.demo_terminals if d.tid == tid), None)
        size = demo.pool_size if demo else 20
        prewrite_small_pool(self.app.data.pools_dir, tid, size)
        self.protocol.reset_c2_history(tid)
        self.store.clear_c2_history(tid)
        self._cached_c2.pop(tid, None)
        self._do_enroll(Job(kind="enroll", tid=tid, n=size, fresh=True,
                            run_id=self.next_run_id()))
        self.hub.publish("server.log", {"level": "info",
                                        "msg": f"demo terminal {tid} reset (pool={size})"})
        return True

    # ---------- 首启引导(幂等) ----------
    def _do_bootstrap(self, job: Job) -> bool:
        for demo in self.app.args.demo_terminals:
            tid = demo.tid
            rec = self.app.state.terminals.get(tid)
            if rec and rec.get("freqs"):
                # Phase A A1:以记录的 16 环频率向量重建器件并注入 transport。
                # LoopbackTransport 构造无参、terminal() 懒创建,公共注入路径不
                # 存在 —— 走 _terminals 私有字典(README 偏差 D20 登记,升级
                # main.py 时复查)。_auth_count 必须一并恢复,否则 C2 计数回卷
                # 会撞上服务端已持久化的重放窗,首次认证被误判 REPLAY。
                freqs = [int(f) for f in rec["freqs"]]
                term = self.app.mods.SimulatedTerminal(tid, freqs=freqs)
                term._auth_count = int(rec.get("auth_count", 0))
                self.transport.inner._terminals[tid] = term
            elif self.protocol.templates.has_terminal(tid):
                self.hub.publish("server.log", {
                    "level": "warn",
                    "msg": f"tid={tid}: templates exist but no persisted freqs; "
                           f"run /api/enroll to re-enroll"})
            if not self.protocol.templates.has_terminal(tid):
                self.hub.publish("server.log", {
                    "level": "info", "msg": f"first boot: enrolling demo terminal {tid}"})
                self._do_enroll(Job(kind="enroll", tid=tid,
                                    n=demo.pool_size, run_id=self.next_run_id()))
            # 让 registry 立即构造该池:否则 /api/status 的 pools[] 在首次认证
            # 之前为空,前端池水位无从显示(registry 是按需建池的)。
            self.protocol.pools.get(tid)
            self.app.persist_terminal(tid)
        self.hub.publish("server.log", {
            "level": "info",
            "msg": "bridge ready: terminals={}".format(
                [d.tid for d in self.app.args.demo_terminals])})
        return True

    # ---------- V1 HD 双系列采样(/api/viz/hd) ----------
    def _do_viz_hd(self, job: Job) -> dict:
        tid = int(job.tid if job.tid is not None else self.app.args.demo_terminals[0].tid)
        templates = self.protocol.templates.templates.get(str(tid))
        if not templates:
            raise RuntimeError(f"no templates for terminal {tid} (enroll first)")
        seed_hexes = list(templates.keys())
        _secrets.SystemRandom().shuffle(seed_hexes)
        seeds = [bytes.fromhex(s) for s in seed_hexes[:200]]
        genuine = self.transport.inner.terminal(tid)
        intra = self.protocol.templates.hamming_distances(
            tid, seeds, genuine.respond(seeds))
        impostor = self.mods.SimulatedTerminal(-1 - tid)
        inter = self.protocol.templates.hamming_distances(
            tid, seeds, impostor.respond(seeds))
        return {"intra": intra, "inter": inter}


# ============================================================
# §6 RealApp —— 组员 server 栈的桥接装配(main.py 主流程同法)
# ============================================================
class RealApp:
    mock = False

    def __init__(self, args, mods: _Mods) -> None:
        self.args = args
        self.mods = mods
        self.hub = SSEHub()
        self.data = DataDir(Path(args.data_dir))
        self.data.mkdir_all()
        # N2/N5(finals-demo) 跨批次契约锚点:注册会话窗口标志。N5 的串口注册
        # runner 进入/退出时置 True/False;RealSerialListener._loop 的信道 IDS
        # 在窗口内静默(注册期站端自己连发 0x0091,防自触发)。在此显式初始化,
        # 使 N5 接线若命名/宿主漂移在导入/首跑即显形,而不是注册演示日弹假红警。
        self.enroll_session_active = False
        # N5(finals-demo): response queue for real-board enrollment
        self.enroll_response_q: Queue = Queue()
        # auto-review R2 P2:串口写互斥锁——_auth(监听线程)与 _do_poll(编排
        # 线程)/N5 enroll runner 并发写同一 ser 会在线上交错损帧;锁住全部写口。
        self.serial_bus_lock = threading.Lock()
        # 认证进行中标志:_loop 进出 _auth 时维护;_do_poll 忙拒用(串行化演示)
        self.auth_in_progress = False
        # Phase A A2:v1(secret_hex)状态与 ROPairingPUF 不兼容 —— 在 TemplateDB /
        # CRPPoolRegistry 构造之前做一次性迁移:凡没有 v2 freqs 记录的模板终端,
        # 连同池文件与状态记录一并作废(残留模板会让首次认证静默 REJECT;且旧
        # pool_<tid>.json 的 committed 容量优先于构造参数,事后清不掉)。
        self.state = BridgeState(self.data.state_json)
        stale = self._legacy_stale_tids()
        if stale:
            self._purge_stale_terminals(stale)
        # S5 小池桩必须在 CRPPoolRegistry 首次构造该池之前落盘
        for demo in args.demo_terminals:
            if demo.pool_size < args.pool_size:
                prewrite_small_pool(self.data.pools_dir, demo.tid, demo.pool_size)
        templates = mods.TemplateDB(str(self.data.templates_json))
        try:
            self.store = mods.DeviceKeyStore(str(self.data.device_keys_json)).load()
        except ValueError as exc:
            raise SystemExit(
                f"[ERROR] device key store unusable: {exc}\n"
                f"        move it aside or pass a fresh --data-dir") from None
        hsm = mods.SpeckHSM(keys=self.store.all_keys())
        pools = mods.CRPPoolRegistry(str(self.data.pools_dir), pool_size=args.pool_size)
        self.protocol = mods.HFIDAProtocol(templates=templates, hsm=hsm, pools=pools)
        for tid in hsm.terminal_ids():
            self.protocol.set_c2_history(tid, self.store.c2_history(tid))
        self.transport = MeasurementProxyTransport(mods.LoopbackTransport())
        self.proxy = TerminalProxy(mods, self.protocol, self.store)
        self.orch = Orchestrator(self)
        self.started = time.monotonic()
        self._telemetry_stop = threading.Event()
        # finals-demo-drone:无人机演示模拟器(独立线程+自有锁;门控=verdict tap)
        self.drone = DroneSim(self.hub)
        # finals-demo-drone 加分项:标准 MAVLink UDP 转发(--mavlink-udp 开启;
        # 真 QGroundControl 可直连,认证门控语义不变)
        self.mavlink_fwd = (_mavlink_start_udp(self.hub, self.drone,
                                               args.mavlink_udp)
                            if getattr(args, "mavlink_udp", None) else None)
        # finals-demo-N6(access gate): 接入闸门——SW7 主动认证的人工选择队列
        # (方案v2: docs/process/plans/access_gate_design_20261116.md)。
        # decide() 必须在 proto.on_access_request 之前调用(C2 重放窗只在其中
        # 消费,入队不得污染:F12);多串口时 main() 强制 enabled=True——两板
        # 并发 SW7 的串行化保护(未选中的一律入队,防 _auth 状态交叉污染)。
        self.serial_listeners: dict = {}
        # auto-review(R3): per-tid 请求信号——闸门唤醒的成功判据必须是"本tid
        # 有新请求"(F1让任何板入队都刷新全局戳,跨板按压会造成假成功并
        # selected_tid 悬挂死锁闸门)。全局戳保留给 _do_poll 遗留契约。
        self.last_access_request_by_tid: dict = {}
        self.tid_port_map: dict = parse_int_kv(getattr(args, "tid_port", None))
        self.access_gate = AccessGate(
            enabled=bool(getattr(args, "access_gate", False)),
            labels=parse_int_kv(getattr(args, "access_label", None)))

    # ---- 生命周期 ----
    def start(self) -> None:
        self.orch.start()
        self.orch.submit(Job(kind="bootstrap"))
        threading.Thread(target=self._telemetry, name="telemetry", daemon=True).start()

    def shutdown(self) -> None:
        self._telemetry_stop.set()
        self.drone.stop()               # finals-demo-drone:停模拟器线程
        if self.mavlink_fwd is not None:
            self.mavlink_fwd.stop()     # finals-demo-drone:停 MAVLink 转发
        try:
            self.mods.flush_c2_state(self.protocol, self.store)
        except Exception:
            pass
        for tid in list(self.state.terminals):
            self.persist_terminal(tid)
        self.orch.stop()

    def _legacy_stale_tids(self) -> set[int]:
        """没有 v2 freqs 记录、却已有模板/池/状态残留的终端集合。"""
        stale: set[int] = set(self.state.legacy_tids)
        has_v2 = {tid for tid, rec in self.state.terminals.items() if rec.get("freqs")}
        try:
            raw = json.loads(self.data.templates_json.read_text(encoding="utf-8"))
            # TemplateDB 存储是扁平的 {tid_str: {seed_hex: resp_hex}},无外层包装
            for tid_s, rows in raw.items():
                if (isinstance(rows, dict) and rows and str(tid_s).isdigit()
                        and int(tid_s) not in has_v2):
                    stale.add(int(tid_s))
        except (OSError, ValueError):
            pass
        for demo in getattr(self.args, "demo_terminals", []):
            if ((self.data.pools_dir / f"pool_{demo.tid}.json").exists()
                    and demo.tid not in has_v2):
                stale.add(demo.tid)
        return stale

    def _purge_stale_terminals(self, tids: set[int]) -> None:
        """级联清理 stale 终端:池文件 + 模板段 + 稳定性 sidecar + 状态记录。"""
        print(f"[INFO] migrating bridge state -> {STATE_SCHEMA}: purging terminals "
              f"{sorted(tids)} (templates+pool+state); bootstrap will re-enroll")
        for tid in tids:
            (self.data.pools_dir / f"pool_{tid}.json").unlink(missing_ok=True)
            self.state.terminals.pop(tid, None)
            self.state.legacy_tids.discard(tid)
        try:
            raw = json.loads(self.data.templates_json.read_text(encoding="utf-8"))
            raw = raw if isinstance(raw, dict) else {}
        except (OSError, ValueError):
            raw = {}
        # TemplateDB 存储是扁平的 {tid_str: {seed_hex: resp_hex}}:直接删顶层键
        for tid in tids:
            raw.pop(str(tid), None)
        self.data.templates_json.parent.mkdir(parents=True, exist_ok=True)
        self.data.templates_json.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        for sidecar in self.data.templates_json.parent.glob("*.stability.json"):
            try:
                sraw = json.loads(sidecar.read_text(encoding="utf-8"))
                if not isinstance(sraw, dict):
                    continue
                for tid in tids:
                    sraw.pop(str(tid), None)
                sidecar.write_text(json.dumps(sraw, indent=2), encoding="utf-8")
            except (OSError, ValueError):
                pass
        self.state.save()

    def persist_terminal(self, tid: int) -> None:
        """把代演终端的 PUF 频率向量落盘(重启后 S1 仍能通过)。"""
        try:
            term = self.transport.inner.terminal(int(tid))
        except Exception:
            return
        self.state.terminals[int(tid)] = {
            # Phase A A2:ROPairingPUF 器件身份 = 16 环频率向量(取代 secret_hex)
            "freqs": [int(f) for f in term.freqs],
            "auth_count": int(getattr(term, "_auth_count", 0)),
        }
        self.state.save()

    def _telemetry(self) -> None:
        warned: set[int] = set()
        while not self._telemetry_stop.wait(5.0):
            self.hub.publish("link.status", self.link_status())
            for pool in self.protocol.status()["pools"]:
                tid, pct = pool["terminal_id"], pool["remaining_pct"]
                if pct < 20:
                    if tid not in warned:
                        warned.add(tid)
                        self.hub.publish("pool.warning", {
                            "terminal_id": tid, "remaining": pool["remaining"],
                            "pct": pct})
                else:
                    warned.discard(tid)

    def link_status(self) -> dict:
        return {"mode": "loopback", "connected": True,
                "uptime_s": int(time.monotonic() - self.started),
                "proxy": True, "version": VERSION}

    # ---- /api/status 三源组装:protocol.status() + templates.status() + hsm_status() ----
    def status(self) -> dict:
        proto = self.protocol.status()
        return {
            "link": self.link_status(),
            "sessions": proto["sessions"],
            "templates": self.protocol.templates.status(),
            "pools": [{"terminal_id": p["terminal_id"], "remaining": p["remaining"],
                       "pool_size": p["pool_size"], "pct": p["remaining_pct"]}
                      for p in proto["pools"]],
            "hsm": {"available": self.mods.hsm_status(self.protocol.hsm)
                    .get("backend") == "speck64/96",
                    "keys": len(self.protocol.hsm.terminal_ids())
                    if isinstance(self.protocol.hsm, self.mods.SpeckHSM) else 0},
            "drone": self.drone.snapshot(),   # finals-demo-drone:SSE 断档重同步
        }

    # ---- REST 面(全部经编排器串行化) ----
    def submit_auth(self, tid: int, mode: str) -> str:
        run_id = self.orch.next_run_id()
        self.orch.submit(Job(kind="auth", tid=tid, mode=mode, run_id=run_id))
        return run_id

    def submit_enroll(self, tid: int, n: int) -> str:
        run_id = self.orch.next_run_id()
        self.orch.submit(Job(kind="enroll", tid=tid, n=n, run_id=run_id))
        return run_id

    def submit_poll(self, tid: int) -> str:
        """N4(finals-demo): station-initiated AUTH_POLL (remote SW7)."""
        run_id = self.orch.next_run_id()
        self.orch.submit(Job(kind="poll", tid=tid, run_id=run_id))
        return run_id

    # ---- finals-demo-N6: 接入闸门 REST 面(access gate) ----
    def resolve_listener(self, tid: int):
        """tid → 监听器路由。查表顺序:闸门队列 port → --tid-port 静态映射 →
        单监听器直通;多监听器且无映射 → None(调用方给人话错误)。
        方案v2 R1-P1 修复:原 serial_listener 单引用在双口下会把板B的 poll
        打到板A口(含录入向导"验证认证"按钮)。"""
        lns = getattr(self, "serial_listeners", None) or {}
        if not lns:
            return getattr(self, "serial_listener", None)
        gate = getattr(self, "access_gate", None)
        if gate is not None:
            e = gate.snapshot(int(tid))
            if e and e["port"] in lns:
                return lns[e["port"]]
        port = self.tid_port_map.get(int(tid))
        if port and port in lns:
            return lns[port]
        if len(lns) == 1:
            return next(iter(lns.values()))
        return None

    def _poll_wake_once(self, ln, tid: int, run_id: str) -> None:
        """发一帧 AUTH_POLL 并等 ACCESS_REQUEST(3s)。纪律照抄 _do_poll:
        串口锁内写、先写后发(时间线不出现未发出的帧)。超时抛 TimeoutError。"""
        nonce = time.time_ns() & 0xFFFFFFFF
        frame = self.protocol.pack(
            type(self.protocol).MSG_AUTH_POLL, terminal_id=tid, nonce=nonce)
        # auto-review(R3): 成功判据 per-tid(本板有新请求才算回应)。
        # 全局戳只作无 per-tid 表(旧假 app)时的回退;闸门下其他板入队/认证
        # 刷的全局戳不得让本次唤醒假成功——那会 selected 悬挂死锁闸门。
        by_tid = getattr(self, "last_access_request_by_tid", None)
        base_t = by_tid.get(tid, 0.0) if by_tid is not None else 0.0
        base = getattr(self, "last_access_request_ts", 0.0)
        with self.serial_bus_lock:
            ln.ser.write(frame); ln.ser.flush()
        self.hub.publish("poll.sent",
                         {"run_id": run_id, "terminal_id": tid, "nonce": nonce})
        self.hub.publish("frame.tx", {
            "run_id": run_id, "terminal_id": tid,
            "msg_id": type(self.protocol).MSG_AUTH_POLL, "name": "AUTH_POLL",
            "hex": frame.hex(), "len": len(frame),
            "dir": "server->term", "source": "real-terminal"})
        t0 = time.time()
        while time.time() - t0 < 3.0:
            if by_tid is not None:
                if by_tid.get(tid, 0.0) > base_t:
                    return
            elif getattr(self, "last_access_request_ts", 0.0) > base:
                return
            time.sleep(0.02)
        raise TimeoutError("no ACCESS_REQUEST within 3s after AUTH_POLL")

    def access_select(self, tid: int) -> tuple[int, dict]:
        """POST /api/access/select:人工选择一台排队机器 → 2.2s 边界对齐唤醒。

        时序依据(方案v2 F10/F11,RTL 定案):板端 2s 等待窗内 POLL 被无视,
        超时即回 S_IDLE——故等 last_request_ts+2.2 再发,一击命中;
        失败防御性重试一次(再对齐 2.2s),仍失败回滚选中并 409。"""
        tid = int(tid)
        gate = getattr(self, "access_gate", None)
        if gate is None or not gate.enabled:
            return 409, {"ok": False,
                         "reason": "access gate disabled (start with --access-gate)"}
        reason = gate.can_select(tid)
        if reason:
            code = 404 if reason == "not queued" else 409
            return code, {"ok": False, "reason": reason}
        ln = self.resolve_listener(tid)
        if ln is None or not getattr(ln, "running", False):
            return 409, {"ok": False,
                         "reason": f"tid={tid} 的串口无法定位:多口模式需 --tid-port "
                                   f"或该机先按一次 SW7 入队"}
        if getattr(self, "auth_in_progress", False):
            return 409, {"ok": False,
                         "reason": "auth in progress; retry after current round"}
        entry = gate.snapshot(tid)
        run_id = f"gate-{int(time.time() * 1000)}"
        gate.set_selected(tid)   # 先置选中:唤醒到达的新请求 decide() 即放行
        try:
            delta = 2.2 - (time.time() - entry["last_request_ts"])
            if delta > 0:
                time.sleep(delta)
            # auto-review(R1-F3): 对齐睡眠期间该板被再按 SW7 → 认证已走完并
            # 出队(finish 清了 entry/selected)。此时不再发 POLL——否则会把
            # 已验证完的机器重新入队。按"已被并发处理"成功返回。
            if gate.snapshot(tid) is None or not gate.is_selected(tid):
                return 200, {"ok": True, "terminal_id": tid, "run_id": run_id,
                             "note": "already consumed by concurrent auth"}
            try:
                self._poll_wake_once(ln, tid, run_id)
            except TimeoutError:
                time.sleep(2.2)   # 防御性重试(板 BLOCKED 长滞/首帧丢失)
                if gate.snapshot(tid) is None or not gate.is_selected(tid):
                    return 200, {"ok": True, "terminal_id": tid, "run_id": run_id,
                                 "note": "already consumed by concurrent auth"}
                self._poll_wake_once(ln, tid, run_id)
        except Exception as exc:  # noqa: BLE001 —— 唤醒失败必须回滚选中
            gate.clear_selected(tid)
            return 409, {"ok": False, "reason":
                         f"唤醒失败({exc}):板端可能 BLOCKED(按 SW13 重置后重试)或链路断"}
        self.hub.publish("access.selected",
                         {"terminal_id": tid, "ts": now_iso(), "run_id": run_id})
        return 200, {"ok": True, "terminal_id": tid, "run_id": run_id}

    def access_dismiss(self, tid: int) -> tuple[int, dict]:
        """POST /api/access/dismiss:手动撤下排队条目(选中验证中的拒 409)。"""
        tid = int(tid)
        gate = getattr(self, "access_gate", None)
        if gate is None or not gate.enabled:
            return 409, {"ok": False, "reason": "access gate disabled"}
        reason = gate.can_dismiss(tid)
        if reason:
            code = 404 if reason == "not queued" else 409
            return code, {"ok": False, "reason": reason}
        gate.dismiss(tid)
        self.hub.publish("access.dismissed", {"terminal_id": tid})
        return 200, {"ok": True, "terminal_id": tid}

    def access_queue(self) -> dict:
        """GET /api/access/queue:队列快照(页面刷新恢复)。"""
        gate = getattr(self, "access_gate", None)
        if gate is None or not gate.enabled:
            return {"entries": [], "selected": None,
                    "enabled": bool(gate is not None and gate.enabled)}
        return {"entries": gate.queue_snapshot(),
                "selected": gate.selected_tid, "enabled": True}

    def c2reset(self, tid: int) -> bool:
        return bool(self.orch.submit_sync(Job(kind="c2reset", tid=tid)).result)

    def setkey(self, tid: int, key_hex: str | None) -> bool:
        return bool(self.orch.submit_sync(
            Job(kind="setkey", tid=tid, key_hex=key_hex)).result)

    def demo_reset(self, tid: int) -> bool:
        return bool(self.orch.submit_sync(
            Job(kind="demo_reset", tid=tid), timeout=300).result)

    def drone_cmd(self, tid: int, cmd: str, body: dict) -> dict:
        """finals-demo-drone:飞行指令(REST /api/drone/cmd)。

        自包含内存操作:DroneSim 自带互斥锁,不触碰 protocol/串口/文件,
        故不走编排器串行化——与上方"REST 面全部经编排器"注释所针对的
        protocol 状态类操作不同源,在此显式豁免并注明防后人误改。
        """
        return self.drone.command(tid, cmd,
                                  body.get("x"), body.get("y"), body.get("alt"))

    # ---- 黄金帧:读 docs/protocol_contract.md §4(静态真实) ----
    def golden_frames(self) -> list[dict[str, str]]:
        path = Path(self.args.repo_root) / "docs" / "protocol_contract.md"
        try:
            text = path.read_text(encoding="utf-8")
            section = text.split("## 4.", 1)[1].split("### 4.1", 1)[0]
            block = section.split("```", 2)[1]
            frames: list[dict[str, str]] = []
            name = note = ""
            buf: list[str] = []
            for line in block.splitlines():
                s = line.strip()
                if s.startswith("#"):
                    if name and buf:
                        frames.append({"name": name, "note": note,
                                       "hex": "".join(buf)})
                    parts = s.lstrip("#").strip().split(None, 1)
                    name = parts[0] if parts else ""
                    note = parts[1] if len(parts) > 1 else ""
                    buf = []
                elif s:
                    toks = s.split()
                    if all(len(t) == 2 and all(c in "0123456789abcdefABCDEF" for c in t)
                           for t in toks):
                        buf.extend(t.lower() for t in toks)
            if name and buf:
                frames.append({"name": name, "note": note, "hex": "".join(buf)})
            if frames:
                return frames
        except Exception as exc:
            print(f"[WARN] golden frames from docs unavailable ({exc}); using built-in copy")
        return GOLDEN_FRAMES_FALLBACK

    def viz_hd(self, fresh: bool) -> dict:
        """V1 的 HD 双系列。缺省先看 tools/sample_hd.py 落盘的离线样本,?fresh=1 现场重采。

        **落盘样本必须带时效校验,且两侧都要校**:HD 是「响应 ↔ 已登记模板」的距离,
        它的两个输入端分别是**模板表**和**器件密钥**,任一端变过,样本就作废。
          - 模板端:templates_sig(跑一次 S6 注册就换一批种子);
          - 器件端:device_sig(状态文件被删/重建后 secret 会重新随机 —— 此时种子
            集合可以完全没变,单看模板签名会误判样本仍然有效)。
        少校任何一端,页面都会继续展示上一版输入的分离度:一个不报错、看起来完全
        正常的错数,而且它会一路进报告。
        """
        if not fresh:
            cached = self.data.read_hd_sample()
            if cached is not None:
                sig, payload = cached
                tid_hint = int(payload["terminal_id"])
                ok_tpl = sig == templates_sig(self.protocol.templates, tid_hint)
                ok_dev = payload.get("device_sig") == self.device_sig(tid_hint)
                if ok_tpl and ok_dev:
                    # 只回传契约要的两个序列 + 两个溯源字段。落盘样本里还有
                    # templates_sig/device_sig/sampled_at/templates_json,那些是**校验
                    # 输入**而非展示数据:尤其 templates_json 是采样那台机器上的绝对
                    # 路径,对本机浏览器毫无意义,却会出现在页面截图上。
                    # 两条支路(intra/inter 同形)也刻意保持一致 —— 前端不该按 source
                    # 分支解析同一个端点。
                    return {
                        "intra": payload["intra"],
                        "inter": payload["inter"],
                        "note": (f"离线采样样本(tools/sample_hd.py,{payload['sampled_at']},"
                                 f"tid={tid_hint},n={len(payload['intra'])});"
                                 f"加 ?fresh=1 可现场重采"),
                        "source": "SAMPLE",
                    }
                why = "模板表变过" if not ok_tpl else "器件密钥换过"
                print(f"[INFO] viz/hd: 落盘样本已失效({why}),改用现场采样")
        job = self.orch.submit_sync(Job(kind="viz_hd"), timeout=120)
        if job.error:
            return {"intra": [], "inter": [], "note": job.error, "source": "LIVE"}
        out = dict(job.result)
        out["source"] = "LIVE"
        out.setdefault("note", f"现场采样(本次请求现算,{len(out.get('intra') or [])} 个种子)")
        return out

    def device_sig(self, tid: int) -> str:
        """代演终端器件指纹(ROPairingPUF freqs;与 tools/sample_hd.py 同法)。"""
        try:
            freqs = self.transport.inner.terminal(int(tid)).freqs
        except Exception:
            return ""
        return freqs_sig(freqs)

    def viz_templates(self) -> dict:
        t = self.protocol.templates
        return {"source": "LIVE",
                "terminals": {
                    tid: {"responses": dict(resp),
                          "stability_mask": t.stability.get(tid, "1" * 64)}
                    for tid, resp in t.templates.items()}}

    def viz_measurements(self, tid: int | None) -> dict:
        series = self.transport.measurements_of(tid)
        return {"terminal_id": tid, "captured": bool(series), "series": series,
                "source": "LIVE",
                "note": None if series else
                        "本次进程尚未捕获注册测量(先跑 S6 注册);捕获仅内存保留"}


    # ---------- B1:ML 攻击实验数据(W4 真实产物,REAL-STATIC) ----------
    def viz_ml(self) -> dict:
        base = Path(self.args.repo_root) / "data" / "ml_attack"
        out: dict[str, Any] = {"source": "STATIC"}
        for key, name in (("a", "exp_a_results.json"), ("b", "exp_b_results.json")):
            try:
                out[key] = json.loads((base / name).read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                out[key] = None
                out.setdefault("errors", {})[key] = str(exc)
        if out.get("a") is None and out.get("b") is None:
            out["note"] = (f"data/ml_attack 结果缺失({base});复现:python -m "
                           f"src.python.evaluation.ml_attack --exp A|B --out data/ml_attack --seed 42")
        else:
            out["note"] = "W4-P5 ML 攻击实验真实产物(e083f63);复现命令见各 payload.repro_command"
        return out

    # ---------- B2:reliability 模型曲线(ROPairingPUF.measure,MODEL) ----------
    def viz_reliability(self, query: str = "") -> dict:
        """黄金模型推演的可靠度-缩放曲线:上板前 G5 reliability 指标的纯 PC 兜底。

        每个缩放点:ROPairingPUF.measure(jitter,scale) 扰动频率向量 → 重建终端 →
        对模板种子逐应答 → hamming_distances 统计。判定口径逐字对齐 threshold.py
        (单响应 HD<=TAU_PASS 判过)。全公共 API,零改服务器。
        """
        try:
            tid = self._reliability_tid()
            rows = self.protocol.templates.templates.get(str(tid)) or {}
            seeds = [bytes.fromhex(s) for s in sorted(rows)[:128]]
            if not seeds:
                return {"source": "MODEL", "points": [],
                        "note": f"终端 {tid} 无模板 —— 先跑 S1/S6 注册"}
            jitter = 1.5
            for kv in query.split("?")[-1].split("&"):
                if kv.startswith("jitter="):
                    try:
                        jitter = max(0.0, min(10.0, float(kv.split("=", 1)[1])))
                    except ValueError:
                        pass
            term = self.transport.inner.terminal(tid)
            puf = self.mods.ROPairingPUF(freqs=term.freqs)
            scales = [0.90, 0.92, 0.94, 0.96, 0.98, 1.00, 1.02, 1.04, 1.06, 1.08, 1.10]
            points = []
            for s in scales:
                pert = puf.measure(jitter_pct=jitter, scale=s)
                probe = self.mods.SimulatedTerminal(tid, freqs=pert)
                pts = list(self.protocol.templates.hamming_distances(
                    tid, seeds, probe.respond(seeds)))
                points.append({
                    "scale": s,
                    "mean_hd": round(sum(pts) / len(pts), 3),
                    "max_hd": max(pts),
                    "pass_rate": round(
                        sum(1 for h in pts if h <= self.mods.TAU_PASS) / len(pts), 4),
                })
            return {
                "source": "MODEL",
                "params": {"terminal_id": tid, "n_seeds": len(seeds),
                           "jitter_pct": jitter, "scales": scales,
                           "flip_prob": "SimulatedTerminal 默认(0.02)"},
                "points": points,
                "note": ("ROPairingPUF 黄金模型推演(measure 缩放+抖动),非上板实测;"
                         "上板后由 VIO 温度实验替换,schema 不变"),
            }
        except Exception as exc:
            return {"source": "MODEL", "points": [], "note": f"模型推演失败:{exc}"}

    def _reliability_tid(self) -> int:
        demos = getattr(self.args, "demo_terminals", None) or []
        if demos:
            return int(demos[0].tid)
        if self.state.terminals:
            return min(int(t) for t in self.state.terminals)
        return 7


# ============================================================
# §7 MockApp —— --mock 回放:零 server import、零数据写入;
# HTTP 层与 RealApp 共享同一路由(§8.4:mock 供 UI/3D 并行开发)
# ============================================================
_MOCK_SEQ = 0x60


def _mock_frame(msg_id: int, payload_hex: str, tid: int) -> str:
    """MOCK 帧头(仅演示用;真帧一律来自 protocol.pack)。"""
    p_len = len(payload_hex) // 2
    return (f"FD{p_len:02X}0000{_MOCK_SEQ:02X}0102{msg_id & 0xFF:02X}"
            f"{(msg_id >> 8) & 0xFF:02X}00" + payload_hex + "0000")


class MockApp:
    """显式 MOCK(报告 §4.4):数据全部标 source=MOCK,不冒充实测。"""
    mock = True

    def __init__(self, args) -> None:
        self.args = args
        self.hub = SSEHub()
        self.started = time.monotonic()
        self._q: Queue = Queue()
        threading.Thread(target=self._replay_worker, name="mock-replay", daemon=True).start()
        threading.Thread(target=self._telemetry, name="telemetry", daemon=True).start()
        self.drone = DroneSim(self.hub)   # finals-demo-drone:mock 演示路径一致
        self.mavlink_fwd = (_mavlink_start_udp(self.hub, self.drone,
                                               args.mavlink_udp)
                            if getattr(args, "mavlink_udp", None) else None)

    def _replay_worker(self) -> None:
        while True:
            run_id, tid, mode = self._q.get()
            for etype, payload in self._script_auth(run_id, tid, mode):
                self.hub.publish(etype, payload)
                time.sleep(0.4)

    def _script_auth(self, run_id: str, tid: int = 7,
                     mode: str = "normal") -> list[tuple[str, dict]]:
        """一条 S1 事件脚本(HD 值与黄金帧 §4 的 RESULT hd=5 对齐)。"""
        tid = 7
        script = [
            (0x0090, "term->server", "ACCESS_REQUEST",
             "07000000" + "2B000000" + "A1A2A3A4A5A6A7A8"),
            (0x0091, "server->term", "CHALLENGE",
             "A000000000000000" "A101010101010101" "A202020202020202" "A303030303030303"),
            (0x0092, "term->server", "RESPONSE_R1",
             "B000000000000000" "B101010101010101" "B202020202020202" "B303030303030303"),
            (0x0093, "server->term", "RESULT", "00" + "05" + "7B45B0545E59AA94"),
            (0x0094, "term->server", "CONFIRM", "07000000" + "00"),
        ]
        out: list[tuple[str, dict]] = []
        for msg_id, direction, name, payload in script:
            out.append(("frame.tx" if direction == "server->term" else "frame.rx", {
                "run_id": run_id, "terminal_id": tid, "msg_id": msg_id, "name": name,
                "hex": _mock_frame(msg_id, payload, tid), "len": 12 + len(payload) // 2,
                "dir": direction, "source": "simulated-terminal"}))
            if msg_id == 0x0093:
                out.append(("verdict", {
                    "run_id": run_id, "terminal_id": tid, "result": 0,
                    "result_name": "PASS", "n_responses": 4, "hd": 5,
                    "hd_per_response": [1, 2, 1, 1], "r2": GOLDEN_R2_HEX,
                    "pool": {"remaining": 484, "pool_size": 500, "pct": 97},
                    "thresholds": {"tau_pass": 6, "tau_reject": 16,
                                   "scaled_pass": 24, "scaled_reject": 64}}))
            if msg_id == 0x0094:
                out.append(("confirm.done", {"run_id": run_id, "terminal_id": tid,
                                             "status": 0, "verified_r2": True}))
        out.append(("session.update", {
            "terminal_id": tid, "state": "SESSION", "challenges_issued": 4,
            "responses_scored": 4, "hd_sum": 5, "last_decision": "PASS"}))
        return out

    def start(self) -> None:
        self.hub.publish("server.log", {
            "level": "warn", "msg": "[MOCK] canned replay data — not measured from hardware"})

    def shutdown(self) -> None:
        self.drone.stop()               # finals-demo-drone
        if self.mavlink_fwd is not None:
            self.mavlink_fwd.stop()

    def _telemetry(self) -> None:
        while True:
            self.hub.publish("link.status", self.link_status())
            time.sleep(5)

    def link_status(self) -> dict:
        return {"mode": "loopback", "connected": True,
                "uptime_s": int(time.monotonic() - self.started),
                "proxy": True, "version": f"{VERSION}-mock"}

    def status(self) -> dict:
        return {
            "link": self.link_status(),
            "sessions": [],
            "templates": [
                {"terminal_id": "7", "n_pairs": 500, "stable_bits": 61},
                {"terminal_id": "9", "n_pairs": 500, "stable_bits": 60},
                {"terminal_id": "88", "n_pairs": 20, "stable_bits": 62}],
            "pools": [
                {"terminal_id": 7, "remaining": 484, "pool_size": 500, "pct": 97},
                {"terminal_id": 9, "remaining": 496, "pool_size": 500, "pct": 99},
                {"terminal_id": 88, "remaining": 3, "pool_size": 20, "pct": 15}],
            "hsm": {"available": True, "keys": 3},
            "drone": self.drone.snapshot(),   # finals-demo-drone
        }

    def submit_auth(self, tid: int, mode: str) -> str:
        run_id = f"mock-{int(time.time() * 1000) % 100000}"
        # P3(mock 保真):回放脚本使用提交的 tid 与 mode —— 原先固定 tid=7、
        # 不分 mode,选其他终端点认证会空转到超时,spoof/replay 也回放 PASS。
        self._q.put((run_id, int(tid), str(mode)))
        return run_id

    def submit_enroll_real(self, tid, n, measurements):
        run_id = "mock-er" + str(int(time.time() * 1000) % 100000)
        self.hub.publish("run.error", {
            "run_id": run_id, "stage": "enroll_real", "terminal_id": tid,
            "error": "enroll_real requires real-serial mode: mock has no board"})
        return run_id

    def submit_poll(self, tid: int) -> str:
        # N4(finals-demo): mock 模式无真板可唤醒,同步回错误(不挂起不假成功);
        # run_id 事件与返回值同源(store.onRunError 按 run_id 关联,R2 P3)
        run_id = f"mock-p{int(time.time() * 1000) % 100000}"
        self.hub.publish("run.error", {
            "run_id": run_id,
            "stage": "poll", "terminal_id": tid,
            "error": "poll requires real-serial mode: mock has no board to wake"})
        return run_id

    # finals-demo-N6: mock 无真板无闸门——与 submit_poll 同款"同步回错"语义
    def access_select(self, tid: int) -> tuple[int, dict]:
        return 409, {"ok": False,
                     "reason": "access gate requires real-serial mode: mock has no board"}

    def access_dismiss(self, tid: int) -> tuple[int, dict]:
        return 409, {"ok": False, "reason": "access gate disabled (mock mode)"}

    def access_queue(self) -> dict:
        return {"entries": [], "selected": None, "enabled": False}

    def drone_cmd(self, tid: int, cmd: str, body: dict) -> dict:
        """finals-demo-drone:与 RealApp 同名方法同构(mock 路径一致)。"""
        return self.drone.command(tid, cmd,
                                  body.get("x"), body.get("y"), body.get("alt"))

    def submit_enroll(self, tid: int, n: int) -> str:
        run_id = f"mock-e{int(time.time() * 1000) % 100000}"

        def later() -> None:
            time.sleep(1.2)
            self.hub.publish("enroll.done", {
                "terminal_id": tid, "n_pairs": n, "added": n, "stable_bits": 61,
                "stability_pct": 95.3,
                "pool": {"remaining": 400, "pool_size": 500, "pct": 80}})
        threading.Thread(target=later, daemon=True).start()
        return run_id

    def c2reset(self, tid: int) -> bool:
        self.hub.publish("server.log", {"level": "info",
                                        "msg": f"[MOCK] c2reset tid={tid}"})
        return True

    def setkey(self, tid: int, key_hex: str | None) -> bool:
        self.hub.publish("server.log", {"level": "info",
                                        "msg": f"[MOCK] setkey tid={tid}"})
        return True

    def demo_reset(self, tid: int) -> bool:
        self.hub.publish("server.log", {"level": "info",
                                        "msg": f"[MOCK] demo reset tid={tid}"})
        return True

    def golden_frames(self) -> list[dict[str, str]]:
        return GOLDEN_FRAMES_FALLBACK

    def viz_hd(self, fresh: bool) -> dict:
        # source 与真跑模式同名同形(三态:SAMPLE/LIVE/MOCK),前端一个徽章就能覆盖,
        # 不必为「这数是不是真的」单独写一条分支 —— §4.4 要求非真数据必须显式标注,
        # 标注写进字段比写进散文更不容易在改版时丢失。
        rng = _secrets.SystemRandom()
        return {"intra": [max(0, min(48, int(rng.gauss(4, 2.5)))) for _ in range(300)],
                "inter": [max(0, min(48, int(rng.gauss(32, 5)))) for _ in range(300)],
                "note": "MOCK sample data (not measured)",
                "source": "MOCK"}

    def viz_templates(self) -> dict:
        rng = _secrets.SystemRandom()
        out: dict[str, Any] = {}
        for tid in ("7", "9", "88"):
            responses = {rng.randbytes(8).hex(): rng.randbytes(8).hex() for _ in range(12)}
            out[tid] = {"responses": responses,
                        "stability_mask": "1" * 58 + "0" * 6}
        return {"source": "MOCK", "terminals": out}

    def viz_measurements(self, tid: int | None) -> dict:
        return {"terminal_id": tid, "captured": False, "series": [],
                "source": "MOCK",
                "note": "MOCK mode carries no measurements"}

    # B1/B2(mock 纪律):--mock 不读仓库 ML 数据、不跑模型推演 —— 数据自述
    # 一律 MOCK,前端据 source 维持占位,不冒充实验产物。
    def viz_ml(self) -> dict:
        return {"source": "MOCK", "a": None, "b": None,
                "note": "--mock 不读取仓库 ML 实验数据(真实产物见 data/ml_attack)"}

    def viz_reliability(self, query: str = "") -> dict:
        return {"source": "MOCK", "points": [],
                "note": "--mock 不执行模型推演;真实曲线由 ROPairingPUF.measure 现算"}


# ============================================================
# §8 HTTP 层 —— 路由(§8.2 全表)+ SSE(§8.3/§8.4)+ 静态 dist
# ============================================================
class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False   # Windows 下 SO_REUSEADDR 会抢绑在用端口,关掉

    def __init__(self, addr, app, web_dist: Path, quiet: bool,
                 docs_dir: Path | None = None) -> None:
        self.app = app
        self.web_dist = web_dist
        self.quiet = quiet
        # 按钮审计 P1-1:/docs/ 映射(缺省 <repo-root>/docs;不存在则 None → 404)
        self.docs_dir = docs_dir
        super().__init__(addr, BridgeHandler)


class BridgeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"     # §8.4 硬要求
    server: BridgeServer

    def log_message(self, fmt, *args):
        if not self.server.quiet:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # ---- 基础 ----
    def _json(self, obj, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))     # §8.4
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    # ---- 路由 ----
    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        app = self.server.app
        if path == "/api/status":
            return self._json(app.status())
        if path == "/api/golden-frames":
            return self._json({"frames": app.golden_frames()})
        if path == "/api/events":
            return self._handle_sse()
        if path == "/api/access/queue":     # finals-demo-N6: 队列快照(刷新恢复)
            return self._json(app.access_queue())
        if path == "/api/viz/hd":
            return self._json(app.viz_hd("fresh=1" in self.path))
        if path == "/api/viz/templates":
            return self._json(app.viz_templates())
        if path == "/api/viz/measurements":
            tid = None
            if "terminal_id=" in self.path:
                try:
                    tid = int(self.path.split("terminal_id=")[1].split("&")[0])
                except ValueError:
                    pass
            return self._json(app.viz_measurements(tid))
        if path == "/api/viz/ml":
            return self._json(app.viz_ml())
        if path == "/api/viz/reliability":
            return self._json(app.viz_reliability(self.path))
        if path.startswith("/docs/"):
            return self._serve_docs(path)
        return self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        body = self._read_body()
        app = self.server.app
        try:
            if path == "/api/auth":
                mode = str(body.get("mode", "normal"))
                if mode not in AUTH_MODES:
                    return self._json({"error": f"bad mode: {mode}"}, 400)
                return self._json({"run_id": app.submit_auth(int(body["terminal_id"]), mode)})
            if path == "/api/enroll":
                return self._json({"run_id": app.submit_enroll(
                    int(body["terminal_id"]), int(body.get("n", 100)))})
            if path == "/api/poll":
                return self._json({"run_id": app.submit_poll(int(body["terminal_id"]))})
            if path == "/api/enroll_real":        # N5(finals-demo)
                from enroll_real import submit_enroll_real as _ser
                return self._json({"run_id": _ser(app,
                    int(body["terminal_id"]), int(body.get("n", 100)),
                    int(body.get("measurements", 3)))})
            if path == "/api/c2reset":
                return self._json({"ok": app.c2reset(int(body["terminal_id"]))})
            if path == "/api/setkey":
                return self._json({"ok": app.setkey(
                    int(body["terminal_id"]), body.get("key_hex"))})
            if path == "/api/demo/reset":        # 附加端点(S5 重演)
                return self._json({"ok": app.demo_reset(int(body["terminal_id"]))})
            if path == "/api/drone/cmd":          # finals-demo-drone:飞行指令
                r = app.drone_cmd(int(body["terminal_id"]),
                                  str(body.get("cmd", "")), body)
                return self._json(r, 200 if r.get("ok") else 409)
            if path == "/api/access/select":       # finals-demo-N6: 人工选择唤醒
                code, body_out = app.access_select(int(body["terminal_id"]))
                return self._json(body_out, code)
            if path == "/api/access/dismiss":      # finals-demo-N6: 手动撤下
                code, body_out = app.access_dismiss(int(body["terminal_id"]))
                return self._json(body_out, code)
            return self._json({"error": "not found"}, 404)
        except (KeyError, ValueError, TypeError) as exc:
            return self._json({"error": f"bad request: {exc}"}, 400)

    # ---- SSE ----
    def _handle_sse(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "close")
        self.end_headers()
        cid, q = self.server.app.hub.subscribe()
        try:
            self.wfile.write(b"retry: 3000\n\n")
            # 首帧即发链路状态(徽章免等 5s 轮询)。seq 用当前值而非 0,否则
            # 前端 seq-断档检测会把 0→N 误判成丢事件,多触发一次全量重同步。
            self._sse_send({"seq": self.server.app.hub.current_seq(), "ts": now_iso(),
                            "type": "link.status",
                            "payload": self.server.app.link_status()})
            while True:
                try:
                    env = q.get(timeout=SSE_PING_S)
                except Empty:
                    self.wfile.write(b": ping\n\n")      # §8.4 心跳
                    self.wfile.flush()
                    continue
                if env is None:                          # poison
                    return
                self._sse_send(env)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            self.server.app.hub.unsubscribe(cid)

    def _sse_send(self, env: dict) -> None:
        self.wfile.write(
            f"id: {env.get('seq', 0)}\nevent: {env.get('type', '')}\n"
            f"data: {json.dumps(env, ensure_ascii=False)}\n\n".encode("utf-8"))
        self.wfile.flush()                               # 每事件 flush

    # ---- /docs/ 映射(按钮审计 P1-1:index 看板互链在桥接交付形态下可达) ----
    def _serve_docs(self, path: str) -> None:
        docs = self.server.docs_dir
        if docs is None:
            return self._json({"error": f"docs not mapped: {path}"}, 404)
        rel = path[len("/docs/"):].lstrip("/")
        target = (docs / rel).resolve()
        # is_relative_to 而非字符串前缀:排除同前缀兄弟目录(round-2 备注①)
        if target.is_file() and target.is_relative_to(docs.resolve()):
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type",
                             mimetypes.guess_type(str(target))[0]
                             or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return self._json({"error": f"not found: {path}"}, 404)

    # ---- 静态(dist/;路径净化;缺 dist 给指引页) ----
    def _serve_static(self, path: str) -> None:
        dist = self.server.web_dist.resolve()
        rel = (path.lstrip("/") or "index.html")
        if rel.endswith("/"):
            rel += "index.html"
        target = (dist / rel).resolve()
        # is_relative_to 而非字符串前缀:排除同前缀兄弟目录(与 _serve_docs 同款)
        if target.is_file() and target.is_relative_to(dist):
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type",
                             mimetypes.guess_type(str(target))[0]
                             or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if rel in ("index.html", "console.html", "viz.html"):
            return self._missing_dist()
        return self._json({"error": f"not found: {path}"}, 404)

    def _missing_dist(self) -> None:
        body = ("<!doctype html><meta charset='utf-8'>"
                "<body style='background:#0a0e1a;color:#dfe7f3;"
                "font-family:Segoe UI,system-ui;padding:40px'>"
                "<h2>web/dist 未构建</h2>"
                "<p>在 <code>web/</code> 下执行 <code>npm install &amp;&amp; npm run build</code> "
                "后刷新;或开发期用 <code>npm run dev</code>(proxy 已指向本桥接 8642)。</p>"
                "</body>").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ============================================================
# §9 CLI / 端口自愈 / 冒烟自检
# ============================================================
def parse_demo_terminal(spec: str) -> DemoTerminal:
    if ":" in spec:
        tid_s, size_s = spec.split(":", 1)
        return DemoTerminal(int(tid_s, 0), int(size_s))
    return DemoTerminal(int(spec, 0), 500)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="web_bridge", description="PUF 无人机认证 · 前端桥接(标准库,离线)")
    p.add_argument("--repo-root", default=None,
                   help="组员仓库根(默认:本文件上两级;须含 src/python/server)")
    p.add_argument("--data-dir", default=None,
                   help="运行态数据目录(默认 <repo-root>/data;开发态指到本地沙箱)")
    p.add_argument("--web-dist", default=None, help="静态产物目录(默认 web/dist)")
    p.add_argument("--docs-dir", default=None,
                   help="组员仓库 docs/ 映射到 /docs/(默认 <repo-root>/docs;不存在则 /docs 返回 404)")
    p.add_argument("--port", "--port-num", dest="port_num", type=int, default=8642,
                   help="HTTP 端口(默认 8642;仅绑 --bind)")
    p.add_argument("--bind", default="127.0.0.1", help="监听地址(默认仅回环)")
    p.add_argument("--strict-port", action="store_true", help="端口被占即失败(默认自愈顺延)")
    p.add_argument("--serial-port", default=None,
                   help="real serial port (e.g. COM11) for real-hardware mode")
    p.add_argument("--serial-baud", type=int, default=115200)
    p.add_argument("--loopback", action="store_true",
                   help="回环模式(当前唯一模式;与报告 §8.1 启动命令保持兼容)")
    p.add_argument("--open", action="store_true", help="启动后打开浏览器")
    p.add_argument("--pool-size", type=int, default=500, help="常规终端 CRP 池容量")
    p.add_argument("--measurements", type=int, default=3, help="注册时每挑战重复测量次数")
    p.add_argument("--demo-terminal", dest="demo_terminals", action="append",
                   type=parse_demo_terminal, metavar="TID[:SIZE]",
                   default=[DemoTerminal(7, 500), DemoTerminal(9, 500), DemoTerminal(88, 20)],
                   help="演示终端 tid[:池容量],可重复(默认 7、9、88:20; N11:99 已让给伪基站攻击)")
    p.add_argument("--mock", action="store_true",
                   help="MOCK 回放模式:零 server 依赖、零数据写入")
    p.add_argument("--once", choices=["s1", "s2", "s3", "s4", "s5", "s6", "s7", "golden"],
                   help="冒烟自检:同步跑一个场景并打印事件流后退出")
    p.add_argument("--once-tid", type=int, default=None,
                   help="--once 使用的终端 id(缺省:S5 取最小池演示终端,其余取第一个)")
    p.add_argument("--reset-demo", type=int, default=None, metavar="TID",
                   help="重置小池演示终端(S5 重演)后退出")
    p.add_argument("--quiet", action="store_true", help="抑制访问日志")
    p.add_argument("--mavlink-udp", default=None, metavar="[HOST:]PORT",
                   help="finals-demo-drone:标准 MAVLink v2 UDP 转发(如 14550;"
                        "QGC 建 UDP 链接监听同端口即可直连演示无人机;"
                        "不开启则零开销)")
    p.add_argument("--serial-multi", dest="serial_port_multi", default=None,
                   metavar="COM6,COM11",
                   help="finals-demo-N6: 多串口监听(逗号分隔);与 --serial-port "
                        "互斥使用,多口时接入闸门强制开启(并发串行化保护)")
    p.add_argument("--access-gate", action="store_true",
                   help="finals-demo-N6: 接入闸门——SW7 主动认证入队,人工选择后 "
                        "AUTH_POLL 唤醒(多串口模式强制开启)")
    p.add_argument("--access-label", default=None, metavar="1=板A,2=板B",
                   help="finals-demo-N6: 接入队列终端标签(默认 终端#tid)")
    p.add_argument("--tid-port", default=None, metavar="1=COM6,2=COM11",
                   help="finals-demo-N6: tid→串口静态映射;/api/poll 与闸门唤醒按 "
                        "tid 路由(多口模式推荐,防 poll 打错板)")
    return p


def probe_alive(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def bind_with_selfheal(app, args) -> tuple[BridgeServer, int]:
    web_dist = Path(args.web_dist) if args.web_dist else \
        Path(__file__).resolve().parents[1] / "dist"
    # 按钮审计 P1-1:/docs/ 映射解析(--docs-dir 优先)。缺省推导不做仓库校验
    # (mock/独立部署也要能起):--repo-root 或脚本上溯两级下的 docs/,存在即映射。
    if getattr(args, "docs_dir", None):
        docs_dir: Path | None = Path(args.docs_dir).resolve()
    else:
        root = Path(args.repo_root) if getattr(args, "repo_root", None) else \
            Path(__file__).resolve().parents[2]
        cand = root / "docs"
        docs_dir = cand if cand.is_dir() else None
    for attempt in range(6):
        port = args.port_num + attempt
        try:
            return BridgeServer((args.bind, port), app, web_dist, args.quiet, docs_dir), port
        except OSError:
            if args.strict_port:
                raise SystemExit(f"[ERROR] port {port} busy (--strict-port)") from None
            if probe_alive(port):
                url = f"http://127.0.0.1:{port}/console.html"
                print(f"[INFO] a bridge is already running on :{port} -> {url}")
                if args.open:
                    webbrowser.open(url)
                raise SystemExit(0)
            if attempt == 5:
                raise SystemExit(f"[ERROR] ports {args.port_num}..{port} all busy") from None
            print(f"[WARN] port {port} busy (not a bridge); trying {port + 1}")
    raise SystemExit("[ERROR] unreachable")


def make_app(args):
    """按 --mock 分派;RealApp 路径完成 sys.path 引导与数据目录解析。"""
    if args.mock:
        return MockApp(args)
    repo_root = resolve_repo_root(args.repo_root)
    if args.repo_root is None:
        print(f"[INFO] repo root resolved from script location: {repo_root}")
    args.repo_root = str(repo_root)
    args.data_dir = str(Path(args.data_dir) if args.data_dir else repo_root / "data")
    return RealApp(args, load_server_modules(repo_root))


def run_once(args) -> int:
    """冒烟自检:不起 HTTP,直接驱动编排器并回放事件流(退出码表达成败)。"""
    app = make_app(args)
    seen: list[tuple[str, dict]] = []
    orig = app.hub.publish

    def hooked(etype: str, payload: dict) -> int:
        seq = orig(etype, payload)
        seen.append((etype, payload))
        print(json.dumps({"seq": seq, "type": etype, "payload": payload},
                         ensure_ascii=False))
        return seq

    app.hub.publish = hooked            # type: ignore[method-assign]
    app.orch.start()
    app.orch.submit_sync(Job(kind="bootstrap"), timeout=600)

    scenario = args.once
    if args.once_tid is not None:
        tid = args.once_tid
    elif scenario == "s5":                      # S5 演示小池枯竭
        tid = min(args.demo_terminals, key=lambda d: d.pool_size).tid
    else:
        tid = args.demo_terminals[0].tid

    def verdict_for(run_id: str) -> dict | None:
        """只认本场景那次运行产生的判定,按 run_id 取。

        不能取 seen 里「第一个 verdict」:引导期 tid 7 的预热认证是异步的,
        它的 verdict 有可能在下面的 seen.clear() **之后**才落到列表里。那样
        --once 会把上一轮认证的结果名印成本场景的结果名 —— 读数看着像对的
        (s1/s2 恰好都是真结果),实则张冠李戴,而自检工具一旦开始骗人,
        整套 §13 走查就失去意义。故按 run_id 认领,认不到再退到最后一个。"""
        hit = next((p for t, p in seen
                    if t == "verdict" and p.get("run_id") == run_id), None)
        if hit is None:
            tail = [p for t, p in seen if t == "verdict"]
            hit = tail[-1] if tail else None
        return hit

    ok = True
    try:
        if scenario == "golden":
            # §4.1:纯净终端 + W3 密钥 → 首次认证 C2=a1..a8 → R2 必为黄金值
            app.orch.submit_sync(Job(kind="enroll", tid=GOLDEN_TID, n=4,
                                     fresh=True, run_id="golden-setup"), timeout=120)
            app.setkey(GOLDEN_TID, None)
            app.c2reset(GOLDEN_TID)
            seen.clear()
            job = app.orch.submit_sync(Job(kind="auth", tid=GOLDEN_TID, mode="normal",
                                           run_id="golden"), timeout=120)
            verdict = verdict_for("golden")
            ok = (job.error is None and verdict is not None
                  and verdict["result"] == 0 and verdict.get("r2") == GOLDEN_R2_HEX)
            print(f"[ONCE golden] result={verdict and verdict.get('result')} "
                  f"r2={verdict and verdict.get('r2')} expected={GOLDEN_R2_HEX} "
                  f"-> {'OK' if ok else 'FAIL'}")
        elif scenario == "s5":
            app.demo_reset(tid)
            seen.clear()
            results = []
            for _ in range(6):
                job = app.orch.submit_sync(Job(kind="auth", tid=tid, mode="normal",
                                               run_id=f"s5-{len(results)}"), timeout=120)
                if job.error:
                    ok = False
                    break
                v = verdict_for(f"s5-{len(results)}")
                assert v is not None
                results.append(v["result"])
                print(f"[ONCE s5] auth#{len(results)} result={v['result']} "
                      f"({v['result_name']}) pool={v['pool']}")
            ok = ok and results[:1] == [0] and 3 in results
            print(f"[ONCE s5] sequence={results} -> {'OK' if ok else 'FAIL'}")
        elif scenario == "s6":
            seen.clear()
            job = app.orch.submit_sync(Job(kind="enroll", tid=tid, n=12,
                                           run_id="s6"), timeout=120)
            done = next((p for t, p in seen if t == "enroll.done"), None)
            ok = job.error is None and done is not None
            print(f"[ONCE s6] enroll.done={done} -> {'OK' if ok else 'FAIL'}")
        else:
            mode = {"s1": "normal", "s2": "spoof", "s3": "replay",
                    "s4": "gray", "s7": "evilbase"}[scenario]
            seen.clear()
            job = app.orch.submit_sync(Job(kind="auth", tid=tid, mode=mode,
                                           run_id=f"once-{scenario}"), timeout=180)
            verdict = verdict_for(f"once-{scenario}")
            # 断言到**具体结果码**,不是「有 verdict 就算过」—— §13 给每个场景
            # 规定的结果各不相同(见 EXPECT),只查存在性的话,把 mode 接错线
            # 也能一路 OK,自检就白做了。
            EXPECT = {"s1": 0, "s2": 1, "s3": 4, "s4": 0, "s7": 0}
            ok = (job.error is None and verdict is not None
                  and verdict.get("result") == EXPECT[scenario])
            if scenario == "s4":
                ok = ok and any(t == "gray.extra" for t, _ in seen)
            if scenario == "s7":
                conf = next((p for t, p in seen if t == "confirm.done"), None)
                ok = ok and conf is not None and conf["verified_r2"] is False
            print(f"[ONCE {scenario}] mode={mode} verdict={verdict and verdict.get('result_name')} "
                  f"-> {'OK' if ok else 'FAIL'}"
                  + ("" if ok else f" ({job.error})"))
    finally:
        app.shutdown()
    return 0 if ok else 1


def parse_int_kv(spec: str | None) -> dict:
    """finals-demo-N6: "1=板A,2=COM6" → {1:"板A",2:"COM6"}。坏段跳过(容错)。"""
    out: dict = {}
    if not spec:
        return out
    for part in spec.split(","):
        part = part.strip()
        if "=" not in part:
            continue
        k, _, v = part.partition("=")
        try:
            out[int(k.strip())] = v.strip()
        except ValueError:
            continue
    return out


class AccessGate:
    """finals-demo-N6: SW7 主动认证的人工选择队列(纯逻辑,不碰串口)。

    设计锚点(方案v2 auto-review R2 PASS):
    - decide() 在 proto.on_access_request 之前调用——入队不污染 C2 重放窗
      (src/python/server/main.py:169-170,F12)。
    - 唤醒 = 2.2s 边界对齐后发 AUTH_POLL:板端 2s 等待窗内 POLL 被无视
      (terminal_fsm.v:392/479-492),超时 S_BLOCKED 立即回 S_IDLE(:930-932)。
    - 同 tid 出现在不同 port = SW12 拨码疑似重复,拒绝第二条入队(显式哨兵)。
    """

    def __init__(self, enabled: bool, labels: dict | None = None):
        self.enabled = enabled
        self.labels = labels or {}
        self._lock = threading.Lock()
        self.entries: dict[int, dict] = {}
        self.selected_tid: int | None = None

    def label(self, tid: int) -> str:
        return self.labels.get(int(tid), f"终端#{int(tid)}")

    def decide(self, tid: int, enroll_active: bool = False,
               auth_busy: bool = False) -> str:
        """监听线程 0x0090 分支调用:'run'=照旧五帧 | 'park'=入队等待人工选择。"""
        if not self.enabled:
            return "run"
        with self._lock:
            if enroll_active or auth_busy:
                return "park"
            if tid == self.selected_tid:
                return "run"
            return "park"

    def park(self, tid: int, port: str, now: float) -> str:
        """入队/刷新。返回 'new' | 'repeat' | 'conflict:<已有port>'。"""
        with self._lock:
            e = self.entries.get(tid)
            if e is not None:
                if e["port"] != port:
                    return f"conflict:{e['port']}"
                e["repeats"] += 1
                e["last_request_ts"] = now
                return "repeat"
            self.entries[tid] = {
                "port": port, "label": self.label(tid),
                "first_seen_ts": now, "last_request_ts": now, "repeats": 0}
            return "new"

    def snapshot(self, tid: int) -> dict | None:
        with self._lock:
            e = self.entries.get(int(tid))
            return dict(e) if e else None

    def queue_snapshot(self) -> list[dict]:
        with self._lock:
            out = []
            for tid, v in sorted(self.entries.items()):
                d = dict(v)
                d["terminal_id"] = tid       # REST 消费者需要键内含 tid
                out.append(d)
            return out

    def can_select(self, tid: int) -> str | None:
        """None=可选择;否则为拒绝原因('not queued' 走 404,其余 409)。"""
        with self._lock:
            if tid not in self.entries:
                return "not queued"
            if self.selected_tid is not None and self.selected_tid != tid:
                return "another verification in progress -- finish or dismiss it first"
            return None

    def can_dismiss(self, tid: int) -> str | None:
        with self._lock:
            if tid == self.selected_tid:
                return "verification in progress -- cannot dismiss"
            if tid not in self.entries:
                return "not queued"
            return None

    def set_selected(self, tid: int) -> None:
        with self._lock:
            self.selected_tid = int(tid)

    def is_selected(self, tid: int) -> bool:
        """锁内读选中态(F3 防护用,免裸读属性)。"""
        with self._lock:
            return self.selected_tid == int(tid)

    def clear_selected(self, tid: int) -> None:
        with self._lock:
            if self.selected_tid == int(tid):
                self.selected_tid = None

    def dismiss(self, tid: int) -> bool:
        with self._lock:
            return self.entries.pop(int(tid), None) is not None

    def finish(self, tid: int, final_state: str) -> bool:
        """_auth 尾部调用:清选中+出队。返回是否确有出队(有则发 finished 事件)。"""
        with self._lock:
            if self.selected_tid == int(tid):
                self.selected_tid = None
            return self.entries.pop(int(tid), None) is not None


class RealSerialListener:
    """D2 real-hardware mode: listens on serial for board ACCESS_REQUEST, runs full auth."""
    def __init__(self, app, port, baud):
        import serial as _ps
        self.ser = _ps.Serial(port, baud, timeout=0.05)
        self.app = app; self.hub = app.hub; self.proto = app.protocol
        self.P = type(app.protocol)
        self.running = False
    def start(self):
        self.running = True
        # Inject real templates + pools so the protocol can authenticate real boards
        import json as _json
        from pathlib import Path as _P
        root = _P(__file__).resolve().parents[2]
        tpl_f = root / "data" / "templates" / "templates.json"
        real_tids = getattr(self.app, "real_serial_tids", set())
        _demo_ids = {str(d.tid) for d in getattr(self.app.args, "demo_terminals", [])} | {"55"}
        if tpl_f.exists():
            real = _json.loads(tpl_f.read_text(encoding="utf-8"))
            for tid, pairs in real.items():
                if tid not in _demo_ids:  # demo tids(含历史 55)不视为真板
                    self.proto.templates.templates[tid] = pairs
                    real_tids.add(int(tid))
                    self._log(f"Injected real template tid={tid} ({len(pairs)} CRPs)")
        else:
            self._log("data/templates/templates.json 缺失:真板模板未注入,real 守卫将为空集", "error")
        # 无条件落属性:守卫生效性不再与文件存在性隐式耦合
        self.app.real_serial_tids = real_tids
        for tid in (1, 2):
            pool_f = root / "data" / "crp_datasets" / "pools" / f"pool_{tid}.json"
            if pool_f.exists():
                pool_data = _json.loads(pool_f.read_text(encoding="utf-8"))
                try:
                    _p = self.proto.pools.get(tid)
                    _p._available = set(pool_data.get("available", []))
                    _p._used = set(pool_data.get("used", []))
                    self._log(f"Pool tid={tid} loaded: {_p.remaining}/{_p.pool_size} available")
                except Exception as _e:
                    self._log(f"Pool tid={tid} inject failed: {_e}", "error")
        threading.Thread(target=self._loop, daemon=True).start()
        self.hub.publish("server.log", {"level":"info",
            "msg":f"REAL SERIAL: {self.ser.port}@{self.ser.baudrate} — press SW7 on board"})
    def _loop(self):
        buf = b""
        while self.running:
            try: n = self.ser.in_waiting
            except OSError as _e:
                self._log(f"REAL serial port lost, listener exiting: {_e}", "error")
                break
            if not n: time.sleep(0.005); continue
            buf += self.ser.read(n)
            # 重同步:流中混入噪声时丢到下一个 0xFD 为止,否则缓冲永久卡死
            if len(buf) >= 12 and buf[0] != 0xFD:
                _nx = buf.find(b'\xfd', 1)
                _dropped = len(buf) if _nx < 0 else _nx
                self._log(f"REAL resync: dropped {_dropped} non-frame bytes", "error")
                # N2(finals-demo) 信道 IDS·噪声半边:1s 滑窗内 >=3 次 resync →
                # 限速发布 channel.noise(纯噪声 DoS 时前端/审计有可订阅信号)。
                # 发布后清空窗口计数,同窗不重复发。
                _now = time.time()
                _nev = getattr(self, "_noise_events", None)
                if _nev is None:
                    _nev = []
                    self._noise_events = _nev
                _nev.append(_now)
                _nev[:] = [t for t in _nev if _now - t <= 1.0]
                if len(_nev) >= 3:
                    _nev.clear()  # 同窗只发一次,窗口重新累计
                    self.hub.publish("channel.noise", {
                        "events": 3, "window_s": 1.0,
                        "dropped_bytes": _dropped,
                        "note": ">=3 resync events within 1s on RX"})
                    self._log("CHANNEL NOISE: 3+ resync/s on RX -- "
                              "suspected noise flood", "error")
                buf = b"" if _nx < 0 else buf[_nx:]
            while len(buf) >= 12 and buf[0] == 0xFD:
                total = 10 + buf[1] + 2
                if len(buf) < total: break
                frame, buf = buf[:total], buf[total:]
                try: mid, fl = self.proto.parse(frame)
                except Exception as _e:
                    self._log(f"REAL frame parse failed ({len(frame)}B): {type(_e).__name__}", "error")
                    continue
                if mid == 0x0090:  # ACCESS_REQUEST
                    try:
                        # finals-demo-N6: 接入闸门决策——必须在 _auth(内部调
                        # proto.on_access_request)之前:F12 重放窗不因入队被动。
                        # park = 入队等人工选择(access.requested),不跑认证。
                        _tid = int(fl.get("terminal_id", 0))
                        # N11(finals-demo): 未注册终端的接入请求 ≠ 无人机——
                        # 直接按信道告警(channel.intrusion kind=access,前端大警报),
                        # 不入待接入队列、不回帧(不喂攻击者)。
                        try:
                            _registered = self.proto.templates.has_terminal(_tid)
                        except Exception:
                            _registered = True   # 查询失败不拦正常流程
                        if not _registered:
                            try:
                                self.hub.publish("channel.intrusion", {
                                    "msg_id": mid, "name": self.P.msg_name(mid),
                                    "hex": frame.hex(), "len": len(frame),
                                    "note": "unregistered terminal access attempt "
                                            "-- rogue base suspected, NOT queued",
                                    "kind": "access", "terminal_id": _tid})
                                self._log(f"CHANNEL IDS: unregistered tid={_tid} "
                                          f"ACCESS_REQUEST -- rogue-base alarm, "
                                          f"NOT queued", "error")
                            except Exception as _ie:  # noqa: BLE001
                                self._log(f"REAL rogue-alarm error: {type(_ie).__name__}: {_ie}", "error")
                        else:
                            _gate = getattr(self.app, "access_gate", None)
                            if _gate is not None and _gate.enabled:
                                _act = _gate.decide(
                                    _tid,
                                    enroll_active=bool(getattr(self.app, "enroll_session_active", False)),
                                    auth_busy=bool(getattr(self.app, "auth_in_progress", False)))
                                if _act == "park":
                                    self._park(_tid)
                            else:
                                _act = "run"
                            if _act == "run":
                                # R2 P2:全程持串口锁(含读写)——与 _do_poll/N5 enroll 的
                                # 写口互斥;忙标志给 poll 快速忙拒,不必等锁
                                self.app.auth_in_progress = True
                                with self.app.serial_bus_lock:
                                    self._auth(int(fl.get("terminal_id",0)), fl, frame)
                    except Exception as e:  # noqa: BLE001 —— 监听线程必须永死不了
                        self._log(f"REAL auth handler error (thread kept alive): {type(e).__name__}: {e}", "error")
                    finally:
                        self.app.auth_in_progress = False
                elif (mid == 0x0092
                      and getattr(self.app, "enroll_session_active", False)):
                    # N5: enrollment RESPONSE_R1 -> queue
                    try:
                        self.app.enroll_response_q.put_nowait(fl)
                    except Exception:
                        pass
                elif (mid in (0x0091, 0x0093, 0x0095)
                      and not getattr(self.app, "enroll_session_active", False)):
                    # N2(finals-demo) 信道 IDS:0x0091/0x0093/0x0095 是站端→终端方向的
                    # 帧,正常链路上永远不会出现在本站 RX 口——共享信道上有第二个
                    # 发射者(伪基站注入/恶意回环)时才会被听到。HC-12 同信道是共享
                    # 广播介质,本站物理上能听见攻击帧,这是 Tier0 检测的物理基础。
                    # 注册窗口(enroll_session_active,N5)内站端自己连发 0x0091,
                    # 静默防自触发。
                    try:
                        self.hub.publish("channel.intrusion", {
                            "msg_id": mid,
                            "name": self.P.msg_name(mid),
                            "hex": frame.hex(),
                            "len": len(frame),
                            "note": "station-only frame heard on RX path"})
                        self._log(
                            f"CHANNEL IDS: station-only frame 0x{mid:04x} "
                            f"{self.P.msg_name(mid)} ({len(frame)}B) on RX -- "
                            f"suspected injection",
                            "error")
                    except Exception as e:  # noqa: BLE001 —— 监听线程必须永死不了(与 _auth 分支同款保护)
                        self._log(f"REAL ids handler error (thread kept alive): "
                                  f"{type(e).__name__}: {e}", "error")
    def _auth(self, tid, ar_f, ar_raw):
        rid = f"real-{int(time.time()*1000)}"
        # N4(finals-demo): poll 超时判定的观测点——每次收到 ACCESS_REQUEST 都刷新
        self.app.last_access_request_ts = time.time()
        _by = getattr(self.app, "last_access_request_by_tid", None)
        if _by is not None:
            _by[tid] = time.time()               # R3: per-tid 信号(_poll_wake_once 用)
        c2 = ar_f.get("c2", b"\0"*8)
        self._ef(rid,tid,0x0090,ar_raw,False)
        self._log(f"REAL auth tid={tid} run={rid}")
        # N13 不变式:可抽种子 ⊆ 有模板对。桥启动会把仓库池播种进沙箱,未录入种子
        # 一旦被抽中即 KeyError('no template for seed')。每次认证前幂等收敛。
        try:
            _tpl = self.proto.templates.templates.get(str(tid)) or {}
            if _tpl:
                self.proto.pools.get(tid).limit_to(_tpl.keys())
        except Exception as _e:  # noqa: BLE001 —— 不变式失败不阻断认证,仅告警
            self._log(f"REAL pool-invariant warn: {type(_e).__name__}: {_e}", "warn")

        try: chal = self.proto.on_access_request(tid, c2=c2)
        except Exception as e:
            self._log(f"REAL error: {e}","error")
            self._early_reject(tid, rid, {"result": 2, "hd": 255})
            return
        mid,chf = self.proto.parse(chal)
        if mid == 0x0093:  # RESULT=error(REPLAY/ERROR/POOL_EMPTY 等)
            # 帧必须真的写给板子,否则板侧只能等超时,而网页却展示了一条"已发送"——
            # 那是伪造的上线证据。写失败也要落日志。
            try:
                time.sleep(0.2)
                self.ser.write(chal); self.ser.flush()
                self._ef(rid,tid,mid,chal,True)  # 先写成功再发事件:时间线不出现"未发出的帧"
                self._log(f"REAL early-RESULT mid=0x{mid:04x} written to board (run={rid})")
            except Exception as e:
                self._log(f"REAL early-RESULT write failed: {e}", "error")
            self._early_reject(tid, rid, chf)
            return
        # CHALLENGE → board
        # 节奏修复(1103):真串口路径的帧间 sleep 不得超过板侧等待窗——R1→RESULT 必须
        # < S_WAIT_RESULT=2.000s。曾为看动画把三处 sleep 提到 1.0s,结果 R1→RESULT≈2.04s
        # 恰好超窗 40ms,板子按超时处理(L+R 双亮、无 CONFIRM)。回退 0.2s(0.2+0.2+计算
        # ≈0.42s,余量 1.6s);网页动画是事件驱动的,不依赖这些 sleep。
        time.sleep(0.2)
        self._ef(rid,tid,0x0091,chal,True)
        self.ser.write(chal); self.ser.flush()
        # ← RESPONSE_R1
        # R4 fix: 限读 rl 字节——竞速攻击下缓冲含 RESPONSE+攻击帧+CONFIRM,
        # 旧代码读全部→parse(83B)失败;限读后多余字节留给 CONFIRM 帧同步处理
        rl = 12 + 8*len(chf["seeds"]); rep=b""; t0=time.time()
        while len(rep)<rl and time.time()-t0<3.0:
            n=min(self.ser.in_waiting, rl-len(rep))
            if n: rep+=self.ser.read(n)
            else: time.sleep(0.005)
        if len(rep)<rl:
            self._log(f"REAL timeout RESPONSE {len(rep)}/{rl}","error")
            self._early_reject(tid, rid, {"result": 2, "hd": 255})
            return
        try: _,rf = self.proto.parse(rep)
        except Exception as e:
            self._log(f"REAL RESPONSE_R1 parse failed ({len(rep)}B): {type(e).__name__}: {e}", "error")
            self._early_reject(tid, rid, {"result": 2, "hd": 255})
            return
        r1s = rf["r1s"]
        time.sleep(0.2)
        self._ef(rid,tid,0x0092,rep,False)
        # RESULT → board
        res = self.proto.on_response(tid, r1s)
        rm,rf2 = self.proto.parse(res)
        time.sleep(0.2)
        self._ef(rid,tid,rm,res,True)
        self.ser.write(res); self.ser.flush()
        rv = int(rf2.get("result",2))
        hd = self.proto.templates.hamming_distances(tid,chf["seeds"],list(r1s))
        from src.python.server.threshold import TAU_PASS, TAU_REJECT
        nr = len(hd); pool_st={"remaining":0,"pool_size":0,"pct":0}
        try:
            _ps=self.proto.pools.get(tid).status()
            pool_st={"remaining":_ps["remaining"],"pool_size":_ps["pool_size"],"pct":_ps["remaining_pct"]}
        except Exception: pass
        vp={"run_id":rid,"terminal_id":tid,"result":rv,
            "result_name":RESULT_NAMES.get(rv,str(rv)),
            "n_responses":nr,"hd":int(rf2.get("hd",255)),
            "hd_per_response":hd,"pool":pool_st,
            "thresholds":{"tau_pass":TAU_PASS,"tau_reject":TAU_REJECT,
                "scaled_pass":TAU_PASS*max(nr,1),"scaled_reject":TAU_REJECT*max(nr,1)}}
        if rv==0 and "r2" in rf2: vp["r2"]=rf2["r2"].hex()
        self.hub.publish("verdict", vp)
        # ← CONFIRM (if PASS) — R4 frame-sync fix (defect-c1 P1)
        # 竞速攻击下串口缓冲含 [攻击RESULT 22B][CONFIRM_FAIL 17B]=39B,
        # 旧裸读17B一把吞→parse失败→三重证据丢失+屏幕假PASS。
        # 改帧同步流:扫0xFD按LEN切帧,站端方向帧路由IDS,找CONFIRM或超时。
        confirm_frame = None; confirm_fields = {}
        if rv == 0:
            buf=b""; t0=time.time()
            while confirm_frame is None and time.time()-t0<2.0:
                n=self.ser.in_waiting
                if n: buf+=self.ser.read(n)
                else: time.sleep(0.005); continue
                # R4 fix: 先 resync(剥垃圾到下一个0xFD)再提帧——顺序颠倒会把
                # 垃圾后的帧卡到超时(外循环无新数据不再进帧提取)
                if len(buf)>=12 and buf[0]!=0xFD:
                    _nx=buf.find(b'\xfd',1)
                    _dropped=len(buf) if _nx<0 else _nx
                    self._log(f"REAL confirm-wait resync: dropped {_dropped}B","error")
                    buf=b"" if _nx<0 else buf[_nx:]
                # 帧同步:与 _loop 主循环同构(扫0xFD+LEN切帧)
                while len(buf)>=12 and buf[0]==0xFD:
                    total=10+buf[1]+2
                    if len(buf)<total: break  # 帧不完整,等更多字节
                    frame,buf=buf[:total],buf[total:]
                    try: fm,ffl=self.proto.parse(frame)
                    except Exception:
                        self._log(f"REAL confirm-wait: bad frame {len(frame)}B skipped","error")
                        continue  # 坏帧跳过继续扫
                    if fm==0x0094:
                        confirm_frame=frame; confirm_fields=ffl
                        break  # 找到CONFIRM,跳出
                    elif fm in (0x0091,0x0093,0x0095):
                        # 站端方向帧出现在RX = 伪基站注入→路由IDS
                        # (与_loop L2129-2151同款;_auth期间_loop被锁阻塞看不到)
                        try:
                            self.hub.publish("channel.intrusion",{
                                "msg_id":fm,"name":self.P.msg_name(fm),
                                "hex":frame.hex(),"len":len(frame),
                                "note":"station-only frame heard on RX path (during auth)"})
                            self._log(f"CHANNEL IDS: station-only frame 0x{fm:04x} "
                                      f"{self.P.msg_name(fm)} ({len(frame)}B) during auth -- "
                                      f"suspected injection","error")
                            self._ef(rid,tid,fm,frame,False)
                        except Exception as _e:
                            self._log(f"REAL ids-in-auth error: {type(_e).__name__}: {_e}","error")
                    else:
                        self._log(f"REAL confirm-wait: unexpected 0x{fm:04x} ignored","error")
            # 处理CONFIRM结果
            if confirm_frame is not None:
                st=int(confirm_fields.get("status",0))
                self._ef(rid,tid,0x0094,confirm_frame,False)
                if st==0:
                    self.hub.publish("confirm.done",
                        {"run_id":rid,"terminal_id":tid,"status":0,"verified_r2":True})
                else:
                    self.hub.publish("confirm.rejected",
                        {"run_id":rid,"terminal_id":tid,"status":st,
                         "own_verdict":rv,
                         "evidence":"terminal rejected our verdict: R2 mismatch"})
                    self.hub.publish("base.spoof.suspected",
                        {"run_id":rid,"terminal_id":tid,
                         "own_verdict":"PASS","terminal_says":"FAIL",
                         "evidence":"R2 mismatch at terminal -- suspected fake-base-station injection"})
                    self._log(f"BASE SPOOF SUSPECTED: tid={tid} rejected our PASS verdict "
                              f"(CONFIRM status={st}) -- R2 mismatch at terminal, suspected injection","error")
            else:
                self._log(f"REAL confirm-wait timeout (run={rid}, rv={rv})","error")
        # R4 fix: session.update 按 CONFIRM 实际 status 发,不再无条件 rv==0→SESSION
        if rv==0 and confirm_frame is not None and int(confirm_fields.get("status",0))==0:
            _final_state="SESSION"
        else:
            _final_state="BLOCKED"
        self.hub.publish("session.update", {"terminal_id":tid,"state":_final_state})
        # finals-demo-N6: 选中验证完成 → 出队 + access.finished(闸门关闭时 no-op)
        _gate = getattr(self.app, "access_gate", None)
        if _gate is not None and _gate.enabled:
            try:
                if _gate.finish(tid, _final_state):
                    self.hub.publish("access.finished",
                                     {"terminal_id": tid, "state": _final_state})
            except Exception as _ge:  # noqa: BLE001 —— 出队失败不得杀监听线程
                self._log(f"ACCESS GATE finish error: {type(_ge).__name__}: {_ge}", "error")

    def _early_reject(self, tid, rid, rf2):
        """早期失败(池空/重放/无模板)的终态补全:verdict + session.update + 闸门出队。

        N6 现场缺陷(2026-11-16): 板A无模板时 on_access_request 直接返回/抛出,
        _auth 静默 return —— 前端收不到 verdict,拒绝动画不播,且 gate.finish
        没跑导致 selected 悬挂、界面永久"验证中"。"""
        from src.python.server.threshold import TAU_PASS, TAU_REJECT
        try:
            rv = int(rf2.get("result", 2))
        except Exception:
            rv = 2
        # 演示语义(步骤④): 未注册机器(该tid无任何模板)不是"池空"这种内部错误,
        # 而是明确的 REJECT。其余早期错误保持原码(POOL_EMPTY/REPLAY/ERROR)。
        try:
            _has_tpl = bool(self.proto.templates.templates.get(str(tid)))
        except Exception:
            _has_tpl = True
        if not _has_tpl and rv != 0:
            rv = 1
        pool_st = {"remaining": 0, "pool_size": 0, "pct": 0}
        try:
            _ps = self.proto.pools.get(tid).status()
            pool_st = {"remaining": _ps["remaining"], "pool_size": _ps["pool_size"],
                       "pct": _ps["remaining_pct"]}
        except Exception:
            pass
        self.hub.publish("verdict", {
            "run_id": rid, "terminal_id": tid, "result": rv,
            "result_name": RESULT_NAMES.get(rv, str(rv)),
            "n_responses": 0, "hd": int(rf2.get("hd", 255)),
            "hd_per_response": [], "pool": pool_st,
            "thresholds": {"tau_pass": TAU_PASS, "tau_reject": TAU_REJECT,
                           "scaled_pass": TAU_PASS, "scaled_reject": TAU_REJECT}})
        self.hub.publish("session.update", {"terminal_id": tid, "state": "BLOCKED"})
        _gate = getattr(self.app, "access_gate", None)
        if _gate is not None and _gate.enabled:
            try:
                if _gate.finish(tid, "BLOCKED"):
                    self.hub.publish("access.finished",
                                     {"terminal_id": tid, "state": "BLOCKED"})
            except Exception as _ge:  # noqa: BLE001
                self._log(f"ACCESS GATE finish error: {type(_ge).__name__}: {_ge}", "error")

    def _park(self, tid):
        """finals-demo-N6: 入队并发布 access.requested(重复按压刷新 repeats)。"""
        gate = getattr(self.app, "access_gate", None)
        if gate is None:
            return
        st = gate.park(tid, self.ser.port, time.time())
        # auto-review(R1-F1): parked 请求也必须刷新 poll 成功信号——
        # _do_poll/_poll_wake_once 只认 last_access_request_ts;闸门模式下
        # /api/poll 唤醒的板子回应会被入队,不刷时间戳 = poll 假超时。
        self.app.last_access_request_ts = time.time()
        # auto-review(R3): 同时落 per-tid 信号——唤醒判据按 tid 精确化,
        # 防跨板按压的全局戳跳变造成 select 假成功(selected 悬挂死锁)。
        _by = getattr(self.app, "last_access_request_by_tid", None)
        if _by is not None:
            _by[tid] = time.time()
        if st.startswith("conflict:"):
            # SW12 拨码疑似重复:同 tid 出现在两个串口——显式哨兵而非静默覆盖
            self._log(f"ACCESS GATE: SW12 拨码疑似重复——tid={tid} 已在 "
                      f"{st.split(':', 1)[1]} 入队,来自 {self.ser.port} 的第二条已拒绝",
                      "error")
            return
        e = gate.snapshot(tid)
        if e:
            self.hub.publish("access.requested", {
                "terminal_id": tid, "port": e["port"], "label": e["label"],
                "first_seen_ts": e["first_seen_ts"], "repeats": e["repeats"]})
            self._log(f"ACCESS GATE: parked tid={tid} ({e['label']}) on "
                      f"{e['port']} repeats={e['repeats']} -- waiting for manual select")

    def _ef(self,rid,tid,mid,frm,out):
        self.hub.publish("frame.tx" if out else "frame.rx", {
            "run_id":rid,"terminal_id":tid,"msg_id":mid,
            "name":self.P.msg_name(mid),
            "hex":frm.hex(),"len":len(frm),
            "dir":"server->term" if out else "term->server",
            "source":"real-terminal"})
    def _log(self,m,lvl="info"):
        self.hub.publish("server.log",{"level":lvl,"msg":m})


def main(argv: list[str] | None = None) -> int:
    console_utf8()
    args = build_parser().parse_args(argv)
    print(f"PUF web bridge v{VERSION} | python {sys.version.split()[0]}")

    try:
        if args.once:
            return run_once(args)
        if args.reset_demo is not None and not args.mock:
            app = make_app(args)
            app.orch.start()
            app.orch.submit_sync(Job(kind="bootstrap"), timeout=600)
            ok = app.demo_reset(args.reset_demo)
            app.shutdown()
            print(f"[RESET] demo terminal {args.reset_demo}: {'ok' if ok else 'failed'}")
            return 0 if ok else 1

        app = make_app(args)
        server, port = bind_with_selfheal(app, args)
        app.start()
        _serial_listener = None
        # finals-demo-N6: 多口监听(--serial-multi COM6,COM11);多口强制开闸门
        _ports = []
        if getattr(args, 'serial_port_multi', None):
            _ports = [p.strip() for p in str(args.serial_port_multi).split(',') if p.strip()]
        elif getattr(args, 'serial_port', None):
            _ports = [str(args.serial_port)]
        if _ports:
            if len(_ports) > 1 and not app.access_gate.enabled:
                print("[INFO] finals-demo-N6: 多串口模式强制开启接入闸门"
                      "(两板并发 SW7 的串行化保护,方案v2)")
                app.access_gate.enabled = True
            _first = None
            for _p in _ports:
                _ln = RealSerialListener(app, _p, args.serial_baud)
                app.serial_listeners[_p] = _ln
                if _first is None:
                    _first = _ln
            _serial_listener = _first
            app.serial_listener = _first  # N4: _do_poll 经此发 AUTH_POLL(单口兼容)
            for _p in _ports:
                app.serial_listeners[_p].start()
        url = f"http://{args.bind}:{port}/console.html"
        print(f"[INFO] serving {server.web_dist} -> {url}")
        print("[INFO] Ctrl+C 停止;仅回环流量,不触外网")
        if args.open:
            webbrowser.open(url)
        try:
            server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            print("\n[INFO] shutting down ...")
        finally:
            server.server_close()
            app.shutdown()
        return 0
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
