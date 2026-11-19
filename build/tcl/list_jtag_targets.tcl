open_hw_manager
connect_hw_server -url localhost:3121
set ts [get_hw_targets -quiet]
puts "TARGET_COUNT=[llength $ts]"
foreach t $ts { puts "TARGET: $t" }
disconnect_hw_server
close_hw_manager
puts "LIST_DONE"
exit
