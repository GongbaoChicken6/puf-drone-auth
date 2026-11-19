"""Dual-board demo bridge launcher - bypasses PowerShell arg parsing issues."""
import sys, os
sys.path.insert(0, r"D:\puf-drone-auth\web\bridge")
os.chdir(r"D:\puf-drone-auth")
import web_bridge
argv = [
    "--serial-multi=COM6,COM11",
    "--access-gate",
    "--access-label=1=Board A,2=Board B",
    "--tid-port=1=COM6,2=COM11",
    "--data-dir=data",
    "--port=8642",
]
print(f"[LAUNCHER] argv: {argv}", flush=True)
web_bridge.main(argv)
