`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Design Name: puf-auth-w2
// Module Name: ro_array
// Description: 
//  16 环 RO-PUF 阵列 + 每环独立频率计数器（复用 W1 架构：ro_ring → ro_div
//  纹波分频 → 2 级同步器 → 边沿检测 → 计数）。测量窗由外部 measure_en 门
//  控：窗内各环累加分频后信号的上升沿数，窗末（measure_en 下降后一拍）单
//  拍 done 脉冲，并把全部计数值锁存到 ring_freq——计数值正比于环振频率
//  （比例系数 = 2^DIV_STAGES / 窗长），比较 / 配对逻辑留给 PC 端（W2 简
//  化口径，设计文档 P1-3）。
//  分频级数取 5（/32）的依据：W1 板上实测环振约 100~307MHz，分频后为
//  3~10MHz，100MHz 时基每分频周期 >= 10 拍，2 级同步 + 边沿检测余量充足；
//  1ms 窗对应计数值约 3.1k~9.6k，16 位计数器上限 65535，余量充足。
//  说明：同步器沿用 W1 ro_ratio_top 的手工 2FF + ASYNC_REG 写法（与既有
//  代码保持一致）；本路径为频率测量路径，单次亚稳只引入 ±1 计数误差，
//  不影响配对比较语义，不构成功能跨域 hazard。
//////////////////////////////////////////////////////////////////////////////////
module ro_array # (
    parameter N_RINGS    = 16    ,   // 环振数量
    parameter CNT_W      = 16    ,   // 每环频率计数器位宽
    parameter DIV_STAGES = 5         // 每环 ro_div 分频级数（2^5 = 32 分频）
  )
  (
    // 时钟与复位
    input                         clk         ,   // 系统时钟（100MHz，测量时基域）
    input                         rst         ,   // 高有效同步复位

    // 测量窗控制（来自上层同域寄存器）
    input                         measure_en  ,   // 测量窗使能：1=窗内计数，拉低结束一窗
    input                         ring_en     ,   // 环振使能（功耗管理）：1=振荡，0=停振
    output                        busy        ,   // 测量进行中（含 done 脉冲拍）

    // 测量结果
    output                        done        ,   // 单拍脉冲：一窗结束，ring_freq 已锁存
    output  [N_RINGS*CNT_W-1:0]   ring_freq       // 各环频率锁存值（环 i = [i*CNT_W +: CNT_W]）
  );

//---------------- 测量窗控制 ---------------//
reg      measure_d1 = 1'b0;                     // measure_en 打拍（窗末检测用，控制，复位）
wire     win_fall;                              // 测量窗结束事件（measure_en 下降，当拍有效）
reg      busy_reg = 1'b0;                       // busy 输出寄存器
reg      done_reg = 1'b0;                       // done 输出寄存器

//---------------- 以下为逻辑实现 ---------------//

//////////////////////////////////////////////////////////////////
// 测量窗结束检测：measure_en 打一拍后做下降沿判决
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        measure_d1 <= 1'b0;
    end
    else begin
        measure_d1 <= measure_en;
    end
end

assign  win_fall = measure_d1 & ( !measure_en );

//////////////////////////////////////////////////////////////////
// busy：测量进行中（从开窗覆盖到 done 脉冲拍）
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        busy_reg <= 1'b0;
    end
    else begin
        busy_reg <= measure_d1 | done_reg;
    end
end

assign  busy = busy_reg;                        // 寄存器直连出端口

//////////////////////////////////////////////////////////////////
// done：窗末事件一拍后出单拍脉冲（此时计数终值已稳定一拍）
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        done_reg <= 1'b0;
    end
    else if( win_fall ) begin
        done_reg <= 1'b1;
    end
    else begin
        done_reg <= 1'b0;
    end
end

assign  done = done_reg;                        // 寄存器直连出端口

//////////////////////////////////////////////////////////////////
// 16 份相同的"环振 + 分频 + 同步 + 边沿 + 计数"结构（逻辑复制）
//////////////////////////////////////////////////////////////////
genvar i;
generate
    for( i = 0; i < N_RINGS; i = i + 1 ) begin : gen_ro_ring
        (* KEEP = "true" *) (* DONT_TOUCH = "true" *) wire ro;   // 环振输出（防优化，见 w2_waiver.xdc）
        wire                     div;                            // 本环分频后慢信号（3~10MHz）
        (* ASYNC_REG = "true" *) reg  div_meta = 1'b0;           // 同步器第 1 级（前馈，不复位）
        (* ASYNC_REG = "true" *) reg  div_sync = 1'b0;           // 同步器第 2 级（前馈，不复位）
        reg                      div_d1 = 1'b0;                  // 边沿检测打拍（前馈，不复位）
        wire                     pos_edge;                       // div 上升沿单拍事件
        reg  [CNT_W-1:0]         cnt = {CNT_W{1'b0}};            // 窗内沿计数（反馈，必复位）
        reg  [CNT_W-1:0]         freq_latch = {CNT_W{1'b0}};     // 窗末锁存读数（出模块，必复位）

        ro_ring u_ro_ring (
            .en     ( ring_en   ),   // 功耗管理：认证期间开振，空闲停振（盲区 #6 修复）
            .ro     ( ro        )    // output，接本环分频链
        );

        ro_div # ( .STAGES   ( DIV_STAGES )
        ) u_ro_div (
            .ro     ( ro        ),   // 分频链输入（异步环振域）
            .div    ( div       )    // output，分频后慢信号
        );

        //////////////////////////////////////////////////////////////
        // 跨域同步 + 边沿检测：把 div 慢信号安全接入 clk 域
        //////////////////////////////////////////////////////////////
        always @ ( posedge clk ) begin
            div_meta <= div;
        end

        always @ ( posedge clk ) begin
            div_sync <= div_meta;
        end

        always @ ( posedge clk ) begin
            div_d1 <= div_sync;
        end

        assign  pos_edge = div_sync & ( !div_d1 );

        //////////////////////////////////////////////////////////////
        // 窗内计数：数 div 上升沿；窗外清零，保证每窗从 0 起算
        //////////////////////////////////////////////////////////////
        always @ ( posedge clk ) begin
            if( rst ) begin
                cnt <= {CNT_W{1'b0}};
            end
            else if( !measure_en ) begin
                cnt <= {CNT_W{1'b0}};
            end
            else if( pos_edge ) begin
                cnt <= cnt + 1'b1;
            end
            else begin
                cnt <= cnt;
            end
        end

        //////////////////////////////////////////////////////////////
        // 窗末锁存：把计数值冻结到 freq_latch（下一窗前保持可读）
        //////////////////////////////////////////////////////////////
        always @ ( posedge clk ) begin
            if( rst ) begin
                freq_latch <= {CNT_W{1'b0}};
            end
            else if( win_fall ) begin
                freq_latch <= cnt;
            end
            else begin
                freq_latch <= freq_latch;
            end
        end

        assign  ring_freq[i*CNT_W +: CNT_W] = freq_latch;   // 扁平总线拼装（纯布线）
    end
endgenerate

endmodule
