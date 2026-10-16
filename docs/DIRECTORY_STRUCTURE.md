# Repository Directory Structure

> This document maps our project layout to the competition submission requirements (自主选题赛道 §3.3.5).
> All directory/file names use pure English (lowercase, digits, underscores, hyphers) per competition rules.

## Top-Level Layout

```
puf-drone-auth/
├── README.md              # Competition-facing project overview + quick start
├── LICENSE                # MIT License
├── src/                   # Source code (RTL + Python)
├── sim/                   # Testbenches + test vectors
├── tests/                 # Python unit tests
├── scripts/               # CI regression + utility scripts
├── tools/                 # Contract sync checker
├── build/                 # Build scripts + synthesis evidence
├── data/                  # ML experiment results + CRP data
├── docs/                  # Competition documentation
├── report/                # Design report (D13)
├── skill/                 # Reusable skill scripts (D14)
├── board/                 # Board hardware documentation
├── external/              # Third-party reference code
└── metrics/               # Competition metrics tables
```

## Competition Requirement Mapping

| Competition Requirement (§3.3.5) | Location | Status |
|---|---|---|
| 工程包：RTL 源码 | `src/rtl/` | ✅ 17 Verilog modules |
| 工程包：PS 侧软件 | `src/python/` | ✅ Server + evaluation + common |
| 工程包：仿真验证 | `sim/tb/` (16 TB) + `tests/` (109 tests) | ✅ CI all green |
| 工程包：综合报告 | `build/vivado_mcp/` (MCP synthesis) | ✅ 4,443 LUT / 8.35% |
| 工程包：构建脚本 | `build/tcl/` + `scripts/ci_regression.ps1` | ✅ |
| 工程包：可复现脚本 | `scripts/ci_regression.ps1` | ✅ Single command |
| 技能包 | `skill/` | 🔶 D14 (teammate) |
| 设计报告 | `report/` | 🔶 D13 (W5 task) |
| LLM 协作记录 | `report/llm_log/` + `docs/process/llm_log/` | ✅ W1-W4 sessions |
| 开源 | GitHub/Gitee push | ⬜ W6 |

## Directory Details

### `src/` — Source Code
```
src/
├── rtl/                        # Verilog-2001 RTL
│   ├── common/                 #   Shared modules (CRC, UART, Speck, FIFO...)
│   ├── w1_ratio/               #   W1: RO ring + divider
│   ├── w2_array/               #   W2: 16-ring array + decoder + entropy
│   └── w3_protocol/            #   W3: terminal FSM + top-level
└── python/                     # Python source
    ├── common/                 #   Speck cipher reference
    ├── evaluation/             #   PUF model + ML attack + analysis tools
    └── server/                 #   Auth server + protocol + CRP pool + HSM
```

### `sim/` — Simulation
```
sim/
├── tb/                         # 16 testbench suites
│   ├── tb_terminal_fsm.v       #   Protocol FSM (golden vectors)
│   ├── tb_puf_path.v           #   PUF pipeline (byte-level golden lock)
│   ├── tb_key_derive.v         #   Key derivation (T5-T15, GJ, GK)
│   ├── tb_ro_entropy.v         #   Entropy sampling (T10-T12)
│   ├── tb_w3top_keyloop.v      #   Top-level integration (T7, T13)
│   └── ... (11 more)
└── testvectors/                # Golden test vectors (.mem files)
```

### `docs/` — Documentation
```
docs/
├── protocol_contract.md        # Protocol specification (S1-S9) [DO NOT MOVE]
├── project_design.md           # Project design document [DO NOT MOVE]
├── process/                    # Development process records
│   ├── plans/                  #   Phase plans (W4_plan, W4_design, etc.)
│   ├── tutorials/              #   W1 tutorial
│   ├── w1_evidence/            #   W1 evidence files
│   ├── llm_log/                #   LLM collaboration log index
│   ├── HANDOFF_SUMMARY.md      #   Cross-session handoff ledger
│   └── crp_pool_sop.md         #   CRP pool operations SOP
└── dashboards/                 # HTML/SVG status dashboards
```

### `build/` — Build & Evidence
```
build/
├── tcl/                        # Vivado build scripts
│   ├── build_w3_board.tcl      #   Board build (all RTL sources)
│   └── synth_w3.tcl            #   Synthesis script
├── reviews/                    # Review evidence
│   └── w4/                     #   W4 review reports + CI logs
└── vivado_mcp/                 # MCP synthesis evidence
    ├── util_head.rpt           #   Resource utilization report
    ├── timing_head.rpt         #   Timing report
    └── vivado_mcp_synth_report.md #  Synthesis summary
```

### `data/` — Experiment Data
```
data/
├── ml_attack/                  # ML attack experiment results
│   ├── exp_a_results.json      #   Experiment A (arbiter + LR)
│   ├── exp_a_accuracy.png      #   Accuracy curve
│   ├── exp_b_results.json      #   Experiment B (ranking reconstruction)
│   └── exp_b_reconstruction.png #  Reconstruction rate curve
└── crp_datasets/               # CRP data (gitignored raw data)
```

### `report/` — Design Report (D13)
```
report/
├── README.md                   # Report skeleton
├── figures/                    # Report figures (to be populated)
└── llm_log/                    # LLM collaboration record
    └── w1_session.md           # W1 session log
```

### `skill/` — Reusable Skills (D14)
```
skill/
└── README.md                   # Skill descriptions (to be populated by teammate)
```

### `metrics/` — Competition Metrics (to be populated)
```
metrics/
└── README.md                   # Metrics table template
```

### `board/` — Hardware Documentation
```
board/
├── zc702/README.md             # ZC702 board setup
└── radio/README.md             # 433MHz radio module
```

### `build/reports/` — Synthesis Evidence (W1-W3)
Historical synthesis/timing reports (6 .rpt/.txt files from early feasibility runs).

### `build/ps1/` — PowerShell Build Helpers
Quick-build scripts for W2/W3 xvlog/xsim runs (6 scripts, superseded by ci_regression.ps1).

### `sim/results/` — Simulation Verification Scripts
Protocol checker + Speck test-vector verifier (2 Python scripts).

### `sim/scripts/` — Simulation Helper Scripts (placeholder)

### `data/bitstreams/` — Pre-generated Bitstreams
W1 RO ratio bitstreams (2 .bit files, gitignored except these two).

### `data/templates/` — CRP Template Data (placeholder, populated at enrollment)

### `data/w1_readings/` — W1 Board Readings (placeholder, populated in P6)

### `src/constraints/` — Additional Constraints Documentation

### `external/` — Third-Party References
```
external/
├── c_library_v2/               # MAVLink C library (reference)
├── fpga_puf/                   # FPGA PUF reference project
├── puf-esp32-auth/             # ESP32 PUF auth reference
└── PUF-lab/                    # PUF lab exercises reference
```

## Path Dependency Notes

The following files are referenced by code at runtime and **must not be moved**:
- `docs/protocol_contract.md` — referenced by `tools/check_contract_sync.py`
- `docs/project_design.md` — referenced by Python module docstrings
- `sim/testvectors/` — referenced by `sim/tb/ro_array_sim.v` ($readmemh)
- `src/`, `sim/`, `tests/`, `scripts/` — referenced by `scripts/ci_regression.ps1`