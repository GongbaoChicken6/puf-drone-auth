# tri_state_probe.tcl -- 3-state scheduled probe (bit pre-programmed by vivado)
connect
catch {targets -set -filter {name =~ "*Cortex-A9*#0"}}
catch {targets -set -filter {name =~ "APU*"}}
after 300
catch {source "D:/vivado/2026.1/data/embeddedsw/sample_sdt/zc706/sdt/ps7_init.tcl"}
catch {ps7_init}
stop
puts "T=[clock seconds] STATE_A_DRIVE_LOW (20s) OEN=[mrd 0xE000A288 1]"
mwr 0xE000A284 0x3
mwr 0xE000A288 0x3
mwr 0xE000A048 0x2
after 20000
mwr 0xE000A288 0x2
puts "T=[clock seconds] STATE_B_RELEASE (20s) OEN=[mrd 0xE000A288 1]"
after 20000
mwr 0xE000A288 0x3
mwr 0xE000A048 0x3
puts "T=[clock seconds] STATE_C_DRIVE_HIGH (15s)"
after 15000
mwr 0xE000A048 0x2
puts "T=[clock seconds] DONE_BACK_TO_DRIVE_LOW"
exit 0