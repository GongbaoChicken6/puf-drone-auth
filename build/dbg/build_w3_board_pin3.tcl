# build_w3_board.tcl -- ZC706 上板构建（板级 wrapper 顶层 + Clk Wizard + 引脚约束）
# 用法: vivado -mode batch -source build_w3_board.tcl -tclargs <part> <outdir> <srcdir>
#   ⚠ srcdir = 仓库的 src 目录（必须含 rtl/ 子目录）——不是仓库根！
#      例: ... -tclargs xc7z045ffg900-2 build\board_zc706 src
#
# 与 build_w3.tcl（dev 模式，top=w3_top、无 IP、无约束、DRC 豁免）的区别：
#   本脚本 top = w3_top_zc706（含 200MHz 差分 -> 100MHz 适配），加载 w3_top_zc706.xdc，
#   生成 clk_wiz_0。W4 B5a 起含 PUF 子系统（challenge_decode + 真实 ro_array，
#   环振本体即组合环，属设计使然）——加载 w2_waiver.xdc 豁免 LUTLP-1，
#   这是唯一保留的 DRC 豁免；其余全约束、全把关。
set PART [lindex $argv 0]
set OD   [lindex $argv 1]
set SRC  [lindex $argv 2]
if {$PART eq "" || $OD eq "" || $SRC eq ""} { puts "ERROR: 用法 build_w3_board.tcl <part> <outdir> <srcdir>"; exit 2 }
# P0 修复(silent-failure)：srcdir 契约守卫——$SRC/rtl 不存在时 14 秒内响亮失败，
# 而不是 add_files 报 12-172 让人摸不着头脑
if {![file isdirectory "$SRC/rtl"]} {
    puts "ERROR: srcdir 应指向 src 目录（须含 rtl/ 子目录），当前: $SRC"
    exit 2
}

file mkdir $OD
create_project -force w3_board $OD -part $PART

add_files [list \
    $SRC/rtl/w1_ratio/ro_ring.v \
    $SRC/rtl/w1_ratio/ro_div.v \
    $SRC/rtl/w2_array/ro_array.v \
    $SRC/rtl/w2_array/challenge_decode.v \
$SRC/rtl/w2_array/ro_entropy.v \
    $SRC/rtl/common/crc16_mcrf4xx.v \
    $SRC/rtl/common/mavlink_frame.v \
    $SRC/rtl/common/frame_parser.v \
    $SRC/rtl/common/byte_fifo.v \
    $SRC/rtl/common/uart_tx.v \
    $SRC/rtl/common/uart_rx.v \
    $SRC/rtl/common/speck64_96.v \
    $SRC/rtl/w3_protocol/terminal_fsm.v \
    $SRC/rtl/w3_protocol/w3_top.v \
    $SRC/rtl/w3_protocol/w3_top_zc706.v \
]

# 引脚约束：w3_top_zc706.xdc 已按 UG954 v1.8 + 板卡文件逐引脚冻结，直接加载
add_files -fileset constrs_1 D:/puf-drone-auth/build/dbg/w3_top_zc706_pin3.xdc
# W4 B5a：环振组合环豁免（设计使然，w2_waiver 头注释自证无豁免必被 LUTLP-1 阻断）
add_files -fileset constrs_1 $SRC/rtl/w2_array/w2_waiver.xdc

# Clk Wizard：200MHz 差分 -> 100MHz + locked + reset（wrapper 里直连 sys_rst_btn_n，板上高有效）
create_ip -name clk_wiz -vendor xilinx.com -library ip -module_name clk_wiz_0
set_property -dict [list \
    CONFIG.PRIM_SOURCE {Differential_clock_capable_pin} \
    CONFIG.PRIM_IN_FREQ {200.000} \
    CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {100.000} \
    CONFIG.USE_RESET {true} \
    CONFIG.USE_LOCKED {true} \
] [get_ips clk_wiz_0]
# P0 修复(silent-failure) 迭代2：全局综合模式（OOC checkpoint 关闭）——
# generate_synth_checkpoint=0 时 IP 生成可综合 Verilog 源，配合 update_compile_order
# 后 synth_design 直接从源综合，绕开 OOC DCP 接线问题（synth 8-439）
set_property generate_synth_checkpoint 0 [get_files clk_wiz_0.xci]
generate_target all [get_ips clk_wiz_0]
update_compile_order -fileset sources_1
# 双保险：显式把 XCI 加入 sources_1（create_ip 在部分流程下不自动入 fileset）
add_files -fileset sources_1 [get_files clk_wiz_0.xci]
update_compile_order -fileset sources_1

set_property top w3_top_zc706 [current_fileset]
synth_design -top w3_top_zc706 -part $PART

# P0 修复续(silent-failure/LUTLP-1)：w2_waiver.xdc 的 get_nets -hierarchical 在
# XDC 读取时（综合前）nets 不存在 -> 静默匹配 0 个对象，豁免在 bitstream DRC
# 从未生效（本脚本首次真实跑通即暴露：32 个 LUTLP-1 错误）。
# 正确做法：综合后在脚本内应用（此时 nets 存在），并响亮校验数量。
set loopnets [get_nets -hierarchical -filter {NAME =~ "*u_ro_ring/n1"}]
puts "LUTLP-1 waiver nets: [llength $loopnets] (expect 32 = ro_array 16 + ro_entropy 16)"
if {[llength $loopnets] == 0} {
    puts "ERROR: LUTLP-1 waiver matched ZERO nets -- ring waiver broken"
    exit 5
}
set_property ALLOW_COMBINATORIAL_LOOPS TRUE $loopnets

opt_design
place_design
route_design

report_utilization -file $OD/utilization.rpt
report_timing_summary -file $OD/timing.rpt
# P2 修复(silent-failure)：时序门禁——WNS<0 时绝不允许产出"成功"比特流
set wns [get_property SLACK [get_timing_paths -delay_type max]]
if {$wns < 0} {
    puts "TIMING_FAILED WNS=$wns"
    exit 4
}
write_bitstream -force $OD/w3_top_zc706.bit
puts "BITSTREAM_SUCCESS WNS=$wns"