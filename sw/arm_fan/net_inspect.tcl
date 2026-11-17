open_checkpoint {D:/puf-drone-auth/build/board_zc706_arm_dbg/post_route.dcp}
set p [get_ports ext_fan]
puts "PORT: $p"
set n [get_nets -of_objects $p -quiet]
puts "NET: $n"
if {[llength $n]} {
    set drv [get_pins -of_objects $n -filter {DIRECTION == OUT} -quiet]
    puts "DRIVER_PIN: $drv"
    foreach d $drv { set c [get_cells -of_objects $d]; puts "  DRIVER_CELL: $c REF=[get_property REF_NAME $c]" }
    set loads [get_pins -of_objects $n -filter {DIRECTION == IN} -quiet]
    puts "LOADS: $loads"
}
foreach c [get_cells -hier -filter {REF_NAME =~ OBUFT* || REF_NAME =~ IOBUF*}] { puts "TRIBUF: $c" }
set ps7 [get_cells -hier -filter {REF_NAME =~ *processing* || REF_NAME =~ *PS7* || REF_NAME =~ *ps7*}]
puts "PS7CELL: $ps7"
foreach pin [get_pins -of_objects $ps7 -quiet] {
    if {[string match *GPIO* $pin]} {
        set nn [get_nets -of_objects $pin -quiet]
        puts "PS7GPIO: $pin -> $nn"
    }
}
exit 0