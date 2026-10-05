"""Scratch smoke test for the PUF server + evaluation tools (deleted after run)."""
import concurrent.futures
import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, r"D:\puf-drone-auth")

from src.python.server import threshold
from src.python.server.crp_pool import CRPPool, CRPPoolRegistry, PoolExhaustedError
from src.python.server.hsm import SimulatedHSM
from src.python.server.protocol import (
    HFIDAProtocol, ProtocolError, RESULT_PASS, RESULT_REJECT,
)
from src.python.server.template_db import TemplateDB, compute_stability

PASS = 0
FAIL = 0

def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")

print("== threshold ==")
check("decide(0)=PASS", threshold.decide(0) == "PASS")
check("decide(6)=PASS", threshold.decide(6) == "PASS")
check("decide(7)=GRAY", threshold.decide(7) == "GRAY")
check("decide(15)=GRAY", threshold.decide(15) == "GRAY")
check("decide(16)=REJECT", threshold.decide(16) == "REJECT")
check("decide(64)=REJECT", threshold.decide(64) == "REJECT")
check("decide_scaled(24,4)=PASS", threshold.decide_scaled(24, 4) == "PASS")
check("decide_scaled(25,4)=GRAY", threshold.decide_scaled(25, 4) == "GRAY")
check("decide_scaled(64,4)=REJECT", threshold.decide_scaled(64, 4) == "REJECT")
check("decide_scaled(42,7)=PASS", threshold.decide_scaled(42, 7) == "PASS")

print("== crp_pool ==")
tmp = Path(tempfile.mkdtemp(prefix="puf_smoke_"))
pool_path = tmp / "pool_1.json"
pool = CRPPool(1, pool_size=500, state_path=pool_path)
minted = pool.reserve(10)
check("reserve(10) returns 10x8B unique",
      len(minted) == 10 and all(len(s) == 8 for s in minted)
      and len({s.hex() for s in minted}) == 10)
check("reserve does not consume", pool.remaining == 10)
seeds = pool.draw(3)
check("draw(3) returns 3x8B", len(seeds) == 3 and all(len(s) == 8 for s in seeds))
check("drawn seeds were reserved", set(s.hex() for s in seeds) <= set(s.hex() for s in minted))
check("remaining == 7", pool.remaining == 7)
pct = pool.remaining_pct
check("remaining_pct is int 0..100", isinstance(pct, int) and 0 <= pct <= 100, f"got {pct!r}")
p10 = CRPPool(3, pool_size=10, state_path=tmp / "pool_10.json")
p10.reserve(10)
p10.draw(3)
check("remaining_pct == 70 (7 of 10)", p10.remaining_pct == 70, f"got {p10.remaining_pct}")
saved = json.loads(pool_path.read_text(encoding="utf-8"))
check("available+used persisted as JSON",
      len(saved["available"]) == 10 and len(saved["used"]) == 3 and saved["pool_size"] == 500)
pool2 = CRPPool(1, state_path=pool_path)
check("state reloads from disk", pool2.remaining == 7)
check("redraw after reload avoids used",
      not (set(s.hex() for s in pool2.draw(2)) & set(saved["used"])))
small = CRPPool(2, pool_size=5, state_path=tmp / "pool_2.json")
small.reserve(5)
try:
    small.draw(6)
    check("PoolExhaustedError raised", False)
except PoolExhaustedError:
    check("PoolExhaustedError raised", True)
    check("exhausted draw consumed nothing", small.remaining == 5)
tiny = CRPPool(4, pool_size=5, state_path=tmp / "pool_4.json")
try:
    tiny.reserve(6)
    check("reserve over capacity raises", False)
except PoolExhaustedError:
    check("reserve over capacity raises", True)
reg = CRPPoolRegistry(tmp / "reg", pool_size=10)
reg.get(7).reserve(4)
check("registry lazy-create + reserve", reg.get(7).remaining == 4 and reg.terminals() == [7])
check("registry per-device isolation", reg.get(8).terminal_id == 8)

print("== template_db ==")
tpl_path = tmp / "templates.json"
db = TemplateDB(tpl_path)
ideal = {bytes([i] * 8): bytes([i, 255 - i, 7, 7, 7, 7, 7, 7]) for i in range(1, 11)}
summary = db.enroll(5, ideal)
check("enroll stores 10 pairs", summary["n_pairs"] == 10)
seed0 = bytes([1] * 8)
check("HD vs exact template = 0", db.hamming_distance(5, ideal[seed0], seed=seed0) == 0)
flipped = (int.from_bytes(ideal[seed0], "big") ^ 0b1011).to_bytes(8, "big")
check("HD 3-bit flip = 3", db.hamming_distance(5, flipped, seed=seed0) == 3)
no_seed_hd = db.hamming_distance(5, ideal[seed0])
check("no-seed mode returns 0..64", isinstance(no_seed_hd, int) and 0 <= no_seed_hd <= 64)
try:
    db.hamming_distance(99, ideal[seed0], seed=seed0)
    check("unknown terminal raises KeyError", False)
except KeyError:
    check("unknown terminal raises KeyError", True)
try:
    db.hamming_distance(5, b"\x00" * 8, seed=b"\xff" * 8)
    check("unknown seed raises KeyError", False)
except KeyError:
    check("unknown seed raises KeyError", True)
noisy = {seed.hex(): [ideal[seed], ideal[seed],
                      (int.from_bytes(ideal[seed], "big") ^ 1).to_bytes(8, "big")]
         for seed in list(ideal)[:3]}
mask = compute_stability(noisy, flip_threshold=0.1)
check("stability mask width 64", len(mask) == 64)
check("stable bit counts (63 of 64)", mask.count("1") == 63, f"got {mask.count('1')}")
db2 = TemplateDB(tpl_path)
check("reload from disk keeps pairs", db2.templates["5"][seed0.hex()] == ideal[seed0].hex())
raw = json.loads(tpl_path.read_text(encoding="utf-8"))
check("on-disk layout {terminal_id:{seed_hex:response_hex}}",
      isinstance(raw, dict) and isinstance(raw["5"], dict)
      and all(len(k) == 16 for k in raw["5"]))

print("== hsm ==")
hsm = SimulatedHSM()
c2 = bytes(range(8))
r2a, r2b = hsm.respond(c2), hsm.respond(c2)
check("respond deterministic", r2a == r2b)
check("respond returns 8 bytes", len(r2a) == 8)
pairs = hsm.enroll(10)
check("enroll returns n pairs of 8B", len(pairs) == 10 and all(len(k) == 8 and len(v) == 8 for k, v in pairs.items()))
sec_file = tmp / "hsm_secret.json"
hsm.save_secret(sec_file)
hsm2 = SimulatedHSM.load_secret(sec_file)
check("secret persists across reload", hsm2.respond(c2) == r2a)

print("== protocol framing ==")
proto = HFIDAProtocol(templates=TemplateDB(), hsm=SimulatedHSM(),
                      pools=CRPPoolRegistry(tmp / "ppools"))
f_acc = proto.pack(HFIDAProtocol.MSG_ACCESS_REQUEST, terminal_id=5, nonce=42, c2=c2)
mid, f = proto.parse(f_acc)
check("ACCESS_REQUEST roundtrip", mid == 0x0090 and f["terminal_id"] == 5 and f["nonce"] == 42 and f["c2"] == c2)
f_res = proto.pack(HFIDAProtocol.MSG_RESULT, result=RESULT_PASS, hd=7, r2=r2a)
mid, f = proto.parse(f_res)
check("RESULT roundtrip", mid == 0x0093 and f["result"] == RESULT_PASS and f["hd"] == 7 and f["r2"] == r2a)
f_conf = proto.pack(HFIDAProtocol.MSG_CONFIRM, terminal_id=5, status=0)
mid, f = proto.parse(f_conf)
check("CONFIRM roundtrip", mid == 0x0094 and f["terminal_id"] == 5 and f["status"] == 0)
bad = bytearray(f_conf); bad[11] ^= 0xFF
try:
    proto.parse(bytes(bad))
    check("CRC mismatch detected", False)
except ValueError:
    check("CRC mismatch detected", True)

print("== protocol full flows (deterministic fake terminal) ==")
def dev_resp(seed, tid):
    return hashlib.sha256(f"dev{tid}".encode() + seed).digest()[:8]

def fresh(tid, n=50):
    """Protocol with a fully enrolled fake device (n CRPs in pool+template)."""
    tdb = TemplateDB(tmp / f"tpl_{tid}.json")
    p = HFIDAProtocol(templates=tdb, hsm=SimulatedHSM(),
                      pools=CRPPoolRegistry(tmp / f"pool_{tid}"))
    seeds = p.pools.get(tid).reserve(n)
    p.templates.enroll(tid, {s: dev_resp(s, tid) for s in seeds})
    return p

def responses_of(tid, seeds):
    return [dev_resp(s, tid) for s in seeds]

def flipped(responses, n_bits):
    mask_val = int("1" * n_bits, 2)
    return [(int.from_bytes(r, "big") ^ mask_val).to_bytes(8, "big") for r in responses]

# PASS flow
p = fresh(1)
frame = p.on_access_request(1, c2=c2)
mid, f = p.parse(frame)
check("access -> CHALLENGE (0x0091)", mid == 0x0091)
check("challenge frame is 44 bytes", len(frame) == 44, f"got {len(frame)}")
check("4 challenges in frame", len(f["seeds"]) == 4)
check("drawn challenges are enrolled",
      all(p.templates.expected(1, s) is not None for s in f["seeds"]))
frame2 = p.on_response(1, responses_of(1, f["seeds"]))
mid2, f2 = p.parse(frame2)
check("genuine -> RESULT PASS", mid2 == 0x0093 and f2["result"] == RESULT_PASS)
check("R2 equals HSM(c2)", f2["r2"] == p.hsm.respond(c2))
check("hd reported 0", f2["hd"] == 0)
check("confirm sets SESSION", p.on_confirm(1, 0) is None)

# REJECT flow (impostor: unrelated responses)
p = fresh(2)
frame = p.on_access_request(2, c2=c2)
mid, f = p.parse(frame)
impostor = [bytes([0xA5, i, 0, 0, 0, 0, 0, 0]) for i, _ in enumerate(f["seeds"])]
frame2 = p.on_response(2, impostor)
mid2, f2 = p.parse(frame2)
check("impostor -> RESULT REJECT", mid2 == 0x0093 and f2["result"] == RESULT_REJECT)
check("impostor hd_sum >= 64", f2["hd"] >= 64, f"got {f2['hd']}")

# GRAY -> extra -> PASS (initial HD 8/response, extra HD 2/response)
p = fresh(3)
frame = p.on_access_request(3, c2=c2)
mid, f = p.parse(frame)
frame2 = p.on_response(3, flipped(responses_of(3, f["seeds"]), 8))
mid2, f2 = p.parse(frame2)
check("borderline -> EXTRA_CHALLENGE (0x0095)", mid2 == 0x0095, f"got {hex(mid2)}")
check("3 extra challenges", len(f2["seeds"]) == 3)
check("extra frame is 36 bytes", len(frame2) == 36, f"got {len(frame2)}")
check("extra challenges are enrolled",
      all(p.templates.expected(3, s) is not None for s in f2["seeds"]))
frame3 = p.on_extra_response(3, flipped(responses_of(3, f2["seeds"]), 2))
mid3, f3 = p.parse(frame3)
check("gray -> aggregate PASS (38 <= 42)", mid3 == 0x0093 and f3["result"] == RESULT_PASS, f"hd={f3['hd']}")
check("aggregate hd reported 38", f3["hd"] == 38, f"got {f3['hd']}")

# GRAY -> extra -> REJECT (extra stays bad: 8/response -> 56 > 42)
p = fresh(4)
frame = p.on_access_request(4, c2=c2)
mid, f = p.parse(frame)
frame2 = p.on_response(4, flipped(responses_of(4, f["seeds"]), 8))
mid2, f2 = p.parse(frame2)
frame3 = p.on_extra_response(4, flipped(responses_of(4, f2["seeds"]), 8))
mid3, f3 = p.parse(frame3)
check("gray -> aggregate REJECT (56 > 42)", mid3 == 0x0093 and f3["result"] == RESULT_REJECT and f3["hd"] == 56)

# state machine errors
p = fresh(5)
try:
    p.on_response(5, [b"\x00" * 8] * 4)
    check("response without access raises", False)
except ProtocolError:
    check("response without access raises", True)
frame = p.on_access_request(5, c2=c2)
mid, f = p.parse(frame)
p.on_response(5, flipped(responses_of(5, f["seeds"]), 8))  # -> GRAY
try:
    p.on_response(5, responses_of(5, f["seeds"]))  # wrong state now
    check("double response raises", False)
except ProtocolError:
    check("double response raises", True)
try:
    p.on_extra_response(5, [b"\x00" * 8] * 2)  # wrong count
    check("wrong extra count raises", False)
except ProtocolError:
    check("wrong extra count raises", True)

# pool exhaustion mid-session (only 4 challenges ever enrolled)
p = fresh(6, n=4)
frame = p.on_access_request(6, c2=c2)  # consumes the last 4
mid, f = p.parse(frame)
frame2 = p.on_response(6, flipped(responses_of(6, f["seeds"]), 8))  # gray, pool empty
mid2, f2 = p.parse(frame2)
check("pool exhaustion in gray zone -> pool-empty result", mid2 == 0x0093 and f2["result"] == 3, f"result={f2['result']}")
frame = p.on_access_request(6, c2=c2)
mid, f = p.parse(frame)
check("empty pool -> immediate pool-empty result", mid == 0x0093 and f["result"] == 3)

# unenrolled terminal
p = fresh(7)
frame = p.on_access_request(999, c2=c2)
mid, f = p.parse(frame)
check("unenrolled terminal -> ERROR result", mid == 0x0093 and f["result"] == 2)

# concurrency smoke: parallel access requests + draws, no deadlock
p = fresh(8)
for t in (10, 11, 12):
    seeds = p.pools.get(t).reserve(100)
    p.templates.enroll(t, {s: dev_resp(s, t) for s in seeds})
done = []
def worker(n):
    fr = p.on_access_request(n % 3 + 10, c2=c2)
    done.append(len(fr))
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
    list(ex.map(worker, range(64)))
check("64 threaded sessions complete (no deadlock)", len(done) == 64 and all(d == 44 for d in done))

print(f"\nTOTAL: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
