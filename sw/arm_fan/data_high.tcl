# data_high.tcl -- DATA bit0=1 (driven HIGH test, 30s window)
connect
catch {targets -set -filter {name =~ "*Cortex-A9*#0"}}
catch {targets -set -filter {name =~ "APU*"}}
after 300
catch {source "D:/vivado/2026.1/data/embeddedsw/sample_sdt/zc706/sdt/ps7_init.tcl"}
catch {ps7_init}
stop
mwr 0xE000A284 0x3
mwr 0xE000A288 0x3
mwr 0xE000A048 0x3
puts "T=[clock seconds] DATA_ALL_ONES (30s window)"
after 30000
mwr 0xE000A048 0x2
puts "T=[clock seconds] DONE_BACK_LOW"
exit 0