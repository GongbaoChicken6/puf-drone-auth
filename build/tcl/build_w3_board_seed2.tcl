# build_w3_board_seed2.tcl -- 布局变体B构建（per-device layout configuration 首个实例）
# 目的：根因修复实验——生产 bit 与本 bit 用同一 RTL/约束，但把 32 个环振单元
#       （ro_array 16 + ro_entropy 16）PBlock 强制搬到不同时钟区域，使环频排序
#       与生产 bit 不同 => 两块板指纹可区分（预期跨配置 HD≈32/64每响应，REJECT）。
# 用法: vivado -mode batch -source build_w3_board_seed2.tcl -tclargs <part> <outdir> <srcdir>
#   例: ... -tclargs xc7z045ffg900-2 build\board_zc706_seed2 src
# 与 build_w3_board.tcl 的差异（全部标注 SEED2）：
#   1) 环振单元 PBlock 重定位（布局差异化的唯一来源）
#   2) 输出 w3_top_zc706_seed2.bit + ring_sites_seed2.rpt（落位证据）
#   3) 其余与生产流程功能等价（同源/同约束/同豁免/同时序门禁；非逐字拷贝，见 CI 清单一致性锁）
set PART [lindex $argv 0]
set OD   [lindex $argv 1]
set SRC  [lindex $argv 2]
if {$PART eq "" || $OD eq "" || $SRC eq ""} { puts "ERROR: 用法 build_w3_board_seed2.tcl <part> <outdir> <srcdir>"; exit 2 }
if {![file isdirectory "$SRC/rtl"]} { puts "ERROR: srcdir 应指向 src 目录（须含 rtl/ 子目录），当前: $SRC"; exit 2 }

file mkdir $OD
create_project -force w3_board_seed2 $OD -part $PART

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
add_files -fileset constrs_1 $SRC/rtl/w3_protocol/w3_top_zc706.xdc
add_files -fileset constrs_1 $SRC/rtl/w2_array/w2_waiver.xdc

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
update_compile_order -fileset sources_1
add_files -fileset sources_1 [get_files clk_wiz_0.xci]
update_compile_order -fileset sources_1

set_property top w3_top_zc706 [current_fileset]
synth_design -top w3_top_zc706 -part $PART

# ---- LUTLP-1 环振豁免（与生产逐字一致）----
set loopnets [get_nets -hierarchical -filter {NAME =~ "*u_ro_ring/n1"}]
puts "LUTLP-1 waiver nets: [llength $loopnets] (expect 32 = ro_array 16 + ro_entropy 16)"
if {[llength $loopnets] == 0} { puts "ERROR: LUTLP-1 waiver matched ZERO nets -- ring waiver broken"; exit 5 }
set_property ALLOW_COMBINATORIAL_LOOPS TRUE $loopnets

# ---- SEED2 差异化：环振单元 PBlock 重定位 ----
set ringcells [get_cells -hierarchical -filter {NAME =~ "*u_ro_ring*"}]
puts "SEED2 ring cells: [llength $ringcells] (32 hier + 160 leaf expected)"
# auto-review P1/P2: 环级精确断言——32 个不同 gen_ro_ring[N].u_ro_ring 实例，防部分匹配静默通过
set ring_inst {}
foreach c $ringcells {
    if {[regexp {gen_ro_ring\[[0-9]+\]\.u_ro_ring$} $c]} { lappend ring_inst $c }
}
set ring_inst_uniq [lsort -unique $ring_inst]
puts "SEED2 ring instances: [llength $ring_inst_uniq] (expect 32)"
if {[llength $ring_inst_uniq] != 32} { puts "ERROR: SEED2 expected 32 distinct ring instances, got [llength $ring_inst_uniq]"; exit 6 }
set pick "X1Y0"   ;# auto-review P2: 钉死区域（原 lsort 取中位是器件相关隐式推导）
set allcr [lsort [get_clock_regions]]
puts "SEED2 clock regions available: $allcr"
if {[lsearch -exact $allcr $pick] < 0} { puts "ERROR: SEED2 target region $pick absent on this part"; exit 8 }
puts "SEED2 relocate region (pinned): $pick"
create_pblock pb_rings_seed2
add_cells_to_pblock pb_rings_seed2 $ringcells
set pbrange "CLOCKREGION_$pick:CLOCKREGION_$pick"
puts "SEED2 pblock range: $pbrange"
if {[catch {resize_pblock pb_rings_seed2 -add [list $pbrange]} err]} {
    puts "ERROR: SEED2 resize_pblock failed: $err"
    exit 7
}

opt_design
place_design
route_design

report_utilization -file $OD/utilization.rpt
report_timing_summary -file $OD/timing.rpt
set wns [get_property SLACK [get_timing_paths -delay_type max]]
if {$wns < 0} { puts "TIMING_FAILED WNS=$wns"; exit 4 }
# auto-review P2: hold 门禁（环频计数捕获路径对 hold 敏感；本次构建实测中间态曾 WHS=-0.270）
set whs [get_property SLACK [get_timing_paths -delay_type min]]
if {$whs < 0} { puts "TIMING_FAILED WHS=$whs"; exit 10 }
puts "TIMING_OK WNS=$wns WHS=$whs"

# SEED2 落位证据（auto-review 修正：仅叶子单元 + 区域归属计数；X1Y0 行界=SLICE_Y49/50，接缝 Y50/51 属合法网格）
set leafcells {}
foreach c $ringcells {
    if {[get_property SITE $c] ne ""} { lappend leafcells $c }
}
puts "SEED2 placed leaf cells: [llength $leafcells] (expect 160)"
if {[llength $leafcells] != 160} { puts "ERROR: SEED2 expected 160 placed leaf ring cells, got [llength $leafcells]"; exit 11 }
set rf [open $OD/ring_sites_seed2.rpt w]
puts $rf "# seed2 ring LEAF cell placement (target region $pick)"
set inregion 0; set seam 0
foreach c $leafcells {
    set s [get_property SITE $c]
    puts $rf "$c $s"
    if {[regexp {Y([0-9]+)$} $s -> y]} {
        if {$y <= 49} { incr inregion } else { incr seam }
    }
}
close $rf
puts "SEED2 region tally: X1Y0=$inregion seam=$seam"
if {$inregion + $seam != 160} { puts "ERROR: SEED2 region tally incomplete"; exit 12 }

# auto-review P3: 机内变体标识（当前入库 bit 未重建不含此属性，见 README 已知边界；自下次构建生效）
set_property BITSTREAM.CONFIG.USERID 0x5EED0002 [current_design]
write_bitstream -force $OD/w3_top_zc706_seed2.bit
puts "BITSTREAM_SUCCESS WNS=$wns WHS=$whs SEED2_REGION=$pick"