set PART xc7z045ffg900-2
set OD   build/board_zc706_ila
set SRC  src
file mkdir $OD
create_project -force ila_board $OD -part $PART
add_files [list \
    $SRC/rtl/w1_ratio/ro_ring.v $SRC/rtl/w1_ratio/ro_div.v \
    $SRC/rtl/w2_array/ro_array.v $SRC/rtl/w2_array/challenge_decode.v \
    $SRC/rtl/common/crc16_mcrf4xx.v $SRC/rtl/common/mavlink_frame.v $SRC/rtl/common/frame_parser.v \
    $SRC/rtl/common/byte_fifo.v $SRC/rtl/common/uart_tx.v $SRC/rtl/common/uart_rx.v $SRC/rtl/common/speck64_96.v \
    $SRC/rtl/w3_protocol/terminal_fsm.v \
    D:/puf-drone-auth/build/dbg/ro_entropy_dbg.v D:/puf-drone-auth/build/dbg/w3_top_dbg.v D:/puf-drone-auth/build/dbg/dbg_top_zc706.v \
]
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
set_property top dbg_top_zc706 [current_fileset]
synth_design -top dbg_top_zc706 -part $PART
set loopnets [get_nets -hierarchical -filter {NAME =~ "*u_ro_ring/n1"}]
puts "LUTLP-1 waiver nets: [llength $loopnets]"
if {[llength $loopnets] == 0} { puts "ERROR: ring waiver broken"; exit 5 }
set_property ALLOW_COMBINATORIAL_LOOPS TRUE $loopnets

# ===== 网名探测（综合后层次信号名核实）=====
puts "NETS seed_valid: [get_nets -hierarchical -filter {NAME =~ *re_seed_valid*}]"
puts "NETS seed_fault: [get_nets -hierarchical -filter {NAME =~ *re_seed_fault*}]"
puts "NETS seed_st: [get_nets -hierarchical -filter {NAME =~ *re_seed_st*}]"
puts "NETS ring_freq count: [llength [get_nets -hierarchical -filter {NAME =~ *re_ring_freq*}]]"
puts "NETS btn_state: [get_nets -hierarchical -filter {NAME =~ *btn_state*}]"

# ===== 官方 UG908 非工程模式 ILA 插入流程 =====
create_debug_core u_ila_0 ila
set_property C_DATA_DEPTH 1024 [get_debug_cores u_ila_0]
set_property C_TRIGIN_EN false [get_debug_cores u_ila_0]
set_property C_TRIGOUT_EN false [get_debug_cores u_ila_0]
set_property C_ADV_TRIGGER false [get_debug_cores u_ila_0]
set_property C_INPUT_PIPE_STAGES 0 [get_debug_cores u_ila_0]
set_property C_EN_STRG_QUAL false [get_debug_cores u_ila_0]
set_property ALL_PROBE_SAME_MU true [get_debug_cores u_ila_0]
set_property ALL_PROBE_SAME_MU_CNT 1 [get_debug_cores u_ila_0]
set_property port_width 1 [get_debug_ports u_ila_0/clk]
connect_debug_port u_ila_0/clk [get_nets clk_100m]
# probe0: seed_valid
set_property port_width 1 [get_debug_ports u_ila_0/probe0]
set n_seed_valid [get_nets -hierarchical -filter {NAME =~ *re_seed_valid*}]
if {[llength $n_seed_valid] == 0} { puts "ERROR: re_seed_valid net not found"; exit 6 }
connect_debug_port u_ila_0/probe0 $n_seed_valid
# probe1: seed_fault
create_debug_port u_ila_0 probe
set_property port_width 1 [get_debug_ports u_ila_0/probe1]
set n_seed_fault [get_nets -hierarchical -filter {NAME =~ *re_seed_fault*}]
if {[llength $n_seed_fault] == 0} { puts "ERROR: re_seed_fault net not found"; exit 6 }
connect_debug_port u_ila_0/probe1 $n_seed_fault
# probe2: ro_entropy 状态机 st[1:0]
create_debug_port u_ila_0 probe
set_property port_width 2 [get_debug_ports u_ila_0/probe2]
set n_st {}
for {set i 0} {$i < 2} {incr i} { lappend n_st [get_nets -hierarchical -filter "NAME =~ *re_seed_st\[$i\]"] }
puts "st nets: $n_st"
connect_debug_port u_ila_0/probe2 $n_st
# probe3: 环0 计数（16bit）
create_debug_port u_ila_0 probe
set_property port_width 16 [get_debug_ports u_ila_0/probe3]
set ring0 {}
for {set i 0} {$i < 16} {incr i} { lappend ring0 [get_nets -hierarchical -filter "NAME =~ *re_ring_freq\[$i\]"] }
puts "ring0 nets: [llength $ring0]"
connect_debug_port u_ila_0/probe3 $ring0
# probe4: 环1 计数（16bit）
create_debug_port u_ila_0 probe
set_property port_width 16 [get_debug_ports u_ila_0/probe4]
set ring1 {}
for {set i 16} {$i < 32} {incr i} { lappend ring1 [get_nets -hierarchical -filter "NAME =~ *re_ring_freq\[$i\]"] }
puts "ring1 nets: [llength $ring1]"
connect_debug_port u_ila_0/probe4 $ring1
puts "DEBUG_CORES: [get_debug_cores] count=[llength [get_debug_cores]]"
puts "ILA probes: [get_debug_ports -of_objects [get_debug_cores u_ila_0]]"

opt_design
place_design
route_design
write_debug_probes -force $OD/ila.ltx
set wns [get_property SLACK [get_timing_paths -delay_type max]]
puts "ILA WNS=$wns"
if {$wns < 0} { puts "TIMING_FAILED"; exit 4 }
write_bitstream -force $OD/ila_top.bit
puts "ILA_BUILD_SUCCESS"
close_project
