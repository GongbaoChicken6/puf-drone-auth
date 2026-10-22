`timescale 1ns / 1ps
//============================================================================
// ro_entropy.v -- W4-P4 T2: 上电熵采样（P1-5 终端跨断电重放修复）
//----------------------------------------------------------------------------
// 设计依据：docs/plans/W4_design.md §6 + docs/plans/W4_T1T2_design.md v2 §2
//
// 行为：start 脉冲 -> 开一个测量窗（SAMPLE_CYCLES）-> 窗末 ro_array done
//       -> 取 16 个环计数器的**低 4 bit 拼接**（冻结算法，非 XOR）成 64-bit
//       boot_seed -> seed_valid=1 锁存。w3_top 用 seed_valid 上升沿产生
//       seed_load 脉冲，重装载 terminal_fsm 的 c2_counter。
//
// 语义：每次上电 C2 初值不同 -> 换电重启后旧 RESULT 帧的 R2 不再匹配 ->
//       terminal_fsm S_VERIFY_R2 比对失败 -> BLOCKED（终端侧重放拒止）。
//
// 诚实边界（设计书冻结）：仿真下 ro_array_sim 频率来自确定性 fixture，
//       boot_seed 可预测（TB 用它做黄金锁）；**真实熵只在板上成立**。
//       有效熵诚实口径 ~16-32bit/次上电 + 服务端 128 窗兜底（R6）。
//============================================================================
module ro_entropy # (
    parameter N_RINGS       = 16        ,   // 环振数量（16 x 4bit = 64bit 恰满）
    parameter CNT_W         = 16        ,   // 每环计数器位宽（同 ro_array）
    parameter [31:0] SAMPLE_CYCLES = 32'd1_000_000  // 采样窗（10ms @100MHz）
  )
  (
    input  wire                       clk         ,
    input  wire                       rst         ,
    input  wire                       start       ,   // 单拍脉冲：启动一次熵采样

    // ro_array 接口（由上层例化并互连）
    output wire                       measure_en  ,
    output wire                       ring_en     ,
    input  wire                       busy        ,
    input  wire                       done        ,
    input  wire [N_RINGS*CNT_W-1:0]   ring_freq   ,

    // 结果
    output reg                        seed_valid  ,   // 1 = boot_seed 已锁存
    output reg  [63:0]                boot_seed   ,   // 16 x 低4bit 拼接
    // M4(auto-review)：独立故障口——seed_valid=0 原是三义信号（采样中/卡死/
    // 零熵被拒），板上无从分辨。seed_fault=1 精确指明"零熵被拒"（E_DONE 锁存），
    // 供板级观测（w3_top 心跳编码）与撤销 SEED_GATE_EN 旁路的回退判据使用
    output reg                        seed_fault      // 1 = 零熵被拒（fail-closed 且可观测）
  );

//---------------- 状态机 ----------------//
localparam [1:0] E_IDLE   = 2'd0,   // 等 start
                 E_SAMPLE = 2'd1,   // 采样窗计数
                 E_WAIT   = 2'd2,   // 等 ro_array done
                 E_DONE   = 2'd3;   // 已锁存（保持）

reg [1:0]  st       = E_IDLE;
reg [31:0] win_cnt  = 32'd0;
reg        me_r     = 1'b0;
reg        re_r     = 1'b0;
reg [63:0] seed_acc = 64'd0;
integer    i;

assign measure_en = me_r;
assign ring_en    = re_r;

always @ ( posedge clk ) begin
    if ( rst ) begin
        st         <= E_IDLE;
        win_cnt    <= 32'd0;
        me_r       <= 1'b0;
        re_r       <= 1'b0;
        seed_acc   <= 64'd0;
        boot_seed  <= 64'd0;
        seed_valid <= 1'b0;
        seed_fault <= 1'b0;
    end
    else begin
        case ( st )
            E_IDLE : begin
                if ( start ) begin
                    me_r    <= 1'b1;            // 开窗
                    re_r    <= 1'b1;            // 使能环振
                    win_cnt <= 32'd0;
                    st      <= E_SAMPLE;
                end
            end
            E_SAMPLE : begin
                if ( win_cnt >= SAMPLE_CYCLES - 32'd1 ) begin
                    me_r    <= 1'b0;            // 关窗 -> ro_array 一拍后 done
                    win_cnt <= 32'd0;
                    st      <= E_WAIT;
                end
                else begin
                    win_cnt <= win_cnt + 32'd1;
                end
            end
            E_WAIT : begin
                re_r <= 1'b0;                   // 采样结束，停振（功耗）
                if ( done ) begin
                    // 冻结算法：各环计数器低 4bit **拼接**（非 XOR）
                    for ( i = 0; i < N_RINGS; i = i + 1 )
                        seed_acc[4*i +: 4] <= ring_freq[i*CNT_W +: 4];
                    st <= E_DONE;
                end
            end
            E_DONE : begin
                boot_seed  <= seed_acc;
                // F4 健康检查：全零种子 = 16 环低4bit 全部相同（板上概率
                // ~2^-64，但仿真 fallback 或极端退化可触发）= 零熵。
                // 拒绝置 seed_valid（fail-closed，与 T1b k_boot 检查对称）；
                // w3_top 的 F2 门控因此压制认证——宁可阻断也不带零熵运行。
                if (seed_acc == 64'd0) begin
                    seed_valid <= 1'b0;         // 保持无效（fail-closed）
                    seed_fault <= 1'b1;         // M4: 独立指示"零熵被拒"（不再三义）
                end else begin
                    seed_valid <= 1'b1;         // 锁存完成
                end
            end
            default : st <= E_IDLE;
        endcase
    end
end

endmodule