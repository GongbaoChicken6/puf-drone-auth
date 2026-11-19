proc safemrd {name addr} {
  if {[catch {set v [mrd $addr]} err]} { puts "$name ($addr): ERROR $err" } else { puts "$name ($addr): $v" }
}
connect -url tcp:localhost:3121
targets -set -filter {name =~ "APU*"}
catch {stop}
safemrd IRQ_STAT     0xE000D004
safemrd RX_THRESH    0xE000D020
safemrd TX_THRESH    0xE000D024
safemrd TXD_00_03    0xE000D028
safemrd RXD_00_03    0xE000D030
safemrd SLAVE_IDLE   0xE000D018
safemrd TXD_04_07    0xE000D02C
safemrd LQSPI_CFG    0xE000D0A0
safemrd LIN_0xFC000000 0xFC000000
safemrd LIN_0xFC000004 0xFC000004
safemrd LIN_0xFC000010 0xFC000010
safemrd LINUP_0xFE000000 0xFE000000
safemrd QSPI_CFG     0xE000D000
puts "PROBE3_DONE"
exit
