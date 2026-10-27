`timescale 1ns / 1ps
//============================================================================
// tb_uart_rx.v — uart_rx 专属回归（2026-10-27 补建；v2 改用 uart_tx 作激励源）
//----------------------------------------------------------------------------
// 背景：uart_rx 的 bit_idx 曾在 DATA 态非边界拍被无条件清零（P0-1 同源缺陷，
// 只修了 tx 漏了 rx），FSM 永久挂死——真硅片 PC→板 0 字节两天才定位。
// v1 手工驱动波形在快速时钟下有采样竞态；v2 改用 uart_tx 作 BFM（与
// tb_w3_top 回环同构、其正确性已被 28 字节帧验证），tx_serial 直连 rx_serial。
//============================================================================
module tb_uart_rx;

    localparam CPB = 32;   // 快速仿真（tb_w3_top 用 86，比例同构）

    reg         clk = 1'b0;
    reg         rst = 1'b1;
    reg         tx_valid = 1'b0;
    reg  [7:0]  tx_byte = 8'h00;
    wire        tx_serial, tx_active, tx_done;
    wire [7:0]  rx_byte;
    wire        rx_valid;

    integer errors = 0;
    integer cycle_count = 0;
    integer valid_count = 0;
    reg [7:0]  last_rx_byte;
    integer    v0;
    integer    k6;

    uart_tx # (.CLKS_PER_BIT(CPB)) bfm_tx (
        .clk(clk), .rst(rst), .tx_valid(tx_valid), .tx_byte(tx_byte),
        .tx_serial(tx_serial), .tx_active(tx_active), .tx_done(tx_done)
    );

    uart_rx # (.CLKS_PER_BIT(CPB)) dut_rx (
        .clk(clk), .rst(rst), .rx_serial(tx_serial),   // 模块级回环
        .rx_byte(rx_byte), .rx_valid(rx_valid)
    );

    always #5 clk = ~clk;
    always @(posedge clk) cycle_count <= cycle_count + 1;
    always @(posedge clk) if (rx_valid) valid_count <= valid_count + 1;
    reg [7:0] prev_rx_byte;
    always @(posedge clk) if (rx_valid) begin
        prev_rx_byte <= last_rx_byte;   // NBA 链：先锁上一个，再更新当前
        last_rx_byte <= rx_byte;
    end

    // 发送并等待完成（uart_tx 是精确时序源）
    task send_one(input [7:0] b);
        integer k;
        begin
            @(negedge clk);
            tx_byte <= b; tx_valid <= 1'b1;
            @(negedge clk);
            tx_valid <= 1'b0;
            for (k = 0; k < 400 && tx_done !== 1'b1; k = k + 1) @(negedge clk);
            if (tx_done !== 1'b1) begin
                errors = errors + 1;
                $display("[TX FAIL] tx_done timeout for %02h", b);
            end
            @(negedge clk);
        end
    endtask

    // 发送+接收+比对（基线先于发送锁存——回环中 tx_done 与 rx_valid 近同拍，
    // 先发后等会漏计）：v0 锁在发送前，字节 valid 必然落在基线之后。
    task send_expect(input [7:0] b);
        integer k;
        begin
            v0 = valid_count;
            send_one(b);
            k = 0;
            while (valid_count == v0 && k < 2000) begin @(negedge clk); k = k + 1; end
            if (valid_count == v0) begin
                errors = errors + 1;
                $display("[RX FAIL] no rx_valid within 2000 edges after %02h (hang!)", b);
            end else if (last_rx_byte === b) begin
                $display("[RX OK] byte=%02h", b);
            end else begin
                errors = errors + 1;
                $display("[RX FAIL] byte=%02h expect %02h", last_rx_byte, b);
            end
        end
    endtask

    initial begin
        repeat (3) @(negedge clk);
        rst = 1'b0;
        repeat (2) @(negedge clk);

        // T1-T4: 正交字节型
        send_expect(8'h55);
        send_expect(8'h00);
        send_expect(8'hFF);
        send_expect(8'hA3);
        $display("[T1-T4] 4 orthogonal bytes done");

        // T5: 计数核对
        repeat (10) @(negedge clk);
        if (valid_count !== 4) begin
            errors = errors + 1;
            $display("[T5 FAIL] valid_count=%0d expect 4", valid_count);
        end else
            $display("[T5 PASS] 4/4 bytes, no hang, no drop, no extra");

        // T6: 背靠背（tx_done 后立即发下一字节——uart_tx 最小间隔）
        v0 = valid_count;
        send_one(8'h11); send_one(8'h22);
        k6 = 0;
        while (valid_count < v0 + 2 && k6 < 4000) begin @(negedge clk); k6 = k6 + 1; end
        if (valid_count < v0 + 2) begin
            errors = errors + 1;
            $display("[T6 FAIL] back-to-back only %0d/2 received", valid_count - v0);
        end else if (prev_rx_byte === 8'h11 && last_rx_byte === 8'h22) begin
            $display("[T6 PASS] back-to-back 0x11,0x22 both received in order");
        end else begin
            errors = errors + 1;
            $display("[T6 FAIL] order/values wrong: prev=%02h last=%02h", prev_rx_byte, last_rx_byte);
        end

        // T7: 终计数
        repeat (10) @(negedge clk);
        if (valid_count !== 6) begin
            errors = errors + 1;
            $display("[T7 FAIL] valid_count=%0d expect 6", valid_count);
        end else
            $display("[T7 PASS] 6/6 total");

        repeat (5) @(negedge clk);
        if (errors == 0) $display("TB_UART_RX_PASS");
        else             $display("TB_UART_RX_FAIL errors=%0d", errors);
        $finish;
    end

    initial begin
        #200_000;   // 审查加固：>TB 内部最坏路径 ~140µs（4×2325+4000 拍），诊断先于看门狗打全
        $display("[WATCHDOG] TIMEOUT cycles=%0d valid=%0d", cycle_count, valid_count);
        $display("TB_UART_RX_FAIL errors=%0d (watchdog)", errors);
        $finish;
    end

endmodule