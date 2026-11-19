"""Dual-board bridge launcher v2: COM6 (board A) + COM9 (board B, confirmed)."""
import sys, os
sys.path.insert(0, r"D:\puf-drone-auth\web\bridge")
os.chdir(r"D:\puf-drone-auth")
import web_bridge
argv = [
    "--serial-multi=COM6,COM9",
    "--access-gate",
    "--access-label=1=Board A,2=Board B",
    "--tid-port=1=COM6,2=COM9",
    "--data-dir=data",
    "--port=8642",
]
print(f"[LAUNCHER] argv: {argv}", flush=True)
web_bridge.main(argv)
