open_checkpoint {D:/puf-drone-auth/build/board_zc706_arm_v3/post_route.dcp}
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
                set n2n [get_property NAME $n2]
                set n2d 0
                if {[llength $n2]} {
                    set src [get_pins -of_objects $n2 -filter {DIRECTION == OUT} -quiet]
                    set n2d [llength $src]
                }
                puts "IN $depth [get_property NAME $ip] net=$n2n srcs=$n2d"
                trace_up $ip [expr {$depth + 1}]
            }
        }
    }
}
puts {=== T_CONE ===}
trace_up [get_pins ext_fan_OBUFT_inst/T] 0
puts {=== I_CONE ===}
trace_up [get_pins ext_fan_OBUFT_inst/I] 0
exit 0