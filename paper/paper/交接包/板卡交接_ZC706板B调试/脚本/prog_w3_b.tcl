open_hw_manager
connect_hw_server -url localhost:3121
# 板 B 专用：按线缆序列号 210251A04F2C 定位（区别于板 A 的 210251A0195C）
set tg [get_hw_targets -quiet *210251A04F2C*]
if {[llength $tg] == 0} { puts "ERROR: board-B cable 210251A04F2C not found"; exit 3 }
current_hw_target $tg
open_hw_target
set dev [lindex [get_hw_devices xc7z045_1] 0]
if {[llength $dev] == 0} { puts "ERROR: no xc7z045_1 on board-B target"; exit 3 }
set bit [file normalize [file join [file dirname [info script]] .. 比特流 w3_top_zc706.bit]]
set_property PROGRAM.FILE $bit $dev
program_hw_devices $dev
refresh_hw_device -update_hw_probes false $dev
puts "W3_PROGRAM_OK_BOARD_B"
close_hw_target
disconnect_hw_server
exit 0