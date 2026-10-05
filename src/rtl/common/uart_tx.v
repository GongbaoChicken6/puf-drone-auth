`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Design Name: puf-auth-w2
// Module Name: uart_tx
// Description: 
//  UART 发送器（改自 external/PUF-lab/sources/uart_tx.v，原版来自
//  nandland）：8 数据位 + 1 起始位 + 1 停止位，无校验。保持原 5 态
//  FSM（IDLE / START / DATA / STOP / CLEANUP）与发送时序（每比特
//  CLKS_PER_BIT 个时钟），按团队规范重构：三段式状态机 + 数据通路每
//  信号一个 always、端口改团队命名、增加高有效同步复位。
//  例：100MHz 时钟、115200 波特 -> CLKS_PER_BIT = 868。
//  接口约定：tx_valid 单拍脉冲即可（空闲时采样并缓存字节）；tx_done
//  单拍脉冲指示一字节发完（CLEANUP 拍输出）。
//////////////////////////////////////////////////////////////////////////////////
module uart_tx # (
    parameter CLKS_PER_BIT = 868    // 每比特时钟数 = 时钟频率 / 波特率
  )
  (
    // 时钟与复位
    input                   clk         ,   // 系统时钟
    input                   rst         ,   // 高有效同步复位

    // 发送命令
    input                   tx_valid    ,   // 发送请求（单拍，源须为本域寄存器）
    input  [7:0]            tx_byte     ,   // 待发送字节

    // 串行接口与状态
    output                  tx_serial   ,   // 串行输出（空闲为高）
    output                  tx_active   ,   // 发送进行中（START~STOP 期间）
    output                  tx_done         // 一字节发完脉冲（单拍）
  );

//---------------- 状态编码 ---------------//
localparam    [2:0]    S_IDLE    = 3'd0;                     // 空闲，等待 tx_valid
localparam    [2:0]    S_START   = 3'd1;                     // 起始位（0）
localparam    [2:0]    S_DATA    = 3'd2;                     // 8 个数据位（LSB 在前）
localparam    [2:0]    S_STOP    = 3'd3;                     // 停止位（1）
localparam    [2:0]    S_CLEANUP = 3'd4;                     // 收尾（恰 1 拍，出 tx_done）

//---------------- 常量 ---------------//
localparam    [19:0]   BIT_LAST  = CLKS_PER_BIT - 1;         // 每比特末拍

//---------------- 状态机 ---------------//
reg      [2:0]         curr_state = 3'd0;                    // 现态
reg      [2:0]         next_state;                           // 次态（组合 always 驱动）

//---------------- 数据通路 ---------------//
reg      [19:0]        cnt_clk = 20'd0;                      // 比特内时钟计数
reg      [2:0]         bit_idx = 3'd0;                       // 数据位下标（0~7）
reg      [7:0]         tx_data_reg = 8'd0;                   // 发送字节缓存

//---------------- 输出寄存器 ---------------//
reg                    tx_serial_reg = 1'b1;                 // 串行输出寄存器（空闲 = 1）
reg                    tx_active_reg = 1'b0;                 // 发送进行中寄存器
reg                    tx_done_reg = 1'b0;                   // 完成脉冲寄存器

//---------------- 共享条件提炼线 ---------------//
wire                   tx_fire;                              // 空闲态采到发送请求
wire                   bit_done;                             // 当前比特计满
wire                   bit_last;                             // 第 8 个数据位

//---------------- 以下为逻辑实现 ---------------//

//////////////////////////////////////////////////////////////////
// 共享条件：全模块只此一份
//////////////////////////////////////////////////////////////////
assign  tx_fire  = ( curr_state == S_IDLE ) & tx_valid;
assign  bit_done = ( cnt_clk >= BIT_LAST );
assign  bit_last = ( bit_idx >= 3'd7 );

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
            if( tx_fire ) begin
                next_state = S_START;
            end
            else begin
                next_state = S_IDLE;
            end
        end   // 等待发送请求
        S_START   : begin
            if( bit_done ) begin
                next_state = S_DATA;
            end
            else begin
                next_state = S_START;
            end
        end   // 起始位发完
        S_DATA    : begin
            if( bit_done & bit_last ) begin
                next_state = S_STOP;
            end
            else begin
                next_state = S_DATA;
            end
        end   // 8 个数据位发完（中途位边界原地停留）
        S_STOP    : begin
            if( bit_done ) begin
                next_state = S_CLEANUP;
            end
            else begin
                next_state = S_STOP;
            end
        end   // 停止位发完
        S_CLEANUP : begin
            next_state = S_IDLE;
        end   // 收尾恰 1 拍
        default   : begin
            next_state = S_IDLE;
        end   // 跑飞恢复
    endcase
end

//////////////////////////////////////////////////////////////////
// 发送字节缓存：空闲态收到请求时锁存
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        tx_data_reg <= 8'd0;
    end
    else if( tx_fire ) begin
        tx_data_reg <= tx_byte;
    end
    else begin
        tx_data_reg <= tx_data_reg;
    end
end

//////////////////////////////////////////////////////////////////
// 比特内时钟计数：START / DATA / STOP 态计数，计满或非计数态清零
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        cnt_clk <= 20'd0;
    end
    else if( ( curr_state == S_START ) | ( curr_state == S_DATA ) | ( curr_state == S_STOP ) ) begin
        if( bit_done ) begin
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
    else begin
        bit_idx <= 3'd0;
    end
end

//////////////////////////////////////////////////////////////////
// 状态机第三段：串行输出寄存（判 next_state，与状态进入同拍对齐；
// DATA 态比特边界提前装载下一位，保证每比特恰 CLKS_PER_BIT 拍）
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        tx_serial_reg <= 1'b1;                  // 复位释放线路为空闲态
    end
    else begin
        case( next_state )
            S_START : begin
                tx_serial_reg <= 1'b0;
            end   // 起始位
            S_DATA  : begin
                if( ( curr_state == S_DATA ) & bit_done ) begin
                    tx_serial_reg <= tx_data_reg[bit_idx + 3'd1];  // 位边界：装下一位
                end
                else begin
                    tx_serial_reg <= tx_data_reg[bit_idx];
                end   // 比特期间保持当前位
            end
            default : begin
                tx_serial_reg <= 1'b1;
            end   // 空闲 / 停止 / 收尾均为高
        endcase
    end
end

assign  tx_serial = tx_serial_reg;              // 寄存器直连出端口

//////////////////////////////////////////////////////////////////
// 发送进行中：START~STOP 期间为高（判 next_state 同拍对齐）
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        tx_active_reg <= 1'b0;
    end
    else begin
        tx_active_reg <= ( next_state == S_START ) | ( next_state == S_DATA ) | ( next_state == S_STOP );
    end
end

assign  tx_active = tx_active_reg;              // 寄存器直连出端口

//////////////////////////////////////////////////////////////////
// 完成脉冲：CLEANUP 拍输出单拍脉冲
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        tx_done_reg <= 1'b0;
    end
    else begin
        tx_done_reg <= ( curr_state == S_CLEANUP );
    end
end

assign  tx_done = tx_done_reg;                  // 寄存器直连出端口

endmodule
