# w3_top.xdc -- ZC702 (xc7z020clg484-1) 引脚/时钟约束底稿
# ⚠ 所有 set_property 仍被注释 —— 请按保姆教程 2.3 逐行核对 UG850 后取消注释。
# 顶层是板级 wrapper w3_top_zc702 (src/rtl/w3_protocol/w3_top_zc702.v)，
# 因此这里的端口名一律用 **wrapper 的端口名**（不是 w3_top 的）。
# Reference: github.com/rithan2001/Xilinx-Zynq-7000-SoC-ZC702 master_constraints.xdc

# === ⚠ 开关前置（UG850 Table 1-10 / A-1）===
# SW10 (JTAG 选择开关, 2 位拨码, callout 23) 必须设为 01 才能用 Digilent USB JTAG：
#   SW10.1=Off(0), SW10.2=On(1) → Digilent U23 ← 出厂默认，正确
#   10 = 14-pin J2 (Platform Cable)  11 = 20-pin J58  00 = 断开
# SW16 (启动模式, 5 位): JTAG 配置 PL 与 SW16 无关（任意设置均可，保持出厂即可）
# VADJ = 2.5V（出厂默认）→ PL Bank 13/33/34/35 的 I/O 电平为 LVCMOS25（含本文件全部 GPIO/FMC 引脚）

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
# set_property -dict {PACKAGE_PIN L21 IOSTANDARD LVCMOS25} [get_ports radio_txd]  ;# FMC1_LPC_LA02_P, FMC 接插件 H7
# set_property -dict {PACKAGE_PIN L22 IOSTANDARD LVCMOS25} [get_ports radio_rxd]  ;# FMC1_LPC_LA02_N, FMC 接插件 H8

# === LEDs (DS15~DS18) —— 引脚号已对照 AMD 官方 ZC702 板卡定义核验 ===
# 官方板卡文件 xilinx.com:zc702:part0:1.4 (part0_pins.xml):
#   leds_4bits_tri_o_0..3 = P17 / P18 / W10 / V7  (LVCMOS25)
#   ⚠ Y11 / T22 / U21 是 FMC2_LPC 的 la33_p / la14_p / la07_n —— **不是 LED**（旧底稿写错）。
#   位号对应（UG850 已核）：P17=DS15 / P18=DS16 / W10=DS17 / V7=DS18。
# set_property -dict {PACKAGE_PIN P17 IOSTANDARD LVCMOS25} [get_ports led_busy]         ;# DS15 (PMOD2_3, Bank 35)
# set_property -dict {PACKAGE_PIN P18 IOSTANDARD LVCMOS25} [get_ports led_heartbeat]    ;# DS16 (PMOD2_2, Bank 35) ← 心跳灯看这颗
# set_property -dict {PACKAGE_PIN W10 IOSTANDARD LVCMOS25} [get_ports {led_result[0]}]  ;# DS17 (PMOD2_1, Bank 35)
# set_property -dict {PACKAGE_PIN V7  IOSTANDARD LVCMOS25} [get_ports {led_result[1]}]  ;# DS18 (PMOD2_0, Bank 35)

# === Auth button (wrapper 端口: auth_btn) ===
# 官方板卡定义里 PL 侧只有两颗按键：GPIO_SW_N=G19（已给复位）、**GPIO_SW_S=F19**。
# 不接则端口悬空 -> UCIO-1 ERROR；不打算接就跳过保姆教程 2.5 的测 3。
# set_property -dict {PACKAGE_PIN F19 IOSTANDARD LVCMOS25} [get_ports auth_btn]   ;# GPIO_SW_S

# === DIP switches (wrapper 端口: term_id_dip[1:0]) ===
# ZC702 PL 侧只有 W6/W7 两颗拨码；wrapper 已把 terminal_id 高 6 位 tie 0
# （.term_id_sw({6'h00, term_id_dip})），所以这里只需约束 2 位。
# set_property -dict {PACKAGE_PIN W6 IOSTANDARD LVCMOS25} [get_ports {term_id_dip[0]}]
# set_property -dict {PACKAGE_PIN W7 IOSTANDARD LVCMOS25} [get_ports {term_id_dip[1]}]