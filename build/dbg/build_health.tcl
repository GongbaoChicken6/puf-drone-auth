set PART xc7z045ffg900-2
set OD   build/board_zc706_health
set SRC  src
file mkdir $OD
create_project -force health_board $OD -part $PART
add_files [list build/dbg/health_top.v]
add_files -fileset constrs_1 $SRC/rtl/w3_protocol/w3_top_zc706.xdc
create_ip -name clk_wiz -vendor xilinx.com -library ip -module_name clk_wiz_0
set_property -dict [list \
    CONFIG.PRIM_SOURCE {Differential_clock_capable_pin} \
    CONFIG.PRIM_IN_FREQ {200.000} \
    CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {100.000} \
    CONFIG.USE_RESET {true} \
    CONFIG.USE_LOCKED {true} \
] [get_ips clk_wiz_0]
set_property generate_synth_checkpoint 0 [get_files clk_wiz_0.xci]
generate_target all [get_ips clk_wiz_0]
add_files -fileset sources_1 [get_files clk_wiz_0.xci]
update_compile_order -fileset sources_1
set_property top health_top [current_fileset]
synth_design -top health_top -part $PART
opt_design
place_design
route_design
set wns [get_property SLACK [get_timing_paths -delay_type max]]
puts "HEALTH WNS=$wns"
write_bitstream -force $OD/health_top.bit
puts "HEALTH_BUILD_SUCCESS"
close_project
