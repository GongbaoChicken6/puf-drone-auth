`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Design Name: puf-auth-w2
// Module Name: challenge_decode
// Description: 
//  挑战解码器：64-bit 种子 → 8 轮 × 8 对的确定性环配对表（512 bit）。
//  算法（与 PC 端 Python 黄金模型逐 bit 冻结一致，对拍基础）：
//    1. 64-bit 斐波那契 LFSR，多项式 x^64 + x^63 + x^61 + x^60 + 1，
//       反馈位 fb = s[63] ^ s[62] ^ s[60] ^ s[59]，初值 = seed；
//    2. 每次取数：先读当前 state[63:56] 作为 8-bit 随机数 d，随后 LFSR
//       前进 8 步（每拍 1 步）；
//    3. 每轮对 ring_order（初值 {15,14,...,0}）做 Fisher-Yates 洗牌：
//       for i = 15 downto 1: j = d % (i+1)，交换 order[i] 与 order[j]；
//       求模用 8 拍"移位-比较-减法"迭代精确实现（等价软件 %，非近似）；
//    4. 洗牌完按相邻两两切分配对：第 p 对 = (order[2p], order[2p+1])，
//       整轮 64-bit 排列写入 pair_table 本轮字段。
//  输出字段格式（位冻结）：round r 占 [r*64 +: 64]；round 内 pair p 占
//  [p*8 +: 8]，低 4 位 = 环 A，高 4 位 = 环 B。
//  排列性质由 Fisher-Yates 构造保证：每轮 16 个环号各出现恰好一次。
//  同一 seed → 同一 pair_table：纯同步确定性逻辑，全部寄存器带初值。
//  全零种子：LFSR 停在 0、j 恒 0，输出仍是合法排列（不挂死）；种子由
//  PC 端 CSPRNG 生成，不会发全零。
//  延迟：每轮 15 次交换 × (8 拍取数 + 8 拍求模 + 1 拍交换) + 1 拍写表
//  = 256 拍，8 轮共约 2050 拍（20.5us @ 100MHz，远小于 8ms 测量窗）。
//////////////////////////////////////////////////////////////////////////////////
module challenge_decode # (
    parameter N_ROUNDS = 8     ,   // 配对轮数
    parameter N_RINGS  = 16    ,   // 环数
    parameter IDX_W    = 4         // 环号位宽
  )
  (
    // 时钟与复位
    input                               clk         ,   // 系统时钟
    input                               rst         ,   // 高有效同步复位

    // 命令与种子
    input                               start       ,   // 启动脉冲（单拍，seed 须已稳定）
    input  [63:0]                       seed        ,   // 64-bit 挑战种子

    // 配对表输出
    output  [N_ROUNDS*N_RINGS*IDX_W-1:0] pair_table ,   // 8 轮 × 8 对 × 2 环号（格式见头注释）
    output                              done            // 完成脉冲（单拍，pair_table 已有效）
  );

//---------------- 状态编码 ---------------//
localparam    [2:0]    S_IDLE      = 3'd0;                   // 等待 start
localparam    [2:0]    S_DRAW      = 3'd1;                   // LFSR 前进 8 步并取 8-bit 随机数
localparam    [2:0]    S_MOD       = 3'd2;                   // 移位-减法求 j = d % (i+1)
localparam    [2:0]    S_SWAP      = 3'd3;                   // 交换 ring_order[i] / ring_order[j]
localparam    [2:0]    S_ROUND_END = 3'd4;                   // 本轮排列写入配对表并复位排列
localparam    [2:0]    S_DONE      = 3'd5;                   // 完成脉冲（恰 1 拍）

//---------------- 常量 ---------------//
// 排列初值 {15,14,...,0}（按 16 环 × 4 bit 冻结；改 N_RINGS/IDX_W 需同步改写，
// elaboration 自检会拦截不匹配的参数组合）
localparam    [N_RINGS*IDX_W-1:0]    ORDER_INIT = { 4'd15, 4'd14, 4'd13, 4'd12,
                                                    4'd11, 4'd10, 4'd9,  4'd8,
                                                    4'd7,  4'd6,  4'd5,  4'd4,
                                                    4'd3,  4'd2,  4'd1,  4'd0 };  // 自然排列

//---------------- 状态机 ---------------//
reg      [2:0]                   curr_state = 3'd0;          // 现态
reg      [2:0]                   next_state;                 // 次态（组合 always 驱动）

//---------------- LFSR 与随机数 ---------------//
reg      [63:0]                  lfsr = 64'd0;               // LFSR 状态（反馈，启动时装载种子）
reg      [7:0]                   draw_reg = 8'd0;            // 本轮取出的 8-bit 随机数 d
wire                                 lfsr_fb;                // 反馈位

//---------------- 洗牌数据通路 ---------------//
reg      [N_RINGS*IDX_W-1:0]     ring_order = ORDER_INIT;    // 当前排列（扁平 16 × 4 bit）
reg      [3:0]                   i_cnt = 4'd0;               // Fisher-Yates 下标 i（15 递减到 1）
reg      [3:0]                   round_cnt = 4'd0;           // 轮计数（0 递增到 7）
reg      [2:0]                   bit_cnt = 3'd0;             // 取数 / 求模位计数（0 到 7）
reg      [4:0]                   mod_work = 5'd0;            // 求模工作余数（迭代中 < 2m <= 32）
wire     [4:0]                   mod_sel;                    // 模数 m = i + 1
wire     [4:0]                   mod_shift;                  // 余数左移并入 d 一位后的中间值
wire     [IDX_W-1:0]             j_sel;                      // 求模结果 j（交换用）

//---------------- 输出 ---------------//
reg      [N_ROUNDS*N_RINGS*IDX_W-1:0] pair_table_reg = {N_ROUNDS*N_RINGS*IDX_W{1'b0}};  // 配对表寄存器
reg                                  done_reg = 1'b0;        // 完成脉冲寄存器

//---------------- 共享条件提炼线 ---------------//
wire                                 start_fire;              // 启动事件（IDLE 态采到 start）
wire                                 in_draw;                 // 处于取数态
wire                                 in_mod;                  // 处于求模态
wire                                 in_swap;                 // 处于交换态
wire                                 in_round_end;            // 处于写表态
wire                                 bit_last;                // 取数 / 求模第 8 拍

//---------------- 以下为逻辑实现 ---------------//

//////////////////////////////////////////////////////////////////
// 共享条件：全模块只此一份（next_state 与各数据通路统一引用）
//////////////////////////////////////////////////////////////////
assign  start_fire  = ( curr_state == S_IDLE      ) & start;
assign  in_draw     = ( curr_state == S_DRAW      );
assign  in_mod      = ( curr_state == S_MOD       );
assign  in_swap     = ( curr_state == S_SWAP      );
assign  in_round_end= ( curr_state == S_ROUND_END );
assign  bit_last    = ( bit_cnt >= 3'd7 );

//////////////////////////////////////////////////////////////////
// LFSR 反馈与求模组合中间量（细线）
//////////////////////////////////////////////////////////////////
assign  lfsr_fb   = lfsr[63] ^ lfsr[62] ^ lfsr[60] ^ lfsr[59];     // x^64+x^63+x^61+x^60+1
assign  mod_sel   = { 1'b0, i_cnt } + 5'd1;                        // m = i + 1，i 属 [1,15] -> m 属 [2,16]
assign  mod_shift = { mod_work[3:0], draw_reg[7 - bit_cnt] };      // 余数左移挤入 d 的一位（MSB 在前）
assign  j_sel     = mod_work[IDX_W-1:0];                           // 8 拍迭代后的最终余数即 j

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
            if( start ) begin
                next_state = S_DRAW;
            end
            else begin
                next_state = S_IDLE;
            end
        end   // 收到启动脉冲
        S_DRAW      : begin
            if( bit_last ) begin
                next_state = S_MOD;
            end
            else begin
                next_state = S_DRAW;
            end
        end   // 8 步移位完成
        S_MOD       : begin
            if( bit_last ) begin
                next_state = S_SWAP;
            end
            else begin
                next_state = S_MOD;
            end
        end   // 8 拍求模完成
        S_SWAP      : begin
            if( i_cnt == 4'd1 ) begin
                next_state = S_ROUND_END;
            end
            else begin
                next_state = S_DRAW;
            end
        end   // 本次交换完成（判的是交换前的 i）
        S_ROUND_END : begin
            if( round_cnt >= 4'd7 ) begin
                next_state = S_DONE;
            end
            else begin
                next_state = S_DRAW;
            end
        end   // 本轮写表完成：末轮收工，否则开下一轮
        S_DONE      : begin
            next_state = S_IDLE;
        end   // 完成脉冲恰 1 拍
        default     : begin
            next_state = S_IDLE;
        end   // 跑飞恢复
    endcase
end

//////////////////////////////////////////////////////////////////
// LFSR：启动时装载种子；取数态每拍前进 1 步
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        lfsr <= 64'd0;
    end
    else if( start_fire ) begin
        lfsr <= seed;
    end
    else if( in_draw ) begin
        lfsr <= { lfsr[62:0], lfsr_fb };
    end
    else begin
        lfsr <= lfsr;
    end
end

//////////////////////////////////////////////////////////////////
// 随机数锁存：取数态第 1 拍读 state[63:56]（冻结语义：先取数后移位）
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        draw_reg <= 8'd0;
    end
    else if( in_draw & ( bit_cnt == 3'd0 ) ) begin
        draw_reg <= lfsr[63:56];
    end
    else begin
        draw_reg <= draw_reg;
    end
end

//////////////////////////////////////////////////////////////////
// 位计数：取数 / 求模期间 0~7 循环，其余状态清零
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        bit_cnt <= 3'd0;
    end
    else if( in_draw | in_mod ) begin
        bit_cnt <= bit_cnt + 3'd1;
    end
    else begin
        bit_cnt <= 3'd0;
    end
end

//////////////////////////////////////////////////////////////////
// 移位-减法求模：每拍挤入 d 的一位，大于等于 m 则减 m（等价 d % m）
// 非求模态清零工作余数（进入 MOD 时初值必为 0；SWAP 态读的是本拍
// 之前的最终余数，非阻塞语义保证不冲突）
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        mod_work <= 5'd0;
    end
    else if( in_mod ) begin
        if( mod_shift >= mod_sel ) begin
            mod_work <= mod_shift - mod_sel;
        end
        else begin
            mod_work <= mod_shift;
        end
    end
    else begin
        mod_work <= 5'd0;
    end
end

//////////////////////////////////////////////////////////////////
// Fisher-Yates 下标 i：启动 / 写表时装载 15，交换态递减
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        i_cnt <= 4'd0;
    end
    else if( start_fire ) begin
        i_cnt <= 4'd15;
    end
    else if( in_round_end ) begin
        i_cnt <= 4'd15;
    end
    else if( in_swap ) begin
        i_cnt <= i_cnt - 4'd1;
    end
    else begin
        i_cnt <= i_cnt;
    end
end

//////////////////////////////////////////////////////////////////
// 轮计数：启动清零，写表态递增（0~7）
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        round_cnt <= 4'd0;
    end
    else if( start_fire ) begin
        round_cnt <= 4'd0;
    end
    else if( in_round_end ) begin
        round_cnt <= round_cnt + 4'd1;
    end
    else begin
        round_cnt <= round_cnt;
    end
end

//////////////////////////////////////////////////////////////////
// 排列寄存器：交换态做 order[i] <-> order[j]（非阻塞读旧值，天然交换）；
// 启动 / 写表态重载自然排列（每轮从 {15..0} 重新洗牌）
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        ring_order <= ORDER_INIT;
    end
    else if( start_fire ) begin
        ring_order <= ORDER_INIT;
    end
    else if( in_round_end ) begin
        ring_order <= ORDER_INIT;
    end
    else if( in_swap ) begin
        ring_order[i_cnt * IDX_W +: IDX_W] <= ring_order[j_sel * IDX_W +: IDX_W];
        ring_order[j_sel * IDX_W +: IDX_W] <= ring_order[i_cnt * IDX_W +: IDX_W];
    end
    else begin
        ring_order <= ring_order;
    end
end

//////////////////////////////////////////////////////////////////
// 配对表：写表态把本轮 64-bit 排列冻结进对应轮字段
// （相邻两两成对：第 p 对 = 低 4 位 order[2p]（环 A）、高 4 位 order[2p+1]（环 B））
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        pair_table_reg <= {N_ROUNDS*N_RINGS*IDX_W{1'b0}};
    end
    else if( in_round_end ) begin
        pair_table_reg[round_cnt * N_RINGS * IDX_W +: N_RINGS*IDX_W] <= ring_order;
    end
    else begin
        pair_table_reg <= pair_table_reg;
    end
end

assign  pair_table = pair_table_reg;            // 寄存器直连出端口

//////////////////////////////////////////////////////////////////
// 状态机第三段：done 输出寄存（判 next_state，与状态进入同拍对齐）
//////////////////////////////////////////////////////////////////
always @ ( posedge clk ) begin
    if( rst ) begin
        done_reg <= 1'b0;
    end
    else begin
        done_reg <= ( next_state == S_DONE );
    end
end

assign  done = done_reg;                        // 寄存器直连出端口

//////////////////////////////////////////////////////////////////
// elaboration 自检：排列初值常量按 16 环 × 4-bit 环号冻结，参数不匹配
// 直接报错（Verilog-2001 不支持参数宽度的 sized literal，无法随参数伸缩）
//////////////////////////////////////////////////////////////////
generate
    if( ( N_RINGS != 16 ) | ( IDX_W != 4 ) ) begin : gen_param_check
        illegal_param_w2_frozen_16rings_4bit_idx u_param_check();
    end
endgenerate

endmodule
