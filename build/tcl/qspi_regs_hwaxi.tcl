open_hw_manager
connect_hw_server -url localhost:3121
set ts [get_hw_targets -quiet]
set t [lsearch -inline $ts *210251A04F2C*]
if {$t eq ""} { puts "ERROR: board B target not found: $ts"; exit 3 }
open_hw_target $t
set axis [get_hw_axis -quiet]
puts "AXI_DEVS=$axis"
set axi [lindex $axis 0]
if {$axi eq ""} { puts "ERROR: no hw_axi"; exit 4 }
proc rd {axi addrHex} {
  set txn [create_hw_axi_txn this_txn $axi $addrHex read]
  run_hw_axi $txn
  set r [report_hw_axi_txn $txn -return_string]
  delete_hw_axi_txn $txn
  return $r
}
puts "=== LIVE REGS board B (after failed sf probe) ==="
foreach {name addr} {
  QSPI_REF_CTRL 0xF8000158
  APER_CLK      0xF800012C
  IO_PLL_CTRL   0xF8000108
  QSPI_RST_CTRL 0xF800022C
  QSPI_CFG      0xE000D000
  QSPI_STS      0xE000D00C
  LQSPI_CFG     0xE000D0A8
  MIO_PIN_00    0xF8000700
  MIO_PIN_01    0xF8000704
  MIO_PIN_02    0xF8000708
  MIO_PIN_03    0xF800070C
  MIO_PIN_04    0xF8000710
  MIO_PIN_05    0xF8000714
  MIO_PIN_06    0xF8000718
  MIO_PIN_08    0xF8000720
  MIO_PIN_09    0xF8000724
  MIO_PIN_10    0xF8000728
  MIO_PIN_13    0xF8000734
} {
  puts "$name ($addr): [rd $axi $addr]"
}
puts "REGS_DONE"
close_hw_target
disconnect_hw_server
close_hw_manager
exit
