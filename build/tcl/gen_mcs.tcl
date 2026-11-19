if {[catch {write_cfgmem -format mcs -interface spix4 -size 128 -loadbit "up 0x0 D:/puf-drone-auth/build/board_zc706/w3_top_zc706.bit" -file D:/puf-drone-auth/build/qspi_boot_boardA.mcs -force} errmsg]} {
    puts "CFGMEM_ERROR: $errmsg"
} else {
    puts "CFGMEM_OK"
}
exit
