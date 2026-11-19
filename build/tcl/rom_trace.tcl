# ROM失败痕迹:停APU读PC+OCM低区(boot已失败,停住安全)
connect -url tcp:localhost:3121
targets -set -filter {name =~ "APU*"}
stop
puts "=== APU PC/寄存器 ==="
puts "PC: [rrd pc]"
puts "SP: [rrd sp]"
puts "R0: [rrd r0]"
puts "=== REBOOT_STATUS(0xF8000258已是BOOT_MODE;再读几个SLCR状态) ==="
foreach a {0xF8000298 0xF8000344 0xF8000614} {
  puts "SLCR $a: [mrd $a]"
}
puts "=== OCM低区(0xFFFC0000起,ROM错误码惯例区) ==="
foreach a {0xFFFC0000 0xFFFC0004 0xFFFC0008 0xFFFC000C 0xFFFC0010} {
  puts "OCM $a: [mrd $a]"
}
puts "ROM_TRACE_DONE"
exit
