# Constraints

Actual XDC constraint files are located alongside their RTL sources:

- `src/rtl/w3_protocol/w3_top_zc706.xdc` — ZC706 final pin & timing constraints (production)
- `src/rtl/w3_protocol/w3_top.xdc` — simulation-only constraints (no pins)
- `src/rtl/w2_array/w2_waiver.xdc` — W2 waiver constraints
- `src/rtl/w1_ratio/w1_ro_waiver.xdc` — W1 waiver constraints

Note: Early development used ZC702/EGO1/Basys3 boards; those constraint files are kept in git history only.
