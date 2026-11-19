open_hw_manager
connect_hw_server -url localhost:3121
set ts [get_hw_targets -quiet]
puts "TARGETS=[llength $ts]"
set t [lindex $ts 0]
if {$t eq ""} { puts "NO_TARGET"; exit 1 }
catch {open_hw_target $t} oerr
puts "OPEN_ERR=$oerr"
set devs [get_hw_devices -quiet]
puts "DEVICE_COUNT=[llength $devs]"
foreach d $devs {
  puts "DEV: $d PART=[get_property PART $d]"
}
# PL是否已配置(有设计): 尝试读USERCODE/IDCODE属性
foreach d $devs {
  if {[catch {set uc [get_property REGISTER.USERCODE $d]} e]} { set uc "N/A($e)" }
  puts "USERCODE $d: $uc"
}
disconnect_hw_server
close_hw_manager
puts "CHAIN_DONE"
exit
