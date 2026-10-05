# measure_w1.tcl —— 烧板并自动轮询 VIO 读数，存 CSV
# 用法: vivado -mode batch -source measure_w1.tcl -tclargs <bit 文件> <读数次数> <输出 csv>
set BIT [lindex $argv 0]
set N   [lindex $argv 1]
set CSV [lindex $argv 2]
if {$BIT eq "" || $N eq "" || $CSV eq ""} { puts "ERROR: 用法 measure_w1.tcl <bit> <次数> <csv>"; exit 2 }

open_hw_manager
connect_hw_server -url localhost:3121
set ts [get_hw_targets -quiet]
if {[llength $ts] == 0} { puts "ERROR: 未找到 JTAG 目标（检查电源/USB/驱动）"; exit 3 }
open_hw_target
set devs [get_hw_devices]
set dev [lindex $devs 0]
set_property PROGRAM.FILE $BIT $dev
program_hw_devices $dev
refresh_hw_device $dev

set vio [lindex [get_hw_vios -quiet] 0]
if {$vio eq ""} { puts "ERROR: 未找到 VIO（确认烧的是含 vio_0 的 bit）"; exit 4 }
set probe [get_hw_probes probe_in0 -of_objects $vio]

set fp [open $CSV w]
puts $fp "timestamp,probe_in0_hex,probe_in0_dec"
puts "开始轮询 $N 次（每 15 秒一次）..."
for {set i 0} {$i < $N} {incr i} {
    after 15000
    refresh_hw_device $dev
    set v [get_property VALUE $probe]
    set d [expr 0x$v]
    set ts [clock format [clock seconds] -format "%Y-%m-%d %H:%M:%S"]
    puts $fp "$ts,0x$v,$d"
    puts "  [expr $i+1]/$N : 0x$v ($d)"
    flush $fp
}
close $fp
close_hw_target
disconnect_hw_server
puts "CSV 已保存: $CSV"