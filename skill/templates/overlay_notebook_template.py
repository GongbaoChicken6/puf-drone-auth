# %% [markdown]
# # Overlay bring-up notebook (template)
#
# Generic first-contact notebook for ANY overlay: load -> static verify ->
# register smoke -> functional golden check -> metrics harvest.
# Copy into the overlay directory on the board (or open via Jupyter at
# http://<board-ip>:9090). Adapt the CONFIG cell; keep the ORDER.
#
# Part of the generic PYNQ skill package (MIT).

# %% CONFIG ---------------------------------------------------
BIT = "overlay.bit"            # this notebook's overlay
GOLDEN = None                  # "golden.csv" once you have a reference
DMA_LOOPBACK = False           # set True if design has an AXI DMA
REGSPEC = {                    # registers safe to poke (see skill docs)
    # "my_accel_0": {"registers": {"ctrl": "rw", "status": "r"}}
}

# %% 1 - static check (fast, catches packaging bugs) ---------
import subprocess, sys
r = subprocess.run(
    [sys.executable, "../pynq-overlay-load-verify/scripts/overlay_doctor.py",
     "--bit", BIT],
    capture_output=True, text=True)
print(r.stdout, r.stderr)
assert r.returncode == 0, "static check FAILED - fix before touching HW"

# %% 2 - load & inventory -------------------------------------
from pynq import Overlay
ol = Overlay(BIT)
print("ip_dict:")
for name, d in ol.ip_dict.items():
    print(f"  {name:<28} {d['type']:<40} @ {hex(d['phys_addr'])}")

# %% 3 - register smoke (only REGSPEC-listed registers) -------
for ip_name, spec in REGSPEC.items():
    ip = getattr(ol, ip_name)
    print(f"--- {ip_name} ---")
    print(ip.register_map)
    for reg, mode in spec["registers"].items():
        attr = getattr(ip.register_map, reg)
        if mode == "r":
            print(f"{reg} (RO) = {int(attr)}")
        else:
            cur = int(attr); test = cur ^ 1
            setattr(ip.register_map, reg, test)
            back = int(getattr(ip.register_map, reg))
            setattr(ip.register_map, reg, cur)   # restore
            status = "PASS" if back == test else "FAIL"
            print(f"{reg} write-readback: {status}")
            assert back == test

# %% 4 - functional check (ADAPT: run your kernel once) -------
# example shape for an HLS-style kernel behind AXI-Lite:
# ol.my_accel_0.register_map.CTRL.AP_START = 1
# ... wait for AP_DONE, read results ...
# then dump results for step 5:
# import numpy as np
# np.savetxt("out.csv", results, fmt="%.6f")

# %% 5 - golden compare (off-board-safe) ----------------------
if GOLDEN:
    r = subprocess.run(
        [sys.executable,
         "../pynq-golden-report/scripts/golden_compare.py",
         "--got", "out.csv", "--golden", GOLDEN, "--md-out", "cmp.md"],
        capture_output=True, text=True)
    print(r.stdout)
    assert r.returncode == 0, "golden compare FAILED"

# %% 6 - DMA loopback (if design has one) ---------------------
if DMA_LOOPBACK:
    r = subprocess.run(
        [sys.executable, "../pynq-dma-coherence/scripts/dma_smoke.py",
         "--bit", BIT, "--size-kb", "1024", "--iters", "20",
         "--md-out", "dma_bench.md"],
        capture_output=True, text=True)
    print(r.stdout)
    assert r.returncode == 0, "DMA smoke FAILED"

# %% [markdown]
# All asserts green -> the overlay is verifiably alive. Commit this
# notebook's outputs + cmp.md/dma_bench.md as the milestone evidence.
