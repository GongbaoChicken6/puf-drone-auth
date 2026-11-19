"""Wait for a queued entry, select it, then report sessions/verdict."""
import json, time, urllib.request

BASE = "http://127.0.0.1:8642"
OUT = r"D:\puf-drone-auth\build\logs\watch_select.log"
DUR = 120.0

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=5) as r:
        return json.loads(r.read().decode())

def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")

log = open(OUT, "w", encoding="utf-8")
def L(m):
    print(m, flush=True); log.write(m + "\n"); log.flush()

t0 = time.time()
did = False
while time.time() - t0 < DUR:
    try:
        q = get("/api/access/queue")
    except Exception:
        time.sleep(0.5); continue
    entries = q.get("entries") or []
    if entries and not did:
        e = entries[0]
        L(f"[{time.time()-t0:.1f}s] saw tid={e['terminal_id']} label={e.get('label')} selected={q.get('selected')}")
        code, body = post("/api/access/select", {"terminal_id": e["terminal_id"]})
        L(f"[{time.time()-t0:.1f}s] select -> {code} {json.dumps(body, ensure_ascii=False)}")
        did = True
        time.sleep(3)
        try:
            s = get("/api/status")
            L(f"sessions after: {json.dumps(s.get('sessions'), ensure_ascii=False)}")
        except Exception as ex:
            L(f"status err {ex}")
        break
    time.sleep(0.4)
L("WATCH_DONE")
log.close()
