# build_w3_board.tcl -- ZC702 上板构建（板级 wrapper 顶层 + Clk Wizard + 引脚约束）
# 用法: vivado -mode batch -source build_w3_board.tcl -tclargs <part> <outdir> <srcdir>
#
# 与 build_w3.tcl（dev 模式，top=w3_top、无 IP、无约束、DRC 豁免）的区别：
#   本脚本 top = w3_top_zc702（含 200MHz 差分 -> 100MHz 适配），加载 w3_top.xdc，
#   生成 clk_wiz_0。W4 B5a 起含 PUF 子系统（challenge_decode + 真实 ro_array，
#   环振本体即组合环，属设计使然）——加载 w2_waiver.xdc 豁免 LUTLP-1，
#   这是唯一保留的 DRC 豁免；其余全约束、全把关。
set PART [lindex $argv 0]
set OD   [lindex $argv 1]
set SRC  [lindex $argv 2]
if {$PART eq "" || $OD eq "" || $SRC eq ""} { puts "ERROR: 用法 build_w3_board.tcl <part> <outdir> <srcdir>"; exit 2 }

file mkdir $OD
create_project -force w3_board $OD -part $PART

add_files [list \
    $SRC/rtl/w1_ratio/ro_ring.v \
    $SRC/rtl/w1_ratio/ro_div.v \
    $SRC/rtl/w2_array/ro_array.v \
    $SRC/rtl/w2_array/challenge_decode.v \
    $SRC/rtl/common/crc16_mcrf4xx.v \
    $SRC/rtl/common/mavlink_frame.v \
    $SRC/rtl/common/frame_parser.v \
    $SRC/rtl/common/byte_fifo.v \
    $SRC/rtl/common/uart_tx.v \
    $SRC/rtl/common/uart_rx.v \
    $SRC/rtl/common/speck64_96.v \
    $SRC/rtl/w3_protocol/terminal_fsm.v \
    $SRC/rtl/w3_protocol/w3_top.v \
    $SRC/rtl/w3_protocol/w3_top_zc702.v \
]

# 引脚约束：引脚号须先按保姆教程 2.3 核对 UG850 后取消 w3_top.xdc 里的注释
add_files -fileset constrs_1 $SRC/rtl/w3_protocol/w3_top.xdc
# W4 B5a：环振组合环豁免（设计使然，w2_waiver 头注释自证无豁免必被 LUTLP-1 阻断）
add_files -fileset constrs_1 $SRC/rtl/w2_array/w2_waiver.xdc

# Clk Wizard：200MHz 差分 -> 100MHz + locked + reset（wrapper 里接 ~sys_rst_btn_n）
create_ip -name clk_wiz -vendor xilinx.com -library ip -module_name clk_wiz_0
set_property -dict [list \
    CONFIG.PRIM_SOURCE {Differential_clock_capable_pin} \
    CONFIG.PRIM_IN_FREQ {200.000} \
    CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {100.000} \
    CONFIG.USE_RESET {true} \
    CONFIG.USE_LOCKED {true} \
] [get_ips clk_wiz_0]
generate_target all [get_ips clk_wiz_0]

set_property top w3_top_zc702 [current_fileset]
synth_design -top w3_top_zc702 -part $PART
opt_design
place_design
route_design

report_utilization -file $OD/utilization.rpt
report_timing_summary -file $OD/timing.rpt
write_bitstream -force $OD/w3_top_zc702.bit
puts "BITSTREAM_SUCCESS"