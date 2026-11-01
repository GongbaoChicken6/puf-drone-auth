create_project -in_memory -part xc7z045ffg900-2
read_verilog D:/puf-drone-auth/data/d1_evidence/rootcause/review/dummy.v
synth_design -top dummy -part xc7z045ffg900-2
foreach cr {X0Y6 X1Y0 X1Y1 X0Y0} {
  set ss [get_property NAME [get_sites -of_objects [get_clock_regions $cr] -filter {SITE_TYPE =~ SLICE*}]]
  set minx 99999; set maxx -1; set miny 99999; set maxy -1
  foreach s $ss {
    if {[scan $s "SLICE_X%dY%d" x y] == 2} {
      if {$x<$minx} {set minx $x}; if {$x>$maxx} {set maxx $x}; if {$y<$miny} {set miny $y}; if {$y>$maxy} {set maxy $y} } }
  puts "CRBOUND $cr : SLICE_X${minx}Y${miny} .. SLICE_X${maxx}Y${maxy} (nsites=[llength $ss]) sample=[lindex $ss 0],[lindex $ss 500]"
}
exit
