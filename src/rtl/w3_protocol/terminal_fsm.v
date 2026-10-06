//============================================================================
// terminal_fsm.v -- HF-IDA 终端协议状态机（W3 收官模块）
//----------------------------------------------------------------------------
// 职责：编排完整双向认证流程（契约 §5 时序）：
//   IDLE → 发ACCESS → 等挑战 → 处理种子 → 发R1 → 等判决
//        → (通过→验R2→发确认→会话 / 灰区→加测→重交 / 拒绝→阻断)
//
// 集成（契约 §6.1 全部 8 条规则）：
//   RX: frame_parser 的 frame_ok 粘滞锁存 + payload_rd_addr 读取
//   TX: mavlink_frame 的 start/payload_phase/frame_done 握手
//   SEQ: frame_done 后自增（§6.1-3）
//   超时: 每个等待态独立计时（§5 的 2s）
//
// W3 简化（PUF 桩）：种子处理 = 种子直通做响应（协议闭环优先）。
//   W3+ 升级路径：替换 compute_response() 为 challenge_decode + ro_array。
//============================================================================

module terminal_fsm # (
    parameter TIMEOUT_CYCLES = 32'd50_000_000     // 0.5s @ 100MHz（板上用 200M=2s）
) (
    input  wire        clk       ,
    input  wire        rst       ,
    // -- 外部控制 ------------------------------------------------------------
    input  wire        auth_start,                 // 启动认证（单拍）
    input  wire [7:0]  terminal_id,                // 终端 ID
    output wire        auth_busy ,                 // 认证进行中
    output wire [1:0]  auth_result,                // 0=进行中 1=通过 2=拒绝 3=阻断
    // -- RX 接口（frame_parser）----------------------------------------------
    input  wire [23:0] fp_msg_id ,                 // 消息 ID（fp_frame_ok_pulse 时有效）
    input  wire [7:0]  fp_pay_len,
    input  wire        fp_frame_ok,                // 单拍脉冲（本模块粘滞锁存）
    input  wire        fp_frame_err,
    output reg  [4:0]  fp_rd_addr,                 // 载荷读地址（本模块驱动）
    input  wire [7:0]  fp_rd_data ,                // 载荷组合读出
    output wire        fp_rx_inhibit,               // 载荷保护：读载荷期间阻止新帧接收
    // -- TX 接口（mavlink_frame）---------------------------------------------
    output reg         mf_start  ,                 // 启动组帧
    output reg  [23:0] mf_msg_id ,
    output reg  [5:0]  mf_pay_len,
    output reg  [7:0]  mf_pay_byte,                // 载荷字节
    output reg         mf_pay_valid,               // 载荷有效（仅 payload_phase=1 期间）
    output reg  [7:0]  mf_seq    ,                 // 序号（自增）
    output wire [7:0]  mf_sysid  ,                 // 系统 ID（固定 01）
    output wire [7:0]  mf_compid ,                 // 组件 ID（固定 02）
    input  wire        mf_busy   ,
    input  wire        mf_pay_phase,               // 载荷窗口
    input  wire        mf_frame_done,
    input  wire        mf_frame_err
);

    //========================================================================
    // 状态定义（4-bit，最多 16 态）
    //========================================================================
    localparam [3:0] S_IDLE        = 4'd0 ,   // 空闲等 auth_start
                     S_TX_ACCESS   = 4'd1 ,   // 发 ACCESS_REQUEST
                     S_WAIT_CHALL  = 4'd2 ,   // 等 CHALLENGE 帧
                     S_PROC_SEEDS  = 4'd3 ,   // 读 4 种子 → 生成 4 响应
                     S_TX_R1       = 4'd4 ,   // 发 RESPONSE_R1（4×8B）
                     S_WAIT_RESULT = 4'd5 ,   // 等 RESULT 或 EXTRA_CHALLENGE
                     S_VERIFY_R2   = 4'd6 ,   // 验证 R2
                     S_TX_CONFIRM  = 4'd7 ,   // 发 CONFIRM
                     S_SESSION     = 4'd8 ,   // 认证通过
                     S_PROC_EXTRA  = 4'd9 ,   // 灰区：读 3 种子
                     S_TX_R1_EXTRA = 4'd10,   // 发 RESPONSE_R1（3×8B=24B）
                     S_BLOCKED     = 4'd11,   // 认证失败阻断
                     S_CALC_R2     = 4'd12;   // 启动 Speck 计算 R2（共享起始状态）

    reg [3:0] state = S_IDLE;

    //========================================================================
    // 内部寄存器
    //========================================================================
    reg [7:0]  seq_cnt      = 8'h00;            // SEQ 自增计数器
    reg [31:0] timeout_cnt  = 32'd0;            // 超时计数（32-bit：板上 200M 需要 28-bit）
    reg        rx_ok_latch  = 1'b0;             // frame_ok 粘滞
    reg [1:0]  result_r     = 2'd0;             // auth_result 寄存

    // 发送载荷缓冲（最大 32B，发 ACCESS/R1/CONFIRM 前预填）
    reg [7:0]  tx_buf [0:31];
    reg [5:0]  tx_len  = 6'd0;                   // 本次发送载荷长度
    reg [5:0]  tx_idx  = 6'd0;                   // 发送索引

    // PUF 响应缓冲（4 种子 → 4×8B 响应 = 32B，W3 桩 = 种子直通）
    reg [7:0]  resp_buf [0:31];

    // C2 反挑战计数器 + 动态 R2（防重放，审查盲区 #2 修复）
    // C2 每次 auth_start 递增 → R2 = ~C2 也变 → 旧 R2 无法重放
    reg [7:0]  c2_counter [0:7];
    reg [7:0]  r2_expected [0:7];

    // Speck64/96 密码核（R2 = Speck_encrypt(device_key, C2)）
    parameter [95:0] DEVICE_KEY = 96'h13121110_0b0a0908_03020100;  // W3 测试值，W4 从 PUF 提取

    wire [95:0] sp_key;
    wire [63:0] sp_plaintext;
    wire [63:0] sp_ciphertext;
    wire        sp_start;     // 门控后输出到 Speck
    wire        sp_done;
    wire        sp_busy;

    reg  [7:0]  calc_wd_cnt = 8'd0;             // S_CALC_R2 看门狗计数器
    reg         sp_start_w  = 1'b0;              // Speck 启动脉冲（内部）
    localparam  CALC_WD_MAX = 8'd255;            // 256 周期看门狗

    assign sp_key = DEVICE_KEY;

    // C2 字节重排：c2_counter[0..7] → sp_plaintext（NSA 小端约定）
    // C2[0]=y LSB → pt[39:32], C2[1] → pt[47:40], C2[2] → pt[55:48], C2[3]=y MSB → pt[63:56]
    // C2[4]=x LSB → pt[7:0],   C2[5] → pt[15:8],  C2[6] → pt[23:16], C2[7]=x MSB → pt[31:24]
    assign sp_plaintext[39:32] = c2_counter[0];  // 已递增（Speck采样时计数器已更新）
    assign sp_plaintext[47:40] = c2_counter[1];
    assign sp_plaintext[55:48] = c2_counter[2];
    assign sp_plaintext[63:56] = c2_counter[3];
    assign sp_plaintext[7:0]   = c2_counter[4];
    assign sp_plaintext[15:8]  = c2_counter[5];
    assign sp_plaintext[23:16] = c2_counter[6];
    assign sp_plaintext[31:24] = c2_counter[7];

    // Speck 密文 → R2 字节（NSA 小端拆包）
    // r2[0]=y LSB → ct[39:32], r2[1] → ct[47:40], r2[2] → ct[55:48], r2[3]=y MSB → ct[63:56]
    // r2[4]=x LSB → ct[7:0],   r2[5] → ct[15:8],  r2[6] → ct[23:16], r2[7]=x MSB → ct[31:24]
    // 注意：这些 wire 用于 S_CALC_R2 中锁存 r2_expected
    wire [7:0] r2_byte_0 = sp_ciphertext[39:32];
    wire [7:0] r2_byte_1 = sp_ciphertext[47:40];
    wire [7:0] r2_byte_2 = sp_ciphertext[55:48];
    wire [7:0] r2_byte_3 = sp_ciphertext[63:56];
    wire [7:0] r2_byte_4 = sp_ciphertext[7:0];
    wire [7:0] r2_byte_5 = sp_ciphertext[15:8];
    wire [7:0] r2_byte_6 = sp_ciphertext[23:16];
    wire [7:0] r2_byte_7 = sp_ciphertext[31:24];

    assign sp_start = sp_start_w & ~sp_busy;  // B 代理建议：忙时不启动

    //--------------------------------------------------------------------
    // Speck64/96 密码核实例
    //--------------------------------------------------------------------
    speck64_96 u_speck (
        .clk            (clk           ),
        .rst            (rst           ),
        .start          (sp_start      ),
        .key_in         (sp_key        ),
        .plaintext_in   (sp_plaintext  ),
        .ciphertext_out (sp_ciphertext ),
        .done           (sp_done       ),
        .busy           (sp_busy       )
    );
    integer    j;
    initial begin
        for (j = 0; j < 8; j = j + 1) begin
            c2_counter[j]  = 8'hA0 + j[7:0];
            r2_expected[j] = ~(8'hA0 + j[7:0]);
        end
    end

    assign auth_busy  = (state != S_IDLE) && (state != S_SESSION);
    // 载荷保护：S_PROC_SEEDS/S_PROC_EXTRA/S_VERIFY_R2 期间读 fp 载荷缓冲，
    // 阻止 frame_parser 接收新帧覆盖缓冲（并发竞态修复）
    assign fp_rx_inhibit = (state == S_CALC_R2) || (state == S_PROC_SEEDS) || (state == S_PROC_EXTRA)
                        || (state == S_VERIFY_R2);
    assign auth_result = result_r;
    assign mf_sysid  = 8'h01;
    assign mf_compid = 8'h02;

    //========================================================================
    // frame_ok 粘滞锁存（契约 §6.1-7）
    //========================================================================
    always @(posedge clk) begin
        if (rst)                       rx_ok_latch <= 1'b0;
        else if (fp_frame_ok)          rx_ok_latch <= 1'b1;
        else if (state == S_PROC_SEEDS || state == S_PROC_EXTRA ||
                 state == S_WAIT_CHALL || state == S_WAIT_RESULT)
            ; // 在等待态保持
        else                           rx_ok_latch <= 1'b0;  // 处理完自动清
    end

    //========================================================================
    // SEQ 自增（契约 §6.1-3：frame_done 之后才自增）
    //========================================================================
    always @(posedge clk) begin
        if (rst)                    seq_cnt <= 8'h00;
        else if (mf_frame_done)      seq_cnt <= seq_cnt + 8'd1;
    end

    //========================================================================
    // 主状态机
    //========================================================================
    integer k;
    // synth translate_off
    reg [3:0] state_prev = S_IDLE;              // 调试用：前态跟踪
    always @(posedge clk) begin
        if (state != state_prev) begin
            $display("[FSM] %0d -> %0d @%0t", state_prev, state, $time);
            state_prev <= state;
        end
    end
    // synth translate_on

    always @(posedge clk) begin
        if (rst) begin
            state       <= S_IDLE;
            timeout_cnt <= 32'd0;
            result_r    <= 2'd0;
            mf_start    <= 1'b0;
            mf_msg_id   <= 24'h0;
            mf_pay_len  <= 6'd0;
            mf_pay_byte <= 8'h00;
            mf_pay_valid<= 1'b0;
            mf_seq      <= 8'h00;
            fp_rd_addr  <= 5'd0;
            tx_idx      <= 6'd0;
        end else begin
            // 默认单拍脉冲清零
            mf_start     <= 1'b0;
            mf_pay_valid <= 1'b0;

            // 超时计数（所有非 IDLE/SESSION/TX 态共享）
            if (state == S_WAIT_CHALL || state == S_WAIT_RESULT) begin
                timeout_cnt <= timeout_cnt + 32'd1;
            end else begin
                timeout_cnt <= 32'd0;
            end

            case (state)
                //====================================================
                S_IDLE: begin
                    // result_r 不在此清零——BLOCKED 的结果需要被外部读到
                    // 只在新一轮认证启动时才清
                    if (auth_start) begin
                        result_r <= 2'd0;
                        state    <= S_CALC_R2;
                    end
                end

                //====================================================
                // 发送帧（共用逻辑：start → 等窗口 → 喂载荷 → 等 done）
                //====================================================
                S_TX_ACCESS, S_TX_R1, S_TX_CONFIRM, S_TX_R1_EXTRA: begin
                    // ⚠ 优先级：frame_done > frame_err > 启动新帧 > 喂载荷
                    // frame_done 必须最先检查：帧完成拍 mf_busy 同步拉低，
                    // 若先查 !mf_busy 会误入"启动新帧"分支（实际 bug#3）
                    if (mf_frame_done) begin
                        // 帧发完：转下一态
                        case (state)
                            S_TX_ACCESS:   state <= S_WAIT_CHALL;
                            S_TX_R1:       state <= S_WAIT_RESULT;
                            S_TX_R1_EXTRA: state <= S_WAIT_RESULT;
                            S_TX_CONFIRM:  state <= S_SESSION;
                            default:       state <= S_IDLE;
                        endcase
                    end else if (mf_frame_err) begin
                        state <= S_BLOCKED;         // 组帧失败
                        result_r <= 2'd3;
                    end else if (!mf_busy && !mf_start) begin
                        // 尚未启动：发 start
                        mf_start   <= 1'b1;
                        mf_seq     <= seq_cnt;
                        tx_idx     <= 6'd0;
                        case (state)
                            S_TX_ACCESS: begin
                                mf_msg_id  <= 24'h0090;  // ACCESS_REQUEST
                                mf_pay_len <= tx_len;    // 16B
                            end
                            S_TX_R1: begin
                                mf_msg_id  <= 24'h0092;  // RESPONSE_R1
                                mf_pay_len <= 6'd32;     // 4×8B
                                for (k = 0; k < 32; k = k + 1)
                                    tx_buf[k] <= resp_buf[k];
                            end
                            S_TX_R1_EXTRA: begin
                                mf_msg_id  <= 24'h0092;  // RESPONSE_R1
                                mf_pay_len <= 6'd24;     // 3×8B
                                for (k = 0; k < 24; k = k + 1)
                                    tx_buf[k] <= resp_buf[k];
                            end
                            S_TX_CONFIRM: begin
                                mf_msg_id  <= 24'h0094;  // CONFIRM
                                mf_pay_len <= 6'd5;      // tid(4)+status(1)
                            end
                        endcase
                    end else if (mf_pay_phase && tx_idx < mf_pay_len) begin
                        // 载荷窗口内：逐字节喂
                        mf_pay_byte  <= tx_buf[tx_idx[4:0]];
                        mf_pay_valid <= 1'b1;
                        tx_idx       <= tx_idx + 6'd1;
                    end
                end

                //====================================================
                S_WAIT_CHALL: begin
                    if (rx_ok_latch && fp_msg_id == 24'h0091 && fp_pay_len == 8'd32) begin
                        // rx_ok_latch 不在此清零——锁存块的"非等待态清零"已覆盖
                        // （消除多驱动：A-P0-1 修复）
                        fp_rd_addr  <= 5'd0;
                        state       <= S_PROC_SEEDS;
                    end else if (timeout_cnt >= TIMEOUT_CYCLES) begin
                        state    <= S_BLOCKED;
                        result_r <= 2'd3;
                    end
                end

                //====================================================
                // 处理 4 个种子（W3 桩：种子直通做响应）
                // frame_parser 载荷 = 4×8B = 32B，逐字节读
                //====================================================
                S_PROC_SEEDS: begin
                    // 逐字节读（fp_rd_addr 是 5-bit，31+1 回绕到 0！
                    // 因此用"==31 即最后一个"判断，不依赖溢出）
                    resp_buf[fp_rd_addr] <= fp_rd_data;
                    if (fp_rd_addr == 5'd31) begin
                        state <= S_TX_R1;            // 第 32 字节处理完，退出
                    end else begin
                        fp_rd_addr <= fp_rd_addr + 5'd1;
                    end
                end

                //====================================================
                S_WAIT_RESULT: begin
                    if (rx_ok_latch && fp_msg_id == 24'h0093 && fp_pay_len == 8'd10) begin
                        // RESULT 帧 → 转验证态（不在本拍读数据！
                        // fp_rd_addr 同拍 NBA，读到的会是旧地址）
                        fp_rd_addr  <= 5'd0;
                        state       <= S_VERIFY_R2;
                    end else if (rx_ok_latch && fp_msg_id == 24'h0095 && fp_pay_len == 8'd24) begin
                        // EXTRA_CHALLENGE：灰区加测
                        fp_rd_addr  <= 5'd0;
                        state       <= S_PROC_EXTRA;
                    end else if (timeout_cnt >= TIMEOUT_CYCLES) begin
                        state    <= S_BLOCKED;
                        result_r <= 2'd3;
                    end
                end

                //====================================================
                // 处理 3 个种子（灰区加测，W3 桩）
                //====================================================
                S_PROC_EXTRA: begin
                    resp_buf[fp_rd_addr] <= fp_rd_data;
                    if (fp_rd_addr == 5'd23) begin
                        state <= S_TX_R1_EXTRA;      // 第 24 字节处理完
                    end else begin
                        fp_rd_addr <= fp_rd_addr + 5'd1;
                    end
                end

                //====================================================
                // 验证 R2（W3 简化：比较载荷 [2..9] 与期望值）
                //====================================================
                S_VERIFY_R2: begin
                    // 载荷布局：result(1)+hd(1)+r2(8) = 地址 [0]=result, [1]=hd, [2..9]=r2
                    if (fp_rd_addr == 5'd0) begin
                        // 第一拍：读 result 码
                        if (fp_rd_data == 8'h00) begin
                            fp_rd_addr <= 5'd2;     // PASS → 跳到 R2 字节
                        end else begin
                            state    <= S_BLOCKED;  // REJECT
                            result_r <= 2'd2;
                        end
                    end else if (fp_rd_addr >= 5'd2 && fp_rd_addr < 5'd10) begin
                        // 读 r2 字节 [2..9]
                        if (fp_rd_data != r2_expected[fp_rd_addr[3:0] - 5'd2]) begin
                            state    <= S_BLOCKED;  // R2 不匹配
                            result_r <= 2'd3;
                        end
                        fp_rd_addr <= fp_rd_addr + 5'd1;
                    end else if (fp_rd_addr >= 5'd10) begin
                        // 8 字节全部匹配 → 通过 → 发 CONFIRM
                        tx_buf[0] <= terminal_id;
                        tx_buf[1] <= 8'h00;
                        tx_buf[2] <= 8'h00;
                        tx_buf[3] <= 8'h00;
                        tx_buf[4] <= 8'h00;         // status = OK (protocol.py CONFIRM_OK=0)
                        tx_len    <= 6'd5;
                        state     <= S_TX_CONFIRM;
                        result_r  <= 2'd1;         // PASS
                    end
                end

                //====================================================
                S_SESSION: begin
                    // 认证通过。auth_start 直接启动新一轮（不经过 IDLE——
                    // 否则 auth_start 脉冲被本态消费后 IDLE 看不到）
                    if (auth_start) begin
                        result_r <= 2'd0;
                        state    <= S_CALC_R2;
                    end
                end

                //====================================================
                S_CALC_R2: begin
                    // 共享认证起始状态：C2++ → 预填载荷 → 启动 Speck → 等 done
                    if (calc_wd_cnt == 8'd0) begin
                        // 第一拍：递增 C2 + 预填载荷 + 启动 Speck
                        tx_buf[0]  <= terminal_id;
                        tx_buf[1]  <= 8'h00;
                        tx_buf[2]  <= 8'h00;
                        tx_buf[3]  <= 8'h00;
                        tx_buf[4]  <= 8'hDE;
                        tx_buf[5]  <= 8'hAD;
                        tx_buf[6]  <= 8'hBE;
                        tx_buf[7]  <= 8'hEF;
                        for (k = 0; k < 8; k = k + 1) begin
                            c2_counter[k] <= c2_counter[k] + 8'd1;
                            tx_buf[8+k]   <= c2_counter[k] + 8'd1;
                        end
                        tx_len     <= 6'd16;
                        sp_start_w <= 1'b1;
                        calc_wd_cnt <= 8'd1;
                    end else begin
                        sp_start_w <= 1'b0;

                        if (sp_done) begin
                            // Speck 完成：锁存 R2 并进入 TX_ACCESS
                            r2_expected[0] <= r2_byte_0;
                            r2_expected[1] <= r2_byte_1;
                            r2_expected[2] <= r2_byte_2;
                            r2_expected[3] <= r2_byte_3;
                            r2_expected[4] <= r2_byte_4;
                            r2_expected[5] <= r2_byte_5;
                            r2_expected[6] <= r2_byte_6;
                            r2_expected[7] <= r2_byte_7;
                            calc_wd_cnt <= 8'd0;
                            state <= S_TX_ACCESS;
                        end else if (calc_wd_cnt >= CALC_WD_MAX) begin
                            // 看门狗超时 → 阻断
                            calc_wd_cnt <= 8'd0;
                            result_r    <= 2'd3;
                            state       <= S_BLOCKED;
                        end else begin
                            calc_wd_cnt <= calc_wd_cnt + 8'd1;
                        end
                    end
                end

                //====================================================
                S_BLOCKED: begin
                    // 阻断冷却（W3 简化：立即回 IDLE；W3+ 加冷却计数器）
                    state <= S_IDLE;
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule