
create_project -in_memory -part xc7z045ffg900-2
if {[catch {get_sites -quiet SLICE_X0Y0} e0] || {[llength [get_sites -quiet SLICE_X0Y0]] == 0}} {
    set fh [open tiny.v w]
    puts $fh "module tiny(input a, output y); assign y = ~a; endmodule"
    close $fh
    read_verilog tiny.v
    synth_design -top tiny -part xc7z045ffg900-2
}
puts "GEOM_ALLCR: [lsort [get_clock_regions]]"
set f [open "D:/puf-drone-auth/build/board_zc706_seed2/ring_sites_seed2.rpt" r]
set n 0
array set crcount {}
set outside {}
while {[gets $f line] >= 0} {
    if {[regexp {(SLICE_X\d+Y\d+)\s*$} $line -> sitename]} {
        incr n
        set cr [get_property CLOCK_REGION [get_sites -quiet $sitename]]
        if {$cr eq ""} { set cr NOSITE }
        incr crcount($cr)
        if {$cr ne "X1Y0"} { lappend outside "$sitename=$cr" }
    }
}
close $f
puts "GEOM_SITES_TOTAL: $n"
foreach k [lsort [array names crcount]] { puts "GEOM_REGION_COUNT_$k: $crcount($k)" }
puts "GEOM_OUTSIDE_X1Y0: $outside"
foreach s {SLICE_X100Y49 SLICE_X100Y50 SLICE_X100Y51 SLICE_X130Y49 SLICE_X130Y50 SLICE_X130Y51 SLICE_X130Y99 SLICE_X130Y100 SLICE_X130Y348 SLICE_X130Y349 SLICE_X130Y350 SLICE_X77Y0 SLICE_X78Y0 SLICE_X155Y0 SLICE_X156Y0} {
    set o [get_sites -quiet $s]
    if {[llength $o] > 0} { puts "GEOM_PROBE $s -> [get_property CLOCK_REGION $o]" } else { puts "GEOM_PROBE $s -> NOSITE" }
}
exit 0
