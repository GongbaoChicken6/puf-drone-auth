`timescale 1ns / 1ps
//============================================================================
// tb_demo_led.v — finals-demo N1/N7 灯语模块自校验 testbench
//----------------------------------------------------------------------------
// 时间缩放：FREQ_HZ=10_000（1ms=10 拍），全部阈值保持产品毫秒值不变，
// 用例总时长 ~2.5s 仿真时间（xsim 秒级跑完）。
// 用例：
//   T1 idle      : result=0 → led=00 / buz=0
//   T2 PASS      : 绿闪3次(亮125灭125×3)后常亮——5 个相位检查点+常亮检查
//   T3 REJECT    : 红亮灭闪 2Hz（250ms 切换）——前半亮/后半灭/次周期再亮
//   T4 BLOCKED   : 双亮常亮（原语义不变）
//   T5 busy 沿   : 蜂鸣单短哔 80ms
//   T6 PASS 哔   : 两短哔（80/隔/80）
//   T7 沿复位    : PASS 中途改 REJECT → 闪序计数从 0 重启
//   T8 ext 映射  : ext_led 位序（琥珀,红,绿2,绿1）四态检查
// 变异锚（规约三）：破坏 REJECT 的 rej_blink 相位/极性 → T3 三个检查点必 FAIL；
//                  破坏 PASS 相位翻转 → T2 必 FAIL。
// 看门狗 5000ms > 所有用例等待上限之和（规约一）。
//============================================================================
module tb_demo_led;

    reg         clk    = 1'b0;
    reg         rst_n  = 1'b0;
    reg  [1:0]  result = 2'd0;
    reg         busy   = 1'b0;

    wire [1:0]  led_result;
    wire        led_busy;
    wire [3:0]  ext_led;
    wire        ext_buzzer;

    integer errors = 0;

    // FREQ_HZ=10kHz：TICKS_PER_MS=10 → 1ms = 10 拍（时间缩放核心）
    demo_led # (
        .FLASH_HALF_MS ( 125     ),   // 产品值不变
        .FREQ_HZ       ( 10_000  )    // 降频只为仿真速度
    ) dut (
        .clk        (clk        ),
        .rst_n      (rst_n      ),
        .result_in  (result     ),
        .busy_in    (busy       ),
        .led_result (led_result ),
        .led_busy   (led_busy   ),
        .ext_led    (ext_led    ),
        .ext_buzzer (ext_buzzer )
    );

    // 时钟：1 拍 = 10ns（快跑）。名义时间只依赖「拍数」——DUT 的 1ms =
    // TICKS_PER_MS=FREQ_HZ/1000=10 拍，wait_ms 同口径，与 wall time 无关。
    always #5 clk = ~clk;

    // 事件探针：驱动变化与内部锁存逐事件落日志
    reg [2:0] prev_kind = 3'd0;
    always @(posedge clk) begin
        if (dut.buz_kind != prev_kind) begin
            $display("[EV] t=%0t kind %0d->%0d (result=%0d busy=%b)",
                     $time, prev_kind, dut.buz_kind, result, busy);
            prev_kind <= dut.buz_kind;
        end
    end

    task wait_ms(input integer n);
        begin
            repeat (n * 10) @(posedge clk);   // TICKS_PER_MS=10
        end
    endtask

    task chk(input [1:0] exp_led, input exp_buz, input [127:0] tag);
        begin
            if (led_result !== exp_led || ext_buzzer !== exp_buz) begin
                errors = errors + 1;
                $display("[%0s FAIL] led=%b(exp %b) buz=%b(exp %b) t=%0t",
                         tag, led_result, exp_led, ext_buzzer, exp_buz, $time);
            end else
                $display("  [%0s ok] led=%b buz=%b", tag, led_result, ext_buzzer);
        end
    endtask

    initial begin
        repeat (3) @(posedge clk);
        rst_n = 1'b1;
        repeat (2) @(posedge clk);

        // ---- T1: idle ----
        $display("[..T1] idle");
        @(negedge clk) result = 2'd0; busy = 1'b0;
        wait_ms(10);
        chk(2'd00, 1'b0, "T1-idle");
        if (ext_led !== 4'b0000) begin errors=errors+1; $display("[T1 FAIL] ext=%b", ext_led); end

        // ---- T5: busy 上升沿短哔（0..79ms 响） ----
        $display("[..T5] busy beep");
        @(negedge clk); busy = 1'b1;
        wait_ms(40);  chk(2'd00, 1'b1, "T5-on");    // 40ms < 80 响
        wait_ms(60);  chk(2'd00, 1'b0, "T5-off");   // 100ms > 80 停
        @(negedge clk) busy = 1'b0;

        // ---- T2/T6: PASS 相位（边界 125n: 0..124 亮,125..249 灭,250..374 亮…） ----
        $display("[..T2/T6] PASS flash");
        @(negedge clk) result = 2'd1;
        wait_ms(50);   chk(2'd01, 1'b1, "T2a-p0+b1");  //  50ms: ph0 亮 + 第1哔(0..79)
        wait_ms(125);  chk(2'd00, 1'b0, "T2b-p1");     // 175ms: ph1 灭
        wait_ms(85);   chk(2'd01, 1'b1, "T2c-p2+b2");  // 260ms: ph2 亮 + 第2哔(200..279)
        wait_ms(115);  chk(2'd00, 1'b0, "T2d-p3");     // 375ms: ph3 灭
        wait_ms(125);  chk(2'd01, 1'b0, "T2e-p4");     // 500ms: ph4 亮
        wait_ms(125);  chk(2'd00, 1'b0, "T2f-p5");     // 625ms: ph5 灭
        wait_ms(125);  chk(2'd01, 1'b0, "T2g-p6");     // 750ms: ph6 亮(第二轮,非锁定)
        wait_ms(900);  chk(2'd01, 1'b0, "T2h-hold");   // 1650ms ≥1500: 常亮
        if (ext_led !== 4'b0011) begin errors=errors+1; $display("[T2 FAIL] ext=%b exp 0011", ext_led); end

        // ---- T3: REJECT 2Hz（半周期 250ms；长鸣 0..599） ----
        $display("[..T3] REJECT blink");
        @(negedge clk) result = 2'd2;
        wait_ms(100);  chk(2'd10, 1'b1, "T3-on");      // 100ms: 前半亮 + 长鸣中
        if (ext_led !== 4'b0100) begin errors=errors+1; $display("[T3 FAIL] ext-on=%b exp 0100", ext_led); end
        wait_ms(200);  chk(2'd00, 1'b1, "T3-off");     // 300ms: 后半灭, 仍<600 响
        if (ext_led !== 4'b1000) begin errors=errors+1; $display("[T3 FAIL] ext-off=%b exp 1000(amber)", ext_led); end
        wait_ms(350);  chk(2'd10, 1'b0, "T3-on2");     // 650ms: 次周期亮, 鸣已停
        // R3 P2 回归锁: REJECT 稳态 >2.2s 仍持续翻转(饱和冻结变异必须 FAIL)
        wait_ms(1700); chk(2'd00, 1'b0, "T3-long-f1");   // ~2350ms: 翻转继续
        wait_ms(250);  chk(2'd10, 1'b0, "T3-long-f2");   // ~2600ms: 再翻转回亮
        wait_ms(250);  chk(2'd00, 1'b0, "T3-long-f3");   // ~2850ms: 又翻转回灭

        // ---- T7: 沿复位（PASS 中途切 REJECT,节拍归零） ----
        $display("[..T7] edge reset");
        @(negedge clk) result = 2'd1; wait_ms(100);      // PASS ph0 亮
        @(negedge clk) result = 2'd2;
        wait_ms(100);  chk(2'd10, 1'b1, "T7-restart"); // REJECT ph0 必亮红(继承则绿)

        // ---- T4: BLOCKED 双亮 + ext 全亮 + 双长哔 ----
        $display("[..T4] BLOCKED");
        @(negedge clk) result = 2'd3;
        wait_ms(50);   chk(2'd3, 1'b1, "T4-dual");    // 第1长哔中
        wait_ms(1450); chk(2'd3, 1'b0, "T4-hold");    // 1500ms: 双亮保持,哔已停
        if (ext_led !== 4'b1111) begin errors=errors+1; $display("[T4 FAIL] ext=%b exp 1111", ext_led); end

        // ---- 总结 ----
        repeat (5) @(posedge clk);
        if (errors == 0) $display("TB_DEMO_LED_PASS");
        else             $display("TB_DEMO_LED_FAIL errors=%0d", errors);
        $finish;
    end

    // 看门狗：5000ms 仿真（> 用例等待和 ~3.9s，规约一）
    initial begin
        #500_000_000;
        $display("[WATCHDOG] TIMEOUT");
        $display("TB_DEMO_LED_FAIL errors=%0d (watchdog)", errors);
        $finish;
    end

endmodule
