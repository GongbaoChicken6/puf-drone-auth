# arm_fan_real_dbg.tcl -- load REAL elf with full diagnostics
connect
puts "CONN_OK"
if {[catch {targets -set -filter {name =~ "*Cortex-A9*#0"}} e]} { catch {targets -set -filter {name =~ "APU*"}} }
after 300
puts "CURRENT: [targets]"
set PS7INIT "D:/vivado/2026.1/data/embeddedsw/sample_sdt/zc706/sdt/ps7_init.tcl"
if {[catch {source $PS7INIT} e]} { puts "SRC_ERR: $e" }
if {[catch {ps7_init} e]} { puts "PS7_ERR: $e" } else { puts "PS7_INIT_DONE" }
after 200
catch {stop}
if {[catch {dow "D:/puf-drone-auth/sw/arm_fan/arm_fan.elf"} e]} {
    puts "DOW_ERR: $e"
} else {
    puts "DOW_OK"
    con
    after 800
    puts "ARM_FAN_OK"
}
exit 0