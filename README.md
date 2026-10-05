# PUF Hardware Fingerprint Authentication System

Chip-intrinsic identity for drone swarm access control — no pre-shared keys, no key storage.

## Overview

This project implements a **Physically Unclonable Function (PUF)** based mutual authentication system on AMD Xilinx FPGA. Each chip's manufacturing process variations create a unique "hardware fingerprint" that cannot be cloned, copied, or software-emulated.

**Target platform**: AMD Zynq-7000 (ZC702 Evaluation Kit)
**Protocol**: Custom HF-IDA over MAVLink v2 on 433MHz telemetry radio
**Server**: PC (Python + pymavlink)

## Quick Start

### Prerequisites
- Vivado 2026.1 with Zynq-7000 device family installed
- ZC702 board with 12V power adapter
- micro-USB data cable (JTAG port)
- Python 3.10+ with pymavlink

### Build & Program (automated)

```powershell
# One command: build bitstream + program board + collect VIO readings
.\build\ps1\run_build.ps1 -Measure
```

### Manual (GUI)

See `docs/tutorials/w1_tutorial.md` for step-by-step Vivado GUI instructions.

## Repository Structure

```
puf-drone-auth/
├── src/
│   ├── rtl/               # Verilog RTL (A line)
│   │   ├── w1_ratio/       #   W1: dual-RO ratio measurement
│   │   ├── w2_array/       #   W2: 16-ring array + XOR-CRO
│   │   ├── w3_protocol/    #   W3: full protocol + multi-instance
│   │   └── common/         #   Shared: UART, CRC, MAVLink frame
│   ├── python/             # PC software (B line)
│   │   ├── server/         #   Authentication server
│   │   ├── evaluation/     #   ROC/EER/NIST/ML-attack
│   │   └── tools/          #   Debug utilities
│   └── constraints/        # Board XDC (W1 waiver in rtl/w1_ratio/)
├── sim/                    # Testbenches & simulation
├── build/                  # Vivado Tcl build scripts
├── board/                  # Board setup & wiring
├── data/                   # Test measurements
├── skill/                  # Reusable Skill package
├── report/                 # Competition report
└── docs/                   # Documentation
    ├── llm_log/            #   AI collaboration log
    ├── architecture/       #   System diagrams
    └── tutorials/          #   Beginner guides
```

## Key Results

| Metric | Value | Notes |
|--------|-------|-------|
| RO ratio resolution | 2^18 | Per measurement window |
| Authentication latency | ≤1s (target) | 5-frame bidirectional |
| EER | ≤5% (target) | Cross-chip discrimination |
| Resource usage | ~700 LUT | Including VIO debug core |

## Security Properties

- **No pre-shared keys** — identity is chip-intrinsic
- **Anti-replay** — challenges never repeat (CRP pool)
- **Anti-forgery** — requires physical possession of the chip
- **Mutual authentication** — terminal verifies base station identity
- **Known boundary** — relay attack mitigated by RTT checking (documented honestly)

## License

MIT

## Team

- **A** (RTL): FPGA hardware design
- **B** (Software): PC server, evaluation scripts
- **C** (Docs): Reports, evidence, project management

Competition: 2026 National Embedded Chip & System Design Contest — FPGA Innovation Track