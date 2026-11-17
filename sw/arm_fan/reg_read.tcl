# reg_read.tcl -- read back PS GPIO registers to verify ELF execution
connect
catch {targets -set -filter {name =~ "*Cortex-A9*#0"}}
catch {targets -set -filter {name =~ "APU*"}}
after 200
catch {source "D:/vivado/2026.1/data/embeddedsw/sample_sdt/zc706/sdt/ps7_init.tcl"}
catch {ps7_init}
catch {stop}
puts "DIRM_2(0x284): [mrd 0xE000A284 1]"
puts "OEN_2 (0x288): [mrd 0xE000A288 1]"
puts "DATA_2(0x048): [mrd 0xE000A048 1]"
puts "DATA2RO(0x68): [mrd 0xE000A068 1]"
catch {con}
exit 0