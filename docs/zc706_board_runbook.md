# ZC706 Board Operation Runbook

## Overview
- Target: 2x AMD Xilinx ZC706 (xc7z045ffg900-2), each with USB JTAG + USB-TTL serial
- Terminal 1 (production layout): JTAG SN 210251A0195C
- Terminal 2 (seed2 variant layout): JTAG SN 210251A04F2C
- Wireless: 433 MHz HC-12 modules (115200 baud)
- Base station: PC (Python) via web bridge

## 1. Power-on Check
1. SW4 = 01 (on-board USB JTAG), SW11 = 00000 (JTAG boot mode)
2. Power on. Check DS35 (heartbeat LED, ~0.75 Hz slow blink). Fast blink (~3 Hz) = entropy fault: do NOT proceed.
3. Verify SW12: Terminal 1 = 0001, Terminal 2 = 0010

## 2. Program Bitstream
```bash
vivado -mode batch -source build/tcl/program_zc706.tcl -tclargs <bit> [jtag_serial]
```
- Terminal 1: `build/board_zc706/w3_top_zc706.bit`
- Terminal 2: `build/board_zc706_seed2/w3_top_zc706_seed2.bit`
- Bitstream is volatile: reprogram after each power cycle

## 3. Start Base Station
```bash
python web/bridge/web_bridge.py --repo-root . --data-dir <fresh_empty_dir> --loopback --serial-port COM<x> --serial-baud 115200 --port 8642
```
**WARNING**: Always pass --data-dir pointing to a fresh empty directory. The default points to data/ and will irreversibly delete measured templates.

Open http://127.0.0.1:8642/console.html

## 4. Authentication (per round)
1. Press SW13 (reset) — clears any BLOCKED state
2. Press SW7 (auth trigger)
3. Observe:
   - DS9 (busy) lights 1-2s = PUF measuring
   - DS8 green steady = PASS
   - DS10 red = REJECT (impostor)
   - DS8+DS10 both = BLOCKED (needs SW13 reset)

## 5. Test Scenarios
| Scenario | Board | SW12 | Expected |
|---|---|---|---|
| Normal auth (T1) | Terminal 1 | 0001 | PASS, HD=0 |
| Spoof attack | Terminal 2 | 0001 (impersonate T1) | REJECT, HD~140 |
| Normal auth (T2) | Terminal 2 | 0010 | PASS, HD=0 |
| Replay | (web console, S3 button) | - | REPLAY rejected |

## 6. Troubleshooting
| Symptom | Cause | Fix |
|---|---|---|
| SW7 no response | Bridge not running / heartbeat fast | Check bridge; entropy fault = reprogram |
| DS8+DS10 both lit | BLOCKED state | Press SW13 |
| Web console no frames | Wrong COM port | Check port, restart bridge |
| Pool exhausted | Too many auth rounds | Restart bridge (reloads pool) |
