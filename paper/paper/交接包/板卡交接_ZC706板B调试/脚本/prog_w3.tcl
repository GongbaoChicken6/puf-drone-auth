open_hw_manager
connect_hw_server -url localhost:3121
open_hw_target
set dev [lindex [get_hw_devices xc7z045_1] 0]
if {[llength $dev] == 0} { puts "ERROR: no xc7z045_1"; exit 3 }
set bit [file normalize [file join [file dirname [info script]] .. 比特流 w3_top_zc706.bit]]
set_property PROGRAM.FILE $bit $dev
program_hw_devices $dev
refresh_hw_device -update_hw_probes false $dev
puts "W3_PROGRAM_OK"
close_hw_target
disconnect_hw_server