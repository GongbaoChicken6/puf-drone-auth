# w3_top.xdc -- ZC702 (xc7z020clg484-1) 引脚/时钟约束底稿
# ⚠ 所有 set_property 仍被注释 —— 请按保姆教程 2.3 逐行核对 UG850 后取消注释。
# 顶层是板级 wrapper w3_top_zc702 (src/rtl/w3_protocol/w3_top_zc702.v)，
# 因此这里的端口名一律用 **wrapper 的端口名**（不是 w3_top 的）。
# Reference: github.com/rithan2001/Xilinx-Zynq-7000-SoC-ZC702 master_constraints.xdc

# === CLOCK (wrapper 端口: clk_p / clk_n) ===
# ZC702 PL 时钟 = D18(SYSCLK_P)/C19(SYSCLK_N)，200MHz 差分，LVDS_25。
# 时钟适配在 wrapper 内完成（clk_wiz_0：200MHz 差分 -> 100MHz + locked）；
# w3_top 本体吃的是 wrapper 产生的 100MHz，**无需**再给 w3_top 加约束。
# set_property -dict {PACKAGE_PIN D18 IOSTANDARD LVDS_25} [get_ports clk_p]
# set_property -dict {PACKAGE_PIN C19 IOSTANDARD LVDS_25} [get_ports clk_n]
# create_clock -period 5.000 -name sys_clk_p [get_ports clk_p]   ;# 200MHz = 5ns

# === RESET (wrapper 端口: sys_rst_btn_n，低有效) ===
# ZC702 的 CPU_RESET (SRST_B/POR_B) 在 PS 域，PL 不可见 —— 用 PL 按键：
# set_property -dict {PACKAGE_PIN G19 IOSTANDARD LVCMOS25} [get_ports sys_rst_btn_n]   ;# GPIO_SW_N

# === UART (连电台/串口桥，经 FMC LPC 或 PMOD) ===
# ZC702 板载 USB-UART 在 PS MIO，PL 够不着；LVCMOS25（不是 LVCMOS15）。
# 引脚需先从 UG850 选定（保姆教程 3.2），未选定前验证点③暂缓：
# set_property -dict {PACKAGE_PIN <FMC/PMOD 引脚> IOSTANDARD LVCMOS25} [get_ports radio_txd]
# set_property -dict {PACKAGE_PIN <FMC/PMOD 引脚> IOSTANDARD LVCMOS25} [get_ports radio_rxd]

# === LEDs (DS9~DS12) —— 引脚号已对照 AMD 官方 ZC702 板卡定义核验 ===
# 官方板卡文件 xilinx.com:zc702:part0:1.4 (part0_pins.xml):
#   leds_4bits_tri_o_0..3 = P17 / P18 / W10 / V7  (LVCMOS25)
#   ⚠ Y11 / T22 / U21 是 FMC2_LPC 的 la33_p / la14_p / la07_n —— **不是 LED**（旧底稿写错）。
#   DS9~DS12 与 bit0..3 的对应关系仍请以 UG850/原理图核实。
# set_property -dict {PACKAGE_PIN P17 IOSTANDARD LVCMOS25} [get_ports led_busy]         ;# LED0
# set_property -dict {PACKAGE_PIN P18 IOSTANDARD LVCMOS25} [get_ports led_heartbeat]    ;# LED1
# set_property -dict {PACKAGE_PIN W10 IOSTANDARD LVCMOS25} [get_ports {led_result[0]}]  ;# LED2
# set_property -dict {PACKAGE_PIN V7  IOSTANDARD LVCMOS25} [get_ports {led_result[1]}]  ;# LED3

# === Auth button (wrapper 端口: auth_btn) ===
# 官方板卡定义里 PL 侧只有两颗按键：GPIO_SW_N=G19（已给复位）、**GPIO_SW_S=F19**。
# 不接则端口悬空 -> UCIO-1 ERROR；不打算接就跳过保姆教程 2.5 的测 3。
# set_property -dict {PACKAGE_PIN F19 IOSTANDARD LVCMOS25} [get_ports auth_btn]   ;# GPIO_SW_S

# === DIP switches (wrapper 端口: term_id_dip[1:0]) ===
# ZC702 PL 侧只有 W6/W7 两颗拨码；wrapper 已把 terminal_id 高 6 位 tie 0
# （.term_id_sw({6'h00, term_id_dip})），所以这里只需约束 2 位。
# set_property -dict {PACKAGE_PIN W6 IOSTANDARD LVCMOS25} [get_ports {term_id_dip[0]}]
# set_property -dict {PACKAGE_PIN W7 IOSTANDARD LVCMOS25} [get_ports {term_id_dip[1]}]