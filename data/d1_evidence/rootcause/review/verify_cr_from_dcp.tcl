open_checkpoint D:/puf-drone-auth/build/board_zc706_seed2/w3_board_seed2.runs/impl_1/w3_top_zc706_routed.dcp
foreach cr [get_clock_regions] {
  puts "CRGRID $cr : [get_property GRID_RANGES [get_clock_regions $cr]]"
}
set ringcells [get_cells -hierarchical -filter {NAME =~ "*u_ro_ring*"}]
puts "RINGCELLS [llength $ringcells]"
foreach c [lrange $ringcells 0 5] { puts "SAMPLESITE $c -> [get_property SITE $c]" }
exit
