# PUF Drone Authentication System

Hardware-rooted mutual authentication for drones using Ring Oscillator (RO) Physically Unclonable Functions (PUF) on AMD Zynq-7020 (ZC702).

## Overview

This project implements a complete PUF-based drone authentication system:
- **RTL** (Verilog-2001): 16-ring RO array, challenge decoder, Speck64/96 cipher, protocol FSM, power-on entropy sampling, key derivation
- **PC Server** (Python): HF-IDA mutual authentication protocol, CRP pool management, fuzzy matching, DoS protection
- **ML Attack Evaluation**: Logistic Regression baseline + RO ranking reconstruction attack

## Directory Structure

| Directory | Content |
|---|---|
| src/ | RTL (Verilog) + Python source code |
| sim/ | Testbenches (16 suites) + test vectors |
| tests/ | Python unit tests (109 tests) |
| scripts/ | CI regression + utility scripts |
| tools/ | Contract sync checker |
| build/tcl/ | Vivado build scripts |
| data/ | ML experiment results + CRP data |
| docs/ | Protocol contract, project design, process docs |
| report/ | Competition report (D13) |
| skill/ | Reusable skill scripts (D14) |
| external/ | Third-party references (MAVLink C library, PUF projects) |
| metrics/ | Competition metrics tables |

## Quick Start

```bash
# Run full CI (16 testbenches + 109 unit tests)
powershell -ExecutionPolicy Bypass -File scripts/ci_regression.ps1

# Run ML attack experiments
python -m src.python.evaluation.ml_attack --exp all --out data/ml_attack/ --seed 42

# Run threat PoC (replay/brute-force/injection)
python scripts/threat_poc.py --case all

# Start the authentication server REPL
python -m src.python.server.main
```

## Key Results

| Metric | Value |
|---|---|
| LUT utilization | 4,443 / 53,200 (8.35%) |
| Flip-flops | 6,545 / 106,400 (6.15%) |
| Effective entropy | ~44 bits (16-ring total ordering) |
| ML attack (LR baseline) | 99.9% accuracy at alpha=0 |
| ML attack (ranking recon) | 100% exact at 120 CRPs (flip=0.02) |

## Documentation

See [docs/DIRECTORY_STRUCTURE.md](docs/DIRECTORY_STRUCTURE.md) for the complete directory mapping to competition requirements.

## License

MIT License -- see LICENSE