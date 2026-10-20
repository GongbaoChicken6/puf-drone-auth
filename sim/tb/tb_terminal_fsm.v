`timescale 1ns / 1ps
//============================================================================
// tb_terminal_fsm.v — 协议状态机端到端测试
//----------------------------------------------------------------------------
// TB 扮演基站（frame_parser + mavlink_frame 的对端），驱动完整认证流：
// T1: 正常通过流程（ACCESS→CHALLENGE→R1→RESULT(pass+R2)→CONFIRM→SESSION）
// T2: 拒绝流程（RESULT 含 reject 码 → BLOCKED）
// T3: 超时流程（等挑战超时 → BLOCKED）
// TE1: Phase 8a 注册流（默认编译 ENROLL_IDLE_ACCEPT=1）：S_IDLE 无按键直收
//      0x0091 → R1 → S_WAIT_RESULT 背靠背再收 → R1 → 停喂后超时自清
// TE2: 注册态重放锁——压制 RESULT->超时->注册挑战->重放黄金 RESULT 必被 P2-1 守卫拒
// TEN: 参数=0 回归锁（CI 附加段自动跑，见 ci_regression.ps1 ENROLL_NEG step）
//============================================================================
module tb_terminal_fsm;

    reg         clk = 1'b0;
    reg         rst = 1'b1;
    reg         auth_start = 1'b0;
    reg  [7:0]  terminal_id = 8'd42;
    wire        auth_busy;
    wire [1:0]  auth_result;

    // frame_parser 模型（TB 驱动）
    reg  [23:0] fp_msg_id = 24'h0;
    reg  [7:0]  fp_pay_len = 8'd0;
    reg         fp_frame_ok = 1'b0;     // TB 发脉冲
    reg         fp_frame_err = 1'b0;
    wire [4:0]  fp_rd_addr;
    reg  [7:0]  fp_payload_buf [0:31];  // TB 填充
    wire [7:0]  fp_rd_data = fp_payload_buf[fp_rd_addr];

    // mavlink_frame 模型（TB 监听并模拟响应）
    wire        mf_start;
    wire [23:0] mf_msg_id;
    wire [5:0]  mf_pay_len;
    wire [7:0]  mf_pay_byte;
    wire        mf_pay_valid;
    wire [7:0]  mf_seq;
    wire [7:0]  mf_sysid;
    wire [7:0]  mf_compid;
    reg         mf_busy = 1'b0;
    reg         mf_pay_phase = 1'b0;
    reg         mf_frame_done = 1'b0;
    reg         mf_frame_err = 1'b0;

    integer errors = 0;
    reg saw_confirm = 1'b0;   // CONFIRM 帧监视（TE2 重放拒绝断言用）
    integer i;
    integer tx_byte_count = 0;
    reg [7:0] tx_captured [0:63];

    //------------------------------------------------------------------------
    // W4 B5a PUF 子系统（challenge_decode + 行为级 ro_array_sim）
    //------------------------------------------------------------------------
    wire        cd_start, cd_done;
    wire [63:0] cd_seed;
    wire [511:0] cd_pair_table;
    wire        ra_measure_en, ra_ring_en, ra_busy, ra_done;
    wire [255:0] ra_ring_freq;

    challenge_decode # (
        .N_ROUNDS ( 8 ), .N_RINGS ( 16 ), .IDX_W ( 4 )
    ) u_cd (
        .clk         (clk           ),
        .rst         (rst           ),
        .start       (cd_start      ),
        .seed        (cd_seed       ),
        .pair_table  (cd_pair_table ),
        .done        (cd_done       )
    );

    ro_array_sim # (
        .N_RINGS ( 16 ), .CNT_W ( 16 )
    ) u_ro_array (
        .clk         (clk           ),
        .rst         (rst           ),
        .measure_en  (ra_measure_en ),
        .ring_en     (ra_ring_en    ),
        .busy        (ra_busy       ),
        .done        (ra_done       ),
        .ring_freq   (ra_ring_freq  )
    );

    //------------------------------------------------------------------------
    // DUT
    //------------------------------------------------------------------------
`ifdef ENROLL_NEG
    // 负向变体（手动 xvlog -d ENROLL_NEG，不入 CI）：参数=0 默认行为回归锁
    terminal_fsm # (.TIMEOUT_CYCLES(1000), .MEASURE_CYCLES(32'd64)) dut (
`else
    // 默认（CI）：参数=1——Phase 8a 注册流覆盖 + 全部既有流程回归
    terminal_fsm # (.TIMEOUT_CYCLES(1000), .MEASURE_CYCLES(32'd64),
                    .ENROLL_IDLE_ACCEPT(1)) dut (
`endif
        .clk           (clk          ),
        .rst           (rst          ),
        .auth_start    (auth_start   ),
        .terminal_id   (terminal_id  ),
        .auth_busy     (auth_busy    ),
        .auth_result   (auth_result  ),
        // W4-T2 可注入端口 tie-off（黄金零改动）
        .c2_boot_seed  (64'hA7A6_A5A4_A3A2_A1A0),
        .device_key_in (96'h1312_1110_0B0A_0908_0302_0100),
        .use_ext_key   (1'b0),
        .seed_load     (1'b0),   // W4-P4 T2: TB 恒 0（板上接 ro_entropy）
        .cd_start      (cd_start     ),
        .cd_seed       (cd_seed      ),
        .cd_pair_table (cd_pair_table),
        .cd_done       (cd_done      ),
        .ra_measure_en (ra_measure_en),
        .ra_ring_en    (ra_ring_en   ),
        .ra_busy       (ra_busy      ),
        .ra_done       (ra_done      ),
        .ra_ring_freq  (ra_ring_freq ),
        .fp_msg_id     (fp_msg_id    ),
        .fp_pay_len    (fp_pay_len   ),
        .fp_frame_ok   (fp_frame_ok  ),
        .fp_frame_err  (fp_frame_err ),
        .fp_rd_addr    (fp_rd_addr   ),
        .fp_rd_data    (fp_rd_data   ),
        .mf_start      (mf_start     ),
        .mf_msg_id     (mf_msg_id    ),
        .mf_pay_len    (mf_pay_len   ),
        .mf_pay_byte   (mf_pay_byte  ),
        .mf_pay_valid  (mf_pay_valid ),
        .mf_seq        (mf_seq       ),
        .mf_sysid      (mf_sysid     ),
        .mf_compid     (mf_compid    ),
        .mf_busy       (mf_busy      ),
        .mf_pay_phase  (mf_pay_phase ),
        .mf_frame_done (mf_frame_done),
        .mf_frame_err  (mf_frame_err )
    );

    always #5 clk = ~clk;

    //------------------------------------------------------------------------
    // CONFIRM 帧监视（TE2：重放 RESULT 被拒后绝不应有 CONFIRM 发出）
    //------------------------------------------------------------------------
    always @(posedge clk) begin
        if (mf_frame_done && mf_msg_id == 24'h0094) saw_confirm <= 1'b1;
    end

    //------------------------------------------------------------------------
    // mavlink_frame 模型：收到 start 后模拟 payload_phase + frame_done
    //------------------------------------------------------------------------
    always @(posedge clk) begin
        mf_frame_done <= 1'b0;
        if (mf_start) begin
            mf_busy      <= 1'b1;
            mf_pay_phase <= 1'b0;
            tx_byte_count <= 0;
        end else if (mf_busy) begin
            // 模拟 10 拍头 + payload 窗口 + CRC + done
            if (!mf_pay_phase && tx_byte_count == 0) begin
                // 头发完，开窗口
                mf_pay_phase <= 1'b1;
            end else if (mf_pay_phase) begin
                // 收载荷字节
                if (mf_pay_valid) begin
                    tx_captured[tx_byte_count] <= mf_pay_byte;
                    tx_byte_count <= tx_byte_count + 1;
                    if (tx_byte_count + 1 >= mf_pay_len) begin
                        mf_pay_phase  <= 1'b0;    // 窗口关闭
                        mf_busy       <= 1'b0;
                        mf_frame_done <= 1'b1;    // 帧完成
                    end
                end
            end
        end
    end

    //------------------------------------------------------------------------
    // 辅助任务：TB 发一帧给 terminal_fsm（模拟 frame_parser 输出）
    //------------------------------------------------------------------------
    task feed_frame(input [23:0] msgid, input [7:0] paylen);
        begin
            @(negedge clk);
            fp_msg_id   <= msgid;
            fp_pay_len  <= paylen;
            fp_frame_ok <= 1'b1;
            @(negedge clk);
            fp_frame_ok <= 1'b0;
            @(negedge clk);   // 等 DUT 锁存
        end
    endtask

    //------------------------------------------------------------------------
    initial begin
        // 黄金数据：R2 期望值（与 DUT 的 r2_expected 一致：C0..C7）
        for (i = 0; i < 8; i = i + 1) begin
            fp_payload_buf[10 + i] = 8'hC0 + i;  // RESULT 载荷 [2..9] = r2
        end
        fp_payload_buf[10] = 8'h00;  // result=PASS（覆盖第一个 r2 字节位置前先设 result）
        // 等等，RESULT 载荷布局是 result(1B)+hd(1B)+r2(8B) = 地址 [0]=result, [1]=hd, [2..9]=r2
        fp_payload_buf[0] = 8'h00;
        fp_payload_buf[1] = 8'h05;
        // R2 = Speck(DEVICE_KEY, C2=A1..A8) = 7b 45 b0 54 5e 59 aa 94（Python 预计算）
        fp_payload_buf[2]  = 8'h7b; fp_payload_buf[3]  = 8'h45;
        fp_payload_buf[4]  = 8'h54; fp_payload_buf[5]  = 8'b0; // 注意：0x54 不是 b0
        fp_payload_buf[4]  = 8'hb0; fp_payload_buf[5]  = 8'h54;
        fp_payload_buf[6]  = 8'h5e; fp_payload_buf[7]  = 8'h59;
        fp_payload_buf[8]  = 8'haa; fp_payload_buf[9]  = 8'h94;

        repeat (3) @(negedge clk);
        rst = 1'b0;
        repeat (2) @(negedge clk);

        // ============ T1: 正常通过流程 ============
        $display("[..T1] normal pass flow");
        @(negedge clk);
        auth_start <= 1'b1;
        @(negedge clk);
        auth_start <= 1'b0;

        // DUT 应发 ACCESS_REQUEST（msgid=0x0090, len=16）
        wait (mf_frame_done === 1'b1);
        @(negedge clk);
        if (mf_msg_id !== 24'h0090) begin
            errors = errors + 1; $display("[T1 FAIL] ACCESS msgid=%h", mf_msg_id);
        end else
            $display("  [T1] ACCESS_REQUEST sent (16B)");

        // TB 发 CHALLENGE（4×8B 种子）
        for (i = 0; i < 32; i = i + 1)
            fp_payload_buf[i] = 8'h50 + i;   // 种子 A0..BF 等效
        feed_frame(24'h0091, 8'd32);

        // DUT 处理种子后应发 RESPONSE_R1（msgid=0x0092, len=32）
        wait (mf_frame_done === 1'b1);
        @(negedge clk);
        if (mf_msg_id !== 24'h0092) begin
            errors = errors + 1; $display("[T1 FAIL] R1 msgid=%h", mf_msg_id);
        end else if (mf_pay_len !== 6'd32) begin
            errors = errors + 1; $display("[T1 FAIL] R1 len=%0d expect 32", mf_pay_len);
        end else
            $display("  [T1] RESPONSE_R1 sent (32B, W4 B5a: PUF comparison bits)");

        // TB 发 RESULT（PASS + R2）——先重填载荷（CHALLENGE 种子已覆盖！）
        fp_payload_buf[0] = 8'h00;                   // result = PASS
        fp_payload_buf[1] = 8'h05;                   // hd = 5
        // R2 = Speck(DEVICE_KEY=13121110_0b0a0908_03020100, C2=A1..A8) — Python 预计算
        // key_bytes = 00 01 02 03 08 09 0a 0b 10 11 12 13 (NSA KAT key)
        // c2_bytes  = a1 a2 a3 a4 a5 a6 a7 a8 (first auth)
        // ct_bytes  = 7b 45 b0 54 5e 59 aa 94
        fp_payload_buf[2]  = 8'h7b; fp_payload_buf[3]  = 8'h45;
        fp_payload_buf[4]  = 8'hb0; fp_payload_buf[5]  = 8'h54;
        fp_payload_buf[6]  = 8'h5e; fp_payload_buf[7]  = 8'h59;
        fp_payload_buf[8]  = 8'haa; fp_payload_buf[9]  = 8'h94;
        feed_frame(24'h0093, 8'd10);

        // DUT 验 R2 后应发 CONFIRM
        wait (mf_frame_done === 1'b1);
        @(negedge clk);
        if (mf_msg_id !== 24'h0094) begin
            errors = errors + 1; $display("[T1 FAIL] CONFIRM msgid=%h", mf_msg_id);
        end else
            $display("  [T1] CONFIRM sent");

        // 最终应到 SESSION（auth_result=1）
        repeat (10) @(negedge clk);
        if (auth_result !== 2'd1) begin
            errors = errors + 1; $display("[T1 FAIL] result=%0d expect 1 (PASS)", auth_result);
        end else
            $display("[T1 PASS] full pass flow: ACCESS→CHALLENGE→R1→RESULT→CONFIRM→SESSION");

        // ============ T2: 拒绝流程 ============
        $display("[..T2] reject flow");
        repeat (5) @(negedge clk);          // 等 FSM 在 IDLE 稳定（SESSION 的 auth_start 已消费）
        @(negedge clk);
        auth_start <= 1'b1;
        @(negedge clk);
        auth_start <= 1'b0;
        wait (mf_frame_done === 1'b1); @(negedge clk);   // ACCESS
        feed_frame(24'h0091, 8'd32);                       // CHALLENGE
        wait (mf_frame_done === 1'b1); @(negedge clk);   // R1

        // 发 RESULT（REJECT）
        fp_payload_buf[0] = 8'h01;  // result = 1 (REJECT)
        fp_payload_buf[1] = 8'h20;  // hd = 32
        feed_frame(24'h0093, 8'd10);

        repeat (10) @(negedge clk);
        if (auth_result !== 2'd2) begin
            errors = errors + 1; $display("[T2 FAIL] result=%0d expect 2 (REJECT)", auth_result);
        end else
            $display("[T2 PASS] reject flow → BLOCKED");

        // ============ T3: 超时流程 ============
        $display("[..T3] timeout flow");
        repeat (5) @(negedge clk);          // 同理等稳定
        @(negedge clk);
        auth_start <= 1'b1;
        @(negedge clk);
        auth_start <= 1'b0;
        wait (mf_frame_done === 1'b1); @(negedge clk);   // ACCESS 发出
        // 不发 CHALLENGE → 等超时（TIMEOUT_CYCLES=1000）
        repeat (1200) @(negedge clk);
        if (auth_result !== 2'd3) begin
            errors = errors + 1; $display("[T3 FAIL] result=%0d expect 3 (timeout)", auth_result);
        end else
            $display("[T3 PASS] challenge timeout → BLOCKED");

`ifndef ENROLL_NEG
        // ============ TE1: Phase 8a 注册流（ENROLL_IDLE_ACCEPT=1） ============
        $display("[..TE1] enroll idle-accept flow (Phase 8a)");
        // 板上语义：enroll 前按 SW13 复位——TB 等价重新拉 rst
        rst = 1'b1;
        repeat (2) @(negedge clk);
        rst = 1'b0;
        repeat (2) @(negedge clk);

        // 1) 无按键：S_IDLE 直接收 CHALLENGE → 应答 R1
        for (i = 0; i < 32; i = i + 1)
            fp_payload_buf[i] = 8'h50 + i;
        feed_frame(24'h0091, 8'd32);
        wait (mf_frame_done === 1'b1); @(negedge clk);
        if (mf_msg_id !== 24'h0092) begin
            errors = errors + 1; $display("[TE1 FAIL] idle R1 msgid=%h", mf_msg_id);
        end else if (mf_pay_len !== 6'd32) begin
            errors = errors + 1; $display("[TE1 FAIL] idle R1 len=%0d expect 32", mf_pay_len);
        end else
            $display("  [TE1] S_IDLE accepted CHALLENGE -> R1 (no button, 32B)");

        // 2) 背靠背第二轮：此刻 DUT 在 S_WAIT_RESULT，直接再喂 CHALLENGE
        for (i = 0; i < 32; i = i + 1)
            fp_payload_buf[i] = 8'h70 + i;
        feed_frame(24'h0091, 8'd32);
        wait (mf_frame_done === 1'b1); @(negedge clk);
        if (mf_msg_id !== 24'h0092) begin
            errors = errors + 1; $display("[TE1 FAIL] back-to-back R1 msgid=%h", mf_msg_id);
        end else if (mf_pay_len !== 6'd32) begin
            errors = errors + 1; $display("[TE1 FAIL] back-to-back R1 len=%0d expect 32", mf_pay_len);
        end else
            $display("  [TE1] S_WAIT_RESULT accepted next CHALLENGE -> R1 (32B)");

        // 3) 停止喂帧：S_WAIT_RESULT 超时 → BLOCKED（会话自清，非挂死）
        repeat (1200) @(negedge clk);
        if (auth_result !== 2'd3) begin
            errors = errors + 1; $display("[TE1 FAIL] result=%0d expect 3 (enroll-idle timeout)", auth_result);
        end else
            $display("[TE1 PASS] enroll flow + idle-timeout self-clear");

        // ============ TE2: 注册态重放锁（defect-reviewer P1 的 CI 回归） ============
        // 攻击链：合法认证 R1 后压制 RESULT -> 超时（旗标陈旧=1）-> 注册挑战 ->
        // R1 -> 重放录制的"合法"RESULT（黄金 R2，与陈旧期望匹配）。
        // 修复后：注册接受即清 calc_done_flag -> S_VERIFY_R2 守卫拦截 -> BLOCKED 且无 CONFIRM。
        $display("[..TE2] enroll replay-reject (P1 regression)");
        rst = 1'b1;
        repeat (2) @(negedge clk);
        rst = 1'b0;
        repeat (2) @(negedge clk);
        saw_confirm = 1'b0;
        @(negedge clk);
        auth_start <= 1'b1;
        @(negedge clk);
        auth_start <= 1'b0;
        wait (mf_frame_done === 1'b1); @(negedge clk);   // ACCESS（rst 后 C2 复位 -> 首 C2=a1..a8）
        for (i = 0; i < 32; i = i + 1)
            fp_payload_buf[i] = 8'h50 + i;
        feed_frame(24'h0091, 8'd32);                      // CHALLENGE（按键路径，calc_done=1）
        wait (mf_frame_done === 1'b1); @(negedge clk);   // R1

        repeat (1200) @(negedge clk);                     // 压制 RESULT -> 超时 BLOCKED -> IDLE
        if (auth_result !== 2'd3) begin
            errors = errors + 1; $display("[TE2 FAIL] expect timeout BLOCKED first, got %0d", auth_result);
        end

        for (i = 0; i < 32; i = i + 1)                    // 注册挑战（S_IDLE 接受并清旗标）
            fp_payload_buf[i] = 8'h60 + i;
        feed_frame(24'h0091, 8'd32);
        wait (mf_frame_done === 1'b1); @(negedge clk);   // 注册 R1
        if (mf_msg_id !== 24'h0092) begin
            errors = errors + 1; $display("[TE2 FAIL] enroll R1 msgid=%h", mf_msg_id);
        end

        fp_payload_buf[0] = 8'h00;                        // 重放黄金 RESULT（R2=7b45b0545e59aa94）
        fp_payload_buf[1] = 8'h05;
        fp_payload_buf[2]  = 8'h7b; fp_payload_buf[3]  = 8'h45;
        fp_payload_buf[4]  = 8'hb0; fp_payload_buf[5]  = 8'h54;
        fp_payload_buf[6]  = 8'h5e; fp_payload_buf[7]  = 8'h59;
        fp_payload_buf[8]  = 8'haa; fp_payload_buf[9]  = 8'h94;
        feed_frame(24'h0093, 8'd10);
        repeat (20) @(negedge clk);
        if (auth_result === 2'd1 || saw_confirm) begin
            errors = errors + 1; $display("[TE2 FAIL] replayed RESULT accepted! result=%0d confirm=%b", auth_result, saw_confirm);
        end else if (auth_result !== 2'd3) begin
            errors = errors + 1; $display("[TE2 FAIL] expect BLOCKED(3), got %0d", auth_result);
        end else
            $display("[TE2 PASS] replayed RESULT rejected by P2-1 guard (no CONFIRM)");
`else
        // ============ TEN: 参数=0 回归锁（ENROLL_NEG 编译） ============
        $display("[..TEN] enroll disabled: S_IDLE must ignore 0x0091");
        feed_frame(24'h0091, 8'd32);
        repeat (100) @(negedge clk);
        if (auth_busy !== 1'b0) begin
            errors = errors + 1; $display("[TEN FAIL] auth_busy=%b expect 0", auth_busy);
        end else
            $display("[TEN PASS] S_IDLE ignored CHALLENGE (param=0)");
`endif

        // ============ 总结 ============
        repeat (5) @(negedge clk);
        if (errors == 0) $display("TB_TERMINAL_FSM_PASS");
        else             $display("TB_TERMINAL_FSM_FAIL errors=%0d", errors);
        $finish;
    end

    // 看门狗
    initial begin
        #2_000_000;   // TE2 加入后总时长 ~0.6ms，看门狗放宽到 2ms
        $display("[WATCHDOG] TIMEOUT, state inspection needed");
        $display("TB_TERMINAL_FSM_FAIL errors=%0d (watchdog)", errors);
        $finish;
    end

endmodule