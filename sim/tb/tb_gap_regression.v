`timescale 1ns / 1ps
//============================================================================
// tb_gap_regression.v -- Gap-filling regression (NOT part of repo; scratch)
// Covers untested Speck-integration scenarios:
//   GA : Scenario A + H  pass flow, C2 on wire, inhibit in CALC_R2/TX/WAIT
//   GD1: Scenario D      2nd auth from SESSION with STALE R2 -> BLOCKED(3)
//   GD2: Scenario D      3rd auth from IDLE with FRESH R2 -> PASS
//   GE1: Scenario E      gray zone EXTRA -> R1(24B) -> same-round R2 -> PASS
//   GE2: Scenario E-neg  gray zone RESULT with re-incremented-C2 R2 -> BLOCKED
//   GF : Scenario F      forged (1-byte-flipped) R2 -> BLOCKED(3)
//   GH : Scenario H      inhibit HIGH in VERIFY_R2 / PROC_EXTRA, LOW in WAIT_*
//============================================================================
module tb_gap_regression;

    reg         clk = 1'b0;
    reg         rst = 1'b1;
    reg         auth_start = 1'b0;
    reg  [7:0]  terminal_id = 8'd42;
    wire        auth_busy;
    wire [1:0]  auth_result;
    wire        fp_rx_inhibit;

    reg  [23:0] fp_msg_id = 24'h0;
    reg  [7:0]  fp_pay_len = 8'd0;
    reg         fp_frame_ok = 1'b0;
    reg         fp_frame_err = 1'b0;
    wire [4:0]  fp_rd_addr;
    reg  [7:0]  fp_payload_buf [0:31];
    wire [7:0]  fp_rd_data = fp_payload_buf[fp_rd_addr];

    wire        mf_start;
    wire [23:0] mf_msg_id;
    wire [5:0]  mf_pay_len;
    wire [7:0]  mf_pay_byte;
    wire        mf_pay_valid;
    wire [7:0]  mf_seq;
    wire        mf_sysid, /*unused*/ mf_compid_x;
    wire [7:0]  mf_sysid_w, mf_compid_w;
    reg         mf_busy = 1'b0;
    reg         mf_pay_phase = 1'b0;
    reg         mf_frame_done = 1'b0;
    reg         mf_frame_err = 1'b0;

    integer errors = 0;
    integer i;
    integer tx_byte_count = 0;
    integer guard = 0;   // W4-P4 GI: 循环保护
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

    terminal_fsm # (.TIMEOUT_CYCLES(1000), .MEASURE_CYCLES(32'd64)) dut (
        .clk(clk), .rst(rst), .auth_start(auth_start), .terminal_id(terminal_id),
        .auth_busy(auth_busy), .auth_result(auth_result),
        // W4-T2 可注入端口 tie-off（黄金零改动）
        .c2_boot_seed(64'hA7A6_A5A4_A3A2_A1A0),
        .device_key_in(96'h1312_1110_0B0A_0908_0302_0100),
        .use_ext_key(1'b0),
        .seed_load     (1'b0),   // W4-P4 T2: TB 恒 0（板上接 ro_entropy）
        .cd_start(cd_start), .cd_seed(cd_seed), .cd_pair_table(cd_pair_table),
        .cd_done(cd_done), .ra_measure_en(ra_measure_en), .ra_ring_en(ra_ring_en),
        .ra_busy(ra_busy), .ra_done(ra_done), .ra_ring_freq(ra_ring_freq),
        .fp_msg_id(fp_msg_id), .fp_pay_len(fp_pay_len),
        .fp_frame_ok(fp_frame_ok), .fp_frame_err(fp_frame_err),
        .fp_rd_addr(fp_rd_addr), .fp_rd_data(fp_rd_data),
        .fp_rx_inhibit(fp_rx_inhibit),
        .mf_start(mf_start), .mf_msg_id(mf_msg_id), .mf_pay_len(mf_pay_len),
        .mf_pay_byte(mf_pay_byte), .mf_pay_valid(mf_pay_valid), .mf_seq(mf_seq),
        .mf_sysid(mf_sysid_w), .mf_compid(mf_compid_w),
        .mf_busy(mf_busy), .mf_pay_phase(mf_pay_phase),
        .mf_frame_done(mf_frame_done), .mf_frame_err(mf_frame_err)
    );

    always #5 clk = ~clk;

    // mavlink_frame model (same as tb_terminal_fsm)
    always @(posedge clk) begin
        mf_frame_done <= 1'b0;
        if (mf_start) begin
            mf_busy <= 1'b1; mf_pay_phase <= 1'b0; tx_byte_count <= 0;
        end else if (mf_busy) begin
            if (!mf_pay_phase && tx_byte_count == 0) mf_pay_phase <= 1'b1;
            else if (mf_pay_phase) begin
                if (mf_pay_valid) begin
                    tx_captured[tx_byte_count] <= mf_pay_byte;
                    tx_byte_count <= tx_byte_count + 1;
                    if (tx_byte_count + 1 >= mf_pay_len) begin
                        mf_pay_phase <= 1'b0; mf_busy <= 1'b0; mf_frame_done <= 1'b1;
                    end
                end
            end
        end
    end

    task feed_frame(input [23:0] msgid, input [7:0] paylen);
        begin
            @(negedge clk);
            fp_msg_id <= msgid; fp_pay_len <= paylen; fp_frame_ok <= 1'b1;
            @(negedge clk);
            fp_frame_ok <= 1'b0;
            @(negedge clk);
        end
    endtask

    task load_result(input [7:0] result_code, input [7:0] r2b0, input [7:0] r2b1,
                     input [7:0] r2b2, input [7:0] r2b3, input [7:0] r2b4,
                     input [7:0] r2b5, input [7:0] r2b6, input [7:0] r2b7);
        begin
            for (i = 0; i < 32; i = i + 1) fp_payload_buf[i] = 8'h00;
            fp_payload_buf[0] = result_code;
            fp_payload_buf[1] = 8'h05;
            fp_payload_buf[2] = r2b0; fp_payload_buf[3] = r2b1;
            fp_payload_buf[4] = r2b2; fp_payload_buf[5] = r2b3;
            fp_payload_buf[6] = r2b4; fp_payload_buf[7] = r2b5;
            fp_payload_buf[8] = r2b6; fp_payload_buf[9] = r2b7;
        end
    endtask

    task load_challenge;
        begin
            for (i = 0; i < 32; i = i + 1) fp_payload_buf[i] = 8'h50 + i[7:0];
        end
    endtask

    task pulse_auth;
        begin
            @(negedge clk); auth_start <= 1'b1;
            @(negedge clk); auth_start <= 1'b0;
        end
    endtask

    task check_c2(input [7:0] e0, input [7:0] e1, input [7:0] e2, input [7:0] e3,
                  input [7:0] e4, input [7:0] e5, input [7:0] e6, input [7:0] e7,
                  input [127:0] tag);
        begin
            if (tx_captured[8]!==e0 || tx_captured[9]!==e1 || tx_captured[10]!==e2 ||
                tx_captured[11]!==e3 || tx_captured[12]!==e4 || tx_captured[13]!==e5 ||
                tx_captured[14]!==e6 || tx_captured[15]!==e7) begin
                errors = errors + 1;
                $display("[%0h] FAIL C2 wire=%2h %2h %2h %2h %2h %2h %2h %2h exp=%2h %2h %2h %2h %2h %2h %2h %2h",
                    tag, tx_captured[8],tx_captured[9],tx_captured[10],tx_captured[11],
                    tx_captured[12],tx_captured[13],tx_captured[14],tx_captured[15],
                    e0,e1,e2,e3,e4,e5,e6,e7);
            end else
                $display("[%0h] C2 wire bytes OK = %2h %2h %2h %2h %2h %2h %2h %2h",
                    tag, e0,e1,e2,e3,e4,e5,e6,e7);
        end
    endtask

    // cycle profiler for S_CALC_R2
    integer calc_cycles = 0;
    integer calc_reported = 0;
    always @(posedge clk) begin
        if (rst) begin calc_cycles = 0; calc_reported = 0; end
        else if (dut.state == 4'd12) calc_cycles = calc_cycles + 1;
        else if (dut.state == 4'd1 && calc_cycles != 0 && !calc_reported) begin
            $display("[INFO] S_CALC_R2 duration = %0d cycles", calc_cycles);
            calc_reported = 1;
        end
    end

    initial begin
        repeat (3) @(negedge clk);
        rst = 1'b0;
        repeat (2) @(negedge clk);

        //================ GA: pass flow + Scenario H sampling ================
        $display("[GA] pass flow + inhibit sampling");
        pulse_auth;
        // inhibit HIGH during S_CALC_R2 (~54 cycles)
        repeat (5) @(negedge clk);
        if (fp_rx_inhibit !== 1'b1) begin errors = errors + 1; $display("[GA FAIL] inhibit not HIGH in S_CALC_R2 (+5cyc)"); end
        repeat (20) @(negedge clk);
        if (fp_rx_inhibit !== 1'b1) begin errors = errors + 1; $display("[GA FAIL] inhibit not HIGH in S_CALC_R2 (+25cyc)"); end
        if (auth_busy !== 1'b1) begin errors = errors + 1; $display("[GA FAIL] busy low during CALC"); end
        wait (mf_frame_done === 1'b1); @(negedge clk);   // ACCESS done -> now in TX_WAIT_CHALL handoff
        check_c2(8'ha1,8'ha2,8'ha3,8'ha4,8'ha5,8'ha6,8'ha7,8'ha8, "GA");
        // inhibit LOW while waiting for CHALLENGE
        repeat (3) @(negedge clk);
        if (fp_rx_inhibit !== 1'b0) begin errors = errors + 1; $display("[GA FAIL] inhibit HIGH in WAIT_CHALL"); end
        load_challenge; feed_frame(24'h0091, 8'd32);
        repeat (2) @(negedge clk);
        if (fp_rx_inhibit !== 1'b1) begin errors = errors + 1; $display("[GA FAIL] inhibit not HIGH in PROC_SEEDS"); end
        wait (mf_frame_done === 1'b1); @(negedge clk);   // R1 sent -> WAIT_RESULT
        repeat (2) @(negedge clk);
        if (fp_rx_inhibit !== 1'b0) begin errors = errors + 1; $display("[GA FAIL] inhibit HIGH in WAIT_RESULT"); end
        load_result(8'h00, 8'h7b,8'h45,8'hb0,8'h54,8'h5e,8'h59,8'haa,8'h94); // R2_1
        feed_frame(24'h0093, 8'd10);
        // inhibit HIGH during VERIFY_R2
        if (fp_rx_inhibit !== 1'b1) begin errors = errors + 1; $display("[GA FAIL] inhibit not HIGH in VERIFY_R2"); end
        wait (mf_frame_done === 1'b1); @(negedge clk);   // CONFIRM
        repeat (10) @(negedge clk);
        if (auth_result !== 2'd1) begin errors = errors + 1; $display("[GA FAIL] result=%0d exp 1", auth_result); end
        else if (auth_busy !== 1'b0) begin errors = errors + 1; $display("[GA FAIL] busy=1 in SESSION"); end
        else $display("[GA PASS] auth1 PASS result=1 busy=0, R2_1=7b45b0545e59aa94 accepted");

        //================ GD1: 2nd auth from SESSION, STALE R2 -> BLOCKED ====
        $display("[GD1] 2nd auth (from SESSION) with STALE R2_1 (replay)");
        pulse_auth;                                        // consumed by S_SESSION
        wait (mf_frame_done === 1'b1); @(negedge clk);     // ACCESS (C2=a2..a9)
        check_c2(8'ha2,8'ha3,8'ha4,8'ha5,8'ha6,8'ha7,8'ha8,8'ha9, "GD1");
        load_challenge; feed_frame(24'h0091, 8'd32);
        wait (mf_frame_done === 1'b1); @(negedge clk);     // R1
        load_result(8'h00, 8'h7b,8'h45,8'hb0,8'h54,8'h5e,8'h59,8'haa,8'h94); // STALE R2_1
        feed_frame(24'h0093, 8'd10);
        repeat (10) @(negedge clk);
        if (auth_result !== 2'd3) begin errors = errors + 1; $display("[GD1 FAIL] result=%0d exp 3 (stale R2 must block)", auth_result); end
        else $display("[GD1 PASS] stale R2_1 rejected -> BLOCKED(3) : r2_expected refreshed");

        //================ GD2: 3rd auth from IDLE, FRESH R2_3 -> PASS ========
        $display("[GD2] 3rd auth (from IDLE) with FRESH R2_3");
        pulse_auth;
        wait (mf_frame_done === 1'b1); @(negedge clk);     // ACCESS (C2=a3..aa)
        check_c2(8'ha3,8'ha4,8'ha5,8'ha6,8'ha7,8'ha8,8'ha9,8'haa, "GD2");
        load_challenge; feed_frame(24'h0091, 8'd32);
        wait (mf_frame_done === 1'b1); @(negedge clk);     // R1
        load_result(8'h00, 8'h5d,8'hb1,8'h9d,8'hec,8'hae,8'h2d,8'h2f,8'h8a); // R2_3
        feed_frame(24'h0093, 8'd10);
        wait (mf_frame_done === 1'b1); @(negedge clk);     // CONFIRM
        repeat (10) @(negedge clk);
        if (auth_result !== 2'd1) begin errors = errors + 1; $display("[GD2 FAIL] result=%0d exp 1", auth_result); end
        else $display("[GD2 PASS] fresh R2_3 accepted -> PASS : counter+Speck correct on 3rd round");

        //================ GE1: gray zone, same-round R2 -> PASS ==============
        $display("[GE1] 4th auth gray zone (EXTRA) + same-round R2_4");
        pulse_auth;
        wait (mf_frame_done === 1'b1); @(negedge clk);     // ACCESS (C2=a4..ab)
        check_c2(8'ha4,8'ha5,8'ha6,8'ha7,8'ha8,8'ha9,8'haa,8'hab, "GE1");
        load_challenge; feed_frame(24'h0091, 8'd32);
        wait (mf_frame_done === 1'b1); @(negedge clk);     // R1 (32B)
        // EXTRA_CHALLENGE: 24 seed bytes
        for (i = 0; i < 24; i = i + 1) fp_payload_buf[i] = 8'h70 + i[7:0];
        feed_frame(24'h0095, 8'd24);
        repeat (2) @(negedge clk);
        if (fp_rx_inhibit !== 1'b1) begin errors = errors + 1; $display("[GE1 FAIL] inhibit not HIGH in PROC_EXTRA"); end
        wait (mf_frame_done === 1'b1); @(negedge clk);     // R1_EXTRA
        if (mf_pay_len !== 6'd24) begin errors = errors + 1; $display("[GE1 FAIL] R1_EXTRA len=%0d exp 24", mf_pay_len); end
        // RESULT with SAME-round R2_4 (C2 unchanged during gray zone)
        load_result(8'h00, 8'h7c,8'hb7,8'hc6,8'ha3,8'h86,8'he9,8'h75,8'hba); // R2_4
        feed_frame(24'h0093, 8'd10);
        wait (mf_frame_done === 1'b1); @(negedge clk);     // CONFIRM
        repeat (10) @(negedge clk);
        if (auth_result !== 2'd1) begin errors = errors + 1; $display("[GE1 FAIL] result=%0d exp 1 (gray-zone same R2 must pass)", auth_result); end
        else $display("[GE1 PASS] gray zone: same-round r2_expected accepted -> PASS");

        //================ GE2: gray zone, re-incremented R2 -> BLOCKED =======
        $display("[GE2] 5th auth gray zone + R2_5 (wrong: as-if-C2-reincremented)");
        pulse_auth;
        wait (mf_frame_done === 1'b1); @(negedge clk);     // ACCESS (C2=a5..ac)
        load_challenge; feed_frame(24'h0091, 8'd32);
        wait (mf_frame_done === 1'b1); @(negedge clk);     // R1
        for (i = 0; i < 24; i = i + 1) fp_payload_buf[i] = 8'h70 + i[7:0];
        feed_frame(24'h0095, 8'd24);
        wait (mf_frame_done === 1'b1); @(negedge clk);     // R1_EXTRA
        load_result(8'h00, 8'hc8,8'h3d,8'h33,8'h4d,8'h3d,8'hd3,8'h02,8'hbc); // R2_5 != expected R2_5? NO: expected is R2_5
        // NOTE: round5 expected = R2_5 = c83d334d3dd302bc. To test "no re-increment on EXTRA",
        // send R2_6 (what it would be if C2 bumped during EXTRA):
        load_result(8'h00, 8'he8,8'h35,8'h86,8'h40,8'h2f,8'hd8,8'hd9,8'h06); // R2_6
        feed_frame(24'h0093, 8'd10);
        repeat (10) @(negedge clk);
        if (auth_result !== 2'd3) begin errors = errors + 1; $display("[GE2 FAIL] result=%0d exp 3", auth_result); end
        else $display("[GE2 PASS] C2 NOT re-incremented during gray zone (R2_6 rejected)");

        //================ GF: forged R2 (1 byte flip) -> BLOCKED =============
        $display("[GF] 6th auth with forged R2 (last byte flipped)");
        pulse_auth;
        wait (mf_frame_done === 1'b1); @(negedge clk);     // ACCESS (C2=a6..ad)
        load_challenge; feed_frame(24'h0091, 8'd32);
        wait (mf_frame_done === 1'b1); @(negedge clk);     // R1
        load_result(8'h00, 8'he8,8'h35,8'h86,8'h40,8'h2f,8'hd8,8'hd9,8'h07); // R2_6 ^ last byte 06->07
        feed_frame(24'h0093, 8'd10);
        repeat (10) @(negedge clk);
        if (auth_result !== 2'd3) begin errors = errors + 1; $display("[GF FAIL] result=%0d exp 3 (forged R2 must block)", auth_result); end
        else $display("[GF PASS] forged R2 (1-byte flip) -> BLOCKED(3) : core security property holds");

        //================ GH: RESULT code 4 (REPLAY) -> REJECT ================
        // A1 阶段 4 语义锁定：终端对任意非零 result 码一律拒绝。即使 R2 完全
        // 正确（本轮期望 R2_7），码 4（服务端重放拒止）也必须被终端拒绝。
        $display("[GH] 7th auth with CORRECT R2_7 but result=4 (REPLAY)");
        pulse_auth;
        wait (mf_frame_done === 1'b1); @(negedge clk);     // ACCESS (C2=a7..ae)
        load_challenge; feed_frame(24'h0091, 8'd32);
        wait (mf_frame_done === 1'b1); @(negedge clk);     // R1
        load_result(8'h04, 8'h7f,8'h3a,8'h29,8'hdf,8'h81,8'h75,8'h1e,8'h59); // R2_7 correct, code=REPLAY
        feed_frame(24'h0093, 8'd10);
        repeat (10) @(negedge clk);
        if (auth_result !== 2'd2) begin errors = errors + 1; $display("[GH FAIL] result=%0d exp 2 (non-zero code must reject)", auth_result); end
        else $display("[GH PASS] result=4 (REPLAY) rejected despite correct R2 -> REJECT(2)");

        
        //==== GI: P2-1 calc_done_flag injection interception ============
        @(negedge clk); auth_start = 1'b1;
        @(negedge clk); auth_start = 1'b0;
        guard = 0;
        while (tx_byte_count < 16 && guard < 10000) begin @(posedge clk); guard = guard + 1; end
        repeat (2) @(negedge clk);
        tx_byte_count = 0;
        guard = 0;
        while (dut.state !== 4'd2 && guard < 10000) begin @(posedge clk); guard = guard + 1; end
        @(negedge clk);
        load_challenge; feed_frame(24'h0091, 8'd32);
        guard = 0;
        while (dut.state !== 4'd5 && guard < 30000) begin @(posedge clk); guard = guard + 1; end
        force dut.calc_done_flag = 1'b0;
        load_result(8'h00, 8'h7b,8'h45,8'hb0,8'h54,8'h5e,8'h59,8'haa,8'h94);
        feed_frame(24'h0093, 8'd10);
        repeat (20) @(negedge clk);
        release dut.calc_done_flag;
        if (auth_result === 2'd3)
            $display("[GI PASS] calc_done_flag=0 injection -> BLOCKED — P2-1 intercepted");
        else begin
            errors = errors + 1;
            $display("[GI FAIL] calc_done_flag=0 injection result=%0d exp 3", auth_result);
        end
        while (auth_busy) @(posedge clk);

        repeat (5) @(negedge clk);
        if (errors == 0) $display("TB_GAP_REGRESSION_PASS");
        else             $display("TB_GAP_REGRESSION_FAIL errors=%0d", errors);
        $finish;
    end

    initial begin
        // W4 B5a：PUF 真实解码 ~82us/认证（4 种子 × 2058 拍）+ 灰区 62us，
    // 七轮认证累计 >1ms——原 500us 预算按种子直通桩的即时路径设定，
    // 提高到 3ms（仅放宽看门狗，不改任何断言语义）
    #3_000_000;
        $display("[WATCHDOG] TIMEOUT result=%0d busy=%b", auth_result, auth_busy);
        $display("TB_GAP_REGRESSION_FAIL (watchdog)");
        $finish;
    end

endmodule