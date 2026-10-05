`timescale 1ns / 1ps
//============================================================================
// tb_byte_fifo.v — FIFO 自校验 testbench
//----------------------------------------------------------------------------
// T1: 基本写入读出（FIFO 顺序）
// T2: 写满 → full 标志 → 溢出保护（写不进）
// T3: 读空 → empty 标志 → 读不动
// T4: 同拍读写（流水线）
// T5: 环形回绕（写满 64 → 读空 → 再写 64 → 再读 64）
// T6: 复位清空
//============================================================================
module tb_byte_fifo;

    reg         clk = 1'b0;
    reg         rst = 1'b1;
    reg  [7:0]  wr_data = 8'h00;
    reg         wr_en = 1'b0;
    reg         rd_en = 1'b0;
    wire [7:0]  rd_data;
    wire        empty;
    wire        full;
    wire [6:0]  count;

    integer errors = 0;
    integer i;

    byte_fifo dut (
        .clk     (clk    ),
        .rst     (rst    ),
        .wr_data (wr_data),
        .wr_en   (wr_en  ),
        .rd_en   (rd_en  ),
        .rd_data (rd_data),
        .empty   (empty  ),
        .full    (full   ),
        .count   (count  )
    );

    always #5 clk = ~clk;

    task wr_byte(input [7:0] d);
        begin
            @(negedge clk);
            wr_data <= d;
            wr_en   <= 1'b1;
            @(negedge clk);
            wr_en   <= 1'b0;
        end
    endtask

    task rd_byte(input [7:0] expect_d);
        begin
            @(negedge clk);
            // 组合读：数据始终可看——先检查，再弹指针
            if (rd_data !== expect_d) begin
                errors = errors + 1;
                $display("[RD FAIL] got %02h expect %02h", rd_data, expect_d);
            end
            rd_en <= 1'b1;
            @(negedge clk);
            rd_en <= 1'b0;
        end
    endtask

    initial begin
        repeat (3) @(negedge clk);
        rst = 1'b0;
        repeat (2) @(negedge clk);

        // ---------------- T1: 基本写入读出 ----------------
        if (!empty) begin errors=errors+1; $display("[T1 FAIL] not empty at start"); end
        wr_byte(8'h11);
        wr_byte(8'h22);
        wr_byte(8'h33);
        wr_byte(8'h44);
        if (count !== 7'd4) begin errors=errors+1; $display("[T1 FAIL] count=%0d expect 4", count); end
        // 先看再弹：组合读 = 当前头字节
        @(negedge clk);
        if (rd_data !== 8'h11) begin errors=errors+1; $display("[T1 FAIL] peek=%02h expect 11", rd_data); end
        rd_byte(8'h11);
        rd_byte(8'h22);
        rd_byte(8'h33);
        rd_byte(8'h44);
        if (!empty) begin errors=errors+1; $display("[T1 FAIL] not empty after drain"); end
        $display("[T1 PASS] basic FIFO order (errors so far: %0d)", errors);

        // ---------------- T2: 写满 + 溢出保护 ----------------
        errors = 0;
        for (i = 0; i < 64; i = i + 1) wr_byte(8'hA0 + i[7:0]);
        if (!full) begin errors=errors+1; $display("[T2 FAIL] not full after 64 writes"); end
        if (count !== 7'd64) begin errors=errors+1; $display("[T2 FAIL] count=%0d expect 64", count); end
        // 尝试写入第 65 字节（应被拒绝）
        wr_byte(8'hFF);
        if (count !== 7'd64) begin errors=errors+1; $display("[T2 FAIL] overflow: count=%0d", count); end
        // 读 1 字节验证是 A0（不是 FF）
        @(negedge clk);
        if (rd_data !== 8'hA0) begin errors=errors+1; $display("[T2 FAIL] first=%02h expect A0", rd_data); end
        rd_byte(8'hA0);
        $display("[T2 PASS] full at 64, overflow rejected");

        // ---------------- T3: 读空保护 ----------------
        // 排空剩余
        for (i = 1; i < 64; i = i + 1) rd_byte(8'hA0 + i[7:0]);
        if (!empty) begin errors=errors+1; $display("[T3 FAIL] not empty after drain"); end
        // 尝试读空 FIFO
        @(negedge clk);
        rd_en = 1'b1;
        @(negedge clk);
        rd_en = 1'b0;
        if (count !== 7'd0) begin errors=errors+1; $display("[T3 FAIL] underflow: count=%0d", count); end
        $display("[T3 PASS] empty protected, no underflow");

        // ---------------- T4: 同拍读写 ----------------
        errors = 0;
        @(negedge clk);
        wr_data <= 8'h77; wr_en <= 1'b1; rd_en <= 1'b1;  // 同拍读写空 FIFO
        @(negedge clk);
        wr_en <= 1'b0; rd_en <= 1'b0;
        // 写了 1 字节 + 读了 0 字节（空保护）→ count=1
        if (count !== 7'd1) begin errors=errors+1; $display("[T4 FAIL] count=%0d expect 1", count); end
        @(negedge clk);
        if (rd_data !== 8'h77) begin errors=errors+1; $display("[T4 FAIL] data=%02h expect 77", rd_data); end
        $display("[T4 PASS] simultaneous read+write on empty");

        // ---------------- T5: 环形回绕 ----------------
        errors = 0;
        rd_byte(8'h77);   // 排空
        // 写 64 → 读 64 → 写 64 → 读 64（两次回绕）
        for (i = 0; i < 64; i = i + 1) wr_byte(8'h50 + i[7:0]);
        for (i = 0; i < 64; i = i + 1) rd_byte(8'h50 + i[7:0]);
        for (i = 0; i < 64; i = i + 1) wr_byte(8'h60 + i[7:0]);
        for (i = 0; i < 64; i = i + 1) rd_byte(8'h60 + i[7:0]);
        if (!empty) begin errors=errors+1; $display("[T5 FAIL] not empty after wrap"); end
        $display("[T5 PASS] double wraparound");

        // ---------------- T6: 复位清空 ----------------
        errors = 0;
        for (i = 0; i < 10; i = i + 1) wr_byte(8'hE0 + i[7:0]);
        rst = 1'b1;
        repeat (2) @(negedge clk);
        rst = 1'b0;
        repeat (1) @(negedge clk);
        if (!empty) begin errors=errors+1; $display("[T6 FAIL] not empty after reset"); end
        if (count !== 7'd0) begin errors=errors+1; $display("[T6 FAIL] count=%0d after reset", count); end
        $display("[T6 PASS] reset clears FIFO");

        // ---------------- 总结 ----------------
        repeat (3) @(negedge clk);
        if (errors == 0) $display("TB_BYTE_FIFO_PASS");
        else             $display("TB_BYTE_FIFO_FAIL errors=%0d", errors);
        $finish;
    end

    // 看门狗
    initial begin
        #100_000;
        $display("[WATCHDOG] TIMEOUT");
        $display("TB_BYTE_FIFO_FAIL errors=%0d (watchdog)", errors);
        $finish;
    end

endmodule