# W1 AI Collaboration Log

## 2026-09-25

### Task
Generate W1 dual-RO ratio measurement RTL for ZC702 (xc7z020clg484-1).

### AI Contribution
- Wrote all RTL modules (ro_ring, ro_div, ro_ratio_top) following team coding standards
- Designed the measurement architecture (ratio-based, pinless, VIO readout)
- Created Vivado batch build scripts (build_w1.tcl, measure_w1.tcl)
- Identified and fixed Nyquist aliasing issue (div_b same-rate sampling)
- Ran Artix-7 proxy synthesis to validate flow end-to-end

### Human Contribution
- Board bring-up (power, USB, Vivado installation)
- Device family installation (Zynq-7000)
- Physical verification on ZC702 (pending)

### AI Tool Usage
- Prompt: "Write a dual ring-oscillator ratio measurement design for ZC702, pinless, using VIO for readout"
- Iterations: 3 (initial → aliasing fix → UI precision update)
- Key human correction: caught ratio direction error (fA/fB vs fB/fA)
