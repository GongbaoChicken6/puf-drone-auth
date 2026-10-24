// health_top -- 底层健康灯语（排除全部上层 RTL，一次定位时钟/复位/按键）
module health_top (
    input  wire         clk_p         ,
    input  wire         clk_n         ,
    input  wire         sys_rst_btn_n ,   // 板上实测高有效：空闲0/按下1（_n 是历史命名，勿按名推极性；2026-10-22 23:27 health 实证）
    input  wire         auth_btn      ,
    input  wire [3:0]   term_id_dip   ,
    output wire         radio_txd     ,
    input  wire         radio_rxd     ,
    output wire         led_busy      ,
    output wire [1:0]   led_result    ,
    output wire         led_heartbeat
);
    wire clk_100m, mmcm_locked;
    clk_wiz_0 u_mmcm (
        .clk_in1_p ( clk_p         ),
        .clk_in1_n ( clk_n         ),
        .reset     ( sys_rst_btn_n   ),   // 板上实测：SW13 按下=1（高有效复位脉冲），空闲=0
        .clk_out1  ( clk_100m      ),
        .locked    ( mmcm_locked   )
    );

    reg [26:0] hb = 27'd0;
    always @(posedge clk_100m) hb <= hb + 1'b1;

    // 灯语：DS35(0)=心跳闪=时钟全好；DS8(L)=mmcm_locked；DS10(R)=SW13电平；DS9(C)=SW7电平
    assign led_heartbeat = mmcm_locked ? hb[26] : 1'b0;
    assign led_result    = { sys_rst_btn_n, mmcm_locked };
    assign led_busy      = auth_btn;
    assign radio_txd     = 1'b1;
endmodule
