create_project -in_memory -part xc7z045ffg900-2
foreach cr [get_clock_regions] {
  puts "CRGRID $cr : [get_property GRID_RANGES [get_clock_regions $cr]]"
}
exit
