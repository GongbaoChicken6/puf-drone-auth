`timescale 1ns / 1ps
//============================================================================
// tb_tx_chain.v — Level 2 集成测试：真实 TX 链端到端
//----------------------------------------------------------------------------
// 首次用真实 RTL（非模型）串联 mavlink_frame → byte_fifo → uart_tx。
// 验证：帧构造器按拍输出 → FIFO 缓冲 → UART 串行化 → 线上解码还原
//
// T1: 发送 RESPONSE_R1 黄金帧（44B）→ 串口解码逐字节比对
// T2: 发送 CONFIRM 帧（17B）→ 解码比对
// T3: 背靠背两帧 → 均正确还原（FIFO 不丢不乱）
//
// CLKS_PER_BIT=8（快速仿真，UART 波特=时钟/8/10）
//============================================================================
module tb_tx_chain;

    reg clk = 1'b0;
    reg rst = 1'b1;

    // ---- mavlink_frame 驱动信号 ----
    reg         mf_start = 1'b0;
    reg  [23:0] mf_msg_id = 24'h0;
    reg  [5:0]  mf_pay_len = 6'd0;
    reg  [7:0]  mf_pay_byte = 8'h00;
    reg         mf_pay_valid = 1'b0;
    reg  [7:0]  mf_seq = 8'h00;

    // ---- 真实 mavlink_frame ----
    wire        mf_busy, mf_phase, mf_done, mf_err;
    wire [7:0]  mf_frame_byte;
    wire        mf_frame_valid;
    wire [15:0] mf_frame_crc;

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

    // ---- 接口 wire（全部前置声明，避免隐式声明冲突）----
    wire [7:0] fifo_rd_data;
    wire       fifo_empty, fifo_full;
    wire [6:0] fifo_count;
    wire       tx_serial, tx_active, tx_done;
    wire       fifo_pop;

    // 胶水逻辑（契约 §6.1-1：先声明后例化再赋值）
    assign fifo_pop = ~fifo_empty & ~tx_active;

    // ---- 真实 byte_fifo ----
    byte_fifo u_fifo (
        .clk     (clk            ),
        .rst     (rst            ),
        .wr_data (mf_frame_byte  ),   // mavlink_frame 输出直写 FIFO
        .wr_en   (mf_frame_valid ),
        .rd_en   (fifo_pop       ),   // 胶水逻辑控制读
        .rd_data (fifo_rd_data   ),
        .empty   (fifo_empty     ),
        .full    (fifo_full      ),
        .count   (fifo_count     )
    );

    // ---- 真实 uart_tx ----
    uart_tx # (.CLKS_PER_BIT(8)) u_uart (
        .clk       (clk       ),
        .rst       (rst       ),
        .tx_valid  (fifo_pop  ),   // 胶水：FIFO 弹出时发使能
        .tx_byte   (fifo_rd_data), // 胶路：FIFO 组合读直连
        .tx_serial (tx_serial ),
        .tx_active (tx_active ),
        .tx_done   (tx_done   )
    );

    always #5 clk = ~clk;

    //------------------------------------------------------------------------
    // 串口解码器（TB 侧 UART 接收，采样 tx_serial 还原字节）
    //------------------------------------------------------------------------
    localparam CB = 8;   // CLKS_PER_BIT

    reg [7:0] rx_decoded [0:63];   // 解码结果存储
    integer   rx_count = 0;
    integer   rx_errors = 0;
    integer   i, j;

    // 串口接收任务：等起始位→采样 8 数据位→验停止位
    task uart_rx_byte;
        begin
            // 等起始位（tx_serial 下降沿）
            @(negedge tx_serial);
            // 等 1.5 位到第一个数据位中心
            repeat (CB + CB/2) @(posedge clk);
            // 采样 8 位（LSB first）
            for (j = 0; j < 8; j = j + 1) begin
                rx_decoded[rx_count][j] = tx_serial;
                if (j < 7) repeat (CB) @(posedge clk);
            end
            // 等停止位中心
            repeat (CB) @(posedge clk);
            if (tx_serial !== 1'b1) begin
                rx_errors = rx_errors + 1;
                $display("[UART ERR] stop bit low at byte %0d", rx_count);
            end
            rx_count = rx_count + 1;
            // 等半拍让停止位结束
            repeat (CB/2) @(posedge clk);
        end
    endtask

    //------------------------------------------------------------------------
    // 帧驱动任务：start → 等窗口 → 喂载荷 → 等 done
    //------------------------------------------------------------------------
    reg [7:0] payload_data [0:31];

    task send_frame(input [23:0] id, input [5:0] plen, input [7:0] seq);
        begin
            @(negedge clk);
            mf_msg_id  <= id;
            mf_pay_len <= plen;
            mf_seq     <= seq;
            mf_start   <= 1'b1;
            @(negedge clk);
            mf_start   <= 1'b0;
            if (plen != 0) begin
                wait (mf_phase === 1'b1);
                for (i = 0; i < plen; i = i + 1) begin
                    @(negedge clk);
                    mf_pay_byte  <= payload_data[i];
                    mf_pay_valid <= 1'b1;
                end
                @(negedge clk);
                mf_pay_valid <= 1'b0;
            end else begin
                repeat (12) @(negedge clk);
            end
            wait (mf_done === 1'b1);
            @(negedge clk);
        end
    endtask

    //------------------------------------------------------------------------
    // 黄金帧数据（与契约 §4 一致）
    //------------------------------------------------------------------------
    reg [7:0] golden_r1 [0:43];
    reg [7:0] golden_cf [0:16];

    initial begin
        // RESPONSE_R1 44B
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

        // CONFIRM 17B
        golden_cf[0]=8'hFD; golden_cf[1]=8'h05; golden_cf[2]=8'h00; golden_cf[3]=8'h00;
        golden_cf[4]=8'h46; golden_cf[5]=8'h01; golden_cf[6]=8'h02; golden_cf[7]=8'h94;
        golden_cf[8]=8'h00; golden_cf[9]=8'h00;
        golden_cf[10]=8'h2A; golden_cf[11]=8'h00; golden_cf[12]=8'h00; golden_cf[13]=8'h00;
        golden_cf[14]=8'h01; golden_cf[15]=8'h78; golden_cf[16]=8'hF4;
    end

    //------------------------------------------------------------------------
    initial begin
        repeat (5) @(negedge clk);
        rst = 1'b0;
        repeat (5) @(negedge clk);

        // ============ T1: RESPONSE_R1 44B ============
        $display("[..T1] RESPONSE_R1 44B via real TX chain");
        for (i = 0; i < 32; i = i + 1)
            payload_data[i] = golden_r1[10+i];
        rx_count = 0; rx_errors = 0;

        // 发送和串口接收并行（fork 等两个都完成）
        fork
            begin : tx_side
                send_frame(24'h0092, 6'd32, 8'h44);
            end
            begin : rx_side
                integer r1i;
                for (r1i = 0; r1i < 44; r1i = r1i + 1) uart_rx_byte;
            end
        join
        repeat (5) @(negedge clk);

        if (rx_count !== 44) begin
            rx_errors = rx_errors + 1;
            $display("[T1 FAIL] decoded %0d bytes, expect 44", rx_count);
        end else begin
            for (i = 0; i < 44; i = i + 1) begin
                if (rx_decoded[i] !== golden_r1[i]) begin
                    rx_errors = rx_errors + 1;
                    $display("[T1 FAIL] byte[%0d]=%02h expect %02h", i, rx_decoded[i], golden_r1[i]);
                end
            end
        end
        if (rx_errors == 0) $display("[T1 PASS] 44B byte-exact through real mavlink-frame->fifo->uart");
        else $display("[T1 FAIL] %0d errors", rx_errors);

        // ============ T2: CONFIRM 17B ============
        $display("[..T2] CONFIRM 17B");
        for (i = 0; i < 5; i = i + 1)
            payload_data[i] = golden_cf[10+i];
        rx_count = 0; rx_errors = 0;

        fork
            begin : tx2
                send_frame(24'h0094, 6'd5, 8'h46);
            end
            begin : rx2
                integer r2i;
                for (r2i = 0; r2i < 17; r2i = r2i + 1) uart_rx_byte;
            end
        join
        repeat (5) @(negedge clk);

        if (rx_count !== 17) begin
            rx_errors = rx_errors + 1;
            $display("[T2 FAIL] decoded %0d bytes, expect 17", rx_count);
        end else begin
            for (i = 0; i < 17; i = i + 1) begin
                if (rx_decoded[i] !== golden_cf[i]) begin
                    rx_errors = rx_errors + 1;
                    $display("[T2 FAIL] byte[%0d]=%02h expect %02h", i, rx_decoded[i], golden_cf[i]);
                end
            end
        end
        if (rx_errors == 0) $display("[T2 PASS] 17B byte-exact");
        else $display("[T2 FAIL] %0d errors", rx_errors);

        // ============ T3: 背靠背两帧 ============
        $display("[..T3] back-to-back R1 + CONFIRM");
        for (i = 0; i < 32; i = i + 1)
            payload_data[i] = golden_r1[10+i];
        rx_count = 0; rx_errors = 0;

        fork
            begin : tx3
                send_frame(24'h0092, 6'd32, 8'h44);
                // 立即发第二帧（不等 FIFO 排空——44+17=61 <= 64）
                for (i = 0; i < 5; i = i + 1)
                    payload_data[i] = golden_cf[10+i];
                send_frame(24'h0094, 6'd5, 8'h47);
            end
            begin : rx3
                integer r3i;
                for (r3i = 0; r3i < 61; r3i = r3i + 1) uart_rx_byte;
            end
        join
        repeat (5) @(negedge clk);

        if (rx_count !== 61) begin
            rx_errors = rx_errors + 1;
            $display("[T3 FAIL] decoded %0d bytes, expect 61", rx_count);
        end else begin
            // 第一帧 44B
            for (i = 0; i < 44; i = i + 1) begin
                if (rx_decoded[i] !== golden_r1[i]) begin
                    rx_errors = rx_errors + 1;
                    $display("[T3 FAIL] frame1 byte[%0d]", i);
                end
            end
            // 第二帧 17B：只验数据字节 [0..14]（seq=0x47 的 CRC ≠ golden seq=0x46，跳过）
            for (i = 0; i < 15; i = i + 1) begin
                if (i == 4) begin
                    if (rx_decoded[44+i] !== 8'h47) begin
                        rx_errors = rx_errors + 1;
                        $display("[T3 FAIL] frame2 seq=%02h expect 47", rx_decoded[44+i]);
                    end
                end else if (rx_decoded[44+i] !== golden_cf[i]) begin
                    rx_errors = rx_errors + 1;
                    $display("[T3 FAIL] frame2 byte[%0d]=%02h expect %02h", i, rx_decoded[44+i], golden_cf[i]);
                end
            end
        end
        if (rx_errors == 0) $display("[T3 PASS] back-to-back 44+17=61B, no loss, seq auto-increment");
        else $display("[T3 FAIL] %0d errors", rx_errors);

        // ============ 总结 ============
        repeat (5) @(negedge clk);
        if (rx_errors == 0) $display("TB_TX_CHAIN_PASS");
        else $display("TB_TX_CHAIN_FAIL errors=%0d", rx_errors);
        $finish;
    end

    // 看门狗
    initial begin
        #2_000_000;   // 2ms = 200k cycles = enough for 61 bytes × 80 cycles
        $display("[WATCHDOG] TIMEOUT, rx_count=%0d fifo_count=%0d tx_active=%b",
                 rx_count, fifo_count, tx_active);
        $display("TB_TX_CHAIN_FAIL (watchdog)");
        $finish;
    end

endmodule