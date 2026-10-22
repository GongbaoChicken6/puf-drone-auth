`timescale 1ns / 1ps
//============================================================================
// tb_w3_top_seedgate.v -- M1(auto-review): SEED_GATE_EN 双向仿真锁定
//----------------------------------------------------------------------------
// 背景：板上唯一运行配置（w3_top_zc706 传 SEED_GATE_EN=0）曾零仿真覆盖，
// 旁路表达式若写反则 CI 全绿、板上复现"按键无反应"同型故障。三 DUT 结构：
//   DUT-A 旁路(0) + 熵未完成（ENTROPY_CYCLES 放大 → 卡 E_SAMPLE，
//        re_seed_valid 恒 0）→ 断言按键仍放行（板级修复核心主张）+ 完整链路
//        超时到 BLOCKED
//   DUT-B 门控(1) + 熵未完成 → 断言认证被永久压制（C-F2/P1-5 fail-closed
//        方向：FSM 停 S_IDLE、零脉冲、零 TX）
//   DUT-C 旁路(0) + 零熵被拒（force 熵阵列频率低 4 位全 0 → ro_entropy
//        E_DONE 拒绝）→ 断言 seed_fault=1 独立故障口 + 心跳快闪编码 +
//        认证仍放行。集成覆盖 ro_entropy.v 零熵分支（板故根因嫌疑的
//        仿真复现锁：该分支被删除时 T6 必失败）
// 附带 M3 锁：复位后静默窗无幽灵认证；按住期零触发（仅松开沿）。
//============================================================================
module tb_w3_top_seedgate;

    reg  sys_clk = 1'b0;
    reg  rst_n   = 1'b0;
    reg  btn_a = 1'b1, btn_b = 1'b1, btn_c = 1'b1;   // 板级空闲电平（空闲1/按下0）
    wire txd_a, txd_b, txd_c;
    wire busy_a, busy_b, busy_c;
    wire [1:0] res_a, res_b, res_c;
    wire hb_a, hb_b, hb_c;

    //---------------- DUT-A: 旁路 + 熵未完成 ----------------//
    w3_top # (
        .FREQ_HZ        (10_000_000    ),
        .BAUD           (115_200       ),
        .TIMEOUT_S      (0.01          ),
        .SEED_GATE_EN   (0             ),   // 板级 bring-up 配置
        .ENTROPY_CYCLES (32'hFFFF_FFFF )    // 采样窗 >> 仿真时长 → 卡 E_SAMPLE
    ) dut_a (
        .sys_clk(sys_clk), .sys_rst_n(rst_n),
        .radio_txd(txd_a), .radio_rxd(txd_a),          // 回环
        .auth_btn(btn_a), .term_id_sw(8'd1),
        .led_busy(busy_a), .led_result(res_a), .led_heartbeat(hb_a)
    );

    //---------------- DUT-B: 门控开启 + 熵未完成 ----------------//
    w3_top # (
        .FREQ_HZ        (10_000_000    ),
        .BAUD           (115_200       ),
        .TIMEOUT_S      (0.01          ),
        .SEED_GATE_EN   (1             ),   // 默认门控（CI 原语义）
        .ENTROPY_CYCLES (32'hFFFF_FFFF )
    ) dut_b (
        .sys_clk(sys_clk), .sys_rst_n(rst_n),
        .radio_txd(txd_b), .radio_rxd(txd_b),
        .auth_btn(btn_b), .term_id_sw(8'd2),
        .led_busy(busy_b), .led_result(res_b), .led_heartbeat(hb_b)
    );

    //---------------- DUT-C: 旁路 + 零熵被拒 ----------------//
    w3_top # (
        .FREQ_HZ        (10_000_000    ),
        .BAUD           (115_200       ),
        .TIMEOUT_S      (0.01          ),
        .SEED_GATE_EN   (0             ),
        .ENTROPY_CYCLES (32'd100_000   )    // 正常走完采样窗（100k 拍）
    ) dut_c (
        .sys_clk(sys_clk), .sys_rst_n(rst_n),
        .radio_txd(txd_c), .radio_rxd(txd_c),
        .auth_btn(btn_c), .term_id_sw(8'd3),
        .led_busy(busy_c), .led_result(res_c), .led_heartbeat(hb_c)
    );

    always #50 sys_clk = ~sys_clk;    // 10MHz

    //---------------- 认证启动脉冲计数（M3 幽灵/极性锁）----------------//
    integer pulse_a = 0, pulse_b = 0, pulse_c = 0;
    always @(posedge sys_clk) begin
        if (rst_n) begin
            if (dut_a.auth_start_pulse) pulse_a = pulse_a + 1;
            if (dut_b.auth_start_pulse) pulse_b = pulse_b + 1;
            if (dut_c.auth_start_pulse) pulse_c = pulse_c + 1;
        end
    end

    integer errors = 0, guard = 0;

    initial begin
        // T6 前置：DUT-C 零熵注入——force 熵阵列锁存频率低 4 位全 0
        // （16×0x1000 → seed_acc 低 4 位全 0 → E_DONE 零熵拒绝路径）
        force dut_c.u_ro_entropy_array.latch_freqs = {16{16'h1000}};

        repeat (10) @(negedge sys_clk);
        rst_n = 1'b1;

        // T1: 复位后空闲静默窗 >2×DEBOUNCE_CYCLES（220k 拍）
        //     消抖复位值若回退 1'b0，第 ~100k 拍必现幽灵沿，pulse 不再为 0
        repeat (220_000) @(negedge sys_clk);
        if (pulse_a !== 0 || pulse_b !== 0 || pulse_c !== 0) begin
            errors = errors + 1;
            $display("[T1 FAIL] 静默窗幽灵认证: A=%0d B=%0d C=%0d（消抖复位值回退？）",
                     pulse_a, pulse_b, pulse_c);
        end else
            $display("[T1 PASS] 复位后 220k 拍空闲窗三 DUT 零触发（幽灵沿回归锁）");

        // T6: DUT-C 熵窗（100k 拍）已过 → 零熵被拒：故障口 + fail-closed
        if (dut_c.re_seed_fault !== 1'b1 || dut_c.re_seed_valid !== 1'b0) begin
            errors = errors + 1;
            $display("[T6 FAIL] 零熵场景 seed_fault=%b seed_valid=%b（期望 1/0；fail-closed 检查被删？）",
                     dut_c.re_seed_fault, dut_c.re_seed_valid);
        end else
            $display("[T6 PASS] 零熵被拒: seed_fault=1 + seed_valid=0（ro_entropy:102 集成锁定）");

        // T9: 心跳故障编码（快闪）与正常模式（慢闪）
        if (dut_c.led_heartbeat !== dut_c.hb_cnt[24]) begin
            errors = errors + 1;
            $display("[T9 FAIL] 故障心跳未切快闪（seed_fault 观测出口失效）");
        end else
            $display("[T9 PASS] 零熵心跳=hb_cnt[24]（~3Hz 快闪，板上可直接观测）");
        if (dut_b.led_heartbeat !== dut_b.hb_cnt[26]) begin
            errors = errors + 1;
            $display("[T9b FAIL] 无故障心跳模式错误（应为 hb_cnt[26]）");
        end else
            $display("[T9b PASS] 正常心跳=hb_cnt[26]（0.75Hz）");

        // T2: 三 DUT 同时按下（1→0），按住期零触发（仅松开沿极性锁）
        btn_a = 1'b0; btn_b = 1'b0; btn_c = 1'b0;
        repeat (150_000) @(negedge sys_clk);
        if (pulse_a !== 0 || pulse_b !== 0 || pulse_c !== 0) begin
            errors = errors + 1;
            $display("[T2 FAIL] 按住期触发: A=%0d B=%0d C=%0d（边沿极性回退？）",
                     pulse_a, pulse_b, pulse_c);
        end else
            $display("[T2 PASS] 按住 150k 拍三 DUT 零触发（松开沿极性锁）");

        // T3/T5/T8: 松开（0→1 上升沿）
        btn_a = 1'b1; btn_b = 1'b1; btn_c = 1'b1;

        // 旁路侧（A/C）应放行：轮询认证启动
        guard = 0;
        while ((pulse_a == 0 || pulse_c == 0) && guard < 400_000) begin
            @(posedge sys_clk); guard = guard + 1;
        end
        if (pulse_a >= 1)
            $display("[T3 PASS] 旁路+熵未完成: 按键放行（auth_start ×%0d）", pulse_a);
        else begin
            errors = errors + 1;
            $display("[T3 FAIL] 旁路未放行——板级修复核心主张被证伪");
        end
        if (pulse_c >= 1)
            $display("[T8 PASS] 旁路+零熵被拒: 按键仍放行（auth_start ×%0d）", pulse_c);
        else begin
            errors = errors + 1;
            $display("[T8 FAIL] 零熵+旁路下未放行");
        end

        // 门控侧（B）应压制：再等 150k 拍确认 fail-closed 锁定
        repeat (150_000) @(negedge sys_clk);
        if (pulse_b == 0 && busy_b === 1'b0 && dut_b.u_fsm.state === 4'd0)
            $display("[T5 PASS] 门控开启+熵未完成: 认证被压制（FSM 停 S_IDLE，P1-5 fail-closed 锁定）");
        else begin
            errors = errors + 1;
            $display("[T5 FAIL] 门控未压制: pulse_b=%0d busy=%b state=%0d",
                     pulse_b, busy_b, dut_b.u_fsm.state);
        end

        // T3b: 旁路下完整链路：DUT-A 超时到 BLOCKED（result=3）
        guard = 0;
        while (!(res_a == 2'd3 && busy_a == 1'b0) && guard < 500_000) begin
            @(posedge sys_clk); guard = guard + 1;
        end
        if (res_a == 2'd3 && busy_a == 1'b0)
            $display("[T3b PASS] 旁路下完整链路: 超时→BLOCKED（result=3, busy=0）");
        else begin
            errors = errors + 1;
            $display("[T3b FAIL] 旁路链路未到 BLOCKED: res_a=%0d busy=%b guard=%0d",
                     res_a, busy_a, guard);
        end

        if (errors == 0) $display("TB_W3_TOP_SEEDGATE_PASS");
        else             $display("TB_W3_TOP_SEEDGATE_FAIL: %0d 项错误", errors);
        $finish;
    end

    // 看门狗：最坏时间线 ~10+220k+150k+400k+150k+500k ≈ 1.43M 拍 = 143ms
    initial begin
        #250_000_000;
        $display("TB_W3_TOP_SEEDGATE_FAIL (global watchdog: pA=%0d pB=%0d pC=%0d fault=%b)",
                 pulse_a, pulse_b, pulse_c, dut_c.re_seed_fault);
        $finish;
    end

endmodule
