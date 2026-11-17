# state_a.tcl -- drive state per design (OEN bit0=1)
connect
catch {targets -set -filter {name =~ "*Cortex-A9*#0"}}
catch {targets -set -filter {name =~ "APU*"}}
after 200
catch {source "D:/vivado/2026.1/data/embeddedsw/sample_sdt/zc706/sdt/ps7_init.tcl"}
catch {ps7_init}
stop
mwr 0xE000A284 0x3   ;# DIRM_2: bit0/1 output
mwr 0xE000A288 0x3   ;# OEN_2 : bit0=1 bit1=1
mwr 0xE000A048 0x2   ;# DATA_2: sel=1 pwm=0
puts "STATE_A_SET DIRM=[mrd 0xE000A284 1] OEN=[mrd 0xE000A288 1] DATA=[mrd 0xE000A048 1]"
exit 0