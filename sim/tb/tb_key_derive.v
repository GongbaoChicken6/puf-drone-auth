`timescale 1ns / 1ps
//============================================================================
// tb_key_derive.v -- W4-P4 T1: 密钥派生端到端验证（ENABLE_KEY_DERIVE=1）
//----------------------------------------------------------------------------
// T5: 首次 auth_start → S_KEY_MEASURE → S_KEY_DERIVE → key_valid=1 + key_reg 黄金
// T6: 二次 auth_start → key_valid 保持 1（不重复派生）→ 直接进 S_CALC_R2
// 黄金 K 从 puf_model.derive_device_key(fixture_freqs) 预计算，字节反转后
// 对应 RTL key_reg_r 的 96-bit 位序。
//============================================================================
module tb_key_derive;

    reg clk = 1'b0, rst = 1'b1, auth_start = 1'b0;
    reg [7:0] terminal_id = 8'h01;
    wire auth_busy;
    wire [1:0] auth_result;
    wire key_valid;
    wire [95:0] key_reg;

    // RX 模型（同 tb_puf_path）
    reg [23:0] fp_msg_id = 24'h0;
    reg [7:0] fp_pay_len = 8'd0;
    reg fp_frame_ok = 1'b0, fp_frame_err = 1'b0;
    wire fp_rx_inhibit;
    wire [4:0] fp_rd_addr;
    reg [7:0] fp_rd_data = 8'h00;
    reg [7:0] fp_payload_buf [0:31];

    // TX 模型（同 tb_puf_path）
    wire mf_start;
    wire [23:0] mf_msg_id;
    wire [5:0] mf_pay_len;
    wire [7:0] mf_pay_byte, mf_seq;
    wire mf_pay_valid;
    wire mf_sysid, unused_compid;
    reg mf_busy = 1'b0, mf_pay_phase = 1'b0, mf_frame_done = 1'b0, mf_frame_err = 1'b0;

    integer errors = 0, guard = 0, tx_byte_count = 0;
    reg [7:0] tx_captured [0:63];

    // 黄金 K（fixture 频率 → puf_model → 字节反转到 RTL 位序）
    localparam [95:0] GOLDEN_KEY = 96'h26c4ec61ba319ff325041dee;

    // PUF 子系统
    wire cd_start, cd_done;
    wire [63:0] cd_seed;
    wire [511:0] cd_pair_table;
    wire ra_measure_en, ra_ring_en, ra_busy, ra_done;
    wire [255:0] ra_ring_freq;

    challenge_decode # (.N_ROUNDS(8), .N_RINGS(16), .IDX_W(4)) u_cd (
        .clk(clk), .rst(rst), .start(cd_start), .seed(cd_seed),
        .pair_table(cd_pair_table), .done(cd_done));

    ro_array_sim # (.N_RINGS(16), .CNT_W(16)) u_ro_array (
        .clk(clk), .rst(rst), .measure_en(ra_measure_en), .ring_en(ra_ring_en),
        .busy(ra_busy), .done(ra_done), .ring_freq(ra_ring_freq));

    // DUT: ENABLE_KEY_DERIVE=1
    terminal_fsm # (
        .TIMEOUT_CYCLES(32'd5000),
        .MEASURE_CYCLES(32'd64),
        .PUF_WD_CYCLES(32'd12000),
        .ENABLE_KEY_DERIVE(1)          // <<< 密钥派生启用
    ) dut (
        .clk(clk), .rst(rst),
        .auth_start(auth_start), .terminal_id(terminal_id),
        .auth_busy(auth_busy), .auth_result(auth_result),
        .c2_boot_seed(64'hA7A6_A5A4_A3A2_A1A0),
        .device_key_in(key_reg),       // 回环（同 w3_top）
        .use_ext_key(key_valid),       // 回环
        .seed_load(1'b0),
        .key_valid(key_valid),
        .key_reg(key_reg),
        .cd_start(cd_start), .cd_seed(cd_seed),
        .cd_pair_table(cd_pair_table), .cd_done(cd_done),
        .ra_measure_en(ra_measure_en), .ra_ring_en(ra_ring_en),
        .ra_busy(ra_busy), .ra_done(ra_done), .ra_ring_freq(ra_ring_freq),
        .fp_msg_id(fp_msg_id), .fp_pay_len(fp_pay_len),
        .fp_frame_ok(fp_frame_ok), .fp_frame_err(fp_frame_err),
        .fp_rd_addr(fp_rd_addr), .fp_rd_data(fp_rd_data),
        .fp_rx_inhibit(fp_rx_inhibit),
        .mf_start(mf_start), .mf_msg_id(mf_msg_id),
        .mf_pay_len(mf_pay_len), .mf_pay_byte(mf_pay_byte),
        .mf_pay_valid(mf_pay_valid), .mf_seq(mf_seq),
        .mf_sysid(mf_sysid), .mf_compid(unused_compid),
        .mf_busy(mf_busy), .mf_pay_phase(mf_pay_phase),
        .mf_frame_done(mf_frame_done), .mf_frame_err(mf_frame_err));

    always #5 clk = ~clk;

    // mavlink 模型（同 tb_puf_path）
    always @(posedge clk) begin
        mf_frame_done <= 1'b0;
        if (mf_start) begin
            mf_busy <= 1'b1; mf_pay_phase <= 1'b0; tx_byte_count <= 0;
        end else if (mf_busy) begin
            if (!mf_pay_phase && tx_byte_count == 0) mf_pay_phase <= 1'b1;
            else if (mf_pay_phase && mf_pay_valid) begin
                tx_captured[tx_byte_count] <= mf_pay_byte;
                tx_byte_count <= tx_byte_count + 1;
                if (tx_byte_count + 1 >= mf_pay_len) begin
                    mf_pay_phase <= 1'b0; mf_busy <= 1'b0; mf_frame_done <= 1'b1;
                end
            end
        end
    end

    always @* fp_rd_data = fp_payload_buf[fp_rd_addr];

    task feed_frame(input [23:0] msgid, input [7:0] paylen);
        begin
            @(negedge clk); fp_msg_id <= msgid; fp_pay_len <= paylen; fp_frame_ok <= 1'b1;
            @(negedge clk); fp_frame_ok <= 1'b0;
            @(negedge clk);
        end
    endtask

    initial begin
        repeat (5) @(negedge clk); rst = 1'b0;
        repeat (2) @(negedge clk);

        //==================== T5: 首次 auth → 密钥派生 ====================
        @(negedge clk); auth_start = 1'b1;
        @(negedge clk); auth_start = 1'b0;

        // 等 key_valid（S_KEY_MEASURE ~3k 拍 + S_KEY_DERIVE ~200 拍）
        guard = 0;
        while (!key_valid && guard < 20000) begin @(posedge clk); guard = guard + 1; end

        if (key_valid && guard > 100) begin
            // 验证 key_reg 黄金值
            $display("[DEBUG] key_reg=%h k_boot=%h", key_reg, dut.k_boot_reg);
            $display("[DEBUG] kdf_key12=%h", dut.kdf_key12);
            $display("[DEBUG] kdf_ct1=%h ct2_last=%h", dut.kdf_ct1, dut.sp_ciphertext);
            $display("[DEBUG] expected_key12=0df58d745de035700df58d74");
            if (key_reg === GOLDEN_KEY)
                $display("[T5 PASS] key_valid=1 (%0d 拍) + key_reg=黄金值", guard);
            else begin
                errors = errors + 1;
                $display("[T5 FAIL] key_reg=%h != 黄金 %h", key_reg, GOLDEN_KEY);
            end
        end else begin
            errors = errors + 1;
            $display("[T5 FAIL] key_valid=%b guard=%0d", key_valid, guard);
        end

        // 等 ACCESS 帧发完（密钥派生后正常进 S_CALC_R2→S_TX_ACCESS）
        guard = 0;
        while (tx_byte_count < 16 && guard < 5000) begin @(posedge clk); guard = guard + 1; end

        //==================== T6: 二次 auth 不重复派生 ====================
        // 等 FSM 回 IDLE（发 REJECT 帧退出）
        fp_payload_buf[0] = 8'h01;  // REJECT
        feed_frame(24'h0093, 8'd10);
        guard = 0;
        while (auth_busy && guard < 5000) begin @(posedge clk); guard = guard + 1; end

        // 二次 auth_start：key_valid 应保持 1，直接进 S_CALC_R2
        tx_byte_count = 0;
        @(negedge clk); auth_start = 1'b1;
        @(negedge clk); auth_start = 1'b0;
        guard = 0;
        while (tx_byte_count < 16 && guard < 5000) begin @(posedge clk); guard = guard + 1; end
        if (key_valid && guard < 500)   // 应远快于派生路径（<500 vs >3000）
            $display("[T6 PASS] 二次 auth 快速通过(%0d 拍, 无重复派生), key_valid=1", guard);
        else begin
            errors = errors + 1;
            $display("[T6 FAIL] key_valid=%b guard=%0d", key_valid, guard);
        end

        //==================== 汇总 ====================
        if (errors == 0)
            $display("TB_KEY_DERIVE_PASS: 密钥派生端到端(黄金值+不重复) 全部通过");
        else
            $display("TB_KEY_DERIVE_FAIL: %0d 项错误", errors);
        $finish;
    end

    initial begin
        #5_000_000;
        $display("TB_KEY_DERIVE_FAIL (global watchdog)");
        $finish;
    end
endmodule
