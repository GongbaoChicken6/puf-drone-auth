connect
after 500
# 列出全部目标，找 Cortex-A9
set tgts [targets]
puts "ALL: $tgts"
targets 2
puts "SELECTED: [targets]"
after 300
catch {source "D:/vivado/2026.1/data/embeddedsw/sample_sdt/zc706/sdt/ps7_init.tcl"}
catch {ps7_init}
after 200
catch {stop}
if {[catch {dow "D:/puf-drone-auth/sw/arm_fan/flight_ctrl.elf"} e]} {
    puts "DOW_ERR: $e"
} else {
    puts "DOW_OK"
    con
    after 1000
    puts "FLIGHT_CTRL_OK"
}
exit 0