connect -url tcp:localhost:3121
targets -set -filter {name =~ "APU*"}
catch {stop}
puts "=== MIO pins 0-13 (SLCR) ==="
foreach a {0xF8000700 0xF8000704 0xF8000708 0xF800070C 0xF8000710 0xF8000714 0xF8000718 0xF800071C 0xF8000720 0xF8000724 0xF8000728 0xF800072C 0xF8000730 0xF8000734} {
  puts "MIO $a: [mrd $a]"
}
puts "=== QSPI controller ==="
puts "CONFIG   (0xE000D000): [mrd 0xE000D000]"
puts "IRQ_STAT (0xE000D004): [mrd 0xE000D004]"
puts "IRQ_MASK (0xE000D008): [mrd 0xE000D008]"
puts "IRQ_ENA  (0xE000D00C): [mrd 0xE000D00C]"
puts "IRQ_DIS  (0xE000D010): [mrd 0xE000D010]"
puts "IRQ_GLOB (0xE000D014): [mrd 0xE000D014]"
puts "SPI_ENA  (0xE000D00E): [mrd 0xE000D00E]"
puts "RX_THR   (0xE000D020): [mrd 0xE000D020]"
puts "TX_THR   (0xE000D024): [mrd 0xE000D024]"
puts "MOD_ID   (0xE000D018): [mrd 0xE000D018]"
puts "LQSPI_CFG(0xE000D0A0): [mrd 0xE000D0A0]"
puts "=== LINEAR flash window 0xFC000000 (lower flash) ==="
foreach a {0xFC000000 0xFC000004 0xFC000010} {
  puts "LIN $a: [mrd $a]"
}
puts "=== upper flash linear 0xFE000000 (stacked) ==="
foreach a {0xFE000000} {
  puts "LINUP $a: [mrd $a]"
}
puts "PROBE2_DONE"
exit
