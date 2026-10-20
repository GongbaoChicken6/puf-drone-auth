# w3_top_zc706.xdc -- ZC706 (xc7z045ffg900-2) 引脚/时钟约束
# 顶层 = w3_top_zc706（wrapper 端口名）。禁止照抄 ZC702 任何引脚。
# 事实来源：part0_pins.xml + xc7z045_ffg900.pkg(bank) + UG954 v1.8。
# ⚠ 验证口径：**前身约束集**（仅 UART/LED 两行与本文件不同）已过本机 Vivado 2026.1
# synth/opt/place 实测（0 错 0 警，WNS=3.724）；本文件自身的终验 = Phase 5 首次综合。

# === CLOCK（bank34=VCC1V5_PL 1.5V 固定轨；LVDS_25 实测 BIVB-1 ERROR，禁抄 ZC702）===
# 取 AMD 官方 zc706/1.5/new.ucf 对 H9/G9 的原生标准 DIFF_SSTL15
# （part0_pins.xml 写"LVDS"亦过 DRC，但与 AMD 自家 MIG 约束对齐取 SSTL15，勿回改）
set_property -dict {PACKAGE_PIN H9 IOSTANDARD DIFF_SSTL15} [get_ports clk_p]
set_property -dict {PACKAGE_PIN G9 IOSTANDARD DIFF_SSTL15} [get_ports clk_n]
create_clock -period 5.000 -name sys_clk_p [get_ports clk_p]

# === 异步 I/O false_path（防伪时序违例）===
set_false_path -from [get_ports sys_rst_btn_n]
set_false_path -from [get_ports auth_btn]
set_false_path -from [get_ports {term_id_dip[*]}]
set_false_path -to [get_ports led_*]

# === RESET：SW13 PL_CPU_RESET（A8，bank34，LVCMOS15！低有效）===
set_property -dict {PACKAGE_PIN A8 IOSTANDARD LVCMOS15} [get_ports sys_rst_btn_n]

# === AUTH 按钮：SW7 GPIO_SW_LEFT（AK25，bank11，空闲1/按下0）===
set_property -dict {PACKAGE_PIN AK25 IOSTANDARD LVCMOS25} [get_ports auth_btn]

# === UART：PMOD1(J58) 经 TXS0108E 3.3V<->2.5V 移位——3.3V USB-TTL 直插免分压 ===
# ⚠ 用 J58（信号名 PMOD1_x 在 J58）；勿插 J57（TCA6416 I2C 扩展器，UART 不可用）
set_property -dict {PACKAGE_PIN AJ21 IOSTANDARD LVCMOS25} [get_ports radio_txd]  ;# PMOD1_0 = J58.1
set_property -dict {PACKAGE_PIN AB21 IOSTANDARD LVCMOS25} [get_ports radio_rxd]  ;# PMOD1_2 = J58.5
# 备选（FMC LPC LA02，需转接板 + rxd 1k/2.2k 分压 + JTAG 旁路确认）:
# set_property -dict {PACKAGE_PIN AE12 IOSTANDARD LVCMOS25} [get_ports radio_txd]
# set_property -dict {PACKAGE_PIN AF12 IOSTANDARD LVCMOS25} [get_ports radio_rxd]

# === LED：结果码=亮灯（DS8/DS10，bank11 2.5V）；busy/心跳=暗位（1.5V bank）===
# NDS331 栅极驱动裕量：1.5V bank 偏暗但可见——bring-up 首查 DS9/DS35
set_property -dict {PACKAGE_PIN Y21 IOSTANDARD LVCMOS25} [get_ports {led_result[0]}]  ;# DS8 亮
set_property -dict {PACKAGE_PIN W21 IOSTANDARD LVCMOS25} [get_ports {led_result[1]}]  ;# DS10 亮
set_property -dict {PACKAGE_PIN G2  IOSTANDARD LVCMOS15} [get_ports led_busy]        ;# DS9 偏暗
set_property -dict {PACKAGE_PIN A17 IOSTANDARD LVCMOS15} [get_ports led_heartbeat]   ;# DS35 偏暗

# === DIP SW12（ON=1/OFF=0，板上 4.7k 下拉无需 PULLUP；ID1=0001、ID2=0010）===
set_property -dict {PACKAGE_PIN AB17 IOSTANDARD LVCMOS25} [get_ports {term_id_dip[0]}]
set_property -dict {PACKAGE_PIN AC16 IOSTANDARD LVCMOS25} [get_ports {term_id_dip[1]}]
set_property -dict {PACKAGE_PIN AC17 IOSTANDARD LVCMOS25} [get_ports {term_id_dip[2]}]
set_property -dict {PACKAGE_PIN AJ13 IOSTANDARD LVCMOS25} [get_ports {term_id_dip[3]}]
