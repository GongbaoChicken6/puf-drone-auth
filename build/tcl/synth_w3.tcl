# OOC synthesis of W3 protocol modules
# Usage: vivado -mode batch -source build/tcl/synth_w3.tcl
set PART xc7z020clg484-1
set OD D:/puf-drone-auth/build/vivado/w3_synth
file mkdir $OD

create_project -force w3_synth $OD -part $PART

add_files [list \
    D:/puf-drone-auth/src/rtl/common/crc16_mcrf4xx.v \
    D:/puf-drone-auth/src/rtl/common/mavlink_frame.v \
    D:/puf-drone-auth/src/rtl/common/frame_parser.v \
    D:/puf-drone-auth/src/rtl/common/byte_fifo.v \
    D:/puf-drone-auth/src/rtl/common/uart_tx.v \
    D:/puf-drone-auth/src/rtl/common/uart_rx.v \
    D:/puf-drone-auth/src/rtl/w3_protocol/terminal_fsm.v \
    D:/puf-drone-auth/src/rtl/w2_array/ro_array.v \
    D:/puf-drone-auth/src/rtl/w2_array/challenge_decode.v \
    D:/puf-drone-auth/src/rtl/w1_ratio/ro_ring.v \
    D:/puf-drone-auth/src/rtl/w1_ratio/ro_div.v \
]

# Set top to terminal_fsm for full W3 stack synthesis
set_property top terminal_fsm [current_fileset]

# OOC synthesis
synth_design -top terminal_fsm -part $PART -mode out_of_context

# Reports
report_utilization -file $OD/utilization.rpt
report_timing_summary -file $OD/timing.rpt
report_power -file $OD/power.rpt

puts "UTILIZATION:"
puts [report_utilization -return_string]
puts "TIMING:"
puts [report_timing_summary -return_string]