# Web Module — Base Station Bridge & Demo Console

## Quick Start

```bash
# ALWAYS use a fresh empty directory for --data-dir (see warning below)
python web/bridge/web_bridge.py --repo-root . --data-dir ./sandbox --loopback --port 8642
```

Open http://127.0.0.1:8642/console.html

## CRITICAL: --data-dir Warning

The default --data-dir points to the bundled data/ directory. On first startup, the bridge performs a stale-terminal cleanup that **irreversibly deletes** measured templates and challenge pools. Always pass --data-dir pointing to a fresh empty directory.

## Directory Layout
- bridge/ — Python HTTP+SSE bridge server (web_bridge.py)
- src/ — TypeScript frontend source (Vite + Three.js)
- dist/ — Pre-built frontend (self-contained, offline)
- tools/ — gen_metrics.py, sample_hd.py

## Real Hardware Mode

```bash
python web/bridge/web_bridge.py --repo-root . --data-dir ./sandbox \
  --serial-port COM<x> --serial-baud 115200 --port 8642
```

The RealSerialListener will:
1. Inject real-board templates (tid 1/2) from data/templates/
2. Listen for ACCESS_REQUEST frames from the board (triggered by SW7)
3. Run full authentication protocol over serial

## Build Frontend (optional, dist/ is pre-built)

```bash
npm install && npm run build
```
