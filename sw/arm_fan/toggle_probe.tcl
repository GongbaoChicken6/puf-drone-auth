# toggle_probe.tcl -- 8s 周期交替 OEN=1/OEN=0，共 6 润（~96s），用户盯表看是否来回跳
connect
catch {targets -set -filter {name =~ "*Cortex-A9*#0"}}
catch {targets -set -filter {name =~ "APU*"}}
after 300
catch {source "D:/vivado/2026.1/data/embeddedsw/sample_sdt/zc706/sdt/ps7_init.tcl"}
catch {ps7_init}
stop
mwr 0xE000A284 0x3
mwr 0xE000A048 0x2
for {set i 1} {$i <= 6} {incr i} {
    mwr 0xE000A288 0x3
    puts "T=[clock seconds] CYC$i OEN=1"
    after 8000
    mwr 0xE000A288 0x2
    puts "T=[clock seconds] CYC$i OEN=0"
    after 8000
}
mwr 0xE000A288 0x2
puts "T=[clock seconds] TOGGLE_DONE (final OEN=0)"
exit 0