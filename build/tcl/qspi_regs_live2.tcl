connect -url tcp:localhost:3121
set tl [targets]
puts "TARGET_LIST: $tl"
if {[catch {targets -set -filter {name =~ "APU*"}} err]} {
  puts "APU filter failed: $err"
  if {[catch {targets -set -filter {name =~ "arm_dap*"}} err2]} {
    puts "arm_dap filter failed: $err2"
    targets 2
  }
}
puts "CUR_TARGET: [targets]"
catch {stop} serr
puts "STOP: $serr"
puts "=== LIVE REGS board B (after failed sf probe) ==="
foreach {name addr} {
  QSPI_REF_CTRL 0xF8000158
  APER_CLK      0xF800012C
  IO_PLL_CTRL   0xF8000108
  QSPI_RST_CTRL 0xF800022C
  QSPI_CFG      0xE000D000
  QSPI_STS      0xE000D00C
  QSPI_LQSPI_CFG 0xE000D0A8
  MIO_PIN_00    0xF8000700
  MIO_PIN_01    0xF8000704
  MIO_PIN_02    0xF8000708
  MIO_PIN_05    0xF8000714
  MIO_PIN_06    0xF8000718
  MIO_PIN_08    0xF8000720
  MIO_PIN_09    0xF8000724
  MIO_PIN_10    0xF8000728
  MIO_PIN_13    0xF8000734
} {
  puts "$name ($addr): [mrd $addr]"
}
puts "REGS_DONE"
exit
