`timescale 1ns / 1ps
//============================================================================
// tb_frame_parser.v — 帧解析器自校验 testbench
//----------------------------------------------------------------------------
// T1: CHALLENGE 黄金帧 (44B)  -> frame_ok, msgid=0x0091, 载荷逐字节正确
// T2: RESULT 黄金帧 (22B)     -> frame_ok, msgid=0x0093, pay_len=10
// T3: 噪声容忍（帧前灌垃圾字节）-> 忽略后正常解析
// T4: 载荷损坏（翻转 1 bit）   -> frame_err（CRC 拒绝）
// T5: 截断帧超时               -> frame_err 后恢复，下一帧正常
// T6: LEN=0 帧                -> 拒绝
// T7: 背靠背两帧              -> 均正确解析
//============================================================================
module tb_frame_parser;

    reg         clk   = 1'b0;
    reg         rst   = 1'b1;
    reg  [7:0]  rx_byte = 8'h00;
    reg         rx_valid = 1'b0;
    wire [23:0] msg_id;
    wire [7:0]  pay_len;
    wire        frame_ok;
    wire        frame_err;
    wire        busy;
    reg  [4:0]  payload_rd_addr = 5'd0;
    wire [7:0]  payload_rd_data;

    integer errors = 0;
    integer i;

    reg ok_seen = 1'b0;
    reg err_seen = 1'b0;
    always @(posedge clk) begin
        if (frame_ok)  ok_seen <= 1'b1;
        if (frame_err) err_seen <= 1'b1;
    end

    frame_parser # (.PARSER_TIMEOUT(128)) dut (
        .clk            (clk            ),
        .rst            (rst            ),
        .rx_byte        (rx_byte        ),
        .rx_valid       (rx_valid       ),
        .msg_id         (msg_id         ),
        .pay_len        (pay_len        ),
        .frame_ok       (frame_ok       ),
        .frame_err      (frame_err      ),
        .busy           (busy           ),
        .payload_rd_addr(payload_rd_addr),
        .payload_rd_data(payload_rd_data)
    );

    always #5 clk = ~clk;

    //------------------------------------------------------------------------
    // 黄金帧数据
    //------------------------------------------------------------------------
    reg [7:0] golden_ch [0:43];   // CHALLENGE 44B
    reg [7:0] golden_re [0:21];   // RESULT 22B

    initial begin
        golden_ch[0]=8'hFD; golden_ch[1]=8'h20; golden_ch[2]=8'h00; golden_ch[3]=8'h00;
        golden_ch[4]=8'h43; golden_ch[5]=8'h01; golden_ch[6]=8'h02; golden_ch[7]=8'h91;
        golden_ch[8]=8'h00; golden_ch[9]=8'h00;
        golden_ch[10]=8'hA0;
        for (i=0;i<7;i=i+1) golden_ch[11+i]=8'h00;
        golden_ch[18]=8'hA1;
        for (i=0;i<7;i=i+1) golden_ch[19+i]=8'h01;
        golden_ch[26]=8'hA2;
        for (i=0;i<7;i=i+1) golden_ch[27+i]=8'h02;
        golden_ch[34]=8'hA3;
        for (i=0;i<7;i=i+1) golden_ch[35+i]=8'h03;
        golden_ch[42]=8'hF2; golden_ch[43]=8'hF7;

        golden_re[0]=8'hFD; golden_re[1]=8'h0A; golden_re[2]=8'h00; golden_re[3]=8'h00;
        golden_re[4]=8'h45; golden_re[5]=8'h01; golden_re[6]=8'h02; golden_re[7]=8'h93;
        golden_re[8]=8'h00; golden_re[9]=8'h00;
        golden_re[10]=8'h00; golden_re[11]=8'h05;              // result=PASS, hd=5
        for (i=0;i<8;i=i+1) golden_re[12+i]=8'hC0+i;          // r2=C0..C7
        golden_re[20]=8'hA5; golden_re[21]=8'hD2;
    end

    //------------------------------------------------------------------------
    // 发送帧任务：逐字节送入
    //------------------------------------------------------------------------
    task send_frame(input integer nbytes);
        begin
            for (i = 0; i < nbytes; i = i + 1) begin
                @(negedge clk);
                rx_byte  <= golden_ch[i];   // 默认用 CHALLENGE（调用方可临时改内存）
                rx_valid <= 1'b1;
                @(negedge clk);
                rx_valid <= 1'b0;
            end
            @(negedge clk);
        end
    endtask

    task send_result_frame;
        begin
            for (i = 0; i < 22; i = i + 1) begin
                @(negedge clk);
                rx_byte  <= golden_re[i];
                rx_valid <= 1'b1;
                @(negedge clk);
                rx_valid <= 1'b0;
            end
            @(negedge clk);
        end
    endtask

    //------------------------------------------------------------------------
    initial begin
        repeat (3) @(negedge clk);
        rst = 1'b0;
        repeat (2) @(negedge clk);

        // ---------------- T1: CHALLENGE 帧 ----------------
        ok_seen = 1'b0; err_seen = 1'b0;
        send_frame(44);
        repeat (3) @(negedge clk);
        if (!ok_seen) begin
            errors = errors + 1; $display("[T1 FAIL] no frame_ok for CHALLENGE");
        end else if (msg_id !== 24'h0091) begin
            errors = errors + 1; $display("[T1 FAIL] msg_id=%h expect 0091", msg_id);
        end else if (pay_len !== 8'd32) begin
            errors = errors + 1; $display("[T1 FAIL] pay_len=%0d expect 32", pay_len);
        end else begin
            // 验证载荷前 4 字节和最后 4 字节
            payload_rd_addr = 5'd0;
            @(negedge clk);
            if (payload_rd_data !== 8'hA0) begin errors=errors+1; $display("[T1 FAIL] pay[0]=%h", payload_rd_data); end
            payload_rd_addr = 5'd8;
            @(negedge clk);
            if (payload_rd_data !== 8'hA1) begin errors=errors+1; $display("[T1 FAIL] pay[8]=%h", payload_rd_data); end
            payload_rd_addr = 5'd31;
            @(negedge clk);
            if (payload_rd_data !== 8'h03) begin errors=errors+1; $display("[T1 FAIL] pay[31]=%h", payload_rd_data); end
            if (errors == 0) $display("[T1 PASS] CHALLENGE 44B parsed: msgid=91 len=32 payload OK");
        end

        // ---------------- T2: RESULT 帧 ----------------
        ok_seen = 1'b0; err_seen = 1'b0;
        send_result_frame;
        repeat (3) @(negedge clk);
        if (!ok_seen) begin
            errors = errors + 1; $display("[T2 FAIL] no frame_ok for RESULT");
        end else if (msg_id !== 24'h0093) begin
            errors = errors + 1; $display("[T2 FAIL] msg_id=%h expect 0093", msg_id);
        end else if (pay_len !== 8'd10) begin
            errors = errors + 1; $display("[T2 FAIL] pay_len=%0d expect 10", pay_len);
        end else begin
            payload_rd_addr = 5'd0;
            @(negedge clk);
            if (payload_rd_data !== 8'h00) begin errors=errors+1; $display("[T2 FAIL] result=%h", payload_rd_data); end
            payload_rd_addr = 5'd1;
            @(negedge clk);
            if (payload_rd_data !== 8'h05) begin errors=errors+1; $display("[T2 FAIL] hd=%h", payload_rd_data); end
            if (errors == 0) $display("[T2 PASS] RESULT 22B parsed: msgid=93 len=10 r2 OK");
        end

        // ---------------- T3: 噪声容忍 ----------------
        ok_seen = 1'b0; err_seen = 1'b0;
        // 灌 5 个垃圾字节
        for (i = 0; i < 5; i = i + 1) begin
            @(negedge clk);
            rx_byte = 8'hAA + i; rx_valid = 1'b1;
            @(negedge clk);
            rx_valid = 1'b0;
        end
        repeat (2) @(negedge clk);
        if (busy !== 1'b0) begin
            errors = errors + 1; $display("[T3 FAIL] busy after garbage, parser confused");
        end
        // 然后发正常帧
        send_frame(44);
        repeat (3) @(negedge clk);
        if (!ok_seen || msg_id !== 24'h0091) begin
            errors = errors + 1; $display("[T3 FAIL] frame after garbage not parsed");
        end else
            $display("[T3 PASS] 5 garbage bytes ignored, frame recovered");

        // ---------------- T4: CRC 损坏 ----------------
        ok_seen = 1'b0; err_seen = 1'b0;
        golden_ch[15] = golden_ch[15] ^ 8'h01;  // 翻转载荷 1 bit
        send_frame(44);
        repeat (3) @(negedge clk);
        if (ok_seen) begin
            errors = errors + 1; $display("[T4 FAIL] corrupted frame accepted!");
        end else if (!err_seen) begin
            errors = errors + 1; $display("[T4 FAIL] no frame_err for corrupted frame");
        end else
            $display("[T4 PASS] corrupted payload rejected by CRC");
        golden_ch[15] = golden_ch[15] ^ 8'h01;  // 恢复

        // ---------------- T5: 截断帧超时 + 恢复 ----------------
        ok_seen = 1'b0; err_seen = 1'b0;
        // 只发前 20 字节（载荷中途截断）
        for (i = 0; i < 20; i = i + 1) begin
            @(negedge clk);
            rx_byte  <= golden_ch[i];
            rx_valid <= 1'b1;
            @(negedge clk);
            rx_valid <= 1'b0;
        end
        // 等 200 拍（超时=128）
        repeat (200) @(negedge clk);
        if (!err_seen) begin
            errors = errors + 1; $display("[T5 FAIL] no timeout for truncated frame");
        end else if (busy !== 1'b0) begin
            errors = errors + 1; $display("[T5 FAIL] busy stuck after timeout");
        end else begin
            // 恢复：发完整帧
            ok_seen = 1'b0;
            send_frame(44);
            repeat (3) @(negedge clk);
            if (!ok_seen) begin
                errors = errors + 1; $display("[T5 FAIL] no recovery after timeout");
            end else
                $display("[T5 PASS] truncated frame timeout + recovery OK");
        end

        // ---------------- T6: LEN=0 帧 ----------------
        ok_seen = 1'b0; err_seen = 1'b0;
        // 手动构造 LEN=0 帧（FD 00 ... — LEN 字节为 0）
        for (i = 0; i < 10; i = i + 1) begin
            @(negedge clk);
            rx_byte  <= (i == 0) ? 8'hFD : (i == 1) ? 8'h00 : 8'h00;
            rx_valid <= 1'b1;
            @(negedge clk);
            rx_valid <= 1'b0;
        end
        repeat (5) @(negedge clk);
        if (ok_seen) begin
            errors = errors + 1; $display("[T6 FAIL] LEN=0 frame accepted");
        end else if (!err_seen) begin
            errors = errors + 1; $display("[T6 FAIL] no err for LEN=0");
        end else
            $display("[T6 PASS] LEN=0 rejected");

        // ---------------- T7: 背靠背两帧 ----------------
        ok_seen = 1'b0; err_seen = 1'b0;
        // 发 CHALLENGE 后立即发 RESULT（间隔 2 拍）
        send_frame(44);
        send_result_frame;
        repeat (3) @(negedge clk);
        if (!ok_seen || msg_id !== 24'h0093) begin
            errors = errors + 1; $display("[T7 FAIL] back-to-back: second frame lost, msgid=%h", msg_id);
        end else
            $display("[T7 PASS] back-to-back frames both parsed");

        // ---------------- 总结 ----------------
        repeat (5) @(negedge clk);
        if (errors == 0) $display("TB_FRAME_PARSER_PASS");
        else             $display("TB_FRAME_PARSER_FAIL errors=%0d", errors);
        $finish;
    end

    // 看门狗
    initial begin
        #500_000;
        $display("[WATCHDOG] TIMEOUT");
        $display("TB_FRAME_PARSER_FAIL errors=%0d (watchdog)", errors);
        $finish;
    end

endmodule
