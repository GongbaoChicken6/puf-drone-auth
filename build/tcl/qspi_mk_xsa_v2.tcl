# QSPI XSA v2 for ZC706 - rebuild with verifiable export (2026-11-15 lead)
# Goal: non-degenerate XSA containing ps7_init with QSPI MIO config
set root D:/puf-drone-auth
set out $root/build/qspi_xsa_v2
file mkdir $out

create_project -force qspi_ps2 $out -part xc7z045ffg900-2
create_bd_design design_1
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7
set_property -dict [list CONFIG.preset {ZC706}] [get_bd_cells ps7]

# Re-assert QSPI per ZC706 board file (values confirmed from design_1.bd of v1 attempt)
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

# Report final QSPI state as evidence
puts "QSPI_ENABLE=[get_property CONFIG.PCW_QSPI_PERIPHERAL_ENABLE [get_bd_cells ps7]]"
puts "QSPI_IO=[get_property CONFIG.PCW_QSPI_QSPI_IO [get_bd_cells ps7]]"
puts "QSPI_IO1=[get_property CONFIG.PCW_QSPI_GRP_IO1_IO [get_bd_cells ps7]]"
puts "QSPI_FBCLK=[get_property CONFIG.PCW_QSPI_GRP_FBCLK_IO [get_bd_cells ps7]]"
puts "UART1=[get_property CONFIG.PCW_UART1_PERIPHERAL_ENABLE [get_bd_cells ps7]]"
puts "UART1_IO=[get_property CONFIG.PCW_UART1_UART1_IO [get_bd_cells ps7]]"

# validate: expected to complain about unconnected FCLK clock - catch and record
if {[catch {validate_bd_design} verr]} {
  puts "VALIDATE_ERR_BEGIN"
  puts $verr
  puts "VALIDATE_ERR_END"
} else {
  puts "VALIDATE_OK"
}
save_bd_design

# generate output products - NOT under catch, errors must be visible
if {[catch {generate_target all [get_files design_1.bd]} gerr]} {
  puts "GENERATE_ERR_BEGIN"
  puts $gerr
  puts "GENERATE_ERR_END"
} else {
  puts "GENERATE_OK"
}
# wait for any async generation
catch {wait_on_generate_target}

# export XSA - NOT under catch
if {[catch {write_hw_platform -fixed -force $out/zc706_qspi_v2.xsa} xerr]} {
  puts "XSA_WRITE_ERR_BEGIN"
  puts $xerr
  puts "XSA_WRITE_ERR_END"
} else {
  puts "XSA_WRITE_OK"
}
if {[file exists $out/zc706_qspi_v2.xsa]} {
  puts "XSA_SIZE=[file size $out/zc706_qspi_v2.xsa]"
  if {[file size $out/zc706_qspi_v2.xsa] > 100000} {
    puts "XSA_SENTINEL=NONSEDEGENERATE"
  } else {
    puts "XSA_SENTINEL=DEGENERATE"
  }
} else {
  puts "XSA_SENTINEL=MISSING"
}

close_project
puts "TCL_DONE"
exit
