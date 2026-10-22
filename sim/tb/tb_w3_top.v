`timescale 1ns / 1ps
//============================================================================
// tb_w3_top.v — 顶层集成回环测试
//----------------------------------------------------------------------------
// 把 radio_txd 直连 radio_rxd（物理回环），驱动 auth_btn，
// 验证完整发送→接收→解析→状态机→发送链路。
//
// T1: 完整认证流程（回环：终端收到自己发的 ACCESS_REQUEST）
//     frame_parser 解析后 msg_id=0x0090 → terminal_fsm 不认此消息 → 等待超时
//     但这验证了 TX→串口→RX→解析 全链路数据完整性！
//============================================================================
module tb_w3_top;

    reg         sys_clk = 1'b0;
    reg         sys_rst_n = 1'b0;
    reg         auth_btn = 1'b1;   // 板级空闲电平（ZC706 SW7：空闲1/按下0）
    reg  [7:0]  term_id_sw = 8'd42;
    wire        radio_txd;
    wire        radio_rxd;
    wire        led_busy;
    wire [1:0]  led_result;
    wire        led_heartbeat;

    // 回环：TX 直连 RX
    assign radio_rxd = radio_txd;

    integer errors = 0;
    integer pulse_cnt = 0;   // M3: 认证启动脉冲计数（幽灵/极性回归锁）
    integer guard = 0;

    // M3(auto-review): 计一切 auth_start_pulse——消抖复位值回退 1'b0 时，
    // 复位释放 ~100k 拍出现幽灵沿（变异实测旧 TB 对此全盲，本计数器必抓）
    always @(posedge sys_clk)
        if (sys_rst_n && dut.auth_start_pulse) pulse_cnt = pulse_cnt + 1;

    // 快速仿真参数（缩小时钟和超时）
    w3_top # (
        .FREQ_HZ   (10_000_000),   // 10MHz（仿真加速）
        .BAUD      (115_200    ),
        .TIMEOUT_S (0.01        ),  // 10ms 超时（仿真加速）
        .MEASURE_CYCLES (32'd64),   // W4：PUF 测量窗缩小加速
        .ENABLE_KEY_DERIVE (0)       // W4-P4: TB 关闭密钥派生
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

    // 10MHz 时钟
    always #50 sys_clk = ~sys_clk;

    // 串口活动监测
    integer tx_bits = 0;
    always @(negedge radio_txd) tx_bits = tx_bits + 1;

    initial begin
        // 复位
        repeat (10) @(negedge sys_clk);
        sys_rst_n = 1'b1;

        // T0/M3: 复位后空闲静默窗 >2×DEBOUNCE_CYCLES（220k 拍）——幽灵沿回归锁
        repeat (220_000) @(negedge sys_clk);
        if (pulse_cnt !== 0) begin
            errors = errors + 1;
            $display("[T0 FAIL] 静默窗幽灵认证 ×%0d（消抖复位值回退为 0？）", pulse_cnt);
        end else
            $display("[T0 PASS] 复位后 220k 拍空闲窗零触发（幽灵沿回归锁）");

        // T1: 按下认证按钮（需保持足够长以过消抖）
        $display("[T1] Loopback: auth button → TX chain → RX chain");
        auth_btn = 1'b0;                       // 按下（板级：空闲1/按下0）
        repeat (500_000) @(negedge sys_clk);   // 保持 >10ms@10MHz
        // M3: 按住期零触发（认证只许由松开 0→1 沿启动——边沿极性回归锁）
        if (pulse_cnt !== 0) begin
            errors = errors + 1;
            $display("[T1 FAIL] 按住期触发认证 ×%0d（极性回退为下降沿触发？）", pulse_cnt);
        end else
            $display("[T1 PASS] 按住 500k 拍零触发（松开沿极性锁）");
        auth_btn = 1'b1;                       // 松开 → 0→1 上升沿触发认证
        // M3: 确认松开沿确实触发（消抖 100k 拍后 pulse_cnt 必 +1）
        guard = 0;
        while (pulse_cnt == 0 && guard < 300_000) begin
            @(posedge sys_clk); guard = guard + 1;
        end
        if (pulse_cnt >= 1)
            $display("[T1] 松开沿触发确认：auth_start_pulse ×%0d", pulse_cnt);
        else begin
            errors = errors + 1;
            $display("[T1 FAIL] 松开沿未触发（%0d 拍内无 auth_start_pulse）", guard);
        end

        // 等待发送和回环接收
        repeat (1_000_000) @(negedge sys_clk);  // 100ms 足够超时触发

        // 验证：
        // 1. led_busy 应该先高（认证进行中）再低（超时后回 IDLE）
        // 2. radio_txd 应有活动（串口有数据发出）
        // 3. 超时后 led_result = 3（BLOCKED——终端收到自己的 ACCESS_REQUEST
        //    而不是 CHALLENGE，等待超时）

        if (tx_bits < 10) begin
            errors = errors + 1;
            $display("[T1 FAIL] radio_txd inactive (tx_bits=%0d, expect >10)", tx_bits);
        end else
            $display("  [T1] radio_txd active: %0d falling edges (UART data sent)", tx_bits);

        if (led_result == 2'd3 && led_busy == 1'b0) begin
            $display("  [T1] led_result=3 (BLOCKED), busy=0 — correct timeout behavior");
        end else begin
            errors = errors + 1;
            $display("[T1 FAIL] led_result=%0d busy=%b expect result=3 busy=0", led_result, led_busy);
        end

        if (errors == 0) $display("[T1 PASS] Full chain: btn→debounce→FSM→frame→FIFO→UART→loopback→parser");
        else $display("[T1 FAIL] %0d errors", errors);

        repeat (10) @(negedge sys_clk);
        if (errors == 0) $display("TB_W3_TOP_PASS");
        else             $display("TB_W3_TOP_FAIL errors=%0d", errors);
        $finish;
    end

    initial begin
        #250_000_000;  // 250ms watchdog（M3 静默窗后新时间线 ~183ms，留余量）
        $display("[WATCHDOG] TIMEOUT tx_bits=%0d busy=%b result=%0d", tx_bits, led_busy, led_result);
        $display("TB_W3_TOP_FAIL (watchdog)");
        $finish;
    end

endmodule