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
    reg  auth_btn = 1'b0;   // 板级空闲电平（ZC706 SW7 板上实测：空闲0/按下1）
    reg  [7:0] term_id_sw = 8'h01;
    wire radio_txd, radio_rxd, led_busy, led_heartbeat;
    wire [1:0] led_result;

    assign radio_rxd = radio_txd;   // 回环

    integer errors = 0, guard = 0, p0 = 0;
    integer pulse_cnt = 0;   // M3: 认证启动脉冲计数（极性/边沿回归锁）
    reg        kv_seen = 1'b0;   // T13 免竞态采样（auto-review #4）：key_valid 上升已采
    reg [7:0]  c2_snap = 8'h00;  // key_valid 上升后首个 negedge 采到的 c2_counter[0]

    // M3(auto-review): 边沿检测失效/极性回退必被抓；复位值≠空闲电平的不变量
    // 由 T0 的 btn_state 直锁承担（真极性下错复位值只产生下降沿，计数器看不见）
    always @(posedge sys_clk)
        if (sys_rst_n && dut.auth_start_pulse) pulse_cnt = pulse_cnt + 1;

    // T13 免竞态采样（auto-review #4）：c2 推进发生在 key_valid 后下一 posedge
    // （key_valid 同拍进 S_CALC_R2 terminal_fsm.v:889-892，S_CALC_R2 首拍 c2+1
    // :700-702；超时路径 :615-616 只进 S_BLOCKED 不碰 c2）。negedge 采样早于该拍
    // 且 NBA 已沉降 → 必读到装载后未被消费的 0x92，插任意等待不再假 FAIL
    always @(negedge sys_clk) begin
        if (!kv_seen && dut.fsm_key_valid === 1'b1) begin
            kv_seen = 1'b1;
            c2_snap = dut.u_fsm.c2_counter[0];
        end
    end

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

        // T0-early/M3（auto-review #1）：复位值不变量直锁须在消抖收敛点（100k 拍）前
        repeat (10) @(negedge sys_clk);
        if (dut.btn_state !== 1'b0 || dut.btn_prev !== 1'b0) begin
            errors = errors + 1;
            $display("[T0-early FAIL] 复位释放+10拍 btn_state=%b btn_prev=%b（复位值≠空闲电平0）",
                     dut.btn_state, dut.btn_prev);
        end else
            $display("[T0-early PASS] 复位释放+10拍 btn_state=0/btn_prev=0（复位值不变量直锁）");

        // T0/M3: 复位后空闲静默窗 >2×DEBOUNCE_CYCLES（220k 拍，btn=0=板级空闲）
        repeat (220_000) @(negedge sys_clk);
        if (pulse_cnt !== 0 || dut.btn_state !== 1'b0 || dut.btn_prev !== 1'b0) begin
            errors = errors + 1;
            $display("[T0 FAIL] 静默窗触发 ×%0d / btn_state=%b（收敛后仍非空闲/幽灵沿？）",
                     pulse_cnt, dut.btn_state);
        end else
            $display("[T0 PASS] 复位后 220k 拍零触发（静默窗回归锁；复位值锁见 T0-early）");

        // T7-1: 回环 wire 不得悬空
        if (dut.fsm_key_valid === 1'bx || dut.fsm_key_valid === 1'bz) begin
            errors = errors + 1;
            $display("[T7-1 FAIL] 回环 fsm_key_valid 悬空 = %b (P0 未修复)", dut.fsm_key_valid);
        end else
            $display("[T7-1 PASS] 回环 wire 已连接 (fsm_key_valid=%b)", dut.fsm_key_valid);

        // 触发认证（板上实测：空闲0/按下1，0→1 上升沿=按下瞬间触发）
        auth_btn = 1'b1;                       // 按下
        // M3: 按下沿出首个 pulse（消抖 ~100k 拍）
        guard = 0;
        while (pulse_cnt == 0 && guard < 300_000) begin
            @(posedge sys_clk); guard = guard + 1;
        end
        if (pulse_cnt >= 1)
            $display("[T0b PASS] 按下沿触发确认：auth_start_pulse ×%0d", pulse_cnt);
        else begin
            errors = errors + 1;
            $display("[T0b FAIL] 按下沿未触发（%0d 拍内无 pulse）", guard);
        end
        // M3: 消抖下界锁（auto-review #5）
        if (pulse_cnt >= 1 && guard < 99_000) begin
            errors = errors + 1;
            $display("[T0b FAIL] pulse 过早（按下后 %0d 拍 < 消抖 100k）——消抖下界违反", guard);
        end
        guard = 0;
        while (dut.fsm_key_valid !== 1'b1 && guard < 600_000) begin
            @(negedge sys_clk); guard = guard + 1;
        end

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
        end else if (!kv_seen || c2_snap === 8'hA0) begin
            errors = errors + 1;
            $display("[T13 FAIL] c2_snap=%h（仍为默认 A0..A7——P1-5 未闭环/采样未触发）", c2_snap);
        end else if (c2_snap !== 8'h92) begin
            errors = errors + 1;
            $display("[T13 FAIL] c2_snap=%h != 8'h92（seed_load 未生效或熵值错）", c2_snap);
        end else
            $display("[T13 PASS] w3_top 级 T2 链路导通: boot_seed=%h -> c2 装载 8'h92 -> 已消费为 %h",
                     dut.re_boot_seed, dut.u_fsm.c2_counter[0]);

        // T7-4: FSM 内部 sp_key 不再用公开向量
        if (dut.u_fsm.sp_key === NSA_VECTOR) begin
            errors = errors + 1;
            $display("[T7-4 FAIL] u_fsm.sp_key 仍为公开向量 — P1-1 未达成");
        end else
            $display("[T7-4 PASS] u_fsm.sp_key 已切离公开向量 (%h)", dut.u_fsm.sp_key);

        // M3: 按住稳定锁——首个 pulse 后计数不再增长。放在 T13 之后：c2 推进在
        // key_valid 后下一拍（terminal_fsm:700-702，非会话超时），T13 现读免竞态
        // 快照，本段位置不再影响黄金值（2026-10-23 CI 首跑教训 + auto-review #4 重构）
        p0 = pulse_cnt;
        repeat (150_000) @(negedge sys_clk);
        if (pulse_cnt !== p0) begin
            errors = errors + 1;
            $display("[T0c FAIL] 按住期重复触发 +%0d（边沿检测失效？）", pulse_cnt - p0);
        end else
            $display("[T0c PASS] 按住 150k 拍计数不增长（首会话已超时 BLOCKED 仍无新 pulse）");

        // M3: 松开沿负向锁（auto-review #2）：双沿(XOR)退化时松开必出 pulse
        auth_btn = 1'b0;                       // 松开
        p0 = pulse_cnt;
        repeat (120_000) @(negedge sys_clk);   // 过消抖（100k）后仍无新 pulse
        if (pulse_cnt !== p0) begin
            errors = errors + 1;
            $display("[T0d FAIL] 松开沿触发 +%0d（边沿检测退化成双沿？）", pulse_cnt - p0);
        end else
            $display("[T0d PASS] 松开后 120k 拍零触发（松开沿负向锁）");

        if (errors == 0) $display("TB_W3TOP_KEYLOOP_PASS");
        else             $display("TB_W3TOP_KEYLOOP_FAIL: %0d 项错误", errors);
        $finish;
    end

    initial begin
        #160_000_000;   // M10: 最坏线 10+10+220k+300k+600k+150k+120k≈1.39M 拍=139ms（松开沿锁后，留 ~15% 余量）
        $display("TB_W3TOP_KEYLOOP_FAIL (global watchdog: errors=%0d pulse=%0d kv=%b kvseen=%b state=%0d c2snap=%h)",
                 errors, pulse_cnt, dut.fsm_key_valid, kv_seen, dut.u_fsm.state, c2_snap);
        $finish;
    end
endmodule
