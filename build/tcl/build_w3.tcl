# build_w3.tcl -- W3 top-level build (synthesis + implementation + bitstream)
# Usage: vivado -mode batch -source build/tcl/build_w3.tcl
set PART xc7z020clg484-1
set OD D:/fpga_work/w3_bitstream
set SRC D:/puf-drone-auth/src

file mkdir $OD
create_project -force w3_build $OD -part $PART

add_files [list \
    $SRC/rtl/common/crc16_mcrf4xx.v \
    $SRC/rtl/common/mavlink_frame.v \
    $SRC/rtl/common/frame_parser.v \
    $SRC/rtl/common/byte_fifo.v \
    $SRC/rtl/common/uart_tx.v \
    $SRC/rtl/common/uart_rx.v \
    $SRC/rtl/w3_protocol/terminal_fsm.v \
    $SRC/rtl/w3_protocol/w3_top.v \
]

# XDC constraints (uncomment when pin assignments are confirmed)
# add_files -fileset constrs_1 $SRC/rtl/w3_protocol/w3_top.xdc

# 开发模式：允许无引脚约束生成比特流（板级引脚确认后删除此行）
set_property SEVERITY {Warning} [get_drc_checks UCIO-1]

set_property top w3_top [current_fileset]
synth_design -top w3_top -part $PART
opt_design
place_design
route_design

report_utilization -file $OD/utilization.rpt
report_timing_summary -file $OD/timing.rpt

write_bitstream -force $OD/w3_top.bit
puts "Bitstream: $OD/w3_top.bit"
