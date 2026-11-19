# 手动开启QSPI线性窗口,直接读flash首地址
# 目的: 绕过ROM,验证flash内容是否正确(0xAA995566 boot header)
connect -url tcp:localhost:3121
targets -set -filter {name =~ "APU*"}
catch {stop}
puts "=== 解锁SLCR ==="
mwr 0xF8000008 0x0000DF0D
after 10
puts "=== 开QSPI控制器时钟 (APER_CLK bit22) ==="
set aper [mrd 0xF800012C]
puts "APER before: $aper"
mwr 0xF800012C 0x01ED044D
after 10
set aper2 [mrd 0xF800012C]
puts "APER after: $aper2"
puts "=== 配置LQSPI (0xE000D0A0) — linear mode, x4, 下片 ==="
# LQSPI_CFG: bit31=enable, bits[1:0]=mode (0=x1,1=x2,2=x4)
# 对于两片stacked,需要设置合适的config
mwr 0xE000D0A0 0x80000003
after 10
puts "LQSPI_CFG: [mrd 0xE000D0A0]"
puts "=== 读flash首地址0xFC000000 (boot header应在) ==="
foreach a {0xFC000000 0xFC000004 0xFC000008 0xFC00000C 0xFC000010 0xFC000014} {
  puts "FLASH $a: [mrd $a]"
}
puts "=== 期望: 第一字=AA995566 (Zynq boot header magic) ==="
puts "FLASH_VERIFY_DONE"
exit
