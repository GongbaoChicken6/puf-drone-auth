set PART xc7z045ffg900-2
set OD   build/board_zc706_dbg2
set SRC  src
file mkdir $OD
create_project -force dbg_board $OD -part $PART
add_files [list     $SRC/rtl/w1_ratio/ro_ring.v $SRC/rtl/w1_ratio/ro_div.v     $SRC/rtl/w2_array/ro_array.v $SRC/rtl/w2_array/challenge_decode.v $SRC/rtl/w2_array/ro_entropy.v     $SRC/rtl/common/crc16_mcrf4xx.v $SRC/rtl/common/mavlink_frame.v $SRC/rtl/common/frame_parser.v     $SRC/rtl/common/byte_fifo.v $SRC/rtl/common/uart_tx.v $SRC/rtl/common/uart_rx.v $SRC/rtl/common/speck64_96.v     $SRC/rtl/w3_protocol/terminal_fsm.v     D:/puf-drone-auth/build/dbg/ro_entropy_dbg.v D:/puf-drone-auth/build/dbg/w3_top_dbg.v D:/puf-drone-auth/build/dbg/dbg_top_zc706.v ]
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
update_compile_order -fileset sources_1
# 加载校验：两个诊断文件必须在 fileset 里
set dbgfiles [get_files -of [get_filesets sources_1] *.v]
puts "FILESET V FILES: [llength $dbgfiles]"
puts "w3_top_dbg in fileset: [llength [lsearch -all -inline $dbgfiles *w3_top_dbg.v*]]"
puts "dbg_top in fileset: [llength [lsearch -all -inline $dbgfiles *dbg_top_zc706.v*]]"
if {[llength [lsearch -all -inline $dbgfiles *w3_top_dbg.v*]] == 0} { puts "ERROR: w3_top_dbg.v missing from fileset"; exit 7 }
set_property top dbg_top_zc706 [current_fileset]
synth_design -top dbg_top_zc706 -part $PART
set loopnets [get_nets -hierarchical -filter {NAME =~ "*u_ro_ring/n1"}]
puts "LUTLP-1 waiver nets: [llength $loopnets] (expect 32)"
if {[llength $loopnets] == 0} { puts "ERROR: ring waiver broken"; exit 5 }
set_property ALLOW_COMBINATORIAL_LOOPS TRUE $loopnets
opt_design
place_design
route_design
report_timing_summary -file $OD/timing.txt
set wns [get_property SLACK [get_timing_paths -delay_type max]]
if {$wns < 0} { puts "TIMING_FAILED WNS=$wns"; exit 4 }
write_bitstream -force $OD/dbg_top_zc706.bit
puts "DBG_BITSTREAM_SUCCESS WNS=$wns"
