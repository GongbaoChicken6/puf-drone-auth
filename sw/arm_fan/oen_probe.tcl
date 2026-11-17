# oen_probe.tcl -- halt CPU, flip OEN bit0, hold for observation
connect
catch {targets -set -filter {name =~ "*Cortex-A9*#0"}}
catch {targets -set -filter {name =~ "APU*"}}
after 200
catch {source "D:/vivado/2026.1/data/embeddedsw/sample_sdt/zc706/sdt/ps7_init.tcl"}
catch {ps7_init}
stop
puts "before: OEN_2=[mrd 0xE000A288 1]"
mwr 0xE000A288 0x00000002
puts "after : OEN_2=[mrd 0xE000A288 1]  (bit0 cleared -> observation window)"
# 保持停核+寄存器状态 25 秒供观察
after 25000
puts "PROBE_DONE"
exit 0