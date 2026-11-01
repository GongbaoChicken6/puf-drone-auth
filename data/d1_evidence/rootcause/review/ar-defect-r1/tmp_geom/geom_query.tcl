
create_project -in_memory -part xc7z045ffg900-2
# 尝试无设计查询；若失败则综合一个空模块后再查
if {[catch {get_clock_regions} em]} {
    set fh [open tiny.v w]
    puts $fh "module tiny(input a, output y); assign y = ~a; endmodule"
    close $fh
    read_verilog tiny.v
    synth_design -top tiny -part xc7z045ffg900-2
}
set allcr [lsort [get_clock_regions]]
puts "GEOM_ALLCR: $allcr"
puts "GEOM_NCR: [llength $allcr]"
foreach cr $allcr {
    puts "GEOM_GRID_$cr: [get_property GRID_RANGES [get_clock_regions $cr]]"
}
# 用 seed2 落位报告中的全部 160 个站点验证 CLOCK_REGION 归属
set f [open "D:/puf-drone-auth/build/board_zc706_seed2/ring_sites_seed2.rpt" r]
set n 0; set inx1y0 0; set outside {}
while {[gets $f line] >= 0} {
    if {[regexp {(SLICE_X\d+Y\d+)\s*$} $line -> sitename]} {
        incr n
        set cr [get_property CLOCK_REGION [get_sites $sitename]]
        if {$cr eq "X1Y0"} { incr inx1y0 } else { lappend outside "$sitename=$cr" }
    }
}
close $f
puts "GEOM_SITES_TOTAL: $n"
puts "GEOM_SITES_IN_X1Y0: $inx1y0"
puts "GEOM_SITES_OUTSIDE: $outside"
exit 0
