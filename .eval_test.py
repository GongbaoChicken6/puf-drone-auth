"""Scratch CLI test for the evaluation tools (deleted after run)."""
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, r"D:\puf-drone-auth")
REPO = Path(r"D:\puf-drone-auth")
rng = random.Random(2026)
tmp = Path(tempfile.mkdtemp(prefix="puf_eval_"))
PY = sys.executable

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

def run(args):
    return subprocess.run([PY] + args, capture_output=True, text=True,
                          cwd=str(REPO), timeout=120)

print("== quantizer CLI ==")
readings_csv = tmp / "readings.csv"
rows = []
for i in range(130):
    value = 1_000_000 + (37 if i % 2 == 0 else -53)
    rows.append(f"12:00:{i % 60:02d},{value:08x},{value}")
readings_csv.write_text("\n".join(rows) + "\n", encoding="utf-8")
r = run(["-m", "src.python.evaluation.quantizer", "-i", str(readings_csv), "--bits", "64"])
check("quantizer exit 0", r.returncode == 0, r.stderr[-400:])
check("quantizer produced 2 words", "produced 2 x 64-bit word" in r.stdout, r.stdout)
check("quantizer weight ~50%", "word 1:" in r.stdout and "word 2:" in r.stdout)
check("quantizer discards remainder", "(2 trailing readings discarded)" in r.stdout)
r = run(["-m", "src.python.evaluation.quantizer", "-i", str(readings_csv), "--center", "1000000", "--bits", "64"])
check("quantizer explicit center works", r.returncode == 0 and "center value = 1000000.0" in r.stdout)

print("== hamming_analysis CLI ==")
base = rng.getrandbits(64)
def noisy(value, flips):
    for _ in range(flips):
        value ^= 1 << rng.randrange(64)
    return value
meas_csv = tmp / "meas.csv"
lines = ["timestamp,hex_value,decimal_value"]
for i in range(20):
    v = noisy(base, rng.randint(0, 3))
    lines.append(f"00:00:{i:02d},{v:016x},{v}")
meas_csv.write_text("\n".join(lines) + "\n", encoding="utf-8")

r = run(["-m", "src.python.evaluation.hamming_analysis", "-i", str(meas_csv)])
check("matrix mode exit 0", r.returncode == 0, r.stderr[-400:])
check("matrix is markdown", "Hamming Distance Matrix (%):" in r.stdout and "| # |" in r.stdout)
r = run(["-m", "src.python.evaluation.hamming_analysis", "-i", str(meas_csv), "-c", "1"])
check("compare mode stats", r.returncode == 0 and "[STATS] Average distance" in r.stdout, r.stdout[-300:])
r = run(["-m", "src.python.evaluation.hamming_analysis", "-i", str(meas_csv), "-r"])
check("rolling mode stats", r.returncode == 0 and "rolling" in r.stdout.lower())
r = run(["-m", "src.python.evaluation.hamming_analysis", "-i", str(meas_csv), "-w"])
check("weight table mode", r.returncode == 0 and "| Device | Ones |" in r.stdout)
r = run(["-m", "src.python.evaluation.hamming_analysis", "-i", str(meas_csv), "--weight-plot"])
auto_png = meas_csv.with_name(f"{meas_csv.stem}_weight.png")
check("weight plot auto-saved (no show)", r.returncode == 0 and auto_png.exists() and auto_png.stat().st_size > 1000, r.stderr[-400:])
r = run(["-m", "src.python.evaluation.hamming_analysis", "-i", str(meas_csv), "-r", "--save", str(tmp / "roll.png")])
check("rolling plot with --save", (tmp / "roll.png").exists() and (tmp / "roll.png").stat().st_size > 1000)

print("== hamming_analysis template mode ==")
tpl = {"1": {f"{rng.getrandbits(64):016x}": f"{base:016x}", f"{rng.getrandbits(64):016x}": f"{noisy(base, 32):016x}"}}
tpl_file = tmp / "templates.json"
tpl_file.write_text(json.dumps(tpl), encoding="utf-8")
r = run(["-m", "src.python.evaluation.hamming_analysis", "-i", str(meas_csv), "--template", str(tpl_file), "--terminal-id", "1"])
check("template mode exit 0", r.returncode == 0, r.stderr[-400:])
check("template mode min-HD table", "Min HD" in r.stdout and "Best match" in r.stdout)
avg_line = [l for l in r.stdout.splitlines() if "Average min distance" in l]
check("template avg min HD small", avg_line and float(avg_line[0].split(":")[1].split("%")[0].strip().split(" ")[0]) < 6.0, str(avg_line))
check("template plot auto-saved", meas_csv.with_name(f"{meas_csv.stem}_template.png").exists())
r = run(["-m", "src.python.evaluation.hamming_analysis", "-i", str(meas_csv), "--template", str(tpl_file)])
check("template mode single-terminal autoselect", r.returncode == 0 and "Min HD" in r.stdout and "[ERROR]" not in r.stdout, r.stdout[-200:])

print("== compare_devices CLI ==")
devdir = tmp / "devices"
devdir.mkdir()
for d in range(3):
    dev_base = rng.getrandbits(64)
    lines = ["timestamp,hex_value,decimal_value"]
    for i in range(15):
        v = noisy(dev_base, rng.randint(0, 3))
        lines.append(f"00:00:{i:02d},{v:016x},{v}")
    (devdir / f"term_{d:02d}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
r = run(["-m", "src.python.evaluation.compare_devices", "-d", str(devdir)])
check("compare exit 0", r.returncode == 0, r.stderr[-400:])
check("matrix markdown with +/- cells", "Inter-Device Hamming Distance Matrix (%):" in r.stdout and "+/-" in r.stdout)
check("intra diagonal present", "reliability" in r.stdout)
avg_line = [l for l in r.stdout.splitlines() if "Average inter-device distance" in l]
avg_val = float(avg_line[0].split(":")[1].split("%")[0].strip().split(" ")[0]) if avg_line else -1
check("inter-device avg near 50%", 35.0 < avg_val < 65.0, f"got {avg_val}")
check("verdict OK line", "[OK] Inter-device distance looks good!" in r.stdout)
r = run(["-m", "src.python.evaluation.compare_devices", "-d", str(devdir), "--first-only"])
check("--first-only compat mode", r.returncode == 0 and "1 measurement(s)" in r.stdout)
r = run(["-m", "src.python.evaluation.compare_devices", "-d", str(tmp / "no_such_dir")])
check("missing dir handled", r.returncode != 0 and "[ERROR]" in r.stdout)

print(f"\nTOTAL: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
