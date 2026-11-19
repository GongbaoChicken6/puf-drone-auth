connect -url tcp:localhost:3121
set tl [targets]
puts "TARGETS: $tl"
if {[catch {targets -set -filter {name =~ "*Cortex-A9*MPCore #0*"}} e]} {
  puts "core0 select fail: $e"
  targets -set -filter {name =~ "APU*"}
}
catch {stop}
puts "CUR: [targets]"
foreach r {pc sp r0} {
  if {[catch {set v [rrd $r]} ee]} { puts "$r: ERR $ee" } else { puts "$r: $v" }
}
foreach a {0xF8000298 0xF8000344} { puts "SLCR $a: [mrd $a]" }
foreach a {0xFFFC0000 0xFFFC0004 0xFFFC0008 0xFFFC000C} { puts "OCM $a: [mrd $a]" }
puts "ROM_TRACE2_DONE"
exit
