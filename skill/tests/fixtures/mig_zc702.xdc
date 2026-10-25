# Synthetic but structurally faithful master-XDC snippet (old board: ZC702)
# for offline migration-gate tests. Pins are placeholders, the FORM is real.
set_property PACKAGE_PIN E12 [get_ports clk]
set_property IOSTANDARD LVCMOS33 [get_ports clk]
create_clock -period 5.000 -name sys_clk -waveform {0.000 2.500} [get_ports clk]

set_property PACKAGE_PIN D5 [get_ports rst_n]
set_property IOSTANDARD LVCMOS33 [get_ports rst_n]

set_property PACKAGE_PIN H17 [get_ports {led[0]}]
set_property PACKAGE_PIN H18 [get_ports {led[1]}]
set_property PACKAGE_PIN H19 [get_ports {led[2]}]
set_property PACKAGE_PIN H20 [get_ports {led[3]}]
set_property IOSTANDARD LVCMOS33 [get_ports {led[0]}]
set_property IOSTANDARD LVCMOS33 [get_ports {led[1]}]
set_property IOSTANDARD LVCMOS33 [get_ports {led[2]}]
set_property IOSTANDARD LVCMOS33 [get_ports {led[3]}]

set_property PACKAGE_PIN J1 [get_ports uart_tx]
set_property IOSTANDARD LVCMOS33 [get_ports uart_tx]
set_property PACKAGE_PIN J2 [get_ports uart_rx]
set_property IOSTANDARD LVCMOS33 [get_ports uart_rx]

set_property PACKAGE_PIN K4 [get_ports {sw[0]}]
set_property PACKAGE_PIN K5 [get_ports {sw[1]}]
set_property IOSTANDARD LVCMOS18 [get_ports {sw[0]}]
set_property IOSTANDARD LVCMOS18 [get_ports {sw[1]}]
