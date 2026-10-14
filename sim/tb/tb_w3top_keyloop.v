`timescale 1ns / 1ps
//============================================================================
// tb_w3top_keyloop.v -- W4-P4 S3/S4 P0 回归: w3_top 级密钥回环验证
//----------------------------------------------------------------------------
// A 代理发现 w3_top 例化缺 .key_valid/.key_reg 连接 -> fsm_key_valid 悬空 z
// -> 派生密钥永远到不了 Speck。此 TB 在 w3_top 层锁定该回环。
//============================================================================
module tb_w3top_keyloop;

    reg  sys_clk = 1'b0;
    reg  sys_rst_n = 1'b0;
    reg  auth_btn = 1'b0;
    reg  [7:0] term_id_sw = 8'h01;
    wire radio_txd, radio_rxd, led_busy, led_heartbeat;
    wire [1:0] led_result;

    assign radio_rxd = radio_txd;   // 回环

    integer errors = 0, guard = 0;

    localparam [95:0] GOLDEN_KEY = 96'h26C4EC61BA319FF325041DEE;
    localparam [95:0] NSA_VECTOR = 96'h1312_1110_0B0A_0908_0302_0100;

    w3_top # (
        .FREQ_HZ   (10_000_000),
        .BAUD      (115_200    ),
        .TIMEOUT_S (0.01       ),
        .MEASURE_CYCLES (32'd64),
        .ENABLE_KEY_DERIVE (1)          // <<< 显式启用（w3_top 默认已改 0 fail-safe）
    ) dut (
        .sys_clk      (sys_clk      ),
        .sys_rst_n    (sys_rst_n    ),
        .radio_txd    (radio_txd    ),
        .radio_rxd    (radio_rxd    ),
        .auth_btn     (auth_btn     ),
        .term_id_sw   (term_id_sw   ),
        .led_busy     (led_busy     ),
        .led_result   (led_result   ),
        .led_heartbeat(led_heartbeat)
    );

    always #50 sys_clk = ~sys_clk;

    initial begin
        repeat (10) @(negedge sys_clk);
        sys_rst_n = 1'b1;
        repeat (10) @(negedge sys_clk);

        // T7-1: 回环 wire 不得悬空
        if (dut.fsm_key_valid === 1'bx || dut.fsm_key_valid === 1'bz) begin
            errors = errors + 1;
            $display("[T7-1 FAIL] 回环 fsm_key_valid 悬空 = %b (P0 未修复)", dut.fsm_key_valid);
        end else
            $display("[T7-1 PASS] 回环 wire 已连接 (fsm_key_valid=%b)", dut.fsm_key_valid);

        // 触发认证（保持过消抖）
        auth_btn = 1'b1;
        guard = 0;
        while (dut.fsm_key_valid !== 1'b1 && guard < 600_000) begin
            @(negedge sys_clk); guard = guard + 1;
        end
        auth_btn = 1'b0;

        // T7-2: 派生完成
        if (dut.fsm_key_valid === 1'b1)
            $display("[T7-2 PASS] w3_top 回环导通: key_valid=1 (%0d 拍)", guard);
        else begin
            errors = errors + 1;
            $display("[T7-2 FAIL] key_valid 未置位 guard=%0d", guard);
        end

        // T7-3: w3_top 层 key_reg = 黄金值
        if (dut.fsm_key_reg === GOLDEN_KEY)
            $display("[T7-3 PASS] w3_top 层 key_reg = 黄金值");
        else begin
            errors = errors + 1;
            $display("[T7-3 FAIL] w3_top key_reg=%h != %h", dut.fsm_key_reg, GOLDEN_KEY);
        end

        // T13: W4-P4 T2 集成——ro_entropy 熵种子必须经 seed_load 装载到
        // c2_counter（模块级 TB 不能替代顶层集成验证，见 P0 教训）。
        // fixture 黄金 boot_seed=0x34F1996F07D25792 -> c2_counter[0]=8'h92
        if (dut.re_seed_valid !== 1'b1) begin
            errors = errors + 1;
            $display("[T13 FAIL] w3_top 级 re_seed_valid 未置位——熵采样未接入");
        end else if (dut.u_fsm.c2_counter[0] !== 8'h92) begin
            errors = errors + 1;
            $display("[T13 FAIL] c2_counter[0]=%h != 8'h92（seed_load 未生效或熵值错）",
                     dut.u_fsm.c2_counter[0]);
        end else if (dut.u_fsm.c2_counter[0] === 8'hA0) begin
            errors = errors + 1;
            $display("[T13 FAIL] c2_counter 仍为默认 A0..A7（P1-5 未闭环）");
        end else
            $display("[T13 PASS] w3_top 级 T2 链路导通: boot_seed=%h -> c2_counter[0]=%h",
                     dut.re_boot_seed, dut.u_fsm.c2_counter[0]);

        // T7-4: FSM 内部 sp_key 不再用公开向量
        if (dut.u_fsm.sp_key === NSA_VECTOR) begin
            errors = errors + 1;
            $display("[T7-4 FAIL] u_fsm.sp_key 仍为公开向量 — P1-1 未达成");
        end else
            $display("[T7-4 PASS] u_fsm.sp_key 已切离公开向量 (%h)", dut.u_fsm.sp_key);

        if (errors == 0) $display("TB_W3TOP_KEYLOOP_PASS");
        else             $display("TB_W3TOP_KEYLOOP_FAIL: %0d 项错误", errors);
        $finish;
    end

    initial begin
        #50_000_000;
        $display("TB_W3TOP_KEYLOOP_FAIL (global watchdog)");
        $finish;
    end
endmodule
