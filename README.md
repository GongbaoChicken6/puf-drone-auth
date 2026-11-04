**English** | [中文](./README_zh.md)

# puf-drone-auth — PUF-Based Hardware Fingerprint Mutual Authentication for UAV Fleets

> **Repository**: https://github.com/GongbaoChicken6/puf-drone-auth (private during scoring; to be made public after the competition)

AMD FPGA Innovation Design Track · Verified on 2× AMD ZC706 (xc7z045ffg900-2) · MIT License

A UAV identity authentication system based on a 16-ring ring-oscillator PUF (RO-PUF): silicon manufacturing variation IS the hardware fingerprint. **No pre-stored keys** — the device key is derived from the PUF at power-on. Mutual authentication via HF-IDA six-message protocol; dual-threshold (6/16) decision with auto-rechallenge in the indeterminate zone; Speck64/96 all-hardware response; 433 MHz wireless link tested on real hardware.

## Key Results (see metrics/metrics.csv and report/design_report.pdf)

| Metric | Value |
|---|---|
| Cross-board fingerprint deviation (mean HD) | 145.8/256 = **57.0%** (same-chip retest ≈ 0) |
| Spoof terminals | **All rejected** (cross-board REJECT HD≈140, no CONFIRM) |
| Replay attacks | Old messages rejected instantly |
| Wired auth latency | 23–32 ms; wireless (433 MHz) full-flow 57 ms; spoof detection 36 ms |
| FPGA resource / timing (ZC706 Routed) | LUT 4375 (2.00%), WNS +1.873 ns @ 100 MHz |

## Directory Mapping (Guide §3.3.5.4 → this package)

The recommended structure is non-mandatory; teams using a different organization must provide a mapping table in README.md. The three recommended items (README.md / src / sim) plus skill/ (§3.3.5.2) and report/ (§3.3.5.3) are placed under their canonical names. Remaining directories follow the five work-package elements of §3.3.5.1. Full mapping:

| Package entry | Guide reference | Contents |
|---|---|---|
| README.md | §3.3.5.4 · README.md | This file (intro + repro steps + directory mapping) |
| README_zh.md | — | Full Chinese version |
| src/ | §3.3.5.4 · src/ | RTL + constraints (src/rtl, incl. XDC), Python base station (src/python) |
| sim/ | §3.3.5.4 · sim/ | 18 testbenches (sim/tb) + test vectors + verification results (sim/results, incl. CI 18/18); standalone simulation entry: build/ps1/ |
| build/ | §3.3.5.1 · board project / synth-impl reports / build scripts | 2 production bitstreams, Vivado synth & program tcl, **ZC706 Routed timing/utilization reports**, w1→w2→w3_synth evolution comparison |
| scripts/ | §3.3.5.1 · reproducible build scripts / run scripts | Full CI regression gate (ci_regression.ps1), vector generation, threat verification |
| tests/ | §3.3.5.1 · simulation or verification results | Full pytest suite (111 passed, see metrics/logs/1101_pytest_all.txt) |
| tools/ | §3.3.5.1 · run scripts | Metric analysis (puf_metrics/puf_sac), contract sync check, HC-12 configuration |
| web/ | §3.3.5.1 · host application (PS-side software) | PC base-station bridge + demo console frontend (offline self-contained dist) |
| data/ | §3.3.5.1 · measured output & reference comparison data | Registration templates / challenge pools / device keys (public demo keys) / ML experiment data / bitstream hash anchor / clone-attack root-cause archive |
| metrics/ | §3.2.5-style metrics directory (voluntary) | metrics.csv (sole authoritative summary) + logs/ (22 raw logs) |
| docs/ | §3.3.5.1 · design documents | System design (project_design.md), protocol contract (protocol_contract.md), principle visualization (visualization.html) |
| skill/ | §3.3.5.2 · skill package | 5 reusable PYNQ skills + pitfall list + workflows (scope/usage/failure conditions in its README) |
| report/ | §3.3.5.3 · design report | design_report.pdf / .docx / figures (23 PNGs named by figure number) / llm_log (AI collaboration record) |
| LICENSE | §3.3.3.3 · open-source license | MIT |
| requirements.txt | §3.3.5.1 · dependency manifest | PC-side Python dependencies |

## Reproduction Steps

**Environment**: Vivado 2026.1, Python 3.13, two AMD ZC706 boards (xc7z045ffg900-2), each with USB JTAG and USB-TTL serial.
> Note: `$vivado` in scripts/ci_regression.ps1 and build/ps1/*.ps1 is hardcoded to `D:\vivado\2026.1\Vivado\bin` — modify for your machine.

1. **Dependencies**: `pip install -r requirements.txt`
2. **Synthesis/Implementation rebuild**: Vivado batch → `build/tcl/build_w3_board.tcl` (terminal 1) and `build/tcl/build_w3_board_seed2.tcl` (terminal 2 · dedicated layout variant). All sources and constraints from `src/rtl`; clk_wiz IP generated on-the-fly. Compare outputs against the bundled Routed reports in `build/board_zc706*/`.
3. **Simulation**: `build/ps1/run_xvlog_w3.ps1` → `build/ps1/run_xsim_w3.ps1`; static pass records: `metrics/logs/1101_ci_regression_full.txt` (18/18 PASS) and `sim/results/`.
4. **PC-side**: `pytest` (111 passed: metrics/logs/1101_pytest_all.txt); full gate `scripts/ci_regression.ps1` (includes bitstream hash anchor verification).
5. **On-board demo**: `vivado -mode batch -source build/tcl/program_zc706.tcl -tclargs <bit> [jtag_sn]` → launch web base station:
   ```
   python web/bridge/web_bridge.py --repo-root . --data-dir <a fresh empty directory> --loopback --serial-port COM<x> --serial-baud 115200 --port 8642
   ```
   **⚠ MUST pass --data-dir pointing to a fresh empty directory**: the default points to the bundled data/, which triggers an irreversible stale-terminal cleanup that destroys measured templates/challenge pools. Open http://127.0.0.1:8642/console.html ; press SW13 (reset) → SW7 (auth) on the board: green LED = PASS, red LED = REJECT (see report/design_report.pdf demo chapter).
6. **Measured-data comparison**: every row in metrics.csv points to its raw log in metrics/logs/; step-by-step board procedures in report/design_report.pdf.

## Notes

- **External reference code**: external/ (c_library_v2, fpga_puf, puf-esp32-auth, PUF-lab, pinned commits) is not bundled; run scripts/setup_external.ps1 to reconstruct — sources credited in file headers.
- **data/device_keys**: tid 1/2 use the public demo test key (0001020308090a0b10111213); others are derived keys for our demo terminals — evaluators registering their own boards will generate their own keys.
- **metrics/logs**: filenames anglicized; content preserved in original Chinese.
- **Open source**: this work is open-sourced under MIT (LICENSE); repository URL to be announced upon submission.
- **Final-round poster**: one-page English PPT poster per AMD template, submitted separately (not in this package).