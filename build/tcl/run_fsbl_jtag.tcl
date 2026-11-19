# JTAG手动加载FSBL并运行 → 如果DS35闪 = 硬件OK，问题在ROM
connect -url tcp:localhost:3121
targets -set -filter {name =~ "APU*"}
stop
puts "=== 加载FSBL到OCM ==="
dow D:/puf-drone-auth/build/vitis_qspi3_192337/zc706_qspi/zynq_fsbl/build/fsbl.elf
puts "=== FSBL已加载, 启动运行 ==="
con
after 5000
puts "=== 5秒后检查PC ==="
stop
puts "PC: [rrd pc]"
puts "R0: [rrd r0]"
con
puts "FSBL_RUNNING"
exit
