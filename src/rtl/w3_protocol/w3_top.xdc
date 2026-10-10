# w3_top.xdc -- ZC702 (xc7z020clg484-1) Constraints
# ⚠ ALL PINS ARE COMMENTED OUT -- uncomment and verify against UG850 + master XDC
# Reference: github.com/rithan2001/Xilinx-Zynq-7000-SoC-ZC702 master_constraints.xdc

# === CLOCK ===
# ZC702 PL clock = 200MHz DIFFERENTIAL on D18(SYSCLK_P)/C19(SYSCLK_N), LVDS_25
# Design expects 100MHz single-ended → need IBUFDS + MMCM/BUFR divide, or change
# w3_top to use FREQ_HZ=200_000_000 with differential input ports
# Option A (recommended): change w3_top to have clk_p/clk_n ports + IBUFDS + MMCM
# Option B (quick): use an FMC pin with 100MHz oscillator (if available)

# === RESET ===
# ZC702 CPU_RESET (SRST_B/POR_B) is PS-DOMAIN, NOT accessible from PL!
# Use PL push buttons instead:
# set_property PACKAGE_PIN G19 [get_ports sys_rst_n]   ;# GPIO_SW_N, LVCMOS25

# === UART (to radio via FMC LPC or PMOD) ===
# ZC702 USB-UART is on PS MIO, NOT PL. Radio must connect via FMC/PMOD.
# LVCMOS25 (not LVCMOS15!) for PL I/O banks on ZC702

# === LEDs (ZC702 GPIO LEDs) ===
# set_property PACKAGE_PIN Y11 [get_ports led_busy]      ;# DS9
# set_property PACKAGE_PIN T22 [get_ports led_heartbeat]  ;# DS10
# set_property PACKAGE_PIN W21 [get_ports {led_result[0]}] ;# DS11
# set_property PACKAGE_PIN U21 [get_ports {led_result[1]}] ;# DS12

# === Auth button (currently NOT in this XDC -- w3_top.v:33 input wire auth_btn) ===
# Without a pin, auth_btn floats and 2.5 test-3 cannot run. Pick a PL push button from UG850:
# set_property PACKAGE_PIN <GPIO_SW_x> [get_ports auth_btn]   ;# LVCMOS25

# === DIP Switches (only 2 available on PL!) ===
# ZC702 has only GPIO_DIP_SW0(W6) and GPIO_DIP_SW1(W7) on PL.
# For 8-bit terminal_id: use constants, FMC pins, or PMOD.
# set_property PACKAGE_PIN W6 [get_ports {term_id_sw[0]}]
# set_property PACKAGE_PIN W7 [get_ports {term_id_sw[1]}]
# term_id_sw[7:2] = tie to constants in w3_top or use external DIP on FMC

# === Timing ===
# Must add create_clock for timing analysis (currently zero constraints!)
# create_clock -period 10.000 -name sys_clk [get_ports sys_clk]  ;# 100MHz
# set_false_path -from [get_ports sys_rst_n] -to [get_pins -filter {NAME =~ *rst_ff1_reg/PRE} -of_objects [get_cells rst_ff1_reg]]
