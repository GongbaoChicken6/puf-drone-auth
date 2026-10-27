`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Design Name: puf-auth-w2
// Module Name: uart_rx
// Description: 
//  UART 接收器（改自 external/PUF-lab/sources/uart_rx.v，原版来自
//  nandland）：8 数据位 + 1 起始位 + 1 停止位，无校验。保持原 5 态
//  FSM（IDLE / START / DATA / STOP / CLEANUP）与采样时序（起始位中点
//  校验 + 数据位中点采样），按团队规范重构：三段式状态机 + 数据通路
//  每信号一个 always、端口改团队命名、增加高有效同步复位。
//  输入线经 2 级同步（前馈打拍，不复位，声明初值 = 空闲高电平）。
//  接口约定：rx_valid 单拍脉冲指示收到一字节，rx_byte 同时有效。
//  例：100MHz 时钟、115200 波特 -> CLKS_PER_BIT = 868。
//  注：w2_top 需经 UART 接收 8 字节种子，本模块为 W2 必需件（设计
//  文件清单原排在 W3，提前到 W2 落地）。
//////////////////////////////////////////////////////////////////////////////////
module uart_rx # (
    parameter CLKS_PER_BIT = 868    // 每比特时钟数 = 时钟频率 / 波特率
  )
  (
    // 时钟与复位
    input                   clk         ,   // 系统时钟
    input                   rst         ,   // 高有效同步复位

    // 串行输入
    input                   rx_serial   ,   // 串行输入（空闲为高）

    // 接收结果
    output  [7:0]           rx_byte     ,   // 收到的字节（rx_valid 拍有效）
    output                  rx_valid        // 字节有效脉冲（单拍）
  );

//---------------- 状态编码 ---------------//
localparam    [2:0]    S_IDLE    = 3'd0;                     // 空闲，等待起始位下降沿
localparam    [2:0]    S_START   = 3'd1;                     // 起始位（半位处校验）
localparam    [2:0]    S_DATA    = 3'd2;                     // 8 个数据位（中点采样）
localparam    [2:0]    S_STOP    = 3'd3;                     // 停止位
localparam    [2:0]    S_CLEANUP = 3'd4;                     // 收尾（恰 1 拍，出 rx_valid）

//---------------- 常量 ---------------//
localparam    [19:0]   BIT_LAST  = CLKS_PER_BIT - 1;         // 每比特末拍
localparam    [19:0]   HALF_LAST = ( CLKS_PER_BIT - 1 ) / 2; // 半比特末拍（起始位校验点）

//---------------- 输入同步器 ---------------//
(* ASYNC_REG = "true" *) reg  rx_meta = 1'b1;                // 同步器第 1 级（前馈，不复位）
(* ASYNC_REG = "true" *) reg  rx_sync = 1'b1;                // 同步器第 2 级（前馈，不复位）

//---------------- 状态机 ---------------//
reg      [2:0]         curr_state = 3'd0;                    // 现态
reg      [2:0]         next_state;                           // 次态（组合 always 驱动）

//---------------- 数据通路 ---------------//
reg      [19:0]        cnt_clk = 20'd0;                      // 比特内时钟计数
reg      [2:0]         bit_idx = 3'd0;                       // 数据位下标（0~7）
reg      [7:0]         rx_byte_reg = 8'd0;                   // 接收字节拼装

//---------------- 输出寄存器 ---------------//
reg                    rx_valid_reg = 1'b0;                  // 字节有效脉冲寄存器

//---------------- 共享条件提炼线 ---------------//
wire                   start_half;                            // 起始位半比特校验点
wire                   bit_done;                             // 当前比特计满
wire                   bit_last;                             // 第 8 个数据位

//---------------- 以下为逻辑实现 ---------------//

//////////////////////////////////////////////////////////////////
// 共享条件：全模块只此一份
//////////////////////////////////////////////////////////////////
assign  start_half = ( curr_state == S_START ) & ( cnt_clk >= HALF_LAST );
assign  bit_done   = ( cnt_clk >= BIT_LAST );
assign  bit_last   = ( bit_idx >= 3'd7 );

//////////////////////////////////////////////////////////////////
// 输入 2 级同步（一 always 一信号）
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    rx_meta <= rx_serial;
end

always @ ( posedge clk ) begin
    rx_sync <= rx_meta;
end

//////////////////////////////////////////////////////////////////
// 状态机第一段：状态寄存（同步复位回 IDLE）
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        curr_state <= S_IDLE;
    end
    else begin
        curr_state <= next_state;
    end
end

//////////////////////////////////////////////////////////////////
// 状态机第二段：次态译码（组合，块首默认保持）
//////////////////////////////////////////////////////////////////
always @ ( * ) begin
    next_state = curr_state;
    case( curr_state )
        S_IDLE    : begin
            if( !rx_sync ) begin
                next_state = S_START;
            end
            else begin
                next_state = S_IDLE;
            end
        end   // 检测到起始位下降沿
        S_START   : begin
            if( start_half ) begin
                if( !rx_sync ) begin
                    next_state = S_DATA;
                end
                else begin
                    next_state = S_IDLE;
                end
            end
            else begin
                next_state = S_START;
            end
        end   // 半位处校验：仍为低则真起始位，否则判假回空闲
        S_DATA    : begin
            if( bit_done & bit_last ) begin
                next_state = S_STOP;
            end
            else begin
                next_state = S_DATA;
            end
        end   // 8 个数据位收完（中途位边界原地停留）
        S_STOP    : begin
            if( bit_done ) begin
                next_state = S_CLEANUP;
            end
            else begin
                next_state = S_STOP;
            end
        end   // 停止位收完
        S_CLEANUP : begin
            next_state = S_IDLE;
        end   // 收尾恰 1 拍
        default   : begin
            next_state = S_IDLE;
        end   // 跑飞恢复
    endcase
end

//////////////////////////////////////////////////////////////////
// 比特内时钟计数：计数态计满 / 起始位半位点即清零（半位清零实现
// 数据位对齐到比特中心），其余状态保持清零
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        cnt_clk <= 20'd0;
    end
    else if( ( curr_state == S_START ) | ( curr_state == S_DATA ) | ( curr_state == S_STOP ) ) begin
        if( bit_done | start_half ) begin
            cnt_clk <= 20'd0;
        end
        else begin
            cnt_clk <= cnt_clk + 20'd1;
        end
    end
    else begin
        cnt_clk <= 20'd0;
    end
end

//////////////////////////////////////////////////////////////////
// 数据位下标：DATA 态比特边界推进，末位回卷，其余状态清零
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        bit_idx <= 3'd0;
    end
    else if( ( curr_state == S_DATA ) & bit_done ) begin
        if( bit_last ) begin
            bit_idx <= 3'd0;
        end
        else begin
            bit_idx <= bit_idx + 3'd1;
        end
    end
    else if( curr_state != S_DATA ) begin
        bit_idx <= 3'd0;                          // 仅非 DATA 态清零
    end
    // S_DATA 态非边界拍：bit_idx 保持（不赋值 = 寄存器保持原值）
    // ⚠ 2026-10-27 修复：原版此处无条件清零，导致 bit_idx 在 DATA 态
    //   非边界拍被反复归零（0→1→0→1...），永远到不了 7，FSM 永久挂死
    //   在 S_DATA——与 uart_tx 曾有的 P0-1 缺陷同源（同一次重构引入，
    //   当时只修了 tx 漏了 rx）。真硅片实证：PC→板方向 0 字节两天。
end

//////////////////////////////////////////////////////////////////
// 接收字节拼装：DATA 态比特边界采入同步后的线路电平（中点采样）
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        rx_byte_reg <= 8'd0;
    end
    else if( ( curr_state == S_DATA ) & bit_done ) begin
        rx_byte_reg[bit_idx] <= rx_sync;
    end
    else begin
        rx_byte_reg <= rx_byte_reg;
    end
end

assign  rx_byte = rx_byte_reg;                  // 寄存器直连出端口

//////////////////////////////////////////////////////////////////
// 状态机第三段：字节有效脉冲（进入 CLEANUP 拍输出，恰 1 拍）
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        rx_valid_reg <= 1'b0;
    end
    else begin
        rx_valid_reg <= ( next_state == S_CLEANUP );
    end
end

assign  rx_valid = rx_valid_reg;                // 寄存器直连出端口

endmodule
