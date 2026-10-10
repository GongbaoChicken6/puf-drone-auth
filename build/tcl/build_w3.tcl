# build_w3.tcl -- W3 设计构建（dev 模式：top=w3_top、无引脚约束、DRC 豁免）
# 上板请用 build_w3_board.tcl（wrapper 顶层 + clk_wiz_0 + w3_top.xdc，无豁免）
set PART xc7z020clg484-1
set OD D:/puf-drone-auth/build/vivado/w3_bitstream
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

set_property top w3_top [current_fileset]
synth_design -top w3_top -part $PART
opt_design
place_design
route_design

# Dev mode: allow unconstrained IO + default IO standard (remove when pins confirmed)
set_property SEVERITY {Warning} [get_drc_checks UCIO-1]
set_property SEVERITY {Warning} [get_drc_checks NSTD-1]

report_utilization -file $OD/utilization.rpt
write_bitstream -force $OD/w3_top.bit
puts "BITSTREAM_SUCCESS"
