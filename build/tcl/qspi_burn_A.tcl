# qspi_burn_A.tcl -- write BOOT_FLIGHT.bin to board A QSPI flash
set SN [lindex $argv 0]
set BIN [lindex $argv 1]
if {$BIN eq ""} { set BIN "D:/puf-drone-auth/build/BOOT_FLIGHT.bin" }
puts "PROGRAM QSPI: SN=$SN BIN=$BIN"
open_hw_manager
connect_hw_server -url localhost:3121
set ts [get_hw_targets -quiet]
set ts [lsearch -all -inline -glob $ts *$SN*]
if {[llength $ts] == 0} { puts "ERROR: no target $SN"; exit 3 }
open_hw_target [lindex $ts 0]
# 创建 QSPI 接口
set cfgmem [create_hw_cfgmem -hw_device [lindex [get_hw_devices] 0] {S25FL128Sxxxxxx0}-x4-none]
set_property PROGRAM.BLANK_CHECK  0 $cfgmem
set_property PROGRAM.ERASE        1 $cfgmem
set_property PROGRAM.CFG_PROGRAM  1 $cfgmem
set_property PROGRAM.VERIFY       1 $cfgmem
set_property PROGRAM.CFG_FILE     $BIN $cfgmem
set_property PROGRAM.UNUSED_PIN_TERMINATION {pull-none} $cfgmem
puts "STARTING QSPI PROGRAM..."
program_hw_cfgmem $cfgmem
puts "QSPI_PROGRAM_OK"
close_hw_target
disconnect_hw_server
close_hw_manager
exit 0