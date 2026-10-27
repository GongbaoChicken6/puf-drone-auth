# v7 终极诊断：pin1 发 + pin3/pin5 输入 + LED
set_property -dict {PACKAGE_PIN H9 IOSTANDARD DIFF_SSTL15} [get_ports clk_p]
set_property -dict {PACKAGE_PIN G9 IOSTANDARD DIFF_SSTL15} [get_ports clk_n]
create_clock -period 5.000 -name sys_clk_p [get_ports clk_p]
set_property -dict {PACKAGE_PIN AJ21 IOSTANDARD LVCMOS25} [get_ports pmod1_0]
set_property -dict {PACKAGE_PIN AK21 IOSTANDARD LVCMOS25} [get_ports pmod1_1]
set_property -dict {PACKAGE_PIN AB21 IOSTANDARD LVCMOS25} [get_ports pmod1_2]
set_property -dict {PACKAGE_PIN A17 IOSTANDARD LVCMOS15} [get_ports led_heartbeat]
set_property -dict {PACKAGE_PIN G2  IOSTANDARD LVCMOS15} [get_ports led_rx]
