# ============================================================
# QSPI 烧写脚本 - 板A (SN 210251A0195C) - 生产版镜像
# 用法A(GUI): Vivado -> Tools -> Run Tcl Script -> 选本文件
# 用法B(命令行): vivado -mode batch -source program_qspi_A.tcl
# 用法C(双击): program_qspi_A.bat
# ============================================================
set ::IMG   "D:/puf-drone-auth/build/BOOT_v3.bin"
set ::PART  "s25fl128s-3.3v-qspi-x4-dual_stacked"
set ::DO_VERIFY 1

if {[lsearch [get_cfgmem_parts $::PART] $::PART] < 0} {
    puts "ERROR: 本机 Vivado 无器件 $::PART"
    puts "可用 s25fl128 变体: [get_cfgmem_parts *s25fl128s-3.3v*]"
    exit 1
}

puts "=============================================================="
puts " QSPI 烧写"
puts " 镜像 : $::IMG"
puts " 器件 : $::PART"
puts " 校验 : $::DO_VERIFY"
puts "=============================================================="

open_hw_manager
connect_hw_server -url localhost:3121
open_hw_target
set dev [lindex [get_hw_devices xc7z045*] 0]
if {$dev eq ""} {
    puts "ERROR: 未找到 xc7z045，检查 JTAG/上电"
    exit 1
}
puts "目标: $dev  SN=[get_property REGISTER.CONFIG_CABLE_PRESENT $dev]"
current_hw_device $dev
refresh_hw_device -update_hw_probes false $dev

# 清掉旧 cfgmem(重复运行时)
catch {
    set old [get_property PROGRAM.HW_CFGMEM $dev]
    if {$old ne ""} { delete_hw_cfgmem -hw_cfgmem $old }
}

create_hw_cfgmem -hw_device $dev -mem_dev [lindex [get_cfgmem_parts $::PART] 0]
set cfg [get_property PROGRAM.HW_CFGMEM $dev]
puts "cfgmem: $cfg"

set_property PROGRAM.ADDRESS_RANGE {use_file} $cfg
set_property PROGRAM.FILES [list $::IMG] $cfg
set_property PROGRAM.ERASE 1 $cfg
set_property PROGRAM.CFG_PROGRAM 1 $cfg
set_property PROGRAM.CHECKSUM 0 $cfg
set_property PROGRAM.UNUSED_PIN_TERMINATION {pull-none} $cfg
if {$::DO_VERIFY} { set_property PROGRAM.VERIFY 1 $cfg } else { set_property PROGRAM.VERIFY 0 $cfg }

puts "开始烧写(13.4MB，请等待几分钟)..."
if {[catch {program_hw_cfgmem -hw_cfgmem $cfg} err]} {
    puts "PROGRAM_FAILED: $err"
    exit 2
}
puts "PROGRAM_QSPI_OK"
