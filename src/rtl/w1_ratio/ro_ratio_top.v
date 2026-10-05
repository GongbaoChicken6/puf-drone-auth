`timescale 1ns / 1ps
////////////////////////////////////////////////////////////////////////////////
// Design Name: puf-auth-w1
// Module Name: ro_ratio_top
// Description: 
//  W1 一号验证点（ZC702 适配版）：双环振比值测量，全片内完成。
//  环振 A 经 4096 分频作窗口时基（2^20 个 div_a 周期 = 2^32/fA 秒，
//  实测约 14~43 秒一窗）；环振 B 经 16384 分频作被测信号——B 链比 A 链
//  深 2 级：保证采样率 fA/4096 对信号 fB/16384 有 >=2 倍奈奎斯特裕量，
//  否则同频采样会混叠成差拍 |fA-fB|（fA≈fB 时读数趋 0，语义全错）。
//  窗内数 B 的上升沿：
//      N ≈ (fB/fA) x 2^18 ≈ 262144（两环完全一致时的理论值）
//  这正是 RO-PUF"成对比较"的本质；比值对温度共模抑制（两环同冷同热）。
//  本工程零引脚 / 零接线；唯一约束是 w1_ro_waiver.xdc 的 2 行环振豁免
//  （环振=组合环，不加豁免 write_bitstream 会被 DRC LUTLP-1 阻断）。
//  读数经 VIO（JTAG）读回；上电后首个完整窗口结束前 ratio_latch=0。
////////////////////////////////////////////////////////////////////////////////
module ro_ratio_top ();

//---------------- 参数区 -------------------------------------------------------//
localparam [19:0] WINDOW = 20'hF_FFFF;                              // 窗口 = 2^20 个 div_a 周期

//---------------- 内部信号 -----------------------------------------------------//
wire  ro_a;                                                          // 环振 A 输出
wire  div_a;                                                        // A 链分频后慢信号（本域时钟 + 窗口时基）
wire  ro_b;                                                          // 环振 B 输出
wire  div_b;                                                        // B 链分频后慢信号（被测信号）
wire  rst;                                                           // 上电复位（div_a 域，高有效 4 拍）
wire  rise;                                                          // div_b 上升沿脉冲（div_a 域）
wire  win_end;                                                       // 窗口结束脉冲

(* ASYNC_REG = "true" *) reg  div_b_meta = 1'b0;                     // 同步器第 1 级（前馈，不复位）
(* ASYNC_REG = "true" *) reg  div_b_sync = 1'b0;                     // 同步器第 2 级（前馈，不复位）
reg  [3:0]  por        = 4'b1111;                                   // 上电复位发生器（仅上电一次）
reg  div_b_d1          = 1'b0;                                      // 边沿检测打拍（前馈，不复位）
reg  [19:0] window_cnt;                                             // 窗口计数器（反馈，复位）
reg  [31:0] edge_cnt;                                               // 窗内 B 沿计数（反馈，复位）
reg  [31:0] ratio_latch;                                            // 每窗锁存的比值读数（出模块，复位）

//////////////////////////////////////////////////////////////////
// 双环振 + 各自纹波分频（本设计核心：两颗"物理指纹"信号源）
//////////////////////////////////////////////////////////////////
ro_ring u_ro_a (
    .en     ( 1'b1      ),
    .ro     ( ro_a      )
);
ro_div # ( .STAGES   ( 12           )
) u_div_a (
    .ro     ( ro_a        ),
    .div    ( div_a       )
);

ro_ring u_ro_b (
    .en     ( 1'b1      ),
    .ro     ( ro_b      )
);
ro_div # ( .STAGES   ( 14           )      // B 链多 2 级（16384 分频）：防同频采样混叠，见头注释
) u_div_b (
    .ro     ( ro_b        ),
    .div    ( div_b       )
);

//////////////////////////////////////////////////////////////////
// 上电复位发生器（div_a 域）：por 高 4 拍后自动清零
//////////////////////////////////////////////////////////////////
always @ ( posedge div_a ) begin
    por <= { por[2:0], 1'b0 };
end
assign rst = por[3];

//////////////////////////////////////////////////////////////////
// 跨域同步：把 div_b 安全接入 div_a 域，并做边沿检测
//////////////////////////////////////////////////////////////////
always @ ( posedge div_a ) begin
    div_b_meta <= div_b;
    div_b_sync <= div_b_meta;
    div_b_d1   <= div_b_sync;
end
assign rise    = div_b_sync & ( ~div_b_d1 );
assign win_end = ( window_cnt == WINDOW );

//////////////////////////////////////////////////////////////////
// 主计数：窗口内数 B 的上升沿，窗末锁存比值并清零
//////////////////////////////////////////////////////////////////
always @ ( posedge div_a ) begin
    if( rst ) begin
        window_cnt <= 20'd0;
        edge_cnt   <= 32'd0;
        ratio_latch<= 32'd0;
    end
    else begin
        if( win_end ) begin
            window_cnt <= 20'd0;
            ratio_latch<= edge_cnt;                                   // 每窗更新一次读数
            edge_cnt   <= rise ? 32'd1 : 32'd0;                       // 开新窗
        end
        else begin
            window_cnt <= window_cnt + 1'b1;
            if( rise ) begin
                edge_cnt <= edge_cnt + 1'b1;
            end
            else begin
                edge_cnt <= edge_cnt;
            end
        end
    end
end

//////////////////////////////////////////////////////////////////
// VIO 虚拟仪器：JTAG 读回 32 位比值读数（无需任何外部接线）
//////////////////////////////////////////////////////////////////
vio_0 u_vio (
    .clk         ( div_a        ),
    .probe_in0   ( ratio_latch  )
);

endmodule
