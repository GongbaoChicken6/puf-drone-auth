`timescale 1ns / 1ps
//============================================================================
// tb_puf_path.v -- W4-P2 T4：PUF 全链语义锁（R1 字节级 vs puf_model 黄金）
//----------------------------------------------------------------------------
// 验证内容（W4 计划书 P2-T4 判据）：
//   T1 首轮 R1：4 种子（黄金 A/B/C/D）经 decode→热稳定 7 窗→测量→打包，
//      TX 的 RESPONSE_R1 32 字节与 puf_model 在 fixture 频率下的 ideal()
//      逐字节一致（RTL↔Python 第二道锁，第一道在 tb_challenge_decode）
//   T2 灰区 R1：EXTRA_CHALLENGE 3 种子（A/B/C）24 字节一致
//   T3 解码看门狗：force cd_done=0 → PUF_WD_CYCLES 内 BLOCKED(result=3)
//   T4 测量看门狗：force ra_done=0 → 同上
// 全部通过打印 TB_PUF_PATH_PASS（CI 门禁约定 TB_<模块名>_PASS）。
// 黄金 R1 由 scripts/gen_puf_fixtures.py --tb-resp 生成（puf_model 同源）。
//============================================================================
module tb_puf_path;

    reg         clk = 1'b0;
    reg         rst = 1'b1;
    reg         auth_start = 1'b0;
    reg  [7:0]  terminal_id = 8'h2A;
    wire        auth_busy;
    wire [1:0]  auth_result;

    // RX (frame_parser 模型)
    reg  [23:0] fp_msg_id = 24'h0;
    reg  [7:0]  fp_pay_len = 8'd0;
    reg         fp_frame_ok = 1'b0;
    wire        fp_rx_inhibit;
    wire [4:0]  fp_rd_addr;
    reg  [7:0]  fp_rd_data = 8'h00;
    reg  [7:0]  fp_payload_buf [0:31];

    // TX (mavlink_frame 模型)
    wire        mf_start;
    wire [23:0] mf_msg_id;
    wire [5:0]  mf_pay_len;
    wire [7:0]  mf_pay_byte;
    wire        mf_pay_valid;
    wire [7:0]  mf_seq;
    wire        mf_sysid, unused_compid;
    reg         mf_busy = 1'b0;
    reg         mf_pay_phase = 1'b0;
    reg         mf_frame_done = 1'b0;
    reg         mf_frame_err = 1'b0;

    integer     errors = 0;
    integer     i;
    integer     tx_byte_count = 0;
    reg [7:0]   tx_captured [0:63];
    integer     guard;
    integer     win_count = 0;     // D-P2/B-P2：ra_measure_en 上升沿计数（热窗可观测性）
    reg         ra_measure_en_prev = 1'b0;

    // 黄金 R1（scripts/gen_puf_fixtures.py --tb-resp，puf_model × fixture 频率）
    localparam [63:0] R1_SEED_A = 64'h6677FEA45A09061F;
    localparam [63:0] R1_SEED_B = 64'hD5B6F7144A4181DF;
    localparam [63:0] R1_SEED_C = 64'h872E6A55E752CF34;
    localparam [63:0] R1_SEED_D = 64'hAED5F9A3967ED9C2;

    // PUF 子系统
    wire        cd_start, cd_done;
    wire [63:0] cd_seed;
    wire [511:0] cd_pair_table;
    wire        ra_measure_en, ra_ring_en, ra_busy, ra_done;
    wire [255:0] ra_ring_freq;

    // 热窗计数（D-P2：ra_measure_en 上升沿 = 开一窗）
    always @(posedge clk) begin
        if (ra_measure_en && !ra_measure_en_prev) win_count = win_count + 1;
        ra_measure_en_prev <= ra_measure_en;
    end

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

    terminal_fsm # (
        .TIMEOUT_CYCLES (32'd1000),
        .MEASURE_CYCLES (32'd64),
        .PUF_WD_CYCLES  (32'd12000)     // 预算：解码 4x2058 + 测量 8x64 + 裕量（T3/T4 触发值）
    ) dut (
        .clk           (clk          ),
        .rst           (rst          ),
        .auth_start    (auth_start   ),
        .terminal_id   (terminal_id  ),
        .auth_busy     (auth_busy    ),
        .auth_result   (auth_result  ),
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
        .fp_frame_err  (1'b0         ),
        .fp_rd_addr    (fp_rd_addr   ),
        .fp_rd_data    (fp_rd_data   ),
        .fp_rx_inhibit (fp_rx_inhibit),
        .mf_start      (mf_start     ),
        .mf_msg_id     (mf_msg_id    ),
        .mf_pay_len    (mf_pay_len   ),
        .mf_pay_byte   (mf_pay_byte  ),
        .mf_pay_valid  (mf_pay_valid ),
        .mf_seq        (mf_seq       ),
        .mf_sysid      (mf_sysid     ),
        .mf_compid     (unused_compid),
        .mf_busy       (mf_busy      ),
        .mf_pay_phase  (mf_pay_phase ),
        .mf_frame_done (mf_frame_done),
        .mf_frame_err  (mf_frame_err )
    );

    always #5 clk = ~clk;

    // mavlink_frame 模型（同 tb_terminal_fsm）
    always @(posedge clk) begin
        mf_frame_done <= 1'b0;
        if (mf_start) begin
            mf_busy       <= 1'b1;
            mf_pay_phase  <= 1'b0;
            tx_byte_count <= 0;
        end else if (mf_busy) begin
            if (!mf_pay_phase && tx_byte_count == 0) begin
                mf_pay_phase <= 1'b1;
            end else if (mf_pay_phase) begin
                if (mf_pay_valid) begin
                    tx_captured[tx_byte_count] <= mf_pay_byte;
                    tx_byte_count <= tx_byte_count + 1;
                    if (tx_byte_count + 1 >= mf_pay_len) begin
                    mf_pay_phase  <= 1'b0;
                    mf_busy       <= 1'b0;
                    mf_frame_done <= 1'b1;
                end
                end
            end
        end
    end

    // fp 载荷组合读出 + 发帧任务（同 tb_terminal_fsm）
    always @* fp_rd_data = fp_payload_buf[fp_rd_addr];

    task feed_frame(input [23:0] msgid, input [7:0] paylen);
        begin
            @(negedge clk);
            fp_msg_id   <= msgid;
            fp_pay_len  <= paylen;
            fp_frame_ok <= 1'b1;
            @(negedge clk);
            fp_frame_ok <= 1'b0;
            @(negedge clk);
        end
    endtask

    task seed_bytes(input [63:0] s, input integer base);
        begin
            fp_payload_buf[base+0] = s[63:56];
            fp_payload_buf[base+1] = s[55:48];
            fp_payload_buf[base+2] = s[47:40];
            fp_payload_buf[base+3] = s[39:32];
            fp_payload_buf[base+4] = s[31:24];
            fp_payload_buf[base+5] = s[23:16];
            fp_payload_buf[base+6] = s[15:8];
            fp_payload_buf[base+7] = s[7:0];
        end
    endtask

    // 等 R1 帧发完（tx_byte_count 达 paylen）
    task wait_r1_frame(input integer nbytes);
        begin
            guard = 0;
            while (tx_byte_count < nbytes && guard < 300000) begin
                @(posedge clk);
                guard = guard + 1;
            end
            if (guard >= 300000) begin
                errors = errors + 1;
                $display("[T] ERROR: R1 帧发送超时（%0d 字节）", nbytes);
            end
            repeat (2) @(negedge clk);
        end
    endtask

    initial begin
        repeat (5) @(negedge clk);
        rst = 1'b0;
        repeat (2) @(negedge clk);

        //==================== T1：首轮 R1（4 种子 A/B/C/D）====================
        seed_bytes(64'hC0FF_EEBE_EF12_3456, 0);   // A
        seed_bytes(64'h0F1E_2D3C_4B5A_6978, 8);   // B
        seed_bytes(64'hFEED_FACE_CAFE_BABE, 16);  // C
        seed_bytes(64'h1234_5678_9ABC_DEF0, 24);  // D

        @(negedge clk); auth_start = 1'b1;
        @(negedge clk); auth_start = 1'b0;
        // 等 ACCESS 发完（16B）→ R2 计算早已完成
        guard = 0;
        while (tx_byte_count < 16 && guard < 10000) begin @(posedge clk); guard = guard + 1; end
        repeat (2) @(negedge clk);
        tx_byte_count = 0;

        feed_frame(24'h0091, 8'd32);              // CHALLENGE
        wait_r1_frame(32);

        if ({tx_captured[0],tx_captured[1],tx_captured[2],tx_captured[3],
             tx_captured[4],tx_captured[5],tx_captured[6],tx_captured[7]} !== R1_SEED_A) begin
            errors = errors + 1;
            $display("[T1] R1_A mismatch: got %h_%h_%h_%h_%h_%h_%h_%h want %h",
                     tx_captured[0],tx_captured[1],tx_captured[2],tx_captured[3],
                     tx_captured[4],tx_captured[5],tx_captured[6],tx_captured[7], R1_SEED_A);
        end
        if ({tx_captured[8],tx_captured[9],tx_captured[10],tx_captured[11],
             tx_captured[12],tx_captured[13],tx_captured[14],tx_captured[15]} !== R1_SEED_B) begin
            errors = errors + 1; $display("[T1] R1_B mismatch: want %h", R1_SEED_B);
        end
        if ({tx_captured[16],tx_captured[17],tx_captured[18],tx_captured[19],
             tx_captured[20],tx_captured[21],tx_captured[22],tx_captured[23]} !== R1_SEED_C) begin
            errors = errors + 1; $display("[T1] R1_C mismatch: want %h", R1_SEED_C);
        end
        if ({tx_captured[24],tx_captured[25],tx_captured[26],tx_captured[27],
             tx_captured[28],tx_captured[29],tx_captured[30],tx_captured[31]} !== R1_SEED_D) begin
            errors = errors + 1; $display("[T1] R1_D mismatch: want %h", R1_SEED_D);
        end
        if (win_count !== 8) begin
            errors = errors + 1;
            $display("[T1] 测量窗计数 %0d != 8（WARMUP_WINS=7+末窗）", win_count);
        end
        if (errors == 0) $display("[T1 PASS] 首轮 R1 32 字节 = puf_model 黄金 + %0d 测量窗（热稳定 7+末窗 1）", win_count);

        //==================== T2：灰区 R1（3 种子 A/B/C）====================
        tx_byte_count = 0;
        feed_frame(24'h0095, 8'd24);              // EXTRA_CHALLENGE（载荷已就位）
        wait_r1_frame(24);
        if ({tx_captured[0],tx_captured[1],tx_captured[2],tx_captured[3],
             tx_captured[4],tx_captured[5],tx_captured[6],tx_captured[7]} !== R1_SEED_A) begin
            errors = errors + 1; $display("[T2] gray R1_A mismatch: want %h", R1_SEED_A);
        end
        if ({tx_captured[8],tx_captured[9],tx_captured[10],tx_captured[11],
             tx_captured[12],tx_captured[13],tx_captured[14],tx_captured[15]} !== R1_SEED_B) begin
            errors = errors + 1; $display("[T2] gray R1_B mismatch: want %h", R1_SEED_B);
        end
        if ({tx_captured[16],tx_captured[17],tx_captured[18],tx_captured[19],
             tx_captured[20],tx_captured[21],tx_captured[22],tx_captured[23]} !== R1_SEED_C) begin
            errors = errors + 1; $display("[T2] gray R1_C mismatch: want %h", R1_SEED_C);
        end
        if (errors == 0) $display("[T2 PASS] 灰区 R1 24 字节 = puf_model 黄金");

        // 收尾：发 REJECT 让 FSM 回 IDLE
        fp_payload_buf[0] = 8'h01;
        feed_frame(24'h0093, 8'd10);
        guard = 0;
        while (auth_busy && guard < 10000) begin @(posedge clk); guard = guard + 1; end

        //==================== T3：解码看门狗（force cd_done=0）====================
        @(negedge clk); auth_start = 1'b1;
        @(negedge clk); auth_start = 1'b0;
        guard = 0;
        while (tx_byte_count < 16 && guard < 10000) begin @(posedge clk); guard = guard + 1; end
        repeat (2) @(negedge clk);
        tx_byte_count = 0;
        force cd_done = 1'b0;
        feed_frame(24'h0091, 8'd32);
        guard = 0;
        while (auth_result !== 2'd3 && guard < 10000) begin @(posedge clk); guard = guard + 1; end
        release cd_done;
        if (auth_result === 2'd3) $display("[T3 PASS] 解码看门狗：cd_done 卡死 → BLOCKED（%0d 拍内）", guard);
        else begin errors = errors + 1; $display("[T3 FAIL] 解码看门狗未触发 result=%0d", auth_result); end
        while (auth_busy) @(posedge clk);   // 等 BLOCKED→IDLE

        //==================== T4：测量看门狗（force ra_done=0）====================
        @(negedge clk); auth_start = 1'b1;
        @(negedge clk); auth_start = 1'b0;
        guard = 0;
        while (tx_byte_count < 16 && guard < 10000) begin @(posedge clk); guard = guard + 1; end
        repeat (2) @(negedge clk);
        tx_byte_count = 0;
        force ra_done = 1'b0;
        feed_frame(24'h0091, 8'd32);
        guard = 0;
        while (auth_result !== 2'd3 && guard < 10000) begin @(posedge clk); guard = guard + 1; end
        release ra_done;
        if (auth_result === 2'd3) $display("[T4 PASS] 测量看门狗：ra_done 卡死 → BLOCKED（%0d 拍内）", guard);
        else begin errors = errors + 1; $display("[T4 FAIL] 测量看门狗未触发 result=%0d", auth_result); end

        //==================== 汇总 ====================
        if (errors == 0)
            $display("TB_PUF_PATH_PASS: R1 字节级语义锁(首轮+灰区) + 解码/测量看门狗 全部通过");
        else
            $display("TB_PUF_PATH_FAIL: %0d 项错误", errors);
        $finish;
    end

    initial begin
        #2_000_000;   // 全局看门狗（T1/T2 ~90us each + T3/T4 ~各 2*PUF_WD）
        $display("TB_PUF_PATH_FAIL (global watchdog)");
        $finish;
    end

endmodule