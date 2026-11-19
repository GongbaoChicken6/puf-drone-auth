"""Capture bridge SSE events to a file (timeout-tolerant)."""
import sys, time, socket, urllib.request

URL = "http://127.0.0.1:8642/api/events"
OUT = r"D:\puf-drone-auth\build\logs\sse_capture.log"
DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0

t0 = time.time()
req = urllib.request.urlopen(URL, timeout=60)
f = open(OUT, "w", encoding="utf-8")
print("SSE connected", flush=True)
while time.time() - t0 < DUR:
    try:
        line = req.readline()
    except (socket.timeout, TimeoutError):
        continue
    except Exception as e:
        print("SSE error:", e, flush=True)
        break
    if not line:
        break
    s = line.decode("utf-8", "replace").rstrip()
    if s.startswith("data:"):
        f.write(f"{time.time()-t0:7.2f}s {s[5:].strip()}\n")
        f.flush()
f.close()
print("SSE watcher done", flush=True)
