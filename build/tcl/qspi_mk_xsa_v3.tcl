# QSPI XSA v3 - fix BD 41-758: connect FCLK_CLK0 -> M_AXI_GP0_ACLK (2026-11-15 lead)
set root D:/puf-drone-auth
set out $root/build/qspi_xsa_v3
file mkdir $out

create_project -force qspi_ps3 $out -part xc7z045ffg900-2
create_bd_design design_1
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7
set_property -dict [list CONFIG.preset {ZC706}] [get_bd_cells ps7]

set_property -dict [list \
  CONFIG.PCW_QSPI_PERIPHERAL_ENABLE {1} \
  CONFIG.PCW_QSPI_QSPI_IO {MIO 1 .. 6} \
  CONFIG.PCW_QSPI_GRP_FBCLK_ENABLE {1} \
  CONFIG.PCW_QSPI_GRP_FBCLK_IO {MIO 8} \
  CONFIG.PCW_QSPI_GRP_IO1_ENABLE {1} \
  CONFIG.PCW_QSPI_GRP_IO1_IO {MIO 0 9 .. 13} \
  CONFIG.PCW_QSPI_GRP_SINGLE_SS_ENABLE {0} \
  CONFIG.PCW_QSPI_GRP_SS1_ENABLE {0} \
] [get_bd_cells ps7]

# THE FIX: clock the GP0 port
connect_bd_net [get_bd_pins ps7/FCLK_CLK0] [get_bd_pins ps7/M_AXI_GP0_ACLK]

puts "QSPI_ENABLE=[get_property CONFIG.PCW_QSPI_PERIPHERAL_ENABLE [get_bd_cells ps7]]"
puts "QSPI_IO=[get_property CONFIG.PCW_QSPI_QSPI_IO [get_bd_cells ps7]]"

if {[catch {validate_bd_design} verr]} {
  puts "VALIDATE_ERR_BEGIN"; puts $verr; puts "VALIDATE_ERR_END"
} else {
  puts "VALIDATE_OK"
}
save_bd_design

if {[catch {generate_target all [get_files design_1.bd]} gerr]} {
  puts "GENERATE_ERR_BEGIN"; puts $gerr; puts "GENERATE_ERR_END"
} else {
  puts "GENERATE_OK"
}

if {[catch {write_hw_platform -fixed -force $out/zc706_qspi_v3.xsa} xerr]} {
  puts "XSA_WRITE_ERR_BEGIN"; puts $xerr; puts "XSA_WRITE_ERR_END"
} else {
  puts "XSA_WRITE_OK"
}
if {[file exists $out/zc706_qspi_v3.xsa]} {
  set sz [file size $out/zc706_qspi_v3.xsa]
  puts "XSA_SIZE=$sz"
  if {$sz > 100000} { puts "XSA_SENTINEL=NONSEDEGENERATE" } else { puts "XSA_SENTINEL=DEGENERATE" }
} else {
  puts "XSA_SENTINEL=MISSING"
}
close_project
puts "TCL_DONE"
exit
