# arm_fan.tcl -- XSDB 加载脚本：ps7_init + dow + con（demo_start.ps1 链式调用）
# 哨兵: ARM_FAN_OK
set REPO [file normalize [file join [file dirname [info script]] ../..]]
connect
if {[catch {targets -set -filter {name =~ "APU*"}} err]} {
    targets -set -filter {name =~ "ARM*#0"}
}
after 300
set PS7INIT "D:/vivado/2026.1/data/embeddedsw/sample_sdt/zc706/sdt/ps7_init.tcl"
if {[file exists $PS7INIT]} {
    source $PS7INIT
    if {[catch {ps7_init} e]} { puts "WARN ps7_init: $e" }
} else {
    puts "WARN ps7_init.tcl not found: $PS7INIT"
}
after 200
stop
dow "$REPO/sw/arm_fan/arm_fan.elf"
con
after 500
puts "ARM_FAN_OK"
exit 0