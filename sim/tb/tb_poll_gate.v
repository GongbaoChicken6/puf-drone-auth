// tb_poll_gate.v -- N14(单信道) AUTH_POLL 点名门控 TB（精简：只验证门控，不跑 PUF/TX）
// 断言：
//   T1 poll(tid 不匹配)          -> 板不醒（state 保持 S_IDLE）
//   T2 poll(tid 匹配, nonce!=0)  -> 板被唤醒（离开 S_IDLE）
//   T3 poll(tid 匹配, nonce==0)  -> 不开认证，但打开注册窗口 -> CHALLENGE 被接受
//   T4 窗口过期后 CHALLENGE      -> 拒绝（state 保持 S_IDLE）
`timescale 1ns/1ps
module tb_poll_gate;
    reg         clk = 1'b0;
    reg         rst = 1'b1;
    reg         auth_start = 1'b0;
    reg  [7:0]  terminal_id = 8'd1;
    wire        auth_busy;
    wire [1:0]  auth_result;
    // frame_parser 模型
    reg         fp_frame_ok  = 1'b0;
    reg         fp_frame_err = 1'b0;
    reg  [23:0] fp_msg_id    = 24'h0;
    reg  [7:0]  fp_pay_len   = 8'd0;
    reg  [7:0]  fp_payload [0:31];
    wire [4:0]  fp_rd_addr;
    wire [7:0]  fp_rd_data = fp_payload[fp_rd_addr];
    // mavlink_frame 模型（本 TB 不关心发送，直接给空闲）
    wire        mf_start;
    wire [23:0] mf_msg_id;
    wire [5:0]  mf_pay_len;
    wire [7:0]  mf_pay_byte;
    wire        mf_pay_valid;
    wire [7:0]  mf_seq, mf_sysid, mf_compid;
    wire        mf_pay_phase;
    reg         mf_frame_done = 1'b0;
    reg         mf_frame_err  = 1'b0;
    // PUF 子系统（本 TB 不让它跑到测量，只要求接口存在）
    wire        cd_start, cd_done;
    wire [63:0] cd_seed;
    wire [511:0] cd_pair_table;
    wire        ra_measure_en, ra_ring_en, ra_busy, ra_done;
    wire [255:0] ra_ring_freq;

    assign cd_done = 1'b1;
    assign ra_done = 1'b1;
    assign ra_busy = 1'b0;

    terminal_fsm # (
        .POLL_GATE_EN   (1),
        .POLL_WIN_CYC   (32'd400),      // TB 缩短窗口便于过期测试
        .TIMEOUT_CYCLES (32'd1000),
        .MEASURE_CYCLES (32'd64),
        .ENROLL_IDLE_ACCEPT (1)
    ) dut (
        .clk(clk), .rst(rst), .auth_start(auth_start), .terminal_id(terminal_id),
        .auth_busy(auth_busy), .auth_result(auth_result),
        .c2_boot_seed(64'hA7A6_A5A4_A3A2_A1A0),
        .device_key_in(96'h1312_1110_0B0A_0908_0302_0100),
        .use_ext_key(1'b0), .seed_load(1'b0),
        .cd_start(cd_start), .cd_seed(cd_seed), .cd_pair_table(cd_pair_table), .cd_done(cd_done),
        .ra_measure_en(ra_measure_en), .ra_ring_en(ra_ring_en), .ra_busy(ra_busy),
        .ra_done(ra_done), .ra_ring_freq(ra_ring_freq),
        .fp_msg_id(fp_msg_id), .fp_pay_len(fp_pay_len), .fp_frame_ok(fp_frame_ok),
        .fp_frame_err(fp_frame_err), .fp_rd_addr(fp_rd_addr), .fp_rd_data(fp_rd_data),
        .mf_start(mf_start), .mf_msg_id(mf_msg_id), .mf_pay_len(mf_pay_len),
        .mf_pay_byte(mf_pay_byte), .mf_pay_valid(mf_pay_valid), .mf_seq(mf_seq),
        .mf_sysid(mf_sysid), .mf_compid(mf_compid), .mf_busy(1'b0),
        .mf_pay_phase(mf_pay_phase), .mf_frame_done(mf_frame_done), .mf_frame_err(mf_frame_err)
    );

    always #5 clk = ~clk;
    integer errors = 0;
    integer k;
    localparam [4:0] S_IDLE = 5'd0;

    // 投递一帧：填 payload + 打一拍 frame_ok
    task feed_frame(input [23:0] mid, input [7:0] len, input [7:0] b0,
                    input [7:0] b1, input [7:0] b2, input [7:0] b3,
                    input [7:0] b4, input [7:0] b5, input [7:0] b6, input [7:0] b7);
        begin
            for (k = 0; k < 8; k = k + 1) fp_payload[k] = 8'h00;
            fp_payload[0]=b0; fp_payload[1]=b1; fp_payload[2]=b2; fp_payload[3]=b3;
            fp_payload[4]=b4; fp_payload[5]=b5; fp_payload[6]=b6; fp_payload[7]=b7;
            fp_msg_id  = mid;
            fp_pay_len = len;
            @(posedge clk); #1 fp_frame_ok = 1'b1;
            @(posedge clk); #1 fp_frame_ok = 1'b0;
            repeat (4) @(posedge clk);
        end
    endtask

    task poll_frame(input [7:0] tid, input [7:0] n3);
        begin
            // payload <II：tid LE + nonce LE（高 3 字节 0，n3 末字节可设非 0）
            feed_frame(24'h0097, 8'd8, tid, 8'h00, 8'h00, 8'h00, 8'h01, 8'h00, 8'h00, n3);
        end
    endtask

    task challenge_frame;
        begin
            // 32B seeds：本 TB 只验"是否被接受"，内容无所谓
            for (k = 0; k < 32; k = k + 1) fp_payload[k] = k[7:0];
            fp_msg_id  = 24'h0091;
            fp_pay_len = 8'd32;
            @(posedge clk); #1 fp_frame_ok = 1'b1;
            @(posedge clk); #1 fp_frame_ok = 1'b0;
            repeat (8) @(posedge clk);
        end
    endtask

    task expect_state_idle(input [127:0] tag);
        begin
            repeat (40) @(posedge clk);
            if (dut.state !== S_IDLE) begin
                errors = errors + 1;
                $display("[N14 FAIL] %0s: state=%0d expect IDLE", tag, dut.state);
            end else $display("[N14 PASS] %0s: 保持 IDLE", tag);
        end
    endtask

    task expect_left_idle(input [127:0] tag);
        begin
            repeat (40) @(posedge clk);
            if (dut.state === S_IDLE) begin
                errors = errors + 1;
                $display("[N14 FAIL] %0s: 仍在 IDLE（未唤醒）", tag);
            end else $display("[N14 PASS] %0s: 已离开 IDLE(state=%0d)", tag, dut.state);
        end
    endtask

    initial begin
        $display("=== tb_poll_gate start ===");
        for (k = 0; k < 8; k = k + 1) fp_payload[k] = 8'h00;
        repeat (5) @(posedge clk);
        rst = 1'b0;
        repeat (5) @(posedge clk);

        // T1: 点名别人的 tid -> 不醒
        poll_frame(8'd2, 8'h00);
        expect_state_idle("T1 poll(tid=2)@板tid=1");

        // T2: 点名自己 + nonce!=0 -> 唤醒
        poll_frame(8'd1, 8'h00);
        expect_left_idle("T2 poll(tid=1,nonce!=0)");
        // 复位回 IDLE 继续下一组
        rst = 1'b1; repeat (3) @(posedge clk); rst = 1'b0; repeat (5) @(posedge clk);

        // T3: 点名自己 + nonce==0 -> 不醒，但开窗 -> CHALLENGE 被接受
        poll_frame(8'd1, 8'h00);
        begin : t3a
            integer guard;
            guard = 0;
            // nonce==0 时我方把 nonce[0] 置 1 才非 0；这里重投一次全 0 的
            for (k = 0; k < 8; k = k + 1) fp_payload[k] = 8'h00;
            fp_payload[0] = 8'd1;
            fp_msg_id  = 24'h0097;
            fp_pay_len = 8'd8;
            @(posedge clk); #1 fp_frame_ok = 1'b1;
            @(posedge clk); #1 fp_frame_ok = 1'b0;
            repeat (40) @(posedge clk);
            if (dut.state !== S_IDLE) begin
                errors = errors + 1; $display("[N14 FAIL] T3 nonce==0 不应开认证(state=%0d)", dut.state);
            end else $display("[N14 PASS] T3 nonce==0 仅开窗");
        end
        challenge_frame;
        begin : t3b
            repeat (40) @(posedge clk);
            if (dut.state === S_IDLE) begin
                errors = errors + 1; $display("[N14 FAIL] T3 窗口内 CHALLENGE 未被接受");
            end else $display("[N14 PASS] T3 窗口内 CHALLENGE 被接受(state=%0d)", dut.state);
        end
        rst = 1'b1; repeat (3) @(posedge clk); rst = 1'b0; repeat (5) @(posedge clk);

        // T4: 开窗后等窗口过期（POLL_WIN_CYC=400），再发 CHALLENGE -> 拒绝
        begin : t4
            for (k = 0; k < 8; k = k + 1) fp_payload[k] = 8'h00;
            fp_payload[0] = 8'd1;
            fp_msg_id  = 24'h0097; fp_pay_len = 8'd8;
            @(posedge clk); #1 fp_frame_ok = 1'b1;
            @(posedge clk); #1 fp_frame_ok = 1'b0;
            repeat (600) @(posedge clk);   // > POLL_WIN_CYC(400)，窗口关
        end
        challenge_frame;
        begin : t4b
            repeat (40) @(posedge clk);
            if (dut.state !== S_IDLE) begin
                errors = errors + 1; $display("[N14 FAIL] T4 窗口过期后 CHALLENGE 仍被接受(state=%0d)", dut.state);
            end else $display("[N14 PASS] T4 窗口过期后 CHALLENGE 被拒");
        end

        if (errors == 0) $display("TB_POLL_GATE_PASS");
        else $display("TB_POLL_GATE_FAIL errors=%0d", errors);
        $finish;
    end
endmodule
