# VALIDATION LOG - offline tests of the skill package

- utc: 2026-10-24T16:00:24+00:00
- host: <host>
- python: 3.12.10
- result: **18/18 passed**

| # | test | verdict |
|---|---|---|
| 1 | T1 overlay_doctor static PASS case | PASS |
| 2 | T2 overlay_doctor static missing-hwh FAIL case | PASS |
| 3 | T3a gen_driver_stub generates driver+tests | PASS |
| 4 | T3b driver content (base/regs/op/span) | PASS |
| 5 | T4 generated tests via pytest (FakeMMIO logic) | PASS |
| 6 | T5a golden_compare CSV PASS case | PASS |
| 7 | T5b golden_compare CSV FAIL case (cell out of tolerance) | PASS |
| 8 | T5c golden_compare row-count mismatch FAILs | PASS |
| 9 | T5d golden_compare binary PASS case | PASS |
| 10 | T6a collect_report real utilization (w1) | PASS |
| 11 | T6b w1 routed-state signoff labeling | PASS |
| 12 | T6c collect_report hier table (real w2 synth report) | PASS |
| 13 | T7 dma_smoke --dry-run prints the discipline | PASS |
| 14 | T8a retarget port-compat PASS case (all ports re-constrained) | PASS |
| 15 | T8b retarget port-compat FAIL case (port lost in migration) | PASS |
| 16 | T8c retarget part-gate PASS (.hwh matches board) | PASS |
| 17 | T8d retarget part-gate FAIL (overlay exported for wrong part) | PASS |
| 18 | T8e retarget --boards verified part table incl. same-part trap | PASS |

## Details

### 1. T1 overlay_doctor static PASS case  ✅ PASS

- exit=0: ok
- contains 'speck_cipher_0': ok
- contains 'axi_gpio_0': ok
- contains '0x43C00000': ok
- contains 'regs=4': ok
- contains '[VERDICT] static check: PASS': ok

```
[WARN ] .bit and .hwh timestamps differ by 14597 min - if they were not exported in the same Vivado run, addresses may not match the bitstream (classic wrong-register-map bug)

2 IP(s) parsed from demo_overlay.hwh:
  - speck_cipher_0                   base=0x43C00000   type=xilinx.com:user:speck_cipher:1.0 params=2 regs=4
  - axi_gpio_0                       base=0x41200000   type=xilinx.com:ip:axi_gpio:2.0 params=2 regs=0

[VERDICT] static check: PASS
```

### 2. T2 overlay_doctor static missing-hwh FAIL case  ✅ PASS

- exit=1: ok
- contains 'no .hwh sidecar': ok
- contains '[VERDICT] static check: FAIL': ok

```
[FAIL ] no .hwh sidecar found next to the .bit - pynq.Overlay will fail or expose an empty ip_dict. Re-export the overlay with both files from the same Vivado run.

0 IP(s) parsed from orphan.bit:

[VERDICT] static check: FAIL
```

### 3. T3a gen_driver_stub generates driver+tests  ✅ PASS

- exit=0: ok
- contains '[GEN ] E:\\mathmodelworkspace\\skilldev\\pynq-skill\\tests\\_tmp\\gen\\driver_speck_cipher_0.py': ok
- contains '[GEN ] E:\\mathmodelworkspace\\skilldev\\pynq-skill\\tests\\_tmp\\gen\\test_speck_cipher_0.py': ok

```
[GEN ] E:\mathmodelworkspace\skilldev\pynq-skill\tests\_tmp\gen\driver_speck_cipher_0.py
[GEN ] E:\mathmodelworkspace\skilldev\pynq-skill\tests\_tmp\gen\test_speck_cipher_0.py
[DONE] next: pytest E:\mathmodelworkspace\skilldev\pynq-skill\tests\_tmp\gen\test_speck_cipher_0.py
```

### 4. T3b driver content (base/regs/op/span)  ✅ PASS

- baked base+span+methods: ok

### 5. T4 generated tests via pytest (FakeMMIO logic)  ✅ PASS

- exit=0: ok
- contains 'passed': ok
- NOT contains 'failed': ok

```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: E:\mathmodelworkspace\skilldev\pynq-skill
plugins: asyncio-1.4.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 5 items

tests\_tmp\gen\test_speck_cipher_0.py ....s                              [100%]

============================== warnings summary ===============================
tests\_tmp\gen\test_speck_cipher_0.py:64
  E:\mathmodelworkspace\skilldev\pynq-skill\tests\_tmp\gen\test_speck_cipher_0.py:64: PytestUnknownMarkWarning: Unknown pytest.mark.board - is this a typo?  You can register custom marks to avoid this warning - for details, see https://docs.pytest.org/en/stable/how-to/mark.html
    @pytest.mark.board

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=================== 4 passed, 1 skipped, 1 warning in 0.04s ===================
```

### 6. T5a golden_compare CSV PASS case  ✅ PASS

- exit=0: ok
- contains '[VERDICT] PASS': ok

```
cells compared : 12
cells failed   : 0
shape mismatch : none
worst |err|    : 0.00012000000000078614
[VERDICT] PASS
```

### 7. T5b golden_compare CSV FAIL case (cell out of tolerance)  ✅ PASS

- exit=1: ok
- contains '[VERDICT] FAIL': ok
- contains 'cells failed   : 1': ok

```
cells compared : 12
cells failed   : 1
shape mismatch : none
worst |err|    : 0.5122749999999998
[VERDICT] FAIL
```

### 8. T5c golden_compare row-count mismatch FAILs  ✅ PASS

- exit=1: ok
- contains 'shape mismatch': ok

```
cells compared : 0
cells failed   : 0
shape mismatch : rows: got 0, golden 3
worst |err|    : None
[VERDICT] FAIL
```

### 9. T5d golden_compare binary PASS case  ✅ PASS

- exit=0: ok
- contains '[VERDICT] PASS': ok

```
cells compared : 8
cells failed   : 0
shape mismatch : none
worst |err|    : 7.152557373046875e-07
[VERDICT] PASS
```

### 10. T6a collect_report real utilization (w1)  ✅ PASS

- exit=0: ok
- contains '| LUT | 699 |': ok
- contains '| FF | 1263 |': ok
- contains 'ro_ratio_top': ok
- contains 'xc7a35t': ok

```
# FPGA metrics auto-report

- utc: 2026-10-24T16:00:23+00:00
- design: `ro_ratio_top`
- device: xc7a35tcsg324-1

## Utilization

| Resource | Used | Available | Util % |
|---|---|---|---|
| LUT | 699 | 20800 | 3.36 |
| FF | 1263 | 41600 | 3.04 |
| BRAM | 0 | 50 | 0.0 |
| DSP | 0 | 90 | 0.0 |
| IO | 0 | 210 | 0.0 |

_source: utilization_w1.txt (state: Routed)_

## Timing (global)

| WNS (ns) | TNS (ns) | WHS (ns) | THS (ns) | WPWS (ns) |
|---|---|---|---|---|
| 26.945 | 0.0 | 0.076 | 0.0 | 15.25 |

Verdict: **TIMING MET (routed)**

## Timing per clock

| Clock | Period (ns) | WNS (ns) | TNS (ns) | WHS (ns) | THS (ns) |
|---|---|---|---|---|---|
| dbg_hub/inst/BSCANID.u_xsdbm_id/SWITCH_N_EXT_BSCAN.bscan_inst/SERIES7_BSCAN.bscan_inst/TCK | - | 26.945 | 0.0 | 0.076 | 0.0 |
```

### 11. T6b w1 routed-state signoff labeling  ✅ PASS

- routed -> signoff label present: ok

### 12. T6c collect_report hier table (real w2 synth report)  ✅ PASS

- exit=0: ok
- contains 'xc7z020': ok
- contains '| w2_top ': ok
- contains '| 490 |': ok
- contains '| 695 |': ok
- contains 'Synthesized': ok

```
# FPGA metrics auto-report

- utc: 2026-10-24T16:00:23+00:00
- design: `w2_top`
- device: xc7z020clg484-1


## Utilization by hierarchy (top modules)

| Instance | Module | LUT | FF | BRAM | DSP |
|---|---|---|---|---|---|
| w2_top | (top) | 490 | 695 | 0 | 0 |
| (w2_top) | (top) | 4 | 52 | 0 | 0 |
| u_array | ro_array | 397 | 506 | 0 | 0 |
| (u_array) | ro_array | 189 | 314 | 0 | 0 |
| u_cdc_div | xpm_cdc_array_single | 0 | 64 | 0 | 0 |
| u_decode | challenge_decode | 81 | 137 | 0 | 0 |

_source: utilization_hier_w2_feas.txt (state: Synthesized)_
```

### 13. T7 dma_smoke --dry-run prints the discipline  ✅ PASS

- exit=0: ok
- contains 'tx.flush()': ok
- contains 'rx.invalidate()': ok
- contains 'sendchannel.transfer': ok

```
planned sequence (on-board run does exactly this):

  from pynq import Overlay, allocate
  import numpy as np

  ol = Overlay("<bit>")
  dma = ol.axi_dma_0                       # name from ol.ip_dict

  for i in range(20):
      with allocate(shape=(262144,), dtype=np.uint32) as tx, \
           allocate(shape=(262144,), dtype=np.uint32) as rx:
          tx[:] = np.arange(262144, dtype=np.uint32) + i
          tx.flush()                       # PS cache -> DDR  (BEFORE send)
          dma.sendchannel.transfer(tx)     # MM2S
          dma.recvchannel.transfer(rx)     # S2MM
          dma.sendchannel.wait()
          dma.recvchannel.wait()
          rx.invalidate()                  # DDR -> PS cache (AFTER wait,
                                           #  BEFORE first read)
          assert (rx == tx).all()          # loopback golden check
```

### 14. T8a retarget port-compat PASS case (all ports re-constrained)  ✅ PASS

- exit=0: ok
- contains '[VERDICT] port-compat: PASS': ok
- contains 'pins relocated (expected on a board swap): 10': ok
- contains '[IOSTD   ] clk: LVCMOS33 -> DIFF_SSTL15': ok
- NOT contains '{led': ok

```
[PORT-COMPAT] old XDC: 10 constrained tokens (6 ports) | new XDC: 10 tokens (6 ports)
[PORT-COMPAT] pins relocated (expected on a board swap): 10
[IOSTD   ] clk: LVCMOS33 -> DIFF_SSTL15 (voltage class changed - verify bank)
[IOSTD   ] led[0]: LVCMOS33 -> LVCMOS15 (voltage class changed - verify bank)
[IOSTD   ] led[1]: LVCMOS33 -> LVCMOS15 (voltage class changed - verify bank)
[IOSTD   ] led[2]: LVCMOS33 -> LVCMOS15 (voltage class changed - verify bank)
[IOSTD   ] led[3]: LVCMOS33 -> LVCMOS15 (voltage class changed - verify bank)
[IOSTD   ] rst_n: LVCMOS33 -> LVCMOS18 (voltage class changed - verify bank)
[IOSTD   ] uart_rx: LVCMOS33 -> LVCMOS18 (voltage class changed - verify bank)
[IOSTD   ] uart_tx: LVCMOS33 -> LVCMOS18 (voltage class changed - verify bank)
[VERDICT] port-compat: PASS
```

### 15. T8b retarget port-compat FAIL case (port lost in migration)  ✅ PASS

- exit=1: ok
- contains '[VERDICT] port-compat: FAIL': ok
- contains '[MISSING ] port uart_rx': ok

```
[PORT-COMPAT] old XDC: 10 constrained tokens (6 ports) | new XDC: 9 tokens (5 ports)
[PORT-COMPAT] pins relocated (expected on a board swap): 9
[IOSTD   ] clk: LVCMOS33 -> DIFF_SSTL15 (voltage class changed - verify bank)
[IOSTD   ] led[0]: LVCMOS33 -> LVCMOS15 (voltage class changed - verify bank)
[IOSTD   ] led[1]: LVCMOS33 -> LVCMOS15 (voltage class changed - verify bank)
[IOSTD   ] led[2]: LVCMOS33 -> LVCMOS15 (voltage class changed - verify bank)
[IOSTD   ] led[3]: LVCMOS33 -> LVCMOS15 (voltage class changed - verify bank)
[IOSTD   ] rst_n: LVCMOS33 -> LVCMOS18 (voltage class changed - verify bank)
[IOSTD   ] uart_tx: LVCMOS33 -> LVCMOS18 (voltage class changed - verify bank)
[MISSING ] port uart_rx present in old XDC, unconstrained in new XDC
[VERDICT] port-compat: FAIL (1 missing port(s), 0 clock(s))
```

### 16. T8c retarget part-gate PASS (.hwh matches board)  ✅ PASS

- exit=0: ok
- contains '[VERDICT] part-gate: PASS': ok

```
[PART-GATE] .hwh says 'xc7z020clg484-1' | expected 'xc7z020clg484-1'
[VERDICT] part-gate: PASS
```

### 17. T8d retarget part-gate FAIL (overlay exported for wrong part)  ✅ PASS

- exit=1: ok
- contains '[VERDICT] part-gate: FAIL': ok

```
[PART-GATE] .hwh says 'xc7z020clg484-1' | expected 'xc7z045ffg900-2'
[VERDICT] part-gate: FAIL (exported for the wrong part/project)
```

### 18. T8e retarget --boards verified part table incl. same-part trap  ✅ PASS

- exit=0: ok
- contains 'xc7z045ffg900-2': ok
- contains 'xc7z020clg400-1': ok
- contains 'IDENTICAL full part to pynq-z2': ok
- contains 'NOT interchangeable': ok

```
[BOARDS] verified part table for --expect-part / G2 retarget:
  pynq-z2  xc7z020clg400-1    TRAP: same SILICON as zc702 (7z020) but CLG400 package - XDC/pins NOT interchangeable (AMD AUP / TUL PYNQ-Z2 specs)
  zc702    xc7z020clg484-1    source: team's own Vivado 2026.1 synthesis runs (UG850 board)
  zc706    xc7z045ffg900-2    source: UG954 (XC7Z045-2FFG900) + team-verified: get_parts and a real synthesis smoke on this part passed in our Vivado 2026.1 (2026-10-24, pre-board gate)
  zybo-z7-20 xc7z020clg400-1    TRAP: IDENTICAL full part to pynq-z2 but a different board - pins, PS preset, image all differ (Digilent reference)
```

## Not covered here (needs hardware, honestly pending)

- overlay_doctor --live register smoke (needs board)
- dma_smoke board run (needs DMA loopback overlay)
- generated test board marker (needs board)
