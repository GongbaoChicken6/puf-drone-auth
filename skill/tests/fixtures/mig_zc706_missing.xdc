# Deliberately BROKEN new-board XDC for the FAIL-direction migration test:
# identical to mig_zc706.xdc but uart_rx was never re-constrained - the
# classic half-done migration the G3 gate must catch.
set_property PACKAGE_PIN A10 [get_ports clk]
set_property IOSTANDARD DIFF_SSTL15 [get_ports clk]
create_clock -period 5.000 -name sys_clk -waveform {0.000 2.500} [get_ports clk]

set_property PACKAGE_PIN B22 [get_ports rst_n]
set_property IOSTANDARD LVCMOS18 [get_ports rst_n]

set_property PACKAGE_PIN AB8 [get_ports {led[0]}]
set_property PACKAGE_PIN AB9 [get_ports {led[1]}]
set_property PACKAGE_PIN AB10 [get_ports {led[2]}]
set_property PACKAGE_PIN AB11 [get_ports {led[3]}]
set_property IOSTANDARD LVCMOS15 [get_ports {led[0]}]
set_property IOSTANDARD LVCMOS15 [get_ports {led[1]}]
set_property IOSTANDARD LVCMOS15 [get_ports {led[2]}]
set_property IOSTANDARD LVCMOS15 [get_ports {led[3]}]

set_property PACKAGE_PIN Y21 [get_ports uart_tx]
set_property IOSTANDARD LVCMOS18 [get_ports uart_tx]

set_property PACKAGE_PIN W19 [get_ports {sw[0]}]
set_property PACKAGE_PIN W20 [get_ports {sw[1]}]
set_property IOSTANDARD LVCMOS18 [get_ports {sw[0]}]
set_property IOSTANDARD LVCMOS18 [get_ports {sw[1]}]
