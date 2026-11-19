# SPI命令模式直接读flash首32字节(绕过ROM/线性窗口)
# 用QSPI控制器手动发 READ(0x03) + addr 0x000000, 读32字节
connect -url tcp:localhost:3121
targets -set -filter {name =~ "APU*"}
catch {stop}

puts "=== 1. 解锁SLCR + 配QSPI MIO ==="
mwr 0xF8000008 0x0000DF0D
after 5
# QSPI MIO[1:6]: 从我们FSBL的ps7_init(已验证板上生效)
# MIO1-6 = QSPI data/clk/cs, MIO8 = feedback clk
# 直接用FSBL ps7_init验证过的值
# MIO_PIN_01..06 = QSPI function (从ps7_init: 0x1202 for MIO1, 0x0202 for MIO2-6)
mwr 0xF8000704 0x00001202  ;# MIO1 = qspi_io0
mwr 0xF8000708 0x00000202  ;# MIO2 = qspi_io1  
mwr 0xF800070C 0x00000202  ;# MIO3 = qspi_io2
mwr 0xF8000710 0x00000202  ;# MIO4 = qspi_io3
mwr 0xF8000714 0x00000202  ;# MIO5 = qspi_sclk
mwr 0xF8000718 0x00000202  ;# MIO6 = qspi_ss_b
puts "MIO configured"

puts "=== 2. 开QSPI时钟 ==="
set aper [mrd 0xF800012C]
mwr 0xF800012C 0x01ED044D
after 5
puts "APER: [mrd 0xF800012C]"

puts "=== 3. QSPI控制器复位 + 使能 ==="
# SLCR QSPI_RST_CTRL: assert then deassert
mwr 0xF800022C 0x00000003
after 10
mwr 0xF800022C 0x00000000
after 10
# SPI_ENABLE register (0xE000D00E): bit0=1 to enable SPI
mwr 0xE000D030 0x00000020  ;# RX threshold = 32 bytes
mwr 0xE000D034 0x00000001  ;# TX threshold  
mwr 0xE000D00E 0x00000001  ;# SPI enable
after 5
puts "SPI enabled: [mrd 0xE000D00E]"

puts "=== 4. 配置QSPI控制器 (master, x1, baud_div=4, manual CS+start) ==="
# CONFIG: bit31=1(manual CS), bit30=1(manual start), bit15=0(no loopback), 
#         bit14=1(CS stays low), bits[2:0]=100 (div4 = ~50MHz)
mwr 0xE000D000 0x80048104
after 5
puts "CONFIG: [mrd 0xE000D000]"

puts "=== 5. 清中断 ==="
mwr 0xE000D014 0x000007FF
after 5

puts "=== 6. 发READ(0x03) + addr 0x000000, 读4字节 ==="
# 先发命令+地址(4字节): 03 00 00 00
# 然后切到读模式收4字节
# TX data: READ opcode + 3-byte address
mwr 0xE000D028 0x03000000  ;# TXD: 0x03 + 24-bit address 0x000000

# Manual start (CONFIG bit16)
set cfg [mrd 0xE000D000]
# 重新写CONFIG带manual start bit
mwr 0xE000D000 0x80048105  ;# bit0=1: manual start
after 10

# 等TX完成
set t0 [clock seconds]
while {[clock seconds] - $t0 < 2} {
  set intr [mrd 0xE000D004]
  # TX_FIFO_Half_Empty = bit5
  if {[expr $intr & 0x20]} { break }
}
puts "TX status: [mrd 0xE000D004]"

# 读RX FIFO (可能还没有数据)
after 100
puts "RX status: [mrd 0xE000D00C]"
catch { puts "RX data: [mrd 0xE000D030]" } rx_err
puts "RX result: $rx_err"

puts "=== 7. 尝试更简单方式: 读STATUS和ID ==="
# 读STATUS register (RDSR 0x05)
mwr 0xE000D014 0x000007FF  ;# clear all interrupts
mwr 0xE000D000 0x80048104  ;# reset manual start
mwr 0xE000D028 0x00000005  ;# TXD: RDSR opcode
mwr 0xE000D000 0x80048105  ;# manual start  
after 100
puts "STATUS after RDSR: [mrd 0xE000D004]"
catch { puts "RX after RDSR: [mrd 0xE000D030]" } rx2
puts "RX2: $rx2"

puts "FLASH_SPI_READ_DONE"
exit
