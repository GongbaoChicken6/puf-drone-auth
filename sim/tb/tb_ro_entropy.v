`timescale 1ns / 1ps
//============================================================================
// tb_ro_entropy.v -- W4-P4 T2: 上电熵采样验证
//----------------------------------------------------------------------------
// T10: start -> 采样窗 -> ro_array done -> seed_valid=1 + boot_seed 黄金值
//      （黄金 = fixture 16 环低 4bit 拼接 = 0x34F1996F07D25792）
// T11: done 之前 seed_valid 必须保持 0（不得提前锁存）
// T12: 第二次 start 不改变已锁存结果（一次性上电语义）
//============================================================================
module tb_ro_entropy;

    reg clk = 1'b0, rst = 1'b1, start = 1'b0;
    wire measure_en, ring_en, busy, done;
    wire [255:0] ring_freq;
    wire seed_valid;
    wire [63:0] boot_seed;

    integer errors = 0, guard = 0;
    reg early_valid = 1'b0;   // T11: done 前是否提前置位

    localparam [63:0] GOLDEN_SEED = 64'h34F1996F07D25792;

    ro_array_sim # (.N_RINGS(16), .CNT_W(16)) u_arr (
        .clk        (clk        ),
        .rst        (rst        ),
        .measure_en (measure_en ),
        .ring_en    (ring_en    ),
        .busy       (busy       ),
        .done       (done       ),
        .ring_freq  (ring_freq  )
    );

    ro_entropy # (
        .N_RINGS       (16),
        .CNT_W         (16),
        .SAMPLE_CYCLES (32'd64)      // 仿真加速（语义不变）
    ) dut (
        .clk        (clk        ),
        .rst        (rst        ),
        .start      (start      ),
        .measure_en (measure_en ),
        .ring_en    (ring_en    ),
        .busy       (busy       ),
        .done       (done       ),
        .ring_freq  (ring_freq  ),
        .seed_valid (seed_valid ),
        .boot_seed  (boot_seed  )
    );

    always #5 clk = ~clk;

    // T11 监视：done 前 seed_valid 不得为 1
    always @ ( posedge clk ) begin
        if (!rst && !done && seed_valid) early_valid <= 1'b1;
    end

    initial begin
        repeat (10) @(negedge clk);
        rst = 1'b0;
        repeat (5) @(negedge clk);

        // T10: 启动
        @(negedge clk); start = 1'b1;
        @(negedge clk); start = 1'b0;

        // 确认开窗 + 使能环振
        repeat (2) @(negedge clk);
        if (!measure_en || !ring_en) begin
            errors = errors + 1;
            $display("[T10 FAIL] 启动后 measure_en=%b ring_en=%b (应全 1)", measure_en, ring_en);
        end

        // 等 seed_valid
        guard = 0;
        while (!seed_valid && guard < 5000) begin @(posedge clk); guard = guard + 1; end

        if (!seed_valid) begin
            errors = errors + 1; $display("[T10 FAIL] seed_valid 未置位 guard=%0d", guard);
        end else if (boot_seed !== GOLDEN_SEED) begin
            errors = errors + 1;
            $display("[T10 FAIL] boot_seed=%h != 黄金 %h", boot_seed, GOLDEN_SEED);
        end else
            $display("[T10 PASS] boot_seed=%h = fixture 低4bit 拼接黄金值 (%0d 拍)", boot_seed, guard);

        // T11
        if (early_valid) begin
            errors = errors + 1; $display("[T11 FAIL] done 之前 seed_valid 提前置位");
        end else
            $display("[T11 PASS] done 前 seed_valid 始终保持 0（无提前锁存）");

        // T12: 二次 start 不改结果
        @(negedge clk); start = 1'b1;
        @(negedge clk); start = 1'b0;
        repeat (200) @(negedge clk);
        if (boot_seed === GOLDEN_SEED && seed_valid)
            $display("[T12 PASS] 二次 start 后结果保持（一次性上电语义）");
        else begin
            errors = errors + 1;
            $display("[T12 FAIL] 二次 start 后 boot_seed=%h valid=%b", boot_seed, seed_valid);
        end

        // T14/M4(auto-review): 零熵 fail-closed 分支——force 阵列频率低 4 位
        // 全 0（16×0x1000）→ E_DONE 拒绝：seed_valid=0 + seed_fault=1 + seed=0。
        // 该分支此前零覆盖：若健康检查被删除（seed_valid 无条件置 1）本用例必失败
        force u_arr.latch_freqs = {16{16'h1000}};
        rst = 1'b1; repeat (5) @(negedge clk); rst = 1'b0;   // 复位重来（fault/valid 清 0）
        @(negedge clk); start = 1'b1;
        @(negedge clk); start = 1'b0;
        guard = 0;
        while (dut.st != 2'd3 && guard < 5000) begin @(posedge clk); guard = guard + 1; end
        repeat (5) @(negedge clk);                            // E_DONE 锁存后
        if (dut.seed_fault === 1'b1 && dut.seed_valid === 1'b0 && boot_seed === 64'd0)
            $display("[T14 PASS] 零熵被拒: seed_fault=1 + seed_valid=0 + boot_seed=0（fail-closed 且可观测）");
        else begin
            errors = errors + 1;
            $display("[T14 FAIL] fault=%b valid=%b seed=%h（期望 1/0/0；健康检查被删或故障口失效？）",
                     dut.seed_fault, dut.seed_valid, boot_seed);
        end
        release u_arr.latch_freqs;

        if (errors == 0) $display("TB_RO_ENTROPY_PASS");
        else             $display("TB_RO_ENTROPY_FAIL: %0d 项错误", errors);
        $finish;
    end

    initial begin
        #200_000;
        $display("TB_RO_ENTROPY_FAIL (global watchdog)");
        $finish;
    end
endmodule