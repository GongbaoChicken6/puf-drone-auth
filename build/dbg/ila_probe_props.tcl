# ila_probe_props.tcl — 枚举 hw_ila/hw_probe 属性名（板已在跑 ILA bit，不重烧）
open_hw_manager
connect_hw_server -url localhost:3121
open_hw_target
set dev [lindex [get_hw_devices xc7z045_1] 0]
if {[llength $dev] == 0} { puts "ERROR: no device"; exit 3 }
set_property PROBES.FILE {D:/puf-drone-auth/build/board_zc706_ila_tx/ila_tx.ltx} $dev
refresh_hw_device -update_hw_probes true $dev
set ila [lindex [get_hw_ilas] 0]
if {[llength $ila] == 0} { puts "ERROR: no ila"; exit 7 }
set p_tx [get_hw_probes -of_objects $ila -filter {NAME =~ *radio_txd*}]
puts "===ILA_PROPS_BEGIN==="
catch { report_property $ila }
puts "===ILA_PROPS_END==="
puts "===PROBE_PROPS_BEGIN==="
catch { report_property $p_tx }
puts "===PROBE_PROPS_END==="
close_hw_target
disconnect_hw_server
