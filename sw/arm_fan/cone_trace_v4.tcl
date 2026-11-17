open_checkpoint D:/puf-drone-auth/build/board_zc706_arm_v4/post_route.dcp
proc trace_up {pin depth} {
    if {$depth > 6} { return }
    set net [get_nets -of_objects $pin -quiet]
    if {![llength $net]} { return }
    set drv [get_pins -of_objects $net -filter {DIRECTION == OUT} -quiet]
    foreach d $drv {
        set c [get_cells -of_objects $d]
        set ref [get_property REF_NAME $c]
        puts "CONE $depth $c $ref"
        if {[string match {LUT*} $ref]} {
            foreach ip [get_pins -of_objects $c -filter {DIRECTION == IN} -quiet] {
                set n2 [get_nets -of_objects $ip -quiet]
                puts "IN $depth [get_property NAME $ip] net=[get_property NAME $n2]"
                trace_up $ip [expr {$depth + 1}]
            }
        }
    }
}
puts {=== V4 T_CONE (expect: led_result logic) ===}
trace_up [get_pins ext_fan_OBUFT_inst/T] 0
puts {=== V4 I_CONE (expect: const/GND) ===}
trace_up [get_pins ext_fan_OBUFT_inst/I] 0
exit 0