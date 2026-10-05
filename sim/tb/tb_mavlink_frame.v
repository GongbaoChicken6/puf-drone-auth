`timescale 1ns / 1ps
//============================================================================
// tb_mavlink_frame.v — 帧构造器自校验 testbench（v2，覆盖审查缺口）
//----------------------------------------------------------------------------
// T1: RESPONSE_R1 (4x8B, 32B)      -> 44B 黄金帧逐字节比对（契约 §4）
// T2: ACCESS_REQUEST (16B)         -> 28B 黄金帧逐字节比对
// T2b: len=0 最小帧                -> 12B 黄金帧（FD 00 00 00 44 01 02 92 00 00 04 69）
// T3: 非法 msgid (0x0099)          -> frame_err，基线快照断言无字节泄漏
// T4: 载荷超限 (33B)               -> frame_err
// T5: busy 期间 pulse start        -> 被忽略，无重复帧无错帧
// T6: payload_phase 窗口           -> 头段喂的字节被丢，相窗口内喂的正确入帧
// T7: 载荷短缺超时                 -> frame_err（PAYLOAD_TIMEOUT=64 实例）
// T8: 复位打断帧中态 + 恢复        -> busy 撤销，新帧照常工作
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
    wire        busy;
    wire        payload_phase;

    integer errors = 0;
    integer i;
    reg err_seen = 1'b0;                     // frame_err 粘滞捕获（单拍脉冲防漏检）
    always @(posedge clk) if (frame_err) err_seen <= 1'b1;

    //------------------------------------------------------------------------
    // DUT：PAYLOAD_TIMEOUT=64（缩短 T7 等待；金路径喂字节无停顿不受影响）
    //------------------------------------------------------------------------
    mavlink_frame # (.PAYLOAD_TIMEOUT(64)) dut (
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
        .busy         (busy         ),
        .payload_phase(payload_phase),
        .frame_byte   (frame_byte   ),
        .frame_valid  (frame_valid  ),
        .frame_done   (frame_done   ),
        .frame_crc    (frame_crc    ),
        .frame_err    (frame_err    )
    );

    always #5 clk = ~clk;

    //------------------------------------------------------------------------
    // 收集器
    //------------------------------------------------------------------------
    reg [7:0] rx_mem [0:63];
    integer   rx_cnt = 0;
    always @(posedge clk) begin
        if (frame_valid) begin
            rx_mem[rx_cnt % 64] <= frame_byte;
            rx_cnt <= rx_cnt + 1;
        end
    end

    //------------------------------------------------------------------------
    // 黄金数据
    //------------------------------------------------------------------------
    reg [7:0] golden_r1 [0:43];
    reg [7:0] golden_ar [0:27];
    reg [7:0] golden_z  [0:11];   // len=0 最小帧
    reg [7:0] payload_r1 [0:31];
    reg [7:0] payload_ar [0:15];

    task load_golden;
        begin
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
            for (i=0;i<32;i=i+1) payload_r1[i] = golden_r1[10+i];

            golden_ar[0]=8'hFD; golden_ar[1]=8'h10; golden_ar[2]=8'h00; golden_ar[3]=8'h00;
            golden_ar[4]=8'h42; golden_ar[5]=8'h01; golden_ar[6]=8'h02; golden_ar[7]=8'h90;
            golden_ar[8]=8'h00; golden_ar[9]=8'h00;
            golden_ar[10]=8'h2A; golden_ar[11]=8'h00; golden_ar[12]=8'h00; golden_ar[13]=8'h00;
            golden_ar[14]=8'hEF; golden_ar[15]=8'hBE; golden_ar[16]=8'hAD; golden_ar[17]=8'hDE;
            for (i=0;i<8;i=i+1) golden_ar[18+i]=8'h00+i;
            golden_ar[26]=8'h3A; golden_ar[27]=8'hD2;
            for (i=0;i<16;i=i+1) payload_ar[i] = golden_ar[10+i];

            // len=0：msg 0x0092, seq 0x44, CRC 域=帧[1..9]+0x5C -> 0x6904
            golden_z[0]=8'hFD; golden_z[1]=8'h00; golden_z[2]=8'h00; golden_z[3]=8'h00;
            golden_z[4]=8'h44; golden_z[5]=8'h01; golden_z[6]=8'h02; golden_z[7]=8'h92;
            golden_z[8]=8'h00; golden_z[9]=8'h00;
            golden_z[10]=8'h04; golden_z[11]=8'h69;
        end
    endtask

    //------------------------------------------------------------------------
    // 发一帧（正确用法：等 payload_phase 再喂）
    //------------------------------------------------------------------------
    task send_frame(input [23:0] id, input [5:0] plen, input [7:0] seq);
        begin
            @(negedge clk);
            msg_id <= id; payload_len <= plen; seq_num <= seq;
            start  <= 1'b1;
            @(negedge clk);
            start  <= 1'b0;
            if (plen != 0) wait (payload_phase === 1'b1);   // len=0 直接跳过载荷段，等不到 phase
            else repeat (12) @(negedge clk);                // 空载荷：等 10B 头发完
            for (i=0;i<plen;i=i+1) begin
                @(negedge clk);
                payload_byte  <= (id == 24'h0092) ? payload_r1[i] : payload_ar[i];
                payload_valid <= 1'b1;
            end
            @(negedge clk);
            payload_valid <= 1'b0;
            wait (frame_done === 1'b1);
            @(negedge clk);
        end
    endtask

    //------------------------------------------------------------------------
    // 看门狗：200us 无进展强制退出（正常全程 <100us）
    initial begin
        #200_000;
        $display("[WATCHDOG] TIMEOUT - simulation hung");
        $display("TB_MAVLINK_FRAME_FAIL errors=%0d (watchdog)", errors);
        $finish;
    end

    initial begin
        load_golden;
        repeat (3) @(negedge clk);
        rst = 1'b0;
        repeat (2) @(negedge clk);

        $display("[..T1]");
        // ---------------- T1: RESPONSE_R1 44B ----------------
        send_frame(24'h0092, 6'd32, 8'h44);
        if (rx_cnt !== 44) begin
            errors = errors + 1; $display("[T1 FAIL] length %0d != 44", rx_cnt);
        end else begin
            for (i=0;i<44;i=i+1)
                if (rx_mem[i] !== golden_r1[i]) begin
                    errors = errors + 1;
                    $display("[T1 FAIL] byte[%0d]=%02h expect %02h", i, rx_mem[i], golden_r1[i]);
                end
            if (errors == 0) $display("[T1 PASS] RESPONSE_R1 44B byte-exact");
        end
        if (frame_crc !== 16'h15A7) begin
            errors = errors + 1; $display("[T1 FAIL] crc=%h expect 15A7", frame_crc);
        end

        $display("[..T2]");
        // ---------------- T2: ACCESS_REQUEST 28B ----------------
        rx_cnt = 0;
        send_frame(24'h0090, 6'd16, 8'h42);
        if (rx_cnt !== 28) begin
            errors = errors + 1; $display("[T2 FAIL] length %0d != 28", rx_cnt);
        end else begin
            for (i=0;i<28;i=i+1)
                if (rx_mem[i] !== golden_ar[i]) begin
                    errors = errors + 1;
                    $display("[T2 FAIL] byte[%0d]=%02h expect %02h", i, rx_mem[i], golden_ar[i]);
                end
            if (errors == 0) $display("[T2 PASS] ACCESS_REQUEST 28B byte-exact");
        end

        $display("[..T2b]");
        // ---------------- T2b: len=0 最小帧 12B ----------------
        rx_cnt = 0;
        send_frame(24'h0092, 6'd0, 8'h44);
        if (rx_cnt !== 12) begin
            errors = errors + 1; $display("[T2b FAIL] length %0d != 12", rx_cnt);
        end else begin
            for (i=0;i<12;i=i+1)
                if (rx_mem[i] !== golden_z[i]) begin
                    errors = errors + 1;
                    $display("[T2b FAIL] byte[%0d]=%02h expect %02h", i, rx_mem[i], golden_z[i]);
                end
            if (errors == 0) $display("[T2b PASS] len=0 frame 12B byte-exact (FD..04 69)");
        end

        $display("[..T3]");
        // ---------------- T3: 非法 msgid（基线快照断言）----------------
        rx_cnt = 0;                       // 基线
        @(negedge clk);
        msg_id <= 24'h0099; payload_len <= 6'd4; start <= 1'b1;
        @(negedge clk);
        start <= 1'b0;
        repeat (4) @(negedge clk);
        if (!err_seen) begin
            errors = errors + 1; $display("[T3 FAIL] illegal msgid did not raise frame_err");
        end else if (rx_cnt !== 0) begin
            errors = errors + 1; $display("[T3 FAIL] frame bytes leaked: %0d", rx_cnt);
        end else
            $display("[T3 PASS] illegal msgid rejected (baseline +0 bytes)");

        $display("[..T4]");
        // ---------------- T4: 载荷超限 ----------------
        err_seen = 1'b0;
        @(negedge clk);
        msg_id <= 24'h0091; payload_len <= 6'd33; start <= 1'b1;
        @(negedge clk);
        start <= 1'b0;
        repeat (4) @(negedge clk);
        if (!err_seen) begin
            errors = errors + 1; $display("[T4 FAIL] oversized payload not rejected");
        end else
            $display("[T4 PASS] oversized payload rejected");

        $display("[..T5]");
        // ---------------- T5: busy 期间 start 被忽略 ----------------
        rx_cnt = 0;
        @(negedge clk);
        msg_id <= 24'h0092; payload_len <= 6'd32; seq_num <= 8'h44; start <= 1'b1;
        @(negedge clk);
        start <= 1'b0;
        repeat (5) @(negedge clk);          // 此时 busy=1（帧进行中）
        if (busy !== 1'b1) begin
            errors = errors + 1; $display("[T5 FAIL] busy low mid-frame");
        end
        start <= 1'b1;                       // 帧中再次 start（应被忽略）
        @(negedge clk);
        start <= 1'b0;
        // 喂完载荷让帧正常结束
        wait (payload_phase === 1'b1);
        for (i=0;i<32;i=i+1) begin
            @(negedge clk);
            payload_byte <= payload_r1[i]; payload_valid <= 1'b1;
        end
        @(negedge clk);
        payload_valid <= 1'b0;
        wait (frame_done === 1'b1);
        @(negedge clk);
        if (rx_cnt !== 44) begin
            errors = errors + 1; $display("[T5 FAIL] mid-frame start corrupted frame: %0d bytes", rx_cnt);
        end else
            $display("[T5 PASS] start during busy ignored, frame intact (busy=1 verified)");

        $display("[..T6]");
        // ---------------- T6: payload_phase 窗口 + 窗口外字节丢弃 ----------------
        rx_cnt = 0;
        @(negedge clk);
        msg_id <= 24'h0090; payload_len <= 6'd16; seq_num <= 8'h42; start <= 1'b1;
        @(negedge clk);
        start <= 1'b0;
        // 头段（payload_phase=0）提前喂 2 个垃圾字节 -> 应被静默丢弃
        repeat (3) begin
            @(negedge clk);
            payload_byte <= 8'hEE; payload_valid <= 1'b1;
        end
        @(negedge clk);
        payload_valid <= 1'b0;
        if (payload_phase !== 1'b0) begin
            errors = errors + 1; $display("[T6 FAIL] payload_phase high during header");
        end
        // 等窗口开
        wait (payload_phase === 1'b1);
        if (payload_phase !== 1'b1) begin
            errors = errors + 1; $display("[T6 FAIL] payload_phase never asserted");
        end
        for (i=0;i<16;i=i+1) begin
            @(negedge clk);
            payload_byte <= payload_ar[i]; payload_valid <= 1'b1;
        end
        @(negedge clk);
        payload_valid <= 1'b0;
        wait (frame_done === 1'b1);
        @(negedge clk);
        if (rx_cnt !== 28) begin
            errors = errors + 1; $display("[T6 FAIL] frame length %0d != 28 (early bytes leaked?)", rx_cnt);
        end else begin
            for (i=0;i<28;i=i+1)
                if (rx_mem[i] !== golden_ar[i]) begin
                    errors = errors + 1;
                    $display("[T6 FAIL] byte[%0d]=%02h expect %02h", i, rx_mem[i], golden_ar[i]);
                end
            if (errors == 0) $display("[T6 PASS] header-phase bytes dropped, payload_phase handshake works");
        end

        $display("[..T7]");
        // ---------------- T7: 载荷短缺超时 -> frame_err ----------------
        rx_cnt = 0; err_seen = 1'b0;
        @(negedge clk);
        msg_id <= 24'h0092; payload_len <= 6'd32; seq_num <= 8'h44; start <= 1'b1;
        @(negedge clk);
        start <= 1'b0;
        wait (payload_phase === 1'b1);
        for (i=0;i<10;i=i+1) begin           // 只喂 10/32
            @(negedge clk);
            payload_byte <= payload_r1[i]; payload_valid <= 1'b1;
        end
        @(negedge clk);
        payload_valid <= 1'b0;
        wait (err_seen === 1'b1);            // 超时触发（64 拍内）
        @(negedge clk);
        if (busy !== 1'b0) begin
            errors = errors + 1; $display("[T7 FAIL] module hung after timeout");
        end else
            $display("[T7 PASS] payload shortage -> frame_err + return IDLE (no hang)");

        $display("[..T8]");
        // ---------------- T8: 复位打断帧中态 + 恢复 ----------------
        rx_cnt = 0;
        @(negedge clk);
        msg_id <= 24'h0092; payload_len <= 6'd32; seq_num <= 8'h44; start <= 1'b1;
        @(negedge clk);
        start <= 1'b0;
        repeat (8) @(negedge clk);           // 帧进行中
        rst = 1'b1;
        repeat (2) @(negedge clk);
        rst = 1'b0;
        repeat (2) @(negedge clk);
        if (busy !== 1'b0) begin
            errors = errors + 1; $display("[T8 FAIL] busy stuck after reset");
        end
        // 恢复：清收集器基线（复位前已泄出 8 个头字节属预期），完整重发一帧
        rx_cnt = 0;
        send_frame(24'h0092, 6'd32, 8'h44);
        if (rx_cnt !== 44) begin
            errors = errors + 1; $display("[T8 FAIL] recovery frame length %0d != 44", rx_cnt);
        end else begin
            for (i=0;i<44;i=i+1)
                if (rx_mem[i] !== golden_r1[i]) begin
                    errors = errors + 1;
                    $display("[T8 FAIL] recovery byte[%0d] mismatch", i);
                end
            if (errors == 0) $display("[T8 PASS] reset mid-frame recovery OK");
        end

        // ---------------- 总结 ----------------
        repeat (5) @(negedge clk);
        if (errors == 0) $display("TB_MAVLINK_FRAME_PASS");
        else             $display("TB_MAVLINK_FRAME_FAIL errors=%0d", errors);
        $finish;
    end

endmodule