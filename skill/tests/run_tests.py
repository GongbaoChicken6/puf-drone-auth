#!/usr/bin/env python3
"""run_tests.py - offline validation of the generic PYNQ skill package.

Runs every board-independent test for real and writes VALIDATION_LOG.md
next to this file. Board-dependent paths (live register smoke, DMA
bench) are NOT claimed here - they are listed as pending.

Usage:  python tests/run_tests.py
Exit 0 iff all checks pass.
"""
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
results = []


def run(name, argv, expect_rc, expect_in=None, expect_not_in=None,
        cwd=None, env_extra=None):
    """Run a subprocess, record pass/fail against expectations."""
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    p = subprocess.run(argv, capture_output=True, text=True, cwd=cwd,
                       env=env, timeout=300)
    out = p.stdout + p.stderr
    checks = [("exit=%d" % p.returncode, p.returncode == expect_rc)]
    if expect_in:
        for s in (expect_in if isinstance(expect_in, list) else [expect_in]):
            checks.append((f"contains {s!r}", s in out))
    if expect_not_in:
        for s in (expect_not_in if isinstance(expect_not_in, list)
                  else [expect_not_in]):
            checks.append((f"NOT contains {s!r}", s not in out))
    ok = all(c[1] for c in checks)
    results.append({"name": name, "ok": ok, "checks": checks,
                    "rc": p.returncode,
                    "tail": out[-1500:] if out else ""})
    print(("PASS " if ok else "FAIL ") + name +
          "".join(f"  [{a}={b}]" for a, b in checks))
    return p, ok


def main():
    fx = os.path.join(HERE, "fixtures")
    tmp = os.path.join(HERE, "_tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)

    # fake .bit next to the fixture .hwh (content irrelevant to static
    # mode; created at the same moment so timestamps match)
    bit = os.path.join(fx, "demo_overlay.bit")
    with open(bit, "wb") as f:
        f.write(b"\x00" * 64)

    # --- T1 overlay_doctor static: healthy overlay -> PASS ----------
    run("T1 overlay_doctor static PASS case",
        [PY, os.path.join(ROOT, "pynq-overlay-load-verify/scripts/",
                          "overlay_doctor.py"), "--bit", bit,
         "--md-out", os.path.join(tmp, "doctor.md")],
        expect_rc=0,
        expect_in=["speck_cipher_0", "axi_gpio_0", "0x43C00000",
                   "regs=4", "[VERDICT] static check: PASS"])

    # --- T2 overlay_doctor static: missing hwh -> FAIL --------------
    orphan = os.path.join(tmp, "orphan.bit")
    with open(orphan, "wb") as f:
        f.write(b"\x00" * 64)
    run("T2 overlay_doctor static missing-hwh FAIL case",
        [PY, os.path.join(ROOT, "pynq-overlay-load-verify/scripts/",
                          "overlay_doctor.py"), "--bit", orphan],
        expect_rc=1,
        expect_in=["no .hwh sidecar", "[VERDICT] static check: FAIL"])

    # --- T3 gen_driver_stub: contract -> driver + tests -------------
    gen = os.path.join(tmp, "gen")
    run("T3a gen_driver_stub generates driver+tests",
        [PY, os.path.join(ROOT, "pynq-interface-contract/scripts/",
                          "gen_driver_stub.py"),
         "--hwh", os.path.join(fx, "demo_overlay.hwh"),
         "--contract", os.path.join(fx, "speck_contract.json"),
         "--out-dir", gen, "--force"],
        expect_rc=0,
        expect_in=["[GEN ] " + os.path.join(gen, "driver_speck_cipher_0.py"),
                   "[GEN ] " + os.path.join(gen, "test_speck_cipher_0.py")])
    # driver must carry the real base address from the .hwh
    drv = open(os.path.join(gen, "driver_speck_cipher_0.py"),
               encoding="utf-8").read()
    t3b_ok = ("0x43C00000" in drv and "def read_ctrl" in drv
              and "def write_key_lo" in drv and "def start" in drv
              and "addrlen=65536" in drv)  # span = high-base+1 = 0x10000
    results.append({"name": "T3b driver content (base/regs/op/span)",
                    "ok": t3b_ok,
                    "checks": [("baked base+span+methods", t3b_ok)],
                    "rc": 0, "tail": ""})
    print(("PASS " if t3b_ok else "FAIL ") + "T3b driver content")

    # --- T4 generated pytest skeleton (off-board logic) -------------
    pytest_ok = shutil.which("pytest") is not None
    if not pytest_ok:
        probe = subprocess.run([PY, "-m", "pytest", "--version"],
                               capture_output=True, text=True)
        pytest_ok = probe.returncode == 0
    if pytest_ok:
        run("T4 generated tests via pytest (FakeMMIO logic)",
            [PY, "-m", "pytest", os.path.join(gen, "test_speck_cipher_0.py"),
             "-v", "--timeout=60" if False else "-q"],
            expect_rc=0,
            expect_in=["passed"],
            expect_not_in=["failed"])
    else:
        results.append({"name": "T4 pytest", "ok": False,
                        "checks": [("pytest available", False)],
                        "rc": -1, "tail": "pytest not installed"})
        print("FAIL T4 pytest not installed")

    # --- T5 golden_compare: pass & fail gates -----------------------
    run("T5a golden_compare CSV PASS case",
        [PY, os.path.join(ROOT, "pynq-golden-report/scripts/",
                          "golden_compare.py"),
         "--got", os.path.join(fx, "got_pass.csv"),
         "--golden", os.path.join(fx, "golden_pass.csv"),
         "--rtol", "1e-5", "--atol", "1e-4",
         "--md-out", os.path.join(tmp, "cmp_pass.md")],
        expect_rc=0, expect_in=["[VERDICT] PASS"])
    run("T5b golden_compare CSV FAIL case (cell out of tolerance)",
        [PY, os.path.join(ROOT, "pynq-golden-report/scripts/",
                          "golden_compare.py"),
         "--got", os.path.join(fx, "got_fail.csv"),
         "--golden", os.path.join(fx, "golden_pass.csv"),
         "--rtol", "1e-5", "--atol", "1e-4"],
        expect_rc=1, expect_in=["[VERDICT] FAIL", "cells failed   : 1"])
    # row-count mismatch must FAIL, not warn
    short = os.path.join(tmp, "got_short.csv")
    with open(short, "w", encoding="utf-8") as f:
        f.write("1,2,3,4\n")
    run("T5c golden_compare row-count mismatch FAILs",
        [PY, os.path.join(ROOT, "pynq-golden-report/scripts/",
                          "golden_compare.py"),
         "--got", short,
         "--golden", os.path.join(fx, "golden_pass.csv")],
        expect_rc=1, expect_in=["shape mismatch"])
    # binary mode (numpy)
    try:
        import numpy  # noqa: F401
        import struct
        gb = os.path.join(tmp, "gold.bin")
        ob = os.path.join(tmp, "got_bin.bin")
        with open(gb, "wb") as f:
            f.write(struct.pack("<8f", *[1.0 + 1e-7 * i
                                         for i in range(8)]))
        with open(ob, "wb") as f:
            f.write(struct.pack("<8f", *[1.0 + 2e-7 * i
                                         for i in range(8)]))
        run("T5d golden_compare binary PASS case",
            [PY, os.path.join(ROOT, "pynq-golden-report/scripts/",
                              "golden_compare.py"),
             "--got", ob, "--golden", gb, "--binary",
             "--dtype", "float32", "--shape", "8",
             "--atol", "1e-5"],
            expect_rc=0, expect_in=["[VERDICT] PASS"])
    except ImportError:
        print("SKIP T5d (numpy not installed)")

    # --- T6 collect_report on REAL Vivado reports (self-contained copy) --
    team = os.path.join(fx, "team_reports")
    if os.path.isdir(team):
        run("T6a collect_report real utilization (w1)",
            [PY, os.path.join(ROOT, "pynq-golden-report/scripts/",
                              "collect_report.py"),
             "--util", os.path.join(team, "utilization_w1.txt"),
             "--timing", os.path.join(team, "timing_w1.txt"),
             "--design-name", "ro_ratio_top",
             "--md-out", os.path.join(tmp, "metrics_w1.md"),
             "--json-out", os.path.join(tmp, "metrics_w1.json")],
            expect_rc=0,
            expect_in=["| LUT | 699 |", "| FF | 1263 |",
                       "ro_ratio_top", "xc7a35t"])
        w1md = open(os.path.join(tmp, "metrics_w1.md"),
                    encoding="utf-8").read()
        routed_ok = ("Routed" in w1md and
                     ("TIMING MET (routed)" in w1md or
                      "TIMING VIOLATED" in w1md))
        results.append({"name": "T6b w1 routed-state signoff labeling",
                        "ok": routed_ok,
                        "checks": [("routed -> signoff label present",
                                    routed_ok)],
                        "rc": 0, "tail": ""})
        print(("PASS " if routed_ok else "FAIL ") + "T6b routed labeling")
        run("T6c collect_report hier table (real w2 synth report)",
            [PY, os.path.join(ROOT, "pynq-golden-report/scripts/",
                              "collect_report.py"),
             "--hier-util", os.path.join(team,
                                         "utilization_hier_w2_feas.txt")],
            expect_rc=0,
            expect_in=["xc7z020", "| w2_top ", "| 490 |", "| 695 |",
                       "Synthesized"],
            cwd=tmp)
    else:
        print(f"SKIP T6 (team reports not found at {team})")

    # --- T7 dma_smoke dry-run ---------------------------------------
    run("T7 dma_smoke --dry-run prints the discipline",
        [PY, os.path.join(ROOT, "pynq-dma-coherence/scripts/",
                          "dma_smoke.py"), "--dry-run"],
        expect_rc=0,
        expect_in=["tx.flush()", "rx.invalidate()",
                   "sendchannel.transfer"])

    # --- T8 board-migration gates -----------------------------------
    mig = os.path.join(ROOT, "pynq-board-migration/scripts/",
                       "retarget_check.py")
    fxm = os.path.join(fx, "mig_zc702.xdc")
    run("T8a retarget port-compat PASS case (all ports re-constrained)",
        [PY, mig, "--old-xdc", fxm,
         "--new-xdc", os.path.join(fx, "mig_zc706.xdc")],
        expect_rc=0,
        expect_in=["[VERDICT] port-compat: PASS",
                   "pins relocated (expected on a board swap): 10",
                   "[IOSTD   ] clk: LVCMOS33 -> DIFF_SSTL15"],
        expect_not_in=["{led"])  # braced-bus regex must not ghost-match
    run("T8b retarget port-compat FAIL case (port lost in migration)",
        [PY, mig, "--old-xdc", fxm,
         "--new-xdc", os.path.join(fx, "mig_zc706_missing.xdc")],
        expect_rc=1,
        expect_in=["[VERDICT] port-compat: FAIL",
                   "[MISSING ] port uart_rx"])
    run("T8c retarget part-gate PASS (.hwh matches board)",
        [PY, mig, "--hwh", os.path.join(fx, "mig_overlay.hwh"),
         "--expect-part", "xc7z020clg484-1"],
        expect_rc=0, expect_in=["[VERDICT] part-gate: PASS"])
    run("T8d retarget part-gate FAIL (overlay exported for wrong part)",
        [PY, mig, "--hwh", os.path.join(fx, "mig_overlay.hwh"),
         "--expect-part", "xc7z045ffg900-2"],
        expect_rc=1, expect_in=["[VERDICT] part-gate: FAIL"])
    run("T8e retarget --boards verified part table incl. same-part trap",
        [PY, mig, "--boards"],
        expect_rc=0,
        expect_in=["xc7z045ffg900-2", "xc7z020clg400-1",
                   "IDENTICAL full part to pynq-z2",
                   "NOT interchangeable"])

    # ---------------- write the validation log ----------------------
    n_ok = sum(1 for r in results if r["ok"])
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [f"# VALIDATION LOG - offline tests of the skill package",
             "", f"- utc: {stamp}", f"- host: {os.uname().nodename
             if hasattr(os, 'uname') else os.environ.get('COMPUTERNAME')}",
             f"- python: {sys.version.split()[0]}",
             f"- result: **{n_ok}/{len(results)} passed**", "",
             "| # | test | verdict |", "|---|---|---|"]
    for i, r in enumerate(results, 1):
        lines.append(f"| {i} | {r['name']} | "
                     f"{'PASS' if r['ok'] else 'FAIL'} |")
    lines += ["", "## Details", ""]
    for i, r in enumerate(results, 1):
        lines.append(f"### {i}. {r['name']}  "
                     f"{'✅ PASS' if r['ok'] else '❌ FAIL'}")
        lines.append("")
        for a, b in r["checks"]:
            lines.append(f"- {a}: {'ok' if b else 'NO'}")
        if r.get("tail"):
            lines += ["", "```", r["tail"].strip()[-1200:], "```"]
        lines.append("")
    lines += ["## Not covered here (needs hardware, honestly pending)", "",
              "- overlay_doctor --live register smoke (needs board)",
              "- dma_smoke board run (needs DMA loopback overlay)",
              "- generated test board marker (needs board)", ""]
    log = os.path.join(HERE, "VALIDATION_LOG.md")
    with open(log, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n{n_ok}/{len(results)} passed -> {log}")
    sys.exit(0 if n_ok == len(results) else 1)


if __name__ == "__main__":
    main()
