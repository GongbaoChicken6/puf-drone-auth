#!/usr/bin/env python3
"""fake_result_attack.py —— N8(finals-demo) 伪基站竞速注入演示工具。

信道模型(HC-12 半双工广播,433MHz 同频):攻击者电台与真基站同配 C001,
听得见信道上的一切,也能随时注入。演示剧本(FEATURES §2 N8):

    真站发起认证 → 板子回 RESPONSE_R1(0x0092)
      → 本工具【零延迟】注入"PASS + 伪 R2"的 RESULT(0x0093)
      → 板端 R2 失配(双向认证识破) → CONFIRM_FAIL 上报(N3) → BLOCKED 双亮
      → 真站随后到场的真 RESULT 已无主;站端 IDS 听到注入帧红警(N2),
        并收到终端 CONFIRM_FAIL → 矛盾关联告警(base.spoof.suspected)

竞速依据:真站 R1→RESULT 之间有 ~0.2s 节奏延迟 + HD 计算(web_bridge
_auth_round),零延迟注入必先到场。半双工碰撞(注入撞上板子发送尾字节,
两帧互毁被 CRC 丢弃)是已知风险——重跑一次本脚本即可(备选剧本)。

用法(真信道,需 pyserial):
    python tools/attack/fake_result_attack.py --port COM9            # 竞速模式
    python tools/attack/fake_result_attack.py --port COM9 --passive  # 只监听(讲"攻击者在听")
    python tools/attack/fake_result_attack.py --port COM9 --inject-now  # 空闲注入一帧(单演 Tier0 IDS)
    python tools/attack/fake_result_attack.py --port COM9 --rogue        # N10 伪基站接入演示(Enter 触发)
    python tools/attack/fake_result_attack.py --port COM9 --rogue-web    # N10 浏览器单按钮版(http://127.0.0.1:8643)
HC-12 同频配置用 tools/hc12 现成脚本。双串口拓扑另一半:真基站侧用
web_bridge.py --serial-port COM6 起桥(见 FEATURES §2 N8)。
仅供本作品决赛演示,信道上无真实密钥(伪 R2 按构造就是错的)。

CI-safe:核心类 FakeResultAttacker 不做任何 I/O(串口/时间都注入),
tests/test_attack_tool.py 直驱验证。运行入口 main() 才 import pyserial。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.python.server.protocol import HFIDAProtocol  # noqa: E402

STX = 0xFD
MSG_ACCESS_REQUEST = HFIDAProtocol.MSG_ACCESS_REQUEST   # 0x0090 term->server
MSG_RESPONSE_R1 = HFIDAProtocol.MSG_RESPONSE_R1         # 0x0092 term->server
MSG_RESULT = HFIDAProtocol.MSG_RESULT                   # 0x0093 server->term
RESULT_PASS = 0

DEFAULT_FAKE_R2 = bytes.fromhex("deadbeefcafe0110")      # 按构造就是错 R2


class FrameSync:
    """最小 MAVLink v2 帧同步器(字节流 → 完整帧列表)。

    与板端 frame_parser.v 同规则:非 STX 字节静默丢弃(噪声容忍);
    帧长 = 10 头 + LEN + 2 CRC。不做 CRC 校验(监听用途,坏帧也能计数)。
    """

    def __init__(self) -> None:
        self.buf = bytearray()
        self.noise = 0

    def feed(self, data: bytes) -> list[tuple[int, bytes]]:
        """返回本批完整的 (msg_id, frame_bytes) 列表。"""
        out: list[tuple[int, bytes]] = []
        self.buf.extend(data)
        while True:
            # 丢掉 STX 之前的噪声字节(find+del,O(n);content-review P3:
            # 逐字节 pop(0) 是 O(n²),256B 纯噪声块 ≈3 万次搬移)
            i = self.buf.find(STX)
            if i < 0:
                self.noise += len(self.buf)
                self.buf.clear()
                break
            if i:
                self.noise += i
                del self.buf[:i]
            if len(self.buf) < 2:
                break
            total = 10 + self.buf[1] + 2
            if len(self.buf) < total:
                break
            frame = bytes(self.buf[:total])
            del self.buf[:total]
            msg_id = frame[7] | (frame[8] << 8) | (frame[9] << 16)
            out.append((msg_id, frame))
        return out


class FakeResultAttacker:
    """状态机:armed --RESPONSE_R1--> 注入伪 RESULT --> disarmed;
    disarmed --ACCESS_REQUEST(新一轮认证)--> re-arm。"""

    def __init__(self, pack_fn=HFIDAProtocol().pack, send=None,
                 r2_fake: bytes = DEFAULT_FAKE_R2, mode: str = "race",
                 delay_s: float = 0.0, log=None, sleeper=time.sleep,
                 clock=time.monotonic):
        self._pack = pack_fn
        self._send = send or (lambda frame: None)
        self._log = log or (lambda msg: print(f"[{time.strftime('%H:%M:%S')}] {msg}",
                                              file=sys.stderr))
        self._sleep = sleeper
        self._clock = clock
        if len(r2_fake) != 8:
            raise ValueError(f"r2_fake must be 8 bytes, got {len(r2_fake)}")
        if mode not in ("race", "passive"):
            raise ValueError(f"mode must be race|passive, got {mode!r}")
        self.r2_fake = r2_fake
        self.mode = mode
        self.delay_s = delay_s
        self.armed = True
        self.injected_rounds = 0
        self.heard_frames = 0
        self.sync = FrameSync()
        self.last_inject_lag_s: float | None = None

    # ---- 入口:喂串口字节(攻击者听到的一切) ----
    def feed(self, data: bytes) -> None:
        for msg_id, frame in self.sync.feed(data):
            self._on_frame(msg_id, frame)

    def _on_frame(self, msg_id: int, frame: bytes) -> None:
        self.heard_frames += 1
        name = HFIDAProtocol.msg_name(msg_id)
        self._log(f"heard {name} ({len(frame)}B) {frame.hex()[:32]}…")
        if msg_id == MSG_ACCESS_REQUEST:
            if not self.armed:
                self._log("new auth round → re-arm")
            self.armed = True
            return
        if msg_id == MSG_RESPONSE_R1 and self.armed and self.mode == "race":
            self._inject(frame)

    # ---- 注入:伪 RESULT(PASS + 错 R2) ----
    def _inject(self, trigger: bytes) -> None:
        t0 = self._clock()
        if self.delay_s > 0:
            self._sleep(self.delay_s)
        fake = self._pack(MSG_RESULT, result=RESULT_PASS, hd=5, r2=self.r2_fake)
        self._send(fake)
        self.injected_rounds += 1
        self.armed = False
        self.last_inject_lag_s = self._clock() - t0
        self._log(f">>> INJECT fake RESULT (PASS + r2={self.r2_fake.hex()}) "
                  f"triggered by RESPONSE_R1, lag={self.last_inject_lag_s * 1000:.1f}ms")

    def inject_now(self) -> bytes:
        """空闲单帧注入(演示 Tier0 IDS:站端不该收到的方向帧)。"""
        fake = self._pack(MSG_RESULT, result=RESULT_PASS, hd=5, r2=self.r2_fake)
        self._send(fake)
        self.injected_rounds += 1
        self._log(f">>> INJECT-NOW idle fake RESULT {fake.hex()}")
        return fake


# ---- N10(finals-demo): 伪基站接入演示 ---------------------------------
# 剧本:攻击者在自己的电脑上"点击认证"→本工具发一组帧→真站前端播放
# "有别的基站在尝试连接→已拒绝"。板 A 全程不参与:0x0090 板端不解析,
# 0x0093 仅 S_WAIT_RESULT 受理(S_IDLE 无条件无视),不动板子状态机。
ROGUE_TID_DEFAULT = 77     # 未注册终端号:真站 on_access_request 查无模板→REJECT
# (勿用 99:repo templates.json 残留 tid99 测试模板,会被种进演示沙箱→秒拒剧本失效)


def build_rogue_burst(pack_fn=None, tid: int = ROGUE_TID_DEFAULT,
                      c2: bytes | None = None, banner: bool = True,
                      r2_fake: bytes = DEFAULT_FAKE_R2) -> list[tuple[str, bytes]]:
    """伪基站"点击认证"一次所发的帧组。

    ① banner 帧 0x0093 伪 RESULT —— 真站 RX 听到站端方向帧→Tier0 信道 IDS
       红横幅"疑似伪基站注入";板端 S_IDLE 不受理 0x0093。
    ② ACCESS_REQUEST(0x0090, 未注册 tid) —— 板端不解析 0x0090;真站闸门弹窗
       (多口模式)或直接验证:无模板→REJECT+BLOCKED→前端拒绝动画。
    """
    if pack_fn is None:
        pack_fn = HFIDAProtocol().pack
    if c2 is None:
        c2 = os.urandom(8)
    if len(c2) != 8:
        raise ValueError(f"c2 must be 8 bytes, got {len(c2)}")
    out: list[tuple[str, bytes]] = []
    if banner:
        out.append(("banner_fake_result_0x0093",
                    pack_fn(MSG_RESULT, result=RESULT_PASS, hd=5, r2=r2_fake)))
    out.append(("rogue_access_request_0x0090",
                pack_fn(MSG_ACCESS_REQUEST, terminal_id=tid, c2=c2)))
    return out


def _rogue_fire(send, args, r2_fake: bytes, log) -> list[tuple[str, bytes]]:
    burst = build_rogue_burst(tid=args.rogue_tid,
                              banner=not args.no_banner, r2_fake=r2_fake)
    for i, (name, frame) in enumerate(burst):
        if i:
            time.sleep(0.3)      # 帧间隔:真站分帧解析,IDS 与拒绝动画各自成立
        send(frame)
        log(f">>> ROGUE {name} ({len(frame)}B) {frame.hex()[:44]}…")
    log(">>> ROGUE burst done: 真站应先后出现 IDS 红横幅 + 拒绝动画/BLOCKED")
    return burst


def _rogue_interactive(ser, args, r2_fake, send, log) -> int:
    print(f"[ROGUE] 伪基站接入演示 tid={args.rogue_tid} @ {ser.port} — "
          f"Enter=发起一次, q=退出", file=sys.stderr)
    rounds = 0
    try:
        while True:
            try:
                line = input()
            except EOFError:
                break
            if line.strip().lower() in ("q", "quit", "exit"):
                break
            try:
                _rogue_fire(send, args, r2_fake, log)
                rounds += 1
            except Exception as exc:  # 串口异常不杀循环:提示后继续等下一轮
                log(f"ROGUE fire failed: {type(exc).__name__}: {exc} "
                    f"(-- 检查 HC-12 接线/串口后重试)")
    except KeyboardInterrupt:
        pass
    print(f"[ROGUE] stop. rounds={rounds}", file=sys.stderr)
    return 0


_ROGUE_PAGE = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>伪基站控制台</title><style>
 body{background:#160608;color:#f5c8c8;font-family:system-ui,'Segoe UI',sans-serif;
      display:flex;flex-direction:column;align-items:center;margin-top:8vh;gap:18px}
 h1{font-size:22px;letter-spacing:2px} button{font-size:20px;padding:16px 42px;
   background:#7a1220;color:#fff;border:1px solid #ff5a5a;border-radius:10px;
   cursor:pointer} button:active{transform:scale(.97)}
 #out{white-space:pre-wrap;font:12px/1.6 Consolas,monospace;color:#ffb3b3;
      max-width:720px;word-break:break-all} .tip{color:#a97;font-size:13px}
</style></head><body>
<h1>☠ 伪基站控制台(仅供决赛演示)</h1>
<button onclick="fire()">发起伪基站认证</button>
<div class="tip">每次点击 = 注入 1 帧伪 RESULT(真站 IDS 红横幅) + 1 帧未注册接入请求
(真站弹窗/验证→拒绝动画 + BLOCKED)。板 A 不参与、不受影响。</div>
<div id="out">待命…</div>
<script>async function fire(){document.getElementById('out').textContent='注入中…';
 try{const r=await fetch('/attack',{method:'POST'});
 const j=await r.json();document.getElementById('out').textContent=
  '已发起 #'+j.rounds+'\\n'+j.frames.join('\\n');}catch(e){
  document.getElementById('out').textContent='失败:'+e;}}</script></body></html>"""


def _rogue_web(ser, args, r2_fake, send, log) -> int:
    import http.server

    state = {"rounds": 0}
    lock = threading.Lock()

    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):                      # noqa: N802
            if self.path.split("?")[0] != "/":
                self.send_error(404)
                return
            body = _ROGUE_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):                     # noqa: N802
            if self.path.split("?")[0] != "/attack":
                self.send_error(404)
                return
            with lock:
                try:
                    burst = _rogue_fire(send, args, r2_fake, log)
                except Exception as exc:  # 串口异常不上 traceback:页面明示,可排查
                    log(f"ROGUE-WEB fire failed: {type(exc).__name__}: {exc}")
                    err = json.dumps({"ok": False,
                                      "error": f"{type(exc).__name__}: {exc}"}).encode("utf-8")
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(err)))
                    self.end_headers()
                    self.wfile.write(err)
                    return
                state["rounds"] += 1
                desc = [f"{name} ({len(f)}B) {f.hex()[:40]}…" for name, f in burst]
            body = json.dumps({"ok": True, "rounds": state["rounds"],
                               "frames": desc}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *a):        # 静默访问日志
            pass

    try:
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", int(args.rogue_web)), _H)
    except OSError as exc:
        print(f"[ROGUE-WEB] 端口 {args.rogue_web} 起不来({exc}) — "
              f"换一个: --rogue-web 8644", file=sys.stderr)
        return 3
    print(f"[ROGUE-WEB] http://127.0.0.1:{int(args.rogue_web)}/ — Ctrl+C 退出",
          file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    print(f"[ROGUE-WEB] stop. rounds={state['rounds']}", file=sys.stderr)
    return 0


def _bridge_call(base: str, path: str, payload: dict | None = None):
    import urllib.request
    url = base.rstrip('/') + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read().decode())


def _rogue_bridge_once(args, r2_fake, log) -> int:
    burst = build_rogue_burst(tid=args.rogue_tid,
                              banner=not args.no_banner, r2_fake=r2_fake)
    frames = [f.hex() for _, f in burst]
    code, j = _bridge_call(args.via_bridge, '/api/attack/inject',
                           {'frames': frames, 'note': 'rogue access burst'})
    log(f">>> ROGUE(via-bridge) inject http={code} ok={j.get('ok')} "
        f"frames={len(frames)}")
    return 0 if j.get('ok') else 1


def _rogue_web_bridge(args, r2_fake, log) -> int:
    """N15: 单按钮网页,点击经桥注入(共享信道);另配武装竞速按钮。"""
    import http.server
    base = args.via_bridge
    state = {"rounds": 0, "armed": 0}

    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):                      # noqa: N802
            if self.path.split('?')[0] != '/':
                self.send_error(404); return
            body = _ROGUE_PAGE_BRIDGE.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):                      # noqa: N802
            pth = self.path.split('?')[0]
            n = int(self.headers.get('Content-Length', 0))
            payload = json.loads(self.rfile.read(n) or b'{}')
            if pth == '/attack':
                burst = build_rogue_burst(tid=args.rogue_tid,
                                          banner=not args.no_banner,
                                          r2_fake=r2_fake)
                code, j = _bridge_call(base, '/api/attack/inject',
                    {'frames': [f.hex() for _, f in burst],
                     'note': 'rogue access burst'})
                state['rounds'] += 1 if j.get('ok') else 0
                out = json.dumps({'ok': j.get('ok'),
                                  'rounds': state['rounds'],
                                  'detail': j}).encode('utf-8')
            elif pth == '/arm':
                tid = int(payload.get('terminal_id', 1))
                code, j = _bridge_call(base, '/api/attack/arm',
                    {'terminal_id': tid, 'r2_hex': r2_fake.hex()})
                state['armed'] = tid if j.get('ok') else 0
                out = json.dumps({'ok': j.get('ok'), 'armed': state['armed'],
                                  'detail': j}).encode('utf-8')
            else:
                self.send_error(404); return
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, fmt, *a):
            pass

    try:
        srv = http.server.ThreadingHTTPServer(('127.0.0.1', int(args.rogue_web)), _H)
    except OSError as exc:
        print(f'[ROGUE-WEB] 端口 {args.rogue_web} 起不来({exc}) — 换: --rogue-web 8644',
              file=sys.stderr)
        return 3
    print(f'[ROGUE-WEB via-bridge {base}] http://127.0.0.1:{int(args.rogue_web)}/ '
          f'— Ctrl+C 退出', file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


_ROGUE_PAGE_BRIDGE = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>伪基站控制台(共享信道)</title><style>
 body{background:#160608;color:#f5c8c8;font-family:system-ui,'Segoe UI',sans-serif;
       display:flex;flex-direction:column;align-items:center;margin-top:8vh;gap:18px}
 h1{font-size:22px;letter-spacing:2px} button{font-size:20px;padding:16px 42px;
   background:#7a1220;color:#fff;border:1px solid #ff5a5a;border-radius:10px;
   cursor:pointer;margin:6px} button:active{transform:scale(.97)}
 #out{white-space:pre-wrap;font:12px/1.6 Consolas,monospace;color:#ffb3b3;
       max-width:760px;word-break:break-all} .tip{color:#a97;font-size:13px}
 input{width:64px;font-size:18px;text-align:center;padding:8px}
</style></head><body>
<h1>☠ 伪基站控制台(共享信道·经基站电台注入)</h1>
<div><button onclick="fire()">伪基站接入(tid 77)</button>
目标板 tid <input id="tid" value="1">
<button onclick="arm()">⚔ 武装竞速注入</button></div>
<div class="tip">【接入】= 注入伪 RESULT + 未注册接入请求(真站 IDS 红横幅+拒绝警报)。
【竞速】= 该板下一轮认证的 R1 刚到即注入伪造 RESULT——板端 R2 校验识破,
CONFIRM_FAIL 上报+BLOCKED,真站关联告警。共享信道下两块板都能听见注入帧。</div>
<div id="out">待命…</div>
<script>
async function fire(){out('注入中…');
 try{const r=await fetch('/attack',{method:'POST'});const j=await r.json();
  out('已发起 #'+j.rounds+'\n'+JSON.stringify(j.detail));}catch(e){out('失败:'+e);}}
async function arm(){out('武装中…');
 const tid=parseInt(document.getElementById('tid').value||'1',10);
 try{const r=await fetch('/arm',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({terminal_id:tid})});const j=await r.json();
  out('已武装 tid='+j.armed+' — 去真站页面选中该板开始验证');}catch(e){out('失败:'+e);}}
function out(s){document.getElementById('out').textContent=s;}
</script></body></html>"""


def main(argv: list[str] | None = None) -> int:

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--via-bridge", default="http://127.0.0.1:8642",
                   help="N15: 经桥注入(共享信道,无需攻击者串口);值为桥基址")
    p.add_argument("--port", default=None,
                   help="攻击者电台串口(如 COM9);--simulate 模式可不填")
    p.add_argument("--baud", type=int, default=115_200)
    p.add_argument("--r2-hex", default=DEFAULT_FAKE_R2.hex(),
                   help="伪 R2(8B hex,默认按构造即错)")
    p.add_argument("--mode", choices=["race", "passive"], default="race")
    p.add_argument("--delay-ms", type=float, default=0.0,
                   help="注入延迟(演示'竞速'用,默认 0)")
    p.add_argument("--inject-now", action="store_true",
                   help="启动即注入一帧(单演 Tier0 IDS)后退出")
    p.add_argument("--simulate", action="store_true",
                   help="不连串口,回放内置演示字节流(排练用,零硬件)")
    p.add_argument("--rogue", action="store_true",
                   help="N10 伪基站接入演示:每按一次 Enter 发一组(banner+接入请求)")
    p.add_argument("--rogue-tid", type=int, default=ROGUE_TID_DEFAULT,
                   help="伪基站自称的终端号(默认 77,未注册→真站 REJECT)")
    p.add_argument("--no-banner", action="store_true",
                   help="rogue 模式不发 0x0093 banner 帧(只发接入请求)")
    p.add_argument("--rogue-web", nargs="?", const=8643, type=int,
                   default=None, metavar="PORT",
                   help="rogue 模式浏览器单按钮版(默认端口 8643)")
    args = p.parse_args(argv)
    if args.rogue and args.rogue_web is not None:
        p.error("--rogue and --rogue-web are exclusive")

    r2 = bytes.fromhex(args.r2_hex)
    if len(r2) != 8:
        p.error("--r2-hex must be 8 bytes")

    sent: list[bytes] = []
    atk = FakeResultAttacker(send=sent.append, r2_fake=r2, mode=args.mode,
                             delay_s=args.delay_ms / 1000.0)

    if args.simulate:                       # 零硬件排练:回放一轮真认证字节流
        proto = HFIDAProtocol()
        c2 = bytes.fromhex("a1a2a3a4a5a6a7a8")
        stream = b"".join([
            b"\x00noise\xff", proto.pack(HFIDAProtocol.MSG_ACCESS_REQUEST,
                                   terminal_id=1, c2=c2),
            proto.pack(HFIDAProtocol.MSG_CHALLENGE,
                       seeds=[bytes(8)] * 4),
            proto.pack(HFIDAProtocol.MSG_RESPONSE_R1,
                       r1s=[bytes(8)] * 4),
        ])
        atk.feed(stream)
        print(f"[SIMULATE] heard={atk.heard_frames} injected={atk.injected_rounds}")
        for f in sent:
            mid, fields = HFIDAProtocol.parse(f)
            print(f"[SIMULATE] sent msg={HFIDAProtocol.msg_name(mid)} {fields}")
        if args.rogue or args.rogue_web is not None:   # N10 排练:打印将发的帧组
            for name, frame in build_rogue_burst(tid=args.rogue_tid,
                                                 banner=not args.no_banner,
                                                 r2_fake=r2):
                rm, rf = proto.parse(frame)
                print(f"[SIMULATE][ROGUE] {name}: {proto.msg_name(rm)} {rf}")
        return 0 if (args.mode == "passive" or atk.injected_rounds == 1) else 1

    if not args.port:
        p.error("--port is required for real-serial mode (or use --simulate / --via-bridge)")
    if getattr(args, 'via_bridge', None) and args.port is None:
        # N15: 共享信道单 HC-12 拓扑——攻击帧经基站电台上空(桥 API 注入),
        # 无需攻击者独立串口;两块板都能听见注入帧。
        if args.rogue_web is not None:
            return _rogue_web_bridge(args, r2, atk._log)
        if args.rogue:
            return _rogue_bridge_once(args, r2, atk._log)
        print('--via-bridge 需配 --rogue 或 --rogue-web 使用', file=sys.stderr)
        return 2

    try:
        import serial  # 仅真信道需要
    except ImportError:
        print("pyserial not installed: pip install pyserial (或先用 --simulate)",
              file=sys.stderr)
        return 2

    atk._send = lambda frame: None           # 换真发送
    with serial.Serial(args.port, args.baud, timeout=0.1) as ser:
        def send(frame: bytes) -> None:
            ser.write(frame)
            ser.flush()
        atk._send = send
        if args.rogue or args.rogue_web is not None:      # N10 伪基站接入演示
            if args.rogue_web is not None:
                return _rogue_web(ser, args, r2, send, atk._log)
            return _rogue_interactive(ser, args, r2, send, atk._log)
        if args.inject_now:
            atk.inject_now()
            return 0
        print(f"[ATTACK] sniffing {args.port}@{args.baud} mode={args.mode} "
              f"r2={r2.hex()} — Ctrl+C 退出", file=sys.stderr)
        try:
            while True:
                chunk = ser.read(256)
                if chunk:
                    atk.feed(chunk)
        except KeyboardInterrupt:
            print(f"[ATTACK] stop. heard={atk.heard_frames} "
                  f"injected={atk.injected_rounds} noise={atk.sync.noise}",
                  file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
