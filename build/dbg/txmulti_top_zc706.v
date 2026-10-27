`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Design Name: bawan-yhy
// Module Name: txmulti_top_zc706
// Description: 
//  v7 终极诊断：uart_rx(pin5) + 回发(pin1)，ILA 同探 pin3/pin5 两输入网。
//  判据：PC 发字节时 ILA 看到 pin3 或 pin5 有下降沿 = 物理通路活（错在我的回声 RTL）；
//  两网皆静默 = 信号未达硅片（TXS/物理层）。仅诊断用。
//////////////////////////////////////////////////////////////////////////////////

module txmulti_top_zc706 (
    input                   clk_p     ,
    input                   clk_n     ,
    output                  pmod1_0   ,   // AJ21 = J58.1 回声发送
    input                   pmod1_1   ,   // AK21 = J58.3 【ILA 探针】
    input                   pmod1_2   ,   // AB21 = J58.5 uart_rx 本体输入
    output                  led_heartbeat ,
    output                  led_rx
  );
wire clk_100m, mmcm_locked;
clk_wiz_0 u_mmcm (.clk_in1_p(clk_p), .clk_in1_n(clk_n), .reset(1'b0), .clk_out1(clk_100m), .locked(mmcm_locked));
wire rst_n = mmcm_locked;
wire rst   = ~rst_n;
reg [26:0] hb_cnt_reg = 27'd0;
always @(posedge clk_100m) begin
    if (!rst_n) hb_cnt_reg <= 27'd0; else hb_cnt_reg <= hb_cnt_reg + 27'd1;
end
assign led_heartbeat = hb_cnt_reg[26];
wire [7:0]  rx_byte_w;
wire        rx_valid_w;
uart_rx # ( .CLKS_PER_BIT ( 868 )
) u_rx (
    .clk       ( clk_100m   ),
    .rst       ( rst        ),
    .rx_serial ( pmod1_2    ),
    .rx_byte   ( rx_byte_w  ),
    .rx_valid  ( rx_valid_w )
);
wire tx_serial_w, tx_active_w;
uart_tx # ( .CLKS_PER_BIT ( 868 )
) u_tx (
    .clk       ( clk_100m             ),
    .rst       ( rst                  ),
    .tx_valid  ( rx_valid_w && !tx_active_w ),
    .tx_byte   ( rx_byte_w            ),
    .tx_serial ( tx_serial_w          ),
    .tx_active ( tx_active_w          ),
    .tx_done   (                      )
);
assign pmod1_0 = tx_serial_w;
reg [27:0] rx_hold_reg = 28'd0;
always @(posedge clk_100m) begin
    if (!rst_n) rx_hold_reg <= 28'd0;
    else if (rx_valid_w) rx_hold_reg <= 28'd30_000_000;
    else if (rx_hold_reg != 28'd0) rx_hold_reg <= rx_hold_reg - 28'd1;
end
assign led_rx = (rx_hold_reg != 28'd0);
// ILA 探针标记（综合后保网）
(* mark_debug = "true" *) wire dbg_pin3 = pmod1_1;
(* mark_debug = "true" *) wire dbg_pin5 = pmod1_2;
(* mark_debug = "true" *) wire dbg_rx_valid = rx_valid_w;
endmodule
