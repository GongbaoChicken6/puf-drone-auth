# QSPI启动失败诊断:启动模式寄存器 + 线性flash窗口 + CPU状态
connect -url tcp:localhost:3121
set tl [targets]
puts "TARGET_LIST: $tl"
if {[catch {targets -set -filter {name =~ "APU*"}} err]} {
  puts "APU select failed: $err"
  targets 1
}
catch {stop} serr
puts "=== BOOT_MODE reg (0xF8000258) —— 板子锁存的真实启动模式 ==="
puts "BOOT_MODE: [mrd 0xF8000258]"
puts "=== QSPI linear window 0xFC000000 (下片0地址,PS域,与PL无关) ==="
foreach a {0xFC000000 0xFC000004 0xFC000008 0xFC000010} {
  puts "LIN $a: [mrd $a]"
}
puts "=== OCM尾部(FSBL若跑过会留痕) & PC ==="
puts "OCM_FFFC: [mrd 0xFFFFFFF0]"
puts "DIAG_DONE"
exit
