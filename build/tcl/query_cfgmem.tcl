puts "=== s25fl128 parts ==="
foreach p [get_cfgmem_parts *s25fl128*] { puts "  $p" }
puts "=== s25fl (all spansion 128) ==="
foreach p [get_cfgmem_parts *fl128*] { puts "  $p" }
puts "QUERY_DONE"
