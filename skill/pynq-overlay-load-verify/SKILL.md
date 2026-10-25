---
name: pynq-overlay-load-verify
description: Load and verify any PYNQ overlay on Zynq boards - static .bit/.hwh integrity check (runs on any PC, no board), then on-board ip_dict/register_map smoke with write-readback. Catches the classic "overlay loads but registers are wrong/missing" failures before they eat board time. Static parser and report generation validated offline on Vivado 2026.1 exports; live mode follows the same flow the team used on ZC702.
license: MIT
compatibility: Static mode: Python 3.8+ only. Live mode: PYNQ image (2.x/3.x) on Zynq-7000 or UltraScale+; overlay exported from Vivado 2017.3+ with .hwh.
metadata:
  author: fpgachina26 team (skill package)
  version: "1.0.0"
---

# PYNQ Overlay Load & Verify

Turn "I copied the overlay to the board and something doesn't work" into a
checklist with hard pass/fail gates. Two stages: an OFF-board static check
that catches packaging errors in seconds, and an ON-board register smoke
test that proves the AXI-Lite path before any functional test.

## When to use

- Before any board session: run static check on the .bit/.hwh you are
  about to upload (works on your PC, in CI, anywhere).
- After loading an overlay on the board, before writing functional code.
- After regenerating an overlay in Vivado, to diff what changed (IP list,
  base addresses) against the previous export.
- When a teammate's overlay "doesn't load" or "has no attributes".

Not for: non-PYNQ bare-metal flows; UltraScale+ overlays exported without
.hwh (older .tcl-metadata flow) - the static check will flag this.

## Workflow

### 1. Static check (PC, seconds)

```bash
python scripts/overlay_doctor.py --overlay-dir <dir-with-.bit+.hwh>
# or point at the bit file directly:
python scripts/overlay_doctor.py --bit overlay.bit --md-out doctor.md
```

Read the output: IP list with base addresses, warnings, verdict.

### 2. Write a register spec (only for live mode)

Which registers may be poked, e.g. `regspec.json`:

```json
{ "ips": {
    "my_accel_0": { "xor_mode": true,
      "registers": { "ctrl": "rw", "status": "r", "result_lo": "r" } }
} }
```

Only list registers whose momentary bit-flip is safe (no start bits that
fire side effects, unless xor_mode=false and you give a safe value).

### 3. Live smoke (board)

```bash
# on the board, inside the overlay directory
python overlay_doctor.py --bit overlay.bit --live --regspec regspec.json
```

## Verification (hard gates)

Static PASS requires ALL of:

- exactly one .bit, with a .hwh sidecar next to it
- .hwh parses as XML and yields >= 1 IP with a base address
- .bit/.hwh timestamps within 1 h of each other (else WARN, human decides)

Live PASS requires ALL of:

- Overlay(...) loads without exception
- every spec'd IP present in ip_dict and exposes register_map
- every "r" register reads back an int
- every "rw" register: write test value -> readback equal -> restored

A clean overlay download is NOT proof - only the write-readback is.

## Never do

- Never claim an overlay works before the register smoke passes.
- Never hand-edit .hwh fields to "fix" a load failure; go back to the
  Vivado export.
- Never smoke-test a register that starts DMA/erases flash with a random
  XOR value; mark it "r" or give an explicit safe value.
- Never debug functional failures while static check is red.

## Common errors

| Symptom | Trigger | Fix |
|---|---|---|
| `Overlay(...)` raises HWH parse error | .hwh missing/corrupt, or .bit and .hwh from different Vivado runs | re-export both in one run; compare timestamps |
| overlay loads, `ol.<ip>` missing | .hwh has different IP name (renamed in BD) | static-check output lists real names; use those |
| `register_map` empty / AttributeError | IP has no AXI-Lite interface, or legacy .tcl metadata | check BD has AXI-Lite + interrupt regs; export with .hwh |
| smoke write-readback fails on all regs | wrong base address (stale .hwh), PL clock not configured, or address in PS-PL GP aperture mismatch | re-run static check; verify FCLK/reset in BD; check GP port enable |
| smoke fails on ONE reg only | register is actually read-only / write-1-to-clear despite docs | fix contract access field; verify in Vivado address editor |
| load hangs | PL not clocked or bitstream for another part | check board LED (done), FCLK_CLK0 config, part matches board |

## Resources

- `scripts/overlay_doctor.py` - the checker itself (stdlib only)
- `references/register-map-paradigm.md` - register_map vs MMIO idioms
- Team evidence: static mode validated on real Vivado 2026.1 .hwh exports
  (ZC702/PYNQ-Z2-class designs) in `tests/`; live mode follows the flow
  used during ZC702 bring-up.
