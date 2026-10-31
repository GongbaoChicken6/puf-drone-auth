# query_targets.tcl -- 列出当前可见 JTAG 目标（只读，不烧写）
open_hw_manager
connect_hw_server -url localhost:3121
set ts [get_hw_targets -quiet]
if {[llength $ts] == 0} { puts "NO_TARGETS" } else { foreach t $ts { puts "TARGET: $t" } }
close_hw_manager
exit
