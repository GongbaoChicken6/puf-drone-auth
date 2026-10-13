`timescale 1ns / 1ps
//============================================================================
// tb_terminal_fsm.v — 协议状态机端到端测试
//----------------------------------------------------------------------------
// TB 扮演基站（frame_parser + mavlink_frame 的对端），驱动完整认证流：
// T1: 正常通过流程（ACCESS→CHALLENGE→R1→RESULT(pass+R2)→CONFIRM→SESSION）
// T2: 拒绝流程（RESULT 含 reject 码 → BLOCKED）
// T3: 超时流程（等挑战超时 → BLOCKED）
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
    integer i;
    integer tx_byte_count = 0;
    reg [7:0] tx_captured [0:63];

    //------------------------------------------------------------------------
    // W4 B5a PUF 子系统（challenge_decode + 行为级 ro_array_sim）
    //------------------------------------------------------------------------

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
    terminal_fsm # (.TIMEOUT_CYCLES(1000), .MEASURE_CYCLES(32'd64)) dut (
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
            $display("  [T1] RESPONSE_R1 sent (32B, stub=seeds passthrough)");

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

        // ============ 总结 ============
        repeat (5) @(negedge clk);
        if (errors == 0) $display("TB_TERMINAL_FSM_PASS");
        else             $display("TB_TERMINAL_FSM_FAIL errors=%0d", errors);
        $finish;
    end

    // 看门狗
    initial begin
        #500_000;
        $display("[WATCHDOG] TIMEOUT, state inspection needed");
        $display("TB_TERMINAL_FSM_FAIL errors=%0d (watchdog)", errors);
        $finish;
    end

endmodule