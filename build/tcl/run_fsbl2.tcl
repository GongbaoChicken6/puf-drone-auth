connect -url tcp:localhost:3121
# 先做PS软复位
targets -set -filter {name =~ "APU*"}
catch {stop}
catch {rst -psr} rst_err
puts "PS reset: $rst_err"
after 2000
# 重新扫描targets
puts "TARGETS after reset: [targets]"
# 选Cortex-A9 #0
targets -set -filter {name =~ "*Cortex-A9*MPCore #0*"}
puts "Selected: [targets]"
catch {stop}
# 加载FSBL
puts "=== dow FSBL ==="
if {[catch {dow D:/puf-drone-auth/build/vitis_qspi3_192337/zc706_qspi/zynq_fsbl/build/fsbl.elf} dow_err]} {
  puts "DOW_ERROR: $dow_err"
  # 尝试不带路径
  puts "Trying with mrd to verify OCM access..."
  catch {mrd 0xFFFC0000} ocm_test
  puts "OCM test: $ocm_test"
} else {
  puts "DOW_OK"
  con
  after 8000
  stop
  puts "PC after 8s: [rrd pc]"
  con
}
puts "FSBL_TEST_DONE"
exit
