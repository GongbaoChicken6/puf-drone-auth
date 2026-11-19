# 干跑:验证器件/连接/cfgmem属性设置链路，不真正烧写
set ::IMG  "D:/puf-drone-auth/build/BOOT_v3.bin"
set ::PART "s25fl128s-3.3v-qspi-x4-dual_stacked"
if {![file exists $::IMG]} { puts "ERR_IMG"; exit 1 }
puts "IMG_OK [file size $::IMG] bytes"
puts "PART_OK [get_cfgmem_parts $::PART]"
open_hw_manager
connect_hw_server -url localhost:3121
open_hw_target
set dev [lindex [get_hw_devices xc7z045*] 0]
if {$dev eq ""} { puts "ERR_NO_DEV"; exit 1 }
puts "DEV_OK $dev"
current_hw_device $dev
refresh_hw_device -update_hw_probes false $dev
catch {
    set old [get_property PROGRAM.HW_CFGMEM $dev]
    if {$old ne ""} { delete_hw_cfgmem -hw_cfgmem $old }
}
create_hw_cfgmem -hw_device $dev -mem_dev [lindex [get_cfgmem_parts $::PART] 0]
set cfg [get_property PROGRAM.HW_CFGMEM $dev]
set_property PROGRAM.ADDRESS_RANGE {use_file} $cfg
set_property PROGRAM.FILES [list $::IMG] $cfg
set_property PROGRAM.ERASE 1 $cfg
set_property PROGRAM.CFG_PROGRAM 1 $cfg
set_property PROGRAM.VERIFY 1 $cfg
puts "CFG_OK $cfg"
puts "FILES=[get_property PROGRAM.FILES $cfg]"
close_hw_manager
puts "DRYRUN_OK"
