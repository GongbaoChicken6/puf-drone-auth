
create_project -in_memory -part xc7z045ffg900-2
set fh [open tiny.v w]
puts $fh "module tiny(input a, output y); assign y = ~a; endmodule"
close $fh
read_verilog tiny.v
synth_design -top tiny -part xc7z045ffg900-2
create_pblock pb_rings_seed2
resize_pblock pb_rings_seed2 -add [list "CLOCKREGION_X1Y0:CLOCKREGION_X1Y0"]
puts "PB_GRID_RANGES: [get_property GRID_RANGES [get_pblocks pb_rings_seed2]]"
puts "PB_CONTAINMENT: [get_property CONTAINMENT_RANGES [get_pblocks pb_rings_seed2]]"
foreach s {SLICE_X134Y50 SLICE_X135Y50 SLICE_X140Y51 SLICE_X141Y51 SLICE_X130Y49 SLICE_X156Y0} {
    set o [get_sites -quiet $s]
    puts "PB_PROBE $s region=[get_property CLOCK_REGION $o]"
}
exit 0
