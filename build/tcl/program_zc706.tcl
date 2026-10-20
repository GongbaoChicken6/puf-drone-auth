# program_zc706.tcl -- ZC706 比特流烧写（Vivado Hardware Manager 批处理，带防御）
# 用法: vivado -mode batch -source build\tcl\program_zc706.tcl -tclargs <bit> [hw_target_serial]
#   例:  D:\vivado\2026.1\Vivado\bin\vivado.bat -mode batch -source build\tcl\program_zc706.tcl \
#          -tclargs build\board_zc706\w3_top_zc706.bit
#   双板同接一台 PC 时传序列号（get_hw_targets 里 Digilent/<serial> 的 serial 段）二选一。
# 前置（板端）：SW4=01（板载 USB JTAG）、SW11=00000（JTAG 启动）、板已上电、Micro-B 插「JTAG」口。
# 说明：JTAG 烧写是易失的——断电后比特流丢失，重新上电需再次烧写（SW11=JTAG 启动模式所致）。
set BIT [lindex $argv 0]
set SN  [lindex $argv 1]
if {$BIT eq ""} { puts "ERROR: 用法 program_zc706.tcl <bit> [serial]"; exit 2 }
if {![file exists $BIT]} { puts "ERROR: bit 文件不存在: $BIT"; exit 2 }
puts "PROGRAM: 目标 $BIT"
open_hw_manager
connect_hw_server -url localhost:3121
set ts [get_hw_targets -quiet]
if {[llength $ts] == 0} { puts "ERROR: 未找到 JTAG 目标（检查电源/USB/驱动/SW4=01?）"; exit 3 }
if {$SN ne ""} {
    set ts [lsearch -all -inline -glob $ts *$SN*]
    if {[llength $ts] == 0} { puts "ERROR: 序列号 $SN 无匹配 target"; exit 4 }
}
if {[llength $ts] > 1} { puts "ERROR: 多个 target，请传序列号二选一: $ts"; exit 5 }
open_hw_target [lindex $ts 0]
set dev [lindex [get_hw_devices] 0]
if {[llength $dev] == 0} { puts "ERROR: 打开 target 后未发现 hw_device"; exit 6 }
if {[get_property PART $dev] ne "xc7z045ffg900"} { puts "ERROR: PART 不符: [get_property PART $dev]"; exit 7 }
set_property PROGRAM.FILE $BIT $dev
program_hw_devices $dev
refresh_hw_device $dev
puts "PROGRAM_OK: [get_property PART $dev] <- $BIT"
close_hw_target
disconnect_hw_server
close_hw_manager
