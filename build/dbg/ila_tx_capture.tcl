# ila_tx_capture.tcl — 烧 ILA 判别 bit + 布防 uart_tx_active==1 触发 + 等触发 + 落盘
# 用法：vivado -mode batch -source build/dbg/ila_tx_capture.tcl（板保持上电、JTAG 连接）
# 标记：ILA_TX_ARMED（可按 SW7）→ ILA_TX_CAPTURED（CSV 已写）
open_hw_manager
connect_hw_server -url localhost:3121
open_hw_target
set dev [lindex [get_hw_devices xc7z045_1] 0]
if {[llength $dev] == 0} { puts "ERROR: no xc7z045_1"; exit 3 }
set_property PROBES.FILE {D:/puf-drone-auth/build/board_zc706_ila_tx/ila_tx.ltx} $dev
set_property PROGRAM.FILE {D:/puf-drone-auth/build/board_zc706_ila_tx/ila_tx.bit} $dev
program_hw_devices $dev
refresh_hw_device -update_hw_probes true $dev
set ila [lindex [get_hw_ilas] 0]
if {[llength $ila] == 0} { puts "ERROR: no hw_ila after program"; exit 7 }
puts "ILAS: $ila"
set allp [get_hw_probes -of_objects $ila]
puts "PROBES: $allp"
set_property CONTROL.TRIGGER_POSITION 512 $ila
catch {set_property CONTROL.CAPTURE_MODE ALWAYS $ila}
set p_tx [get_hw_probes -of_objects $ila -filter {NAME =~ *radio_txd*}]
if {[llength $p_tx] != 1} { puts "ERROR: radio_txd probe not found in: $allp"; exit 7 }
set_property TRIGGER_COMPARE_VALUE {eq1'b0} $p_tx
run_hw_ila $ila
puts "ILA_TX_ARMED"
# 阻塞等待触发（用户按 SW7 后 tx 引擎启动即触发；深度 16384@100MHz≈164µs）
wait_on_hw_ila $ila
write_hw_ila_data -force -csv_file {D:/puf-drone-auth/build/board_zc706_ila_tx/ila_tx_cap.csv} $ila
puts "ILA_TX_CAPTURED"
close_hw_target
disconnect_hw_server
