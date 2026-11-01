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
# auto-review P3: 变体横幅防烧错（硬校验走预登记 SHA 规约）
if {[string match "*seed2*" $BIT]} { puts "VARIANT: seed2 (layout-variant B, rings->X1Y0) size=[file size $BIT]" } elseif {[string match "*prod*" $BIT]} { puts "VARIANT: PRODUCTION baseline size=[file size $BIT]" } else { puts "VARIANT: UNKNOWN naming -- verify against prereg SHA! size=[file size $BIT]" }
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
set dev ""
foreach d [get_hw_devices] {
    set p [get_property PART $d]
    puts "CHAIN: $d PART=$p"
    if {[string match "xc7z045*" $p]} { set dev $d; break }
}
if {$dev eq ""} { puts "ERROR: JTAG 链上未找到 xc7z045ffg900（链上器件: [get_hw_devices]）"; exit 6 }
if {![string match "xc7z045*" [get_property PART $dev]]} { puts "ERROR: PART 不符: [get_property PART $dev]"; exit 7 }
set_property PROGRAM.FILE $BIT $dev
program_hw_devices $dev
refresh_hw_device $dev
puts "PROGRAM_OK: [get_property PART $dev] <- $BIT"
close_hw_target
disconnect_hw_server
close_hw_manager
