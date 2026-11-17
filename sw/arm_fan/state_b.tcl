# state_b.tcl -- release state (OEN bit0=0)
connect
catch {targets -set -filter {name =~ "*Cortex-A9*#0"}}
catch {targets -set -filter {name =~ "APU*"}}
after 200
catch {source "D:/vivado/2026.1/data/embeddedsw/sample_sdt/zc706/sdt/ps7_init.tcl"}
catch {ps7_init}
stop
mwr 0xE000A284 0x3
mwr 0xE000A288 0x2   ;# OEN bit0=0 = 释放
mwr 0xE000A048 0x2
puts "STATE_B_SET OEN=[mrd 0xE000A288 1]"
exit 0