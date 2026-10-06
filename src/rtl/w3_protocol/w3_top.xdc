# w3_top.xdc -- ZC702 (xc7z020clg484-1) 约束模板
# ⚠ 引脚待板级连接确认后填入实际值（当前为占位符）
# 用法：Vivado → Add Sources → Constraints → 选择此文件

# 时钟（ZC702 200MHz 差分或 100MHz 单端，待确认具体引脚）
# create_clock -period 10.000 -name sys_clk [get_ports sys_clk]

# 复位（ZC702 CPU_RESET 按钮，待确认引脚）
# set_property PACKAGE_PIN H19 [get_ports sys_rst_n]
# set_property IOSTANDARD LVCMOS15 [get_ports sys_rst_n]

# UART 连电台（待确认 FMC/PMod 引脚）
# set_property PACKAGE_PIN xx [get_ports radio_txd]
# set_property IOSTANDARD LVCMOS15 [get_ports radio_txd]
# set_property PACKAGE_PIN xx [get_ports radio_rxd]
# set_property IOSTANDARD LVCMOS15 [get_ports radio_rxd]

# 认证按钮
# set_property PACKAGE_PIN xx [get_ports auth_btn]
# set_property IOSTANDARD LVCMOS15 [get_ports auth_btn]

# 终端 ID 拨码开关
# set_property PACKAGE_PIN xx [get_ports {term_id_sw[0]}]
# ...（8 位）

# LED
# set_property PACKAGE_PIN xx [get_ports led_busy]
# set_property PACKAGE_PIN xx [get_ports {led_result[0]}]
# set_property PACKAGE_PIN xx [get_ports {led_result[1]}]
# set_property PACKAGE_PIN xx [get_ports led_heartbeat]

# 时序约束
# set_false_path -from [get_ports sys_rst_n] -to [get_pins -hierarchical -filter {NAME =~ *rst_ff1*}]
