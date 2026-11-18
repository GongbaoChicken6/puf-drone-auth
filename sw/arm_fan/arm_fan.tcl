# arm_fan.tcl -- XSDB 加载脚本：ps7_init + dow + con（demo_start.ps1 链式调用）
# 哨兵: ARM_FAN_OK
# 2026-11-18 修复：①APU 是组目标,dow 会 "invalid context"——必须选到 Cortex-A9 核;
#   ②核已 Suspended 时 stop 抛 "Already stopped"——包 catch。(板上两次复现)
set REPO [file normalize [file join [file dirname [info script]] ../..]]
connect
# 核优先,逐级回退(老 xsdb 树/无 ps7 场景仍可用)
if {[catch {targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0"}}] &&
    [catch {targets -set -filter {name =~ "*Cortex*#0"}}]} {
    targets -set -filter {name =~ "APU*"}
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
catch {stop}          ;# 已挂起的核再 stop 会抛 Already stopped,不致命
after 200
dow "$REPO/sw/arm_fan/arm_fan.elf"
con
after 500
puts "ARM_FAN_OK"
exit 0
