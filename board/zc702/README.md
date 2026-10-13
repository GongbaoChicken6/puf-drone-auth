# ZC702 Board Setup

## Power
- 12V DC adapter (included with kit)
- Power switch ON after connecting adapter

## USB Connection
- Three USB ports (per UG850) — do not mistake one for another:
  - **J17 (Mini-B)** = USB-UART bridge (CP2103GM). Powered from the PC's USB 5V, so the COM port enumerates even with the board off — used by factory BIST / Tera Term.
  - **U23 (Micro-B, on the Digilent JTAG module)** = PL JTAG — used by Vivado Hardware Manager for programming + VIO.
  - **J1 (Mini-B)** = PS USB 2.0 ULPI (OTG). Enumerates nothing without a PS program — the easiest port to plug into by mistake.
- Use a **data cable** (not charge-only)

## Boot Mode (SW16)
- PL-only bitstream via JTAG: **any setting works**
- Default (all OFF) is fine for W1

## FMC
- Do NOT hot-plug FMC cards. Power off first.

## Reference
- [UG850](https://docs.amd.com/r/en-US/ug850-zc702-eval-board) — Official User Guide
