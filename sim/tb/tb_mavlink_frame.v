`timescale 1ns / 1ps
//============================================================================
// tb_mavlink_frame.v — 帧构造器自校验 testbench
//----------------------------------------------------------------------------
// T1: RESPONSE_R1 (4x8B, 32B 载荷) -> 44B 黄金帧逐字节比对（契约 §4）
// T2: ACCESS_REQUEST (16B 载荷)   -> 28B 黄金帧逐字节比对
// T3: 非法 msgid (0x0099)         -> frame_err 脉冲，无帧输出
// T4: 载荷超限 (33B)              -> frame_err 脉冲
// T5: frame_crc 输出与黄金帧尾部 CRC 一致
//============================================================================
module tb_mavlink_frame;

    reg         clk   = 1'b0;
    reg         rst   = 1'b1;
    reg         start = 1'b0;
    reg  [23:0] msg_id = 24'h0;
    reg  [5:0]  payload_len = 6'd0;
    reg  [7:0]  payload_byte = 8'h00;
    reg         payload_valid = 1'b0;
    reg  [7:0]  seq_num = 8'h00;
    reg  [7:0]  sys_id  = 8'h01;
    reg  [7:0]  comp_id = 8'h02;

    wire [7:0]  frame_byte;
    wire        frame_valid;
    wire        frame_done;
    wire [15:0] frame_crc;
    wire        frame_err;

    integer errors = 0;
    integer i;
    reg err_seen = 1'b0;                     // frame_err 粘滞捕获（单拍脉冲防漏检）
    always @(posedge clk) if (frame_err) err_seen <= 1'b1;

    mavlink_frame dut (
        .clk          (clk          ),
        .rst          (rst          ),
        .start        (start        ),
        .msg_id       (msg_id       ),
        .payload_len  (payload_len  ),
        .payload_byte (payload_byte ),
        .payload_valid(payload_valid),
        .seq_num      (seq_num      ),
        .sys_id       (sys_id       ),
        .comp_id      (comp_id      ),
        .frame_byte   (frame_byte   ),
        .frame_valid  (frame_valid  ),
        .frame_done   (frame_done   ),
        .frame_crc    (frame_crc    ),
        .frame_err    (frame_err    )
    );

    always #5 clk = ~clk;

    //------------------------------------------------------------------------
    // 收集器：所有 frame_valid 的字节按序存入 rx_mem
    //------------------------------------------------------------------------
    reg [7:0] rx_mem [0:63];
    integer   rx_cnt = 0;
    always @(posedge clk) begin
        if (frame_valid) begin
            rx_mem[rx_cnt] <= frame_byte;
            rx_cnt <= rx_cnt + 1;
        end
    end

    //------------------------------------------------------------------------
    // 黄金帧
    //------------------------------------------------------------------------
    reg [7:0] golden_r1 [0:43];   // RESPONSE_R1 44B
    reg [7:0] golden_ar [0:27];   // ACCESS_REQUEST 28B
    reg [7:0] payload_r1 [0:31];
    reg [7:0] payload_ar [0:15];

    initial begin
        // RESPONSE_R1 黄金帧（契约 §4）
        golden_r1[0]=8'hFD; golden_r1[1]=8'h20; golden_r1[2]=8'h00; golden_r1[3]=8'h00;
        golden_r1[4]=8'h44; golden_r1[5]=8'h01; golden_r1[6]=8'h02; golden_r1[7]=8'h92;
        golden_r1[8]=8'h00; golden_r1[9]=8'h00;
        golden_r1[10]=8'hB0;
        for (i=0;i<7;i=i+1) golden_r1[11+i]=8'h00;
        golden_r1[18]=8'hB1;
        for (i=0;i<7;i=i+1) golden_r1[19+i]=8'h01;
        golden_r1[26]=8'hB2;
        for (i=0;i<7;i=i+1) golden_r1[27+i]=8'h02;
        golden_r1[34]=8'hB3;
        for (i=0;i<7;i=i+1) golden_r1[35+i]=8'h03;
        golden_r1[42]=8'hA7; golden_r1[43]=8'h15;
        // 对应载荷（就是帧[10..41]）
        for (i=0;i<32;i=i+1) payload_r1[i] = golden_r1[10+i];

        // ACCESS_REQUEST 黄金帧（契约 §4）
        golden_ar[0]=8'hFD; golden_ar[1]=8'h10; golden_ar[2]=8'h00; golden_ar[3]=8'h00;
        golden_ar[4]=8'h42; golden_ar[5]=8'h01; golden_ar[6]=8'h02; golden_ar[7]=8'h90;
        golden_ar[8]=8'h00; golden_ar[9]=8'h00;
        golden_ar[10]=8'h2A; golden_ar[11]=8'h00; golden_ar[12]=8'h00; golden_ar[13]=8'h00;
        golden_ar[14]=8'hEF; golden_ar[15]=8'hBE; golden_ar[16]=8'hAD; golden_ar[17]=8'hDE;
        for (i=0;i<8;i=i+1) golden_ar[18+i]=8'h00+i;
        golden_ar[26]=8'h3A; golden_ar[27]=8'hD2;
        for (i=0;i<16;i=i+1) payload_ar[i] = golden_ar[10+i];
    end

    //------------------------------------------------------------------------
    // 发一帧的驱动任务
    //------------------------------------------------------------------------
    task send_frame(input [23:0] id, input [5:0] plen, input [7:0] seq);
        begin
            @(negedge clk);
            msg_id       <= id;
            payload_len  <= plen;
            seq_num      <= seq;
            start        <= 1'b1;
            @(negedge clk);
            start        <= 1'b0;
            // 等 10 个头字节发完再喂载荷（收集器计数即可靠同步）
            wait (rx_cnt >= 10);
            for (i=0;i<plen;i=i+1) begin
                @(negedge clk);
                payload_byte  <= (id == 24'h0092) ? payload_r1[i] : payload_ar[i];
                payload_valid <= 1'b1;
            end
            @(negedge clk);
            payload_valid <= 1'b0;
            // 等帧完成
            wait (frame_done === 1'b1);
            @(negedge clk);
        end
    endtask

    //------------------------------------------------------------------------
    initial begin
        repeat (3) @(negedge clk);
        rst = 1'b0;
        repeat (2) @(negedge clk);

        // ---------------- T1: RESPONSE_R1 44B ----------------
        send_frame(24'h0092, 6'd32, 8'h44);
        if (rx_cnt !== 44) begin
            errors = errors + 1;
            $display("[T1 FAIL] length %0d != 44", rx_cnt);
        end else begin
            for (i=0;i<44;i=i+1) begin
                if (rx_mem[i] !== golden_r1[i]) begin
                    errors = errors + 1;
                    $display("[T1 FAIL] byte[%0d]=%02h expect %02h", i, rx_mem[i], golden_r1[i]);
                end
            end
            if (errors == 0) $display("[T1 PASS] RESPONSE_R1 44B byte-exact");
        end
        if (frame_crc !== 16'h15A7) begin
            errors = errors + 1;
            $display("[T1 FAIL] crc=%h expect 15A7", frame_crc);
        end

        // ---------------- T2: ACCESS_REQUEST 28B ----------------
        rx_cnt = 0;
        send_frame(24'h0090, 6'd16, 8'h42);
        if (rx_cnt !== 28) begin
            errors = errors + 1;
            $display("[T2 FAIL] length %0d != 28", rx_cnt);
        end else begin
            for (i=0;i<28;i=i+1) begin
                if (rx_mem[i] !== golden_ar[i]) begin
                    errors = errors + 1;
                    $display("[T2 FAIL] byte[%0d]=%02h expect %02h", i, rx_mem[i], golden_ar[i]);
                end
            end
            if (errors == 0) $display("[T2 PASS] ACCESS_REQUEST 28B byte-exact");
        end

        // ---------------- T3: 非法 msgid ----------------
        @(negedge clk);
        msg_id  <= 24'h0099;
        payload_len <= 6'd4;
        start   <= 1'b1;
        @(negedge clk);
        start   <= 1'b0;
        repeat (4) @(negedge clk);
        if (!err_seen) begin
            errors = errors + 1;
            $display("[T3 FAIL] illegal msgid did not raise frame_err");
        end else if (rx_cnt != 28) begin
            errors = errors + 1;
            $display("[T3 FAIL] frame bytes leaked on error path");
        end else
            $display("[T3 PASS] illegal msgid rejected with frame_err");

        // ---------------- T4: 载荷超限 ----------------
        err_seen = 1'b0;
        @(negedge clk);
        msg_id      <= 24'h0091;
        payload_len <= 6'd33;   // 超过 MAX_PAYLOAD=32
        start       <= 1'b1;
        @(negedge clk);
        start       <= 1'b0;
        repeat (4) @(negedge clk);
        if (!err_seen) begin
            errors = errors + 1;
            $display("[T4 FAIL] oversized payload not rejected");
        end else
            $display("[T4 PASS] oversized payload rejected");

        // ---------------- 总结 ----------------
        repeat (5) @(negedge clk);
        if (errors == 0) $display("TB_MAVLINK_FRAME_PASS");
        else             $display("TB_MAVLINK_FRAME_FAIL errors=%0d", errors);
        $finish;
    end

endmodule