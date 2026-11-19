import sys, time, socket, urllib.request
URL = "http://127.0.0.1:8642/api/events"
OUT = r"D:\puf-drone-auth\build\logs\sse_now.log"
DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
t0 = time.time()
req = urllib.request.urlopen(URL, timeout=30)
f = open(OUT, "w", encoding="utf-8")
while time.time() - t0 < DUR:
    try:
        line = req.readline()
    except (socket.timeout, TimeoutError):
        continue
    except Exception:
        break
    if not line:
        break
    s = line.decode("utf-8", "replace").rstrip()
    if s.startswith("data:"):
        f.write(f"{time.time()-t0:6.2f}s {s[5:].strip()}\n"); f.flush()
f.close()
print("DONE", flush=True)
