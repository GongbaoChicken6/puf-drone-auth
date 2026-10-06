`timescale 1ns / 1ps
//============================================================================
// tb_level3_protocol.v — Level 3 全链路集成：真实协议栈端到端
//----------------------------------------------------------------------------
// 首次用真实 RTL 串联 terminal_fsm + mavlink_frame + frame_parser。
// 验证协议状态机与真实帧构造器/帧解析器的接口时序（非简化模型）。
//
// T1: 完整通过流程（ACCESS→CHALLENGE→R1→RESULT→CONFIRM→SESSION）
//     R2 = ~C2（动态绑定，验证 C2 重放修复）
//============================================================================
module tb_level3_protocol;

    reg clk = 1'b0;
    reg rst = 1'b1;

    // ---- terminal_fsm 端口 ----
    reg         auth_start = 1'b0;
    reg  [7:0]  terminal_id = 8'd42;
    wire        auth_busy;
    wire [1:0]  auth_result;
    wire        fp_rx_inhibit;

    // ---- mavlink_frame ↔ terminal_fsm 互连 ----
    wire        mf_start;
    wire [23:0] mf_msg_id;
    wire [5:0]  mf_pay_len;
    wire [7:0]  mf_pay_byte;
    wire        mf_pay_valid;
    wire [7:0]  mf_seq;
    wire        mf_busy, mf_phase, mf_done, mf_err;
    wire [7:0]  mf_frame_byte;
    wire        mf_frame_valid;
    wire [15:0] mf_frame_crc;

    // ---- frame_parser ↔ terminal_fsm 互连 ----
    wire [23:0] fp_msg_id;   // 由 frame_parser 驱动（输出端口）
    wire [7:0]  fp_pay_len;
    wire        fp_frame_ok;
    wire        fp_frame_err;
    wire [4:0]  fp_rd_addr;
    wire [7:0]  fp_rd_data;
    reg  [7:0]  fp_payload_buf [0:31];

    integer errors = 0;
    integer i, k;

    //------------------------------------------------------------------------
    // 真实 terminal_fsm
    //------------------------------------------------------------------------
    terminal_fsm # (.TIMEOUT_CYCLES(2000)) u_fsm (
        .clk           (clk           ),
        .rst           (rst           ),
        .auth_start    (auth_start    ),
        .terminal_id   (terminal_id   ),
        .auth_busy     (auth_busy     ),
        .auth_result   (auth_result   ),
        .fp_msg_id     (fp_msg_id     ),
        .fp_pay_len    (fp_pay_len    ),
        .fp_frame_ok   (fp_frame_ok   ),
        .fp_frame_err  (fp_frame_err  ),
        .fp_rd_addr    (fp_rd_addr    ),
        .fp_rd_data    (fp_rd_data    ),
        .fp_rx_inhibit (fp_rx_inhibit ),
        .mf_start      (mf_start      ),
        .mf_msg_id     (mf_msg_id     ),
        .mf_pay_len    (mf_pay_len    ),
        .mf_pay_byte   (mf_pay_byte   ),
        .mf_pay_valid  (mf_pay_valid  ),
        .mf_seq        (mf_seq        ),
        .mf_sysid      (              ),  // DUT 内部固定 01，不接
        .mf_compid     (              ),  // DUT 内部固定 02，不接
        .mf_busy       (mf_busy       ),
        .mf_pay_phase  (mf_phase      ),
        .mf_frame_done (mf_done       ),
        .mf_frame_err  (mf_err        )
    );

    //------------------------------------------------------------------------
    // 真实 mavlink_frame（被 terminal_fsm 驱动）
    //------------------------------------------------------------------------
    mavlink_frame u_mf (
        .clk           (clk           ),
        .rst           (rst           ),
        .start         (mf_start      ),
        .msg_id        (mf_msg_id     ),
        .payload_len   (mf_pay_len    ),
        .payload_byte  (mf_pay_byte   ),
        .payload_valid (mf_pay_valid  ),
        .seq_num       (mf_seq        ),
        .sys_id        (8'h01         ),
        .comp_id       (8'h02         ),
        .busy          (mf_busy       ),
        .payload_phase (mf_phase      ),
        .frame_byte    (mf_frame_byte ),
        .frame_valid   (mf_frame_valid),
        .frame_done    (mf_done       ),
        .frame_crc     (mf_frame_crc  ),
        .frame_err     (mf_err        )
    );

    // TB 驱动 frame_parser 的字节输入（先声明再例化）
    reg [7:0] fp_rx_byte = 8'h00;
    reg       fp_rx_valid = 1'b0;

    //------------------------------------------------------------------------
    // 真实 frame_parser（输出驱动 terminal_fsm 的 fp_* 输入）
    //------------------------------------------------------------------------
    frame_parser # (.PARSER_TIMEOUT(2000)) u_fp (
        .clk            (clk           ),
        .rst            (rst           ),
        .rx_inhibit     (fp_rx_inhibit ),
        .rx_byte        (fp_rx_byte    ),
        .rx_valid       (fp_rx_valid   ),
        .msg_id         (fp_msg_id     ),
        .pay_len        (fp_pay_len    ),
        .frame_ok       (fp_frame_ok   ),
        .frame_err      (fp_frame_err  ),
        .payload_rd_addr(fp_rd_addr    ),
        .payload_rd_data(fp_rd_data    )
    );

    always #5 clk = ~clk;

    //------------------------------------------------------------------------
    // 辅助任务：向 frame_parser 逐字节喂帧
    //------------------------------------------------------------------------
    reg [7:0] frame_bytes [0:63];
    integer   frame_len = 0;

    task feed_frame_bytes(input integer nbytes);
        integer fi;
        begin
            for (fi = 0; fi < nbytes; fi = fi + 1) begin
                @(negedge clk);
                fp_rx_byte  <= frame_bytes[fi];
                fp_rx_valid <= 1'b1;
                @(negedge clk);
                fp_rx_valid <= 1'b0;
            end
            @(negedge clk);
        end
    endtask

    //------------------------------------------------------------------------
    // 黄金帧数据
    //------------------------------------------------------------------------
    // CHALLENGE (44B) - 由 Python 生成
    reg [7:0] chall_gold [0:43];
    // RESULT (22B) - R2 = Speck(K,C2) Python precomputed
    reg [7:0] result_gold [0:21];

    initial begin
        // CHALLENGE: FD 20 00 00 51 01 02 91 00 00 ...
        chall_gold[0]=8'hFD; chall_gold[1]=8'h20; chall_gold[2]=8'h00; chall_gold[3]=8'h00;
        chall_gold[4]=8'h51; chall_gold[5]=8'h01; chall_gold[6]=8'h02; chall_gold[7]=8'h91;
        chall_gold[8]=8'h00; chall_gold[9]=8'h00;
        chall_gold[10]=8'h50;
        for (i=0;i<7;i=i+1) chall_gold[11+i]=8'h00;
        chall_gold[18]=8'h51;
        for (i=0;i<7;i=i+1) chall_gold[19+i]=8'h01;
        chall_gold[26]=8'h52;
        for (i=0;i<7;i=i+1) chall_gold[27+i]=8'h02;
        chall_gold[34]=8'h53;
        for (i=0;i<7;i=i+1) chall_gold[35+i]=8'h03;
        chall_gold[42]=8'h62; chall_gold[43]=8'h80;

        // RESULT: FD 0A 00 00 50 01 02 93 00 00 00 05 7b 45 b0 54 5e 59 aa 94 f5 35
        result_gold[0]=8'hFD;  result_gold[1]=8'h0A;  result_gold[2]=8'h00;  result_gold[3]=8'h00;
        result_gold[4]=8'h50;  result_gold[5]=8'h01;  result_gold[6]=8'h02;  result_gold[7]=8'h93;
        result_gold[8]=8'h00;  result_gold[9]=8'h00;
        result_gold[10]=8'h00; // result = PASS
        result_gold[11]=8'h05; // hd = 5
        // R2 = Speck(key=0001020308090a0b10111213, C2=a1..a8) = 7b 45 b0 54 5e 59 aa 94
        result_gold[12]=8'h7b; result_gold[13]=8'h45; result_gold[14]=8'hb0; result_gold[15]=8'h54;
        result_gold[16]=8'h5e; result_gold[17]=8'h59; result_gold[18]=8'haa; result_gold[19]=8'h94;
        result_gold[20]=8'hff; result_gold[21]=8'h1d; // CRC (9-byte header verified)
    end

    //------------------------------------------------------------------------
    // 主测试
    //------------------------------------------------------------------------
    initial begin
        repeat (5) @(negedge clk);
        rst = 1'b0;
        repeat (5) @(negedge clk);

        $display("[L3] Full protocol with REAL mavlink_frame + REAL frame_parser");

        // Step 1: 启动认证
        @(negedge clk);
        auth_start <= 1'b1;
        @(negedge clk);
        auth_start <= 1'b0;

        // Step 2: 等 ACCESS_REQUEST 发完（真实 mavlink_frame 的 frame_done）
        wait (mf_done === 1'b1);
        @(negedge clk);
        if (mf_msg_id !== 24'h0090) begin
            errors = errors + 1; $display("[L3 FAIL] ACCESS msgid=%h", mf_msg_id);
        end else
            $display("  [L3] ACCESS_REQUEST sent via real mavlink_frame (16B)");

        // Step 3: 喂 CHALLENGE 到真实 frame_parser
        for (i = 0; i < 44; i = i + 1) frame_bytes[i] = chall_gold[i];
        feed_frame_bytes(44);

        // Step 4: 等 RESPONSE_R1 发完
        wait (mf_done === 1'b1);
        @(negedge clk);
        if (mf_msg_id !== 24'h0092) begin
            errors = errors + 1; $display("[L3 FAIL] R1 msgid=%h", mf_msg_id);
        end else
            $display("  [L3] RESPONSE_R1 sent via real mavlink_frame (32B)");

        // Step 5: 等 frame_parser 输出 frame_ok（terminal 收到 CHALLENGE）
        // （frame_ok 是单拍，可能已经过了——用 auth_busy 或直接等 R1 的 done）

        // Step 6: 喂 RESULT（R2 = ~C2）
        for (i = 0; i < 22; i = i + 1) frame_bytes[i] = result_gold[i];
        feed_frame_bytes(22);

        // Step 7: 等 CONFIRM 发完
        wait (mf_done === 1'b1);
        @(negedge clk);
        if (mf_msg_id !== 24'h0094) begin
            errors = errors + 1; $display("[L3 FAIL] CONFIRM msgid=%h", mf_msg_id);
        end else
            $display("  [L3] CONFIRM sent via real mavlink_frame (5B)");

        // Step 8: 检查最终结果
        repeat (20) @(negedge clk);
        if (auth_result !== 2'd1) begin
            errors = errors + 1;
            $display("[L3 FAIL] auth_result=%0d expect 1 (PASS)", auth_result);
        end else
            $display("[L3 PASS] Full protocol: real FSM + real TX + real RX, dynamic R2 verified");

        // ============ T2: rx_inhibit active-path test ============
        $display("[..T2] rx_inhibit test");
        repeat (5) @(negedge clk);
        auth_start <= 1'b1;
        @(negedge clk);
        auth_start <= 1'b0;
        wait (mf_done === 1'b1); @(negedge clk);  // ACCESS sent
        for (i = 0; i < 44; i = i + 1) frame_bytes[i] = chall_gold[i];
        feed_frame_bytes(44);
        // During S_PROC_SEEDS: rx_inhibit should be HIGH
        repeat (3) @(negedge clk);
        if (fp_rx_inhibit !== 1'b1) begin
            errors = errors + 1;
            $display("[T2 FAIL] rx_inhibit not high during PROC_SEEDS");
        end
        // Feed noise frame during inhibit - should be ignored
        @(negedge clk); fp_rx_byte <= 8'hFD; fp_rx_valid <= 1'b1;
        @(negedge clk); fp_rx_valid <= 1'b0;
        repeat (10) @(negedge clk);
        // Wait for R1 done
        wait (mf_done === 1'b1); @(negedge clk);
        // In S_WAIT_RESULT: rx_inhibit should be LOW
        if (fp_rx_inhibit !== 1'b0) begin
            errors = errors + 1;
            $display("[T2 FAIL] rx_inhibit stuck high in WAIT_RESULT");
        end
        if (errors == 0) $display("[T2 PASS] rx_inhibit works");
        // ============ Summary ============
        repeat (5) @(negedge clk);
        if (errors == 0) $display("TB_LEVEL3_PROTOCOL_PASS");
        else             $display("TB_LEVEL3_PROTOCOL_FAIL errors=%0d", errors);
        $finish;
    end

    // 看门狗
    initial begin
        #200_000;
        $display("[WATCHDOG] TIMEOUT, auth_result=%0d auth_busy=%b", auth_result, auth_busy);
        $display("TB_LEVEL3_PROTOCOL_FAIL (watchdog)");
        $finish;
    end

endmodule