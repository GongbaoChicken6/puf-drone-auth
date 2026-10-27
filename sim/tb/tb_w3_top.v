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
    reg         auth_btn = 1'b0;   // 板级空闲电平（ZC706 SW7 板上实测：空闲0/按下1）
    reg  [7:0]  term_id_sw = 8'd42;
    wire        radio_txd;
    wire        radio_rxd;
    wire        led_busy;
    wire [1:0]  led_result;
    wire        led_heartbeat;

    // 回环：TX 直连 RX
    assign radio_rxd = radio_txd;

    integer errors = 0;
    integer pulse_cnt = 0;   // M3: 认证启动脉冲计数（极性/边沿回归锁）
    integer guard = 0;
    integer p0 = 0;          // M3: 按住稳定锁快照（首 pulse 后计数不增长）

    // M3(auto-review): 计一切 auth_start_pulse——边沿检测失效/极性回退时必被抓
    // （复位值≠空闲电平的不变量由 T0 的 btn_state 直锁承担：真极性下复位值
    //  错成 1 只产生下降沿，本计数器看不见，必须直查 btn_state）
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

    // RX 正向证据（2026-10-27 补）：数 uart_rx 的 rx_valid 脉冲。
    // 背景：原判据只看 TX 活动 + 超时 BLOCKED——uart_rx 整个挂死时
    // 同样超时进 BLOCKED，判据对 RX 死亡失明（真硅片 0 字节两天才定位）。
    integer rx_valid_cnt = 0;
    always @(posedge sys_clk) if (dut.u_rx.rx_valid) rx_valid_cnt = rx_valid_cnt + 1;
    // 审查加固（auto-review 2026-10-27）：TX 侧 done 计数——回环下 RX 必须逐字节等于 TX
    integer tx_done_cnt = 0;
    always @(posedge sys_clk) if (dut.u_tx.tx_done) tx_done_cnt = tx_done_cnt + 1;

    initial begin
        // 复位
        repeat (10) @(negedge sys_clk);
        sys_rst_n = 1'b1;

        // T0-early/M3（auto-review #1）：复位值=空闲电平不变量必须在消抖收敛点
        // （DEBOUNCE_CYC=100k 拍）之前直查——晚于该点，错误复位值已自愈为 0
        repeat (10) @(negedge sys_clk);
        if (dut.btn_state !== 1'b0 || dut.btn_prev !== 1'b0) begin
            errors = errors + 1;
            $display("[T0-early FAIL] 复位释放+10拍 btn_state=%b btn_prev=%b（复位值≠空闲电平0）",
                     dut.btn_state, dut.btn_prev);
        end else
            $display("[T0-early PASS] 复位释放+10拍 btn_state=0/btn_prev=0（复位值=空闲电平不变量直锁）");

        // T0/M3: 复位后空闲静默窗 >2×DEBOUNCE_CYCLES（220k 拍，btn=0=板级空闲）
        //        （静默零触发+收敛后状态；复位真值锁在 T0-early）
        repeat (220_000) @(negedge sys_clk);
        if (pulse_cnt !== 0 || dut.btn_state !== 1'b0 || dut.btn_prev !== 1'b0) begin
            errors = errors + 1;
            $display("[T0 FAIL] 静默窗触发 ×%0d / btn_state=%b（收敛后仍非空闲/幽灵沿？）",
                     pulse_cnt, dut.btn_state);
        end else
            $display("[T0 PASS] 复位后 220k 拍零触发（静默窗回归锁；复位值锁见 T0-early）");

        // T1: 按下认证按钮（板上实测按下=1；0→1 上升沿=按下瞬间触发）
        $display("[T1] Loopback: auth button → TX chain → RX chain");
        auth_btn = 1'b1;                       // 按下（板上：空闲0/按下1）
        // M3: 确认按下沿确实触发（消抖 ~100k 拍后 pulse_cnt 必 +1）
        guard = 0;
        while (pulse_cnt == 0 && guard < 300_000) begin
            @(posedge sys_clk); guard = guard + 1;
        end
        if (pulse_cnt >= 1)
            $display("[T1] 按下沿触发确认：auth_start_pulse ×%0d", pulse_cnt);
        else begin
            errors = errors + 1;
            $display("[T1 FAIL] 按下沿未触发（%0d 拍内无 auth_start_pulse）", guard);
        end
        // M3: 消抖下界锁（auto-review #5）——pulse 不得早于按下+~DEBOUNCE_CYC(100k) 拍
        if (pulse_cnt >= 1 && guard < 99_000) begin
            errors = errors + 1;
            $display("[T1 FAIL] pulse 过早（按下后 %0d 拍 < 消抖 100k）——消抖下界违反", guard);
        end
        // M3: 按住稳定锁——首个 pulse 后计数不再增长（边沿触发=单拍语义）
        p0 = pulse_cnt;
        repeat (220_000) @(negedge sys_clk);
        if (pulse_cnt !== p0) begin
            errors = errors + 1;
            $display("[T1 FAIL] 按住期重复触发 +%0d（边沿检测失效？）", pulse_cnt - p0);
        end else
            $display("[T1 PASS] 按住 220k 拍计数不增长（按下沿单触发锁）");

        // M3: 松开沿负向锁（auto-review #2）：松开产生 1→0 下降沿——边沿检测退化成
        // 双沿(XOR)时此处必出 pulse（极性重写时旧 TB 的对称方向锁丢失，本段补回）
        auth_btn = 1'b0;                       // 松开
        p0 = pulse_cnt;
        repeat (150_000) @(negedge sys_clk);   // 过消抖（100k）后仍无新 pulse
        if (pulse_cnt !== p0) begin
            errors = errors + 1;
            $display("[T1 FAIL] 松开沿触发 +%0d（边沿检测退化成双沿？）", pulse_cnt - p0);
        end else
            $display("[T1 PASS] 松开后 150k 拍零触发（松开沿负向锁）");

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

        // RX 正向锁（2026-10-27 审查加固版）：TX/RX 等价锁——回环同 CPB 下
        // 每个发出的字节必须被收到（不多不少），并保留 TX 活性下界防"双零假过"。
        if (tx_done_cnt < 20) begin
            errors = errors + 1;
            $display("[T1 FAIL] TX dead: tx_done_cnt=%0d expect >=20", tx_done_cnt);
        end else if (rx_valid_cnt !== tx_done_cnt) begin
            errors = errors + 1;
            $display("[T1 FAIL] RX mismatch: rx_valid_cnt=%0d != tx_done_cnt=%0d (uart_rx hang/drop/extra!)", rx_valid_cnt, tx_done_cnt);
        end else
            $display("  [T1] rx==tx==%0d (loopback frame fully received, no loss/extra)", rx_valid_cnt);

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
        #250_000_000;  // 250ms watchdog（极性回退+松开沿锁后最坏 ~189ms，留余量）
        $display("[WATCHDOG] TIMEOUT tx_bits=%0d busy=%b result=%0d", tx_bits, led_busy, led_result);
        $display("TB_W3_TOP_FAIL (watchdog)");
        $finish;
    end

endmodule