# ila_tx_readout.tcl — 上传板内已捕获的 ILA 数据（不重烧、不复位）
open_hw_manager
connect_hw_server -url localhost:3121
open_hw_target
set dev [lindex [get_hw_devices xc7z045_1] 0]
if {[llength $dev] == 0} { puts "ERROR: no device"; exit 3 }
set_property PROBES.FILE {D:/puf-drone-auth/build/board_zc706_ila_tx/ila_tx.ltx} $dev
refresh_hw_device -update_hw_probes true $dev
set ila [lindex [get_hw_ilas] 0]
if {[llength $ila] == 0} { puts "ERROR: no ila"; exit 7 }
puts "ILA: $ila"
set ud [upload_hw_ila_data $ila]
write_hw_ila_data -force -csv_file {D:/puf-drone-auth/build/board_zc706_ila_tx/ila_tx_cap.csv} $ud
puts "ILA_TX_READOUT_DONE"
close_hw_target
disconnect_hw_server
