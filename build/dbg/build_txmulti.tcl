set PART xc7z045ffg900-2
set OD   build/board_zc706_txmulti
set SRC  src
file mkdir $OD
create_project -force txmulti_board $OD -part $PART
add_files [list $SRC/rtl/common/uart_tx.v $SRC/rtl/common/uart_rx.v D:/puf-drone-auth/build/dbg/txmulti_top_zc706.v]
add_files -fileset constrs_1 D:/puf-drone-auth/build/dbg/txmulti.xdc
create_ip -name clk_wiz -vendor xilinx.com -library ip -module_name clk_wiz_0
set_property -dict [list CONFIG.PRIM_SOURCE {Differential_clock_capable_pin} CONFIG.PRIM_IN_FREQ {200.000} CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {100.000} CONFIG.USE_RESET {true} CONFIG.USE_LOCKED {true}] [get_ips clk_wiz_0]
set_property generate_synth_checkpoint 0 [get_files clk_wiz_0.xci]
generate_target all [get_ips clk_wiz_0]
add_files -fileset sources_1 [get_files clk_wiz_0.xci]
update_compile_order -fileset sources_1
set_property top txmulti_top_zc706 [current_fileset]
synth_design -top txmulti_top_zc706 -part $PART
create_debug_core u_ila_0 ila
set_property C_DATA_DEPTH 4096 [get_debug_cores u_ila_0]
set_property C_TRIGIN_EN false [get_debug_cores u_ila_0]
set_property C_TRIGOUT_EN false [get_debug_cores u_ila_0]
set_property C_ADV_TRIGGER false [get_debug_cores u_ila_0]
set_property C_INPUT_PIPE_STAGES 0 [get_debug_cores u_ila_0]
set_property C_EN_STRG_QUAL false [get_debug_cores u_ila_0]
set_property ALL_PROBE_SAME_MU true [get_debug_cores u_ila_0]
set_property ALL_PROBE_SAME_MU_CNT 1 [get_debug_cores u_ila_0]
set_property port_width 1 [get_debug_ports u_ila_0/clk]
connect_debug_port u_ila_0/clk [get_nets clk_100m]
set_property port_width 1 [get_debug_ports u_ila_0/probe0]
set n0 [get_nets -hierarchical -filter {NAME =~ *dbg_pin3*}]
if {[llength $n0] != 1} { puts "ERROR: dbg_pin3 nets=$n0"; exit 6 }
connect_debug_port u_ila_0/probe0 $n0
create_debug_port u_ila_0 probe
set_property port_width 1 [get_debug_ports u_ila_0/probe1]
set n1 [get_nets -hierarchical -filter {NAME =~ *dbg_pin5*}]
if {[llength $n1] != 1} { puts "ERROR: dbg_pin5 nets=$n1"; exit 6 }
connect_debug_port u_ila_0/probe1 $n1
create_debug_port u_ila_0 probe
set_property port_width 1 [get_debug_ports u_ila_0/probe2]
set n2 [get_nets -hierarchical -filter {NAME =~ *dbg_rx_valid*}]
if {[llength $n2] != 1} { puts "ERROR: dbg_rx_valid nets=$n2"; exit 6 }
connect_debug_port u_ila_0/probe2 $n2
opt_design
place_design
route_design
write_debug_probes -force $OD/v7.ltx
set wns [get_property SLACK [get_timing_paths -delay_type max]]
puts "V7 WNS=$wns"
if {$wns < 0} { puts "TIMING_FAILED"; exit 4 }
write_bitstream -force $OD/txmulti.bit
puts "TXMULTI_BUILD_SUCCESS"
close_project
