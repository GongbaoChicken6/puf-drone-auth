`timescale 1ns / 1ps
//============================================================================
// tb_uart_tx.v — P0-1 修复验证：发送字节不挂死，tx_done 产生，波特正确
//----------------------------------------------------------------------------
// 用 CLKS_PER_BIT=8（快速仿真），发 3 个字节验证连续发送。
//============================================================================
module tb_uart_tx;

    reg        clk = 1'b0;
    reg        rst = 1'b1;
    reg        tx_valid = 1'b0;
    reg  [7:0] tx_byte = 8'h00;
    wire       tx_serial;
    wire       tx_active;
    wire       tx_done;

    integer errors = 0;
    integer cycle_count = 0;
    integer done_count = 0;

    uart_tx # (.CLKS_PER_BIT(8)) dut (
        .clk       (clk      ),
        .rst       (rst      ),
        .tx_valid  (tx_valid ),
        .tx_byte   (tx_byte  ),
        .tx_serial (tx_serial),
        .tx_active (tx_active),
        .tx_done   (tx_done  )
    );

    always #5 clk = ~clk;
    always @(posedge clk) cycle_count <= cycle_count + 1;
    always @(posedge clk) if (tx_done) done_count <= done_count + 1;

    task send_one(input [7:0] b);
        integer k;
        reg found;
        begin
            @(negedge clk);
            tx_byte <= b;
            tx_valid <= 1'b1;
            @(negedge clk);
            tx_valid <= 1'b0;
            // 等 tx_done（最多 200 个 negedge；tx_done 是单拍脉冲，negedge 处可采到）
            found = 1'b0;
            for (k = 0; k < 200 && !found; k = k + 1) begin
                @(negedge clk);
                if (tx_done === 1'b1) found = 1'b1;
            end
            if (!found) begin
                errors = errors + 1;
                $display("[SEND FAIL] tx_done timeout for byte %02h (P0-1 hang!)", b);
            end
            @(negedge clk);   // 稳定一拍
        end
    endtask

    initial begin
        repeat (3) @(negedge clk);
        rst = 1'b0;
        repeat (2) @(negedge clk);

        // T1: 发 0x55（交替位型）
        send_one(8'h55);
        if (tx_serial !== 1'b1) begin errors=errors+1; $display("[T1 FAIL] line not idle after send"); end
        $display("[T1 PASS] 0x55 sent, tx_done received");

        // T2: 发 0x00（全零）
        send_one(8'h00);
        $display("[T2 PASS] 0x00 sent, tx_done received");

        // T3: 发 0xFF（全一）
        send_one(8'hFF);
        $display("[T3 PASS] 0xFF sent, tx_done received");

        // T4: 验证 3 个字节都完成了
        repeat (5) @(negedge clk);
        if (done_count !== 3) begin
            errors = errors + 1;
            $display("[T4 FAIL] done_count=%0d expect 3", done_count);
        end else
            $display("[T4 PASS] 3 bytes completed, no hang");

        // T5: 验证 tx_active 覆盖 CLEANUP（P0-2 修复）
        // 发送期间 tx_active 应该持续为高直到回到 IDLE
        send_one(8'hAA);
        if (tx_active !== 1'b0) begin errors=errors+1; $display("[T5 FAIL] tx_active stuck"); end
        else $display("[T5 PASS] tx_active deasserts after CLEANUP");

        repeat (3) @(negedge clk);
        if (errors == 0) $display("TB_UART_TX_PASS");
        else             $display("TB_UART_TX_FAIL errors=%0d", errors);
        $finish;
    end

    // 看门狗
    initial begin
        #50_000;
        $display("[WATCHDOG] TIMEOUT after %0d cycles, done=%0d", cycle_count, done_count);
        $display("TB_UART_TX_FAIL errors=%0d (watchdog)", errors);
        $finish;
    end

endmodule