`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Design Name: puf-auth-w2
// Module Name: w2_top
// Description: 
//  W2 顶层：挑战-响应全流程（UART 版，W2 简化口径，设计文档 P1-3）。
//  对外协议（115200-8-N-1，帧格式冻结）：
//    PC -> PL：8 字节挑战种子，低字节在前（byte0 -> seed[7:0]）；
//    PL -> PC：32 字节频率数据 = 16 环 × 16-bit 计数值，每环低字节在前
//              （byte0/1 = 环 0 低/高字节，...，byte30/31 = 环 15）。
//  流程（FSM：IDLE -> RECV_SEED -> DECODE -> MEASURE(轮 0~7) -> SEND -> IDLE）：
//    1. RECV_SEED：逐字节拼装 64-bit 种子；
//    2. DECODE：触发 challenge_decode 生成 512-bit 配对表——W2 简化下
//       配对比较在 PC 端完成（PC 用同一种子按同一算法重算配对表，再对
//       收到的 16 个频率做 8 轮 × 8 对比较，拼出 64-bit 响应 R1），PL 侧
//       配对表只触发不消费，留待 W3 移入 PL 做片内比较；
//    3. MEASURE：ro_array 以 1ms 测量窗连测 8 轮——前 7 轮作环振热稳定
//       （上电频率漂移），仅末轮锁存的 16 个频率被发出；轮控结构对齐
//       W3 的"每轮 8 bit 胜者"版，升级只改发送数据路径；
//    4. SEND：32 字节频率数据经 uart_tx 发回，收工回 IDLE。
//  时序口径：测量窗长以 MEAS_CYCLES 为准（measure_en 对状态的跟随误差
//  ±2 拍，对 1ms 窗可忽略）；8 轮总时长约 8ms + 解码 21us + UART 发送
//  32 字节约 2.8ms，认证延迟 << 1s 目标。
//////////////////////////////////////////////////////////////////////////////////
module w2_top # (
    parameter CLKS_PER_BIT = 868     ,   // UART 每比特时钟数（100MHz / 115200）
    parameter MEAS_CYCLES  = 100000  ,   // 测量窗长度（clk 周期数，1ms @ 100MHz）
    parameter N_ROUNDS     = 8           // 测量轮数（前 N-1 轮热稳定，末轮有效）
  )
  (
    // 时钟与复位
    input                       clk     ,   // 系统时钟（100MHz）
    input                       rst     ,   // 高有效同步复位

    // UART 接口
    input                       rx      ,   // UART 接收线（PC -> PL，挑战种子）
    output                      tx          // UART 发送线（PL -> PC，频率数据）
  );

//---------------- 状态编码 ---------------//
localparam    [2:0]    S_IDLE       = 3'd0;                   // 等待种子首字节
localparam    [2:0]    S_RECV_SEED  = 3'd1;                   // 收 8 字节拼种子
localparam    [2:0]    S_DECODE     = 3'd2;                   // 挑战解码（等 done）
localparam    [2:0]    S_MEASURE    = 3'd3;                   // 当前轮测量窗开启
localparam    [2:0]    S_ROUND_END  = 3'd4;                   // 等一窗完成，轮进位
localparam    [2:0]    S_SEND       = 3'd5;                   // 装载一字节并启动发送
localparam    [2:0]    S_SEND_WAIT  = 3'd6;                   // 等一字节发完

//---------------- 常量 ---------------//
localparam    [16:0]   WIN_LAST     = MEAS_CYCLES - 1;        // 测量窗末拍
localparam    [3:0]    LAST_ROUND   = N_ROUNDS - 1;           // 末轮轮号
localparam    [5:0]    TX_BYTE_NUM  = 6'd32;                  // 发送字节总数（16 环 × 2 字节）

//---------------- 状态机 ---------------//
reg      [2:0]         curr_state = 3'd0;                     // 现态
reg      [2:0]         next_state;                            // 次态（组合 always 驱动）

//---------------- 种子拼装 ---------------//
reg      [63:0]        seed_reg = 64'd0;                      // 8 字节拼装的种子
reg      [3:0]         cnt_seed_byte = 4'd0;                  // 种子字节计数（收到的下一字节号）

//---------------- 挑战解码接口 ---------------//
reg                    cd_start = 1'b0;                       // 解码启动脉冲
wire                   cd_done;                               // 解码完成脉冲

//---------------- 测量窗 ---------------//
reg                    measure_en = 1'b0;                     // 测量窗使能（跟随 S_MEASURE）
reg      [16:0]        cnt_win = 17'd0;                       // 测量窗计数
reg      [3:0]         round_cnt = 4'd0;                      // 测量轮计数（0~7）
wire                   ro_busy;                               // 阵列忙（观察用，可挂 ILA）
wire                   ro_done;                               // 一窗完成脉冲
wire  [255:0]          ring_freq;                             // 16 环 × 16-bit 频率锁存

//---------------- UART 发送 ---------------//
reg      [7:0]         tx_byte = 8'd0;                        // 发送字节
reg                    tx_valid = 1'b0;                       // 发送请求脉冲
reg      [5:0]         cnt_tx_byte = 6'd0;                    // 已装载发送字节数
wire                   tx_done;                               // 一字节发完脉冲

//---------------- UART 接收 ---------------//
wire  [7:0]            rx_byte;                               // 收到的字节
wire                   rx_valid;                              // 字节有效脉冲

//---------------- 共享条件提炼线 ---------------//
wire                   in_idle;                               // 处于空闲态
wire                   in_recv;                               // 处于收种子态
wire                   in_measure;                            // 处于测量态
wire                   byte_fire;                             // 种子字节落袋事件
wire                   decode_done_fire;                      // 解码完成事件
wire                   send_fire;                             // 发送字节装载事件

//---------------- 以下为逻辑实现 ---------------//

//////////////////////////////////////////////////////////////////
// 共享条件：全模块只此一份
//////////////////////////////////////////////////////////////////
assign  in_idle          = ( curr_state == S_IDLE      );
assign  in_recv          = ( curr_state == S_RECV_SEED );
assign  in_measure       = ( curr_state == S_MEASURE   );
assign  byte_fire        = rx_valid & ( in_idle | in_recv );  // 仅收种子的两个状态采样
assign  decode_done_fire = ( curr_state == S_DECODE ) & cd_done;
assign  send_fire        = ( next_state == S_SEND );

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
        S_IDLE      : begin
            if( rx_valid ) begin
                next_state = S_RECV_SEED;
            end
            else begin
                next_state = S_IDLE;
            end
        end   // 收到种子第 0 字节
        S_RECV_SEED : begin
            if( byte_fire & ( cnt_seed_byte == 4'd7 ) ) begin
                next_state = S_DECODE;
            end
            else begin
                next_state = S_RECV_SEED;
            end
        end   // 收满 8 字节（判的是本拍落袋字节的序号）
        S_DECODE     : begin
            if( cd_done ) begin
                next_state = S_MEASURE;
            end
            else begin
                next_state = S_DECODE;
            end
        end   // 解码完成
        S_MEASURE    : begin
            if( cnt_win >= WIN_LAST ) begin
                next_state = S_ROUND_END;
            end
            else begin
                next_state = S_MEASURE;
            end
        end   // 测量窗计满
        S_ROUND_END  : begin
            if( ro_done ) begin
                if( round_cnt >= LAST_ROUND ) begin
                    next_state = S_SEND;
                end
                else begin
                    next_state = S_MEASURE;
                end
            end
            else begin
                next_state = S_ROUND_END;
            end
        end   // 一轮完成：末轮转发送，否则开下一轮
        S_SEND       : begin
            next_state = S_SEND_WAIT;
        end   // 装载一字节（恰 1 拍）
        S_SEND_WAIT  : begin
            if( tx_done & ( cnt_tx_byte >= TX_BYTE_NUM ) ) begin
                next_state = S_IDLE;
            end
            else if( tx_done ) begin
                next_state = S_SEND;
            end
            else begin
                next_state = S_SEND_WAIT;
            end
        end   // 一字节发完：全部发完收工，否则发下一字节
        default     : begin
            next_state = S_IDLE;
        end   // 跑飞恢复
    endcase
end

//////////////////////////////////////////////////////////////////
// 种子拼装：字节按低字节在前落位（byte0 -> seed[7:0]）
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        seed_reg <= 64'd0;
    end
    else if( byte_fire ) begin
        seed_reg[cnt_seed_byte * 8 +: 8] <= rx_byte;
    end
    else begin
        seed_reg <= seed_reg;
    end
end

//////////////////////////////////////////////////////////////////
// 种子字节计数：落袋递增；空闲态清零（为下一次挑战复位）
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        cnt_seed_byte <= 4'd0;
    end
    else if( byte_fire ) begin
        cnt_seed_byte <= cnt_seed_byte + 4'd1;
    end
    else if( in_idle ) begin
        cnt_seed_byte <= 4'd0;
    end
    else begin
        cnt_seed_byte <= cnt_seed_byte;
    end
end

//////////////////////////////////////////////////////////////////
// 解码启动脉冲：进入 DECODE 的首拍为高（恰 1 拍）
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        cd_start <= 1'b0;
    end
    else begin
        cd_start <= ( next_state == S_DECODE );
    end
end

//////////////////////////////////////////////////////////////////
// 测量窗使能：跟随 S_MEASURE（±1 拍跟随误差，见头注释时序口径）
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        measure_en <= 1'b0;
    end
    else begin
        measure_en <= in_measure;
    end
end

//////////////////////////////////////////////////////////////////
// 测量窗计数：测量态计数，其余状态清零（每轮重新开窗）
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        cnt_win <= 17'd0;
    end
    else if( in_measure ) begin
        cnt_win <= cnt_win + 17'd1;
    end
    else begin
        cnt_win <= 17'd0;
    end
end

//////////////////////////////////////////////////////////////////
// 测量轮计数：解码完成清零，一窗完成递增（0~7）
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        round_cnt <= 4'd0;
    end
    else if( decode_done_fire ) begin
        round_cnt <= 4'd0;
    end
    else if( ( curr_state == S_ROUND_END ) & ro_done ) begin
        round_cnt <= round_cnt + 4'd1;
    end
    else begin
        round_cnt <= round_cnt;
    end
end

//////////////////////////////////////////////////////////////////
// 发送字节装载：发送态首拍从频率扁平总线取一字节（低字节在前）
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        tx_byte <= 8'd0;
    end
    else if( send_fire ) begin
        tx_byte <= ring_freq[cnt_tx_byte * 8 +: 8];
    end
    else begin
        tx_byte <= tx_byte;
    end
end

//////////////////////////////////////////////////////////////////
// 发送请求脉冲：进入 SEND 的首拍为高（恰 1 拍，uart_tx 空闲采样）
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        tx_valid <= 1'b0;
    end
    else begin
        tx_valid <= ( next_state == S_SEND );
    end
end

//////////////////////////////////////////////////////////////////
// 已发字节计数：装载递增；空闲态清零（为下一次响应复位）
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        cnt_tx_byte <= 6'd0;
    end
    else if( send_fire ) begin
        cnt_tx_byte <= cnt_tx_byte + 6'd1;
    end
    else if( in_idle ) begin
        cnt_tx_byte <= 6'd0;
    end
    else begin
        cnt_tx_byte <= cnt_tx_byte;
    end
end

//////////////////////////////////////////////////////////////////
// UART 接收：PC -> PL 种子字节流
//////////////////////////////////////////////////////////////////
uart_rx # ( .CLKS_PER_BIT ( CLKS_PER_BIT )
) u_uart_rx (
    .clk         ( clk          ),   // 系统时钟
    .rst         ( rst          ),   // 高有效同步复位
    .rx_serial   ( rx           ),   // 串行输入（顶层 rx 引脚）
    .rx_byte     ( rx_byte      ),   // output，收到的字节
    .rx_valid    ( rx_valid     )    // output，字节有效脉冲
);

//////////////////////////////////////////////////////////////////
// UART 发送：PL -> PC 频率字节流
//////////////////////////////////////////////////////////////////
uart_tx # ( .CLKS_PER_BIT ( CLKS_PER_BIT )
) u_uart_tx (
    .clk         ( clk          ),   // 系统时钟
    .rst         ( rst          ),   // 高有效同步复位
    .tx_valid    ( tx_valid     ),   // 发送请求脉冲
    .tx_byte     ( tx_byte      ),   // 待发送字节
    .tx_serial   ( tx           ),   // output，串行输出（顶层 tx 引脚）
    .tx_active   (              ),   // output，未使用
    .tx_done     ( tx_done      )    // output，一字节发完脉冲
);

//////////////////////////////////////////////////////////////////
// 挑战解码：种子 -> 8 轮配对表
//////////////////////////////////////////////////////////////////
challenge_decode # ( .N_ROUNDS ( N_ROUNDS ),
                     .N_RINGS  ( 16       ),
                     .IDX_W    ( 4        )
) u_cd (
    .clk         ( clk           ),   // 系统时钟
    .rst         ( rst           ),   // 高有效同步复位
    .start       ( cd_start      ),   // 启动脉冲
    .seed        ( seed_reg      ),   // 拼装完成的种子
    .pair_table  (               ),   // output，W2 未使用：比较在 PC 端（同种子同算法重算），留待 W3 片内比较
    .done        ( cd_done       )    // output，完成脉冲
);

//////////////////////////////////////////////////////////////////
// RO 阵列：16 环频率测量（组合环豁免见 w2_waiver.xdc）
//////////////////////////////////////////////////////////////////
ro_array # ( .N_RINGS    ( 16            ),
             .CNT_W      ( 16            ),
             .DIV_STAGES ( 5             )
) u_ro_array (
    .clk         ( clk           ),   // 系统时钟
    .rst         ( rst           ),   // 高有效同步复位
    .measure_en  ( measure_en    ),   // 测量窗使能
    .busy        ( ro_busy       ),   // output，测量进行中（观察用）
    .done        ( ro_done       ),   // output，一窗完成脉冲
    .ring_freq   ( ring_freq     )    // output，16 环频率锁存
);

endmodule
