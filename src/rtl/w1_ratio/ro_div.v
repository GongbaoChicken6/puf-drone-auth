`timescale 1ns / 1ps
////////////////////////////////////////////////////////////////////////////////
// Design Name: puf-auth-w1
// Module Name: ro_div
// Description: 
//  RO 异步域纹波分频器（T 触发器链，每级二分频）。作用：把环振输出降为
//  慢信号，供上层时基域安全采样。注意：被测链与时基链必须保留足够频率差
//  （本工程 A 链 4096 分频、B 链 16384 分频）——若同级，同频采样会把
//  比值混叠成差拍 |fA-fB|，两环越接近读数越趋 0。
//  说明：本模块工作在 RO 异步域，同步复位不可达，故各级不复位——
//  上电初值由声明处赋值（GSR）保证；首个测量窗的数据在顶层丢弃。
////////////////////////////////////////////////////////////////////////////////
(* DONT_TOUCH = "true" *) module ro_div # (
    parameter STAGES = 12                                           // 分频级数：2^12=4096
  )
  (
    input                   ro      ,                               // 环振输出（异步时钟源）
    output                  div                                     // 分频后慢信号（约百 kHz）
  );

//---------------- 纹波链：第 0 级由 ro 驱动，其后每级由前级驱动 ---------------//
wire [STAGES:0] ripple;
assign ripple[0] = ro;

genvar g;
generate
    for( g = 0; g < STAGES; g = g + 1 ) begin : gen_ripple
        (* KEEP = "true" *) reg tff = 1'b0;                          // T 触发器，异步域不复位
        always @ ( posedge ripple[g] ) begin
            tff <= ~tff;
        end
        assign ripple[g+1] = tff;
    end
endgenerate

assign div = ripple[STAGES];

endmodule
