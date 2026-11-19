# QSPI启动诊断v2:全非侵入(不stop,纯总线读)——可在FSBL运行中安全执行
connect -url tcp:localhost:3121
puts "TARGETS_RAW: [targets]"
if {[catch {targets -set -filter {name =~ "APU*"}} err]} {
  puts "APU_ABSENT: $err"
} else {
  puts "APU_OK"
  puts "BOOT_MODE(0xF8000258): [mrd 0xF8000258]"
  puts "=== QSPI线性窗口(下片0地址,期望AA995566头) ==="
  foreach a {0xFC000000 0xFC000004} { puts "LIN $a: [mrd $a]" }
  puts "=== OCM 0xFFFC0000(FSBL居留痕迹) ==="
  foreach a {0xFFFC0000 0xFFFC0100 0xFFFC1000} { puts "OCM $a: [mrd $a]" }
}
puts "DIAG2_DONE"
exit
