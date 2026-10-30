open_hw_manager
connect_hw_server -url localhost:3121
set tgs [get_hw_targets -quiet]
puts "TARGET_COUNT: [llength $tgs]"
foreach t $tgs {
    puts "TARGET: $t"
    current_hw_target $t
    if {[catch {open_hw_target} err]} { puts "  OPEN_ERR: $err"; continue }
    foreach d [get_hw_devices -quiet] { puts "  DEVICE: $d" }
    catch {close_hw_target}
}
disconnect_hw_server
exit 0
