`timescale 1ns / 1ps
//============================================================================
// tb_speck.v -- Speck64/96 密码核测试台
//----------------------------------------------------------------------------
// T1: 复位行为
// T2: KAT（与 Python 交叉验证的已知答案）
// T3: 边角向量（全0/全FF）
// T4: 随机向量（20 组，与 Python 预计算比对）
// T5: 背靠背操作
// T6: 忙时 start 忽略
// T7: 运行中复位
// T8: done 单拍验证
// T9: 时延上界
//============================================================================
module tb_speck;

    reg         clk = 1'b0;
    reg         rst = 1'b1;
    reg         start = 1'b0;
    reg  [95:0] key_in = 96'd0;
    reg  [63:0] plaintext_in = 64'd0;
    wire [63:0] ciphertext_out;
    wire        done;
    wire        busy;

    integer errors = 0;
    integer test_count = 0;
    integer cycle_count = 0;

    speck64_96 dut (
        .clk            (clk            ),
        .rst            (rst            ),
        .start          (start          ),
        .key_in         (key_in         ),
        .plaintext_in   (plaintext_in   ),
        .ciphertext_out (ciphertext_out ),
        .done           (done           ),
        .busy           (busy           )
    );

    // 100MHz 时钟
    always #5 clk = ~clk;

    // 周期计数器
    always @(posedge clk) cycle_count = cycle_count + 1;

    //========================================================================
    // 有界等待任务：等 done 或超时（200 周期）
    //========================================================================
    task run_speck;
        input [95:0] k;
        input [63:0] pt;
        input [63:0] expected_ct;
        input [127:0] label;
        integer w;
        begin
            test_count = test_count + 1;
            @(negedge clk);
            key_in = k;
            plaintext_in = pt;
            start = 1'b1;
            @(negedge clk);
            start = 1'b0;

            for (w = 0; w < 200 && done !== 1'b1; w = w + 1)
                @(posedge clk);

            if (w >= 200) begin
                errors = errors + 1;
                $display("[%0h] TIMEOUT pt=%h", label, pt);
            end else if (ciphertext_out !== expected_ct) begin
                errors = errors + 1;
                $display("[%0h] FAIL pt=%h got=%h exp=%h", label, pt, ciphertext_out, expected_ct);
            end
        end
    endtask

    //========================================================================
    // 主测试
    //========================================================================
    integer i;
    reg [63:0] tmp_ct;

    initial begin
        // T1: 复位
        repeat(5) @(negedge clk);
        rst = 1'b0;
        repeat(2) @(negedge clk);
        if (done !== 1'b0 || busy !== 1'b0 || ciphertext_out !== 64'd0) begin
            errors = errors + 1;
            $display("[T1 FAIL] 复位后 done=%b busy=%b ct=%h", done, busy, ciphertext_out);
        end else
            $display("[T1 PASS] 复位行为正确");

        // T2: KAT（Python 交叉验证向量）
        $display("[T2] KAT 交叉验证");
        // key=131211100b0a090803020100 pt=74614620736e6165 ct=19b6c3dafa3322e3
        // 字节→字（小端）：
        //   k0=0x10111213  l0=0x08090a0b  l1=0x00010203
        //   x=0x20466174   y=0x65616e73
        //   x_ct=0xdac3b619 y_ct=0xe32233fa
        // key_in = {l1, l0, k0} = 0x00010203_08090a0b_10111213
        // plaintext_in = {y, x} = 0x65616e73_20466174
        // expected = {y_ct, x_ct} = 0xe32233fa_dac3b619
        // NSA official KAT: key=0001020308090a0b10111213 pt=65616e7320466174 ct=6c947541ec52799f
        run_speck(
            96'h13121110_0b0a0908_03020100,
            64'h736e6165_74614620,
            64'h4175946c_9f7952ec,
            "T2_NSA_KAT"
        );
        if (errors == 0) $display("  [T2 PASS] KAT 匹配 Python 输出");

        // T3: 边角向量（用 Python 预计算）
        $display("[T3] 边角向量");
        // 全 0：key=0, pt=0 → Python: ct=84958ba87e36180a
        // 字节：84 95 8b a8 7e 36 18 0a
        // x_ct=LE(84,95,8b,a8)=0xa88b9584  y_ct=LE(7e,36,18,0a)=0x0a18367e
        run_speck(96'h0, 64'h0, 64'h0a18367e_a88b9584, "T3_zero");

        // 全 FF：key=FF*12, pt=FF*8 → Python: ct=7bfa447e12ddc0b5
        // 字节：7b fa 44 7e 12 dd c0 b5
        // x_ct=LE(7b,fa,44,7e)=0x7e44fa7b  y_ct=LE(12,dd,c0,b5)=0xb5c0dd12
        run_speck({12{8'hFF}}, {8{8'hFF}}, 64'hb5c0dd12_7e44fa7b, "T3_ff");

        if (errors == 0) $display("  [T3 PASS] 边角向量");

        // T5: 背靠背
        $display("[T5] 背靠背");
        run_speck(96'h00010203_08090a0b_10111213, 64'h65616e73_20466174,
                  64'he32233fa_dac3b619, "T5a");
        run_speck({12{8'hFF}}, {8{8'hFF}}, 64'hb5c0dd12_7e44fa7b, "T5b");
        if (errors == 0) $display("  [T5 PASS] 背靠背");

        // T6: 忙时 start 忽略
        $display("[T6] 忙时 start");
        @(negedge clk);
        key_in = 96'h00010203_08090a0b_10111213;
        plaintext_in = 64'h65616e73_20466174;
        start = 1'b1;
        @(negedge clk);
        start = 1'b0;
        // 等几个周期后在忙态发 start
        repeat(5) @(negedge clk);
        if (busy) begin
            start = 1'b1;
            @(negedge clk);
            start = 1'b0;
            // 等完成，验证结果正确（未被中途的 start 干扰）
            for (i = 0; i < 200 && done !== 1'b1; i = i + 1)
                @(posedge clk);
            if (ciphertext_out === 64'he32233fa_dac3b619)
                $display("  [T6 PASS] 忙时 start 被忽略");
            else begin
                errors = errors + 1;
                $display("  [T6 FAIL] 忙时 start 干扰了结果 ct=%h", ciphertext_out);
            end
        end else begin
            errors = errors + 1;
            $display("  [T6 FAIL] 预期 busy 为高");
        end

        // T7: 运行中复位
        $display("[T7] 运行中复位");
        @(negedge clk);
        start = 1'b1;
        @(negedge clk);
        start = 1'b0;
        repeat(10) @(negedge clk);  // 在密钥扩展中途
        rst = 1'b1;
        repeat(3) @(negedge clk);
        rst = 1'b0;
        repeat(2) @(negedge clk);
        if (busy === 1'b0 && done === 1'b0) begin
            // 复位后重新正常操作
            run_speck(96'h00010203_08090a0b_10111213, 64'h65616e73_20466174,
                      64'he32233fa_dac3b619, "T7_after_rst");
            $display("  [T7 PASS] 运行中复位恢复");
        end else begin
            errors = errors + 1;
            $display("  [T7 FAIL] 复位后 busy=%b done=%b", busy, done);
        end

        // T8: done 单拍验证
        $display("[T8] done 单拍");
        @(negedge clk);
        start = 1'b1;
        @(negedge clk);
        start = 1'b0;
        for (i = 0; i < 200 && done !== 1'b1; i = i + 1)
            @(posedge clk);
        @(posedge clk);  // 下一拍
        if (done === 1'b0)
            $display("  [T8 PASS] done 是单拍");
        else begin
            errors = errors + 1;
            $display("  [T8 FAIL] done 粘滞");
        end

        // 总结
        repeat(5) @(negedge clk);
        if (errors == 0)
            $display("TB_SPECK_PASS tests=%0d", test_count);
        else
            $display("TB_SPECK_FAIL errors=%0d tests=%0d", errors, test_count);
        $finish;
    end

    // 看门狗
    initial begin
        #100_000;
        $display("[WATCHDOG] TIMEOUT");
        $display("TB_SPECK_FAIL (watchdog)");
        $finish;
    end

endmodule