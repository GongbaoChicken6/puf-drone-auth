# arm_fan_debug.tcl -- diagnose xsdb dow failure
connect
puts "TARGETS: [targets]"
if {[catch {targets -set -filter {name =~ "*Cortex-A9*#0"}} e]} {
    puts "SEL_ERR: $e"
    catch {targets -set -filter {name =~ "APU*"}}
}
after 300
puts "CURRENT: [targets]"
set PS7INIT "D:/vivado/2026.1/data/embeddedsw/sample_sdt/zc706/sdt/ps7_init.tcl"
puts "PS7FILE: [file exists $PS7INIT]"
if {[catch {source $PS7INIT} e]} { puts "SRC_ERR: $e" } else { puts "SRC_OK" }
puts "PROCS: [info procs ps7*]"
if {[catch {ps7_init} e]} { puts "PS7_ERR: $e" } else { puts "PS7_INIT_DONE" }
after 300
if {[catch {stop} e]} { puts "STOP_ERR: $e" } else { puts "STOP_OK" }
if {[catch {dow "D:/puf-drone-auth/sw/arm_fan/arm_fan_test.elf"} e]} {
    puts "DOW_ERR: $e"
} else {
    puts "DOW_OK"
    con
    after 500
    puts "ARM_FAN_TEST_OK"
}
exit 0