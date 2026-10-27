open_hw_manager
connect_hw_server -url localhost:3121
open_hw_target
set dev [lindex [get_hw_devices xc7z045_1] 0]
if {[llength $dev] == 0} { puts "ERROR: no xc7z045_1"; exit 3 }
set_property PROGRAM.FILE {D:/puf-drone-auth/build/board_zc706_txmulti/txmulti.bit} $dev
program_hw_devices $dev
refresh_hw_device -update_hw_probes false $dev
puts "TXMULTI_PROGRAM_OK"
close_hw_target
disconnect_hw_server
