# build_ila_tx.tcl — TX 链 ILA 判别 bit（基于 build_ila.tcl；探针=发送链，深度 16384）
# 判别目标：按 SW7 后 fifo→uart_tx→tx_serial_reg→radio_txd(AJ21) 上是否真有 115200 波形
# 与生产 bit 行为一致性：dbg_top_zc706 与 w3_top_zc706 参数全同（ENROLL_EN=1/SEED_GATE_EN=1/100MHz/115200）
set PART xc7z045ffg900-2
set OD   build/board_zc706_ila_tx
set SRC  src
file mkdir $OD
create_project -force ila_tx_board $OD -part $PART
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

# ===== TX 链网名探测（供失败时诊断） =====
puts "NETS tx_serial_reg: [get_nets -hierarchical -filter {NAME =~ *tx_serial_reg*}]"
puts "NETS uart_tx_active: [get_nets -hierarchical -filter {NAME =~ *uart_tx_active*}]"
puts "NETS u_tx/curr_state count: [llength [get_nets -hierarchical -filter {NAME =~ *u_tx/curr_state*}]]"
puts "NETS mf_frame_valid: [get_nets -hierarchical -filter {NAME =~ *mf_frame_valid*}]"

# ===== ILA 插入（UG908 非工程模式） =====
create_debug_core u_ila_0 ila
set_property C_DATA_DEPTH 16384 [get_debug_cores u_ila_0]
set_property C_TRIGIN_EN false [get_debug_cores u_ila_0]
set_property C_TRIGOUT_EN false [get_debug_cores u_ila_0]
set_property C_ADV_TRIGGER false [get_debug_cores u_ila_0]
set_property C_INPUT_PIPE_STAGES 0 [get_debug_cores u_ila_0]
set_property C_EN_STRG_QUAL false [get_debug_cores u_ila_0]
set_property ALL_PROBE_SAME_MU true [get_debug_cores u_ila_0]
set_property ALL_PROBE_SAME_MU_CNT 1 [get_debug_cores u_ila_0]
set_property port_width 1 [get_debug_ports u_ila_0/clk]
connect_debug_port u_ila_0/clk [get_nets clk_100m]
# probe0: radio_txd 端口网络（= tx_serial_reg 的 Q，综合后网名取端口名；端锚定+恰好1条）
set_property port_width 1 [get_debug_ports u_ila_0/probe0]
puts "TXPORTNETS_ALL: [lsort [get_nets -hierarchical -filter {NAME =~ *radio_txd*}]]"
set n_tx {}
foreach pat {u_top/u_tx/radio_txd u_top/radio_txd radio_txd_OBUF radio_txd} {
  set c [get_nets -hierarchical -filter "NAME =~ $pat"]
  if {[llength $c] == 1} { set n_tx $c; puts "probe0 picked: $c (pat=$pat)"; break }
}
if {[llength $n_tx] != 1} { puts "ERROR: no unique radio_txd net"; exit 6 }
connect_debug_port u_ila_0/probe0 $n_tx
# probe1: 发送活动指示（tx_active 寄存器直出端口链；自适应挑唯一匹配，挑不到则降级删除）
create_debug_port u_ila_0 probe
set_property port_width 1 [get_debug_ports u_ila_0/probe1]
set n_act {}
foreach pat {*u_top/uart_tx_active *u_tx/tx_active *tx_active} {
  set c [get_nets -hierarchical -filter "NAME =~ $pat"]
  if {[llength $c] == 1} { set n_act $c; puts "probe1 picked: $c (pat=$pat)"; break }
}
if {[llength $n_act] == 1} {
  connect_debug_port u_ila_0/probe1 $n_act
} else {
  puts "WARN: tx_active not unique ([lsort [get_nets -hierarchical -filter {NAME =~ *tx_active*}]]); drop probe1"
  delete_debug_port u_ila_0/probe1
}
# probe2: mf_frame_valid（组帧器→FIFO 写使能，证明帧真入队）
create_debug_port u_ila_0 probe
set_property port_width 1 [get_debug_ports u_ila_0/probe2]
set n_mfv [get_nets -hierarchical -filter {NAME =~ u_top/mf_frame_valid}]
if {[llength $n_mfv] != 1} { puts "ERROR: mf_frame_valid match=[llength $n_mfv] all=[lsort [get_nets -hierarchical -filter {NAME =~ *mf_frame_valid*}]]"; exit 6 }
connect_debug_port u_ila_0/probe2 $n_mfv
puts "DEBUG_CORES: [get_debug_cores] count=[llength [get_debug_cores]]"

opt_design
place_design
route_design
write_debug_probes -force $OD/ila_tx.ltx
set wns [get_property SLACK [get_timing_paths -delay_type max]]
puts "ILA_TX WNS=$wns"
if {$wns < 0} { puts "TIMING_FAILED"; exit 4 }
write_bitstream -force $OD/ila_tx.bit
puts "ILA_TX_BUILD_SUCCESS"
close_project
