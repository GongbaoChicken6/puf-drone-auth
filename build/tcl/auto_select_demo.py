"""Watch gate queue; auto-select tid on arrival; log the whole auth."""
import json, time, urllib.request

BASE = "http://127.0.0.1:8642"
OUT = r"D:\puf-drone-auth\build\logs\auto_select.log"
DUR = 150.0

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=5) as r:
        return json.loads(r.read().decode())

def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")

log = open(OUT, "w", encoding="utf-8")
def L(m):
    print(m, flush=True); log.write(m + "\n"); log.flush()

t0 = time.time()
selected_done = False
while time.time() - t0 < DUR:
    try:
        q = get("/api/access/queue")
    except Exception as e:
        L(f"queue err: {e}"); time.sleep(0.5); continue
    entries = q.get("entries") or []
    if entries and not selected_done:
        e = entries[0]
        tid = e["terminal_id"]
        L(f"[{time.time()-t0:.1f}s] queued tid={tid} label={e.get('label')} port={e.get('port')} selected={q.get('selected')}")
        if q.get("selected") is None:
            code, body = post("/api/access/select", {"terminal_id": tid})
            L(f"[{time.time()-t0:.1f}s] SELECT -> {code} {json.dumps(body, ensure_ascii=False)}")
            selected_done = True
    elif selected_done:
        try:
            s = get("/api/status")
        except Exception:
            s = {}
        sess = s.get("sessions") or []
        pools = {p["terminal_id"]: p["remaining"] for p in (s.get("pools") or [])}
        L(f"[{time.time()-t0:.1f}s] queue={[x['terminal_id'] for x in entries]} sessions={[x.get('terminal_id') for x in sess]} pools={pools}")
        # stop once we see a session or the queue empties and stays empty
    time.sleep(0.5)
L("AUTO_SELECT_DONE")
log.close()
