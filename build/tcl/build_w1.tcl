# build_w1.tcl —— W1 工程一键构建（批处理，无需 GUI；源文件须放在纯 ASCII 路径）
# 用法: vivado -mode batch -source build_w1.tcl -tclargs <part> <输出目录> <源文件目录>
set PART [lindex $argv 0]
set OD   [lindex $argv 1]
set SRC  [lindex $argv 2]
if {$PART eq "" || $OD eq "" || $SRC eq ""} { puts "ERROR: 用法 build_w1.tcl <part> <outdir> <srcdir>"; exit 2 }

file mkdir $OD
create_project -force w1_auto $OD -part $PART
add_files [list $SRC/ro_ring.v $SRC/ro_div.v $SRC/ro_ratio_top.v]
add_files -fileset constrs_1 $SRC/w1_ro_waiver.xdc
set_property top ro_ratio_top [current_fileset]

create_ip -name vio -vendor xilinx.com -library ip -module_name vio_0
set_property -dict [list CONFIG.C_NUM_PROBE_IN {1} CONFIG.C_NUM_PROBE_OUT {0} CONFIG.C_PROBE_IN0_WIDTH {32}] [get_ips vio_0]
generate_target all [get_ips vio_0]

launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} { puts "ERROR: run 未完成"; exit 3 }
puts "BITSTREAM: $OD/w1_auto.runs/impl_1/ro_ratio_top.bit"

open_run impl_1
report_utilization -file $OD/utilization.txt
report_timing_summary -file $OD/timing.txt
close_project
puts "BUILD_DONE"