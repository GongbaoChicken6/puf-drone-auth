# ZC702 Board Setup

## Power
- 12V DC adapter (included with kit)
- Power switch ON after connecting adapter

## USB Connection
- Two USB ports with different roles: **J17 = USB-UART (CP210x serial, used by the factory BIST/Tera Term)**, the other = **JTAG (used by Vivado Hardware Manager for programming + VIO)**. For Vivado, plug the JTAG port; the connector type per port varies between docs, so go by the silkscreen. + IOSTANDARD
- Use a **data cable** (not charge-only)

## Boot Mode (SW16)
- PL-only bitstream via JTAG: **any setting works**
- Default (all OFF) is fine for W1

## FMC
- Do NOT hot-plug FMC cards. Power off first.

## Reference
- [UG850](https://docs.amd.com/r/en-US/ug850-zc702-eval-board) — Official User Guide
