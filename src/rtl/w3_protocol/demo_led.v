`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Design Name: bawan-yhy
// Module Name: demo_led
// Description: 
//  决赛演示灯语增强（finals-demo N1/N7）。消费 terminal_fsm 的 auth_result 码，
//  生成 1 米外可辨认的 LED 闪烁模式 + PMOD J58 外接大灯/蜂鸣器驱动：
//    0 进行中 : 全灭；busy 上升沿蜂鸣短哔一声（认证开始）
//    1 PASS   : 绿灯快闪 3 次（125ms 亮/125ms 灭）后常亮；蜂鸣两短哔
//    2 REJECT : led_result 在 2'd2/2'd0 间 2Hz 切换（红亮灭闪，非红绿交替）；
//                蜂鸣 600ms 长鸣
//    3 BLOCKED: 红绿双亮（保持既有语义）；蜂鸣双长哔
//  纯函数于 result_in + 自由计数器：result 变化沿复位闪序计数，无独立 FSM；
//  不改 terminal_fsm（18 个既有 TB 语义不动）。引脚见 w3_top_zc706.xdc。
//////////////////////////////////////////////////////////////////////////////////

module demo_led # (
    parameter FLASH_HALF_MS = 125          ,   // 半闪周期(ms)：亮/灭各 125ms
    parameter FREQ_HZ       = 100_000_000      // 系统时钟(Hz)，用于推导 ms tick
  )
  (
    input                   clk         ,   // 系统时钟
    input                   rst_n       ,   // 低有效同步复位

    // -- 待增强的原始信号（来自 w3_top 直连 terminal_fsm） ------------------
    input      [1:0]        result_in   ,   // 0进行中 1PASS 2REJECT 3BLOCKED
    input                   busy_in     ,   // 认证进行中（透传 + 上升沿触发短哔）

    // -- 板载 LED（增强后） --------------------------------------------------
    output     [1:0]        led_result  ,   // DS8/DS10（亮=高，01绿 10红 11双）
    output                   led_busy   ,   // DS9 透传

    // -- N7 外接 PMOD J58 大灯/蜂鸣器（3.3V 侧，经 TXS0108E） ----------------
    output     [3:0]        ext_led     ,   // 绿1/绿2/红/琥珀
    output                   ext_buzzer     // 蜂鸣器（高=响）
  );

    //========================================================================
    // 参数推导（单点 FREQ_HZ；ms tick 与闪序节拍全部由此换算）
    //========================================================================
    localparam           TICKS_PER_MS = FREQ_HZ / 1000;              // 100_000
    localparam           REJECT_HALF  = FLASH_HALF_MS * 2;            // 250ms：2Hz 亮灭
    localparam           PASS_FLASHES = 6;                            // 3 闪 = 6 个半周期
    localparam           BUZ_WIN_MS   = 1500;                         // 蜂鸣序列窗(ms)

    localparam  [2:0]    BZ_NONE  = 3'd0  ,                            // 无蜂鸣
                       BZ_SHORT = 3'd1  ,                            // busy 沿：80ms 单哔
                       BZ_PASS  = 3'd2  ,                            // PASS：两短哔
                       BZ_LONG  = 3'd3  ,                            // REJECT：600ms 长鸣
                       BZ_DLONG = 3'd4;                              // BLOCKED：双长哔

    //========================================================================
    // 内部计数器（声明初值 + 同步复位双保险；GSR 上电即确定）
    //========================================================================
    reg  [16:0]  tick_cnt     = 17'd0;    // 0..TICKS_PER_MS-1 → 1ms tick
    reg          ms_tick      = 1'b0;     // 单拍 ms 脉冲
    reg  [10:0]  flash_ms     = 11'd0;    // result 沿以来的 ms 数（闪序节拍）
    reg  [10:0]  buz_ms       = 11'd0;    // 蜂鸣序列以来的 ms 数
    reg  [2:0]   buz_kind     = BZ_NONE;  // 当前蜂鸣序列种类

    reg  [1:0]   result_d     = 2'd0;     // result_in 打一拍（沿检测）
    reg          busy_d       = 1'b0;     // busy_in 打一拍（沿检测）

    wire         result_rise  = (result_in != result_d);              // 任意变化沿（新一轮判决）
    wire         busy_rise    = busy_in & ~busy_d;                    // 认证开始沿

    always @(posedge clk) begin
        if (!rst_n) begin
            tick_cnt <= 17'd0;
            ms_tick  <= 1'b0;
            flash_ms <= 11'd0;
            buz_ms   <= 11'd0;
            buz_kind <= BZ_NONE;
            result_d <= 2'd0;
            busy_d   <= 1'b0;
        end else begin
            result_d <= result_in;
            busy_d   <= busy_in;

            // 1ms tick 生成
            ms_tick <= 1'b0;
            if (tick_cnt >= TICKS_PER_MS - 1) begin
                tick_cnt <= 17'd0;
                ms_tick  <= 1'b1;
            end else begin
                tick_cnt <= tick_cnt + 17'd1;
            end

            // 闪序节拍：result 变化沿立即清零（新一轮从头闪）
            if (result_rise)
                flash_ms <= 11'd0;
            else if (ms_tick && flash_ms < 11'h7FF)
                flash_ms <= flash_ms + 11'd1;

            // 蜂鸣序列：沿触发锁种类，窗内计时，窗满自动熄
            if (busy_rise) begin
                buz_kind <= BZ_SHORT;
                buz_ms   <= 11'd0;
            end else if (result_rise) begin
                case (result_in)
                    2'd1:    begin buz_kind <= BZ_PASS;  buz_ms <= 11'd0; end
                    2'd2:    begin buz_kind <= BZ_LONG;  buz_ms <= 11'd0; end
                    2'd3:    begin buz_kind <= BZ_DLONG; buz_ms <= 11'd0; end
                    default: begin buz_kind <= BZ_NONE;  buz_ms <= 11'd0; end
                endcase
            end else if (ms_tick) begin
                if (buz_ms >= BUZ_WIN_MS)
                    buz_kind <= BZ_NONE;                       // 窗满：序列结束
                else
                    buz_ms <= buz_ms + 11'd1;
            end
        end
    end

    //========================================================================
    // 灯语组合（纯函数于 result_in + flash_ms）
    //========================================================================
    // PASS 相位：0,2,4 亮 / 1,3,5 灭 / >=6 常亮 → phase[0]==0 || phase>=6
    wire [10:0]  pass_phase   = flash_ms / FLASH_HALF_MS;
    wire         pass_lit     = (pass_phase >= PASS_FLASHES) || (~pass_phase[0] && (pass_phase < PASS_FLASHES));

    // REJECT 2Hz：独立翻转节拍（R3 P2 修复：不依赖 flash_ms——11 位饱和后
    // 2047/250=8 偶数会冻结 rej_blink 为常亮。改用专用 1 位翻转 + 独立
    // 半周期计数器，永不冻结。）
    reg  [7:0]   rej_half_cnt = 8'd0;    // 0..REJECT_HALF-1（250ms 需 8 位）
    reg          rej_blink_r  = 1'b1;    // 当前半周期亮/灭
    always @(posedge clk) begin
        if (!rst_n) begin
            rej_half_cnt <= 8'd0;
            rej_blink_r  <= 1'b1;
        end else if (result_rise) begin
            rej_half_cnt <= 8'd0;
            rej_blink_r  <= 1'b1;          // 新判决从头亮
        end else if (ms_tick) begin
            if (rej_half_cnt >= REJECT_HALF - 1) begin
                rej_half_cnt <= 8'd0;
                rej_blink_r  <= ~rej_blink_r;  // 翻转
            end else begin
                rej_half_cnt <= rej_half_cnt + 8'd1;
            end
        end
    end
    wire         rej_blink    = rej_blink_r;

    reg  [1:0]   led_result_r;
    always @* begin
        case (result_in)
            2'd1:    led_result_r = pass_lit ? 2'd1 : 2'd0;   // 绿闪3后常亮
            2'd2:    led_result_r = rej_blink ? 2'd2 : 2'd0;  // 红亮灭闪
            2'd3:    led_result_r = 2'd3;                     // 双亮(原语义)
            default: led_result_r = 2'd0;                     // 进行中/未判：灭
        endcase
    end

    //========================================================================
    // 外接大灯映射（N7）：绿×2 跟板载绿；红跟板载红；琥珀=BLOCKED 常亮/REJECT 交替
    //========================================================================
    wire [3:0]   ext_led_r = { (result_in == 2'd3) || ((result_in == 2'd2) && ~rej_blink),   // 琥珀
                               led_result_r[1]                 ,                              // 红
                               led_result_r[0]                 ,                              // 绿2
                               led_result_r[0]                 };                             // 绿1

    //========================================================================
    // 蜂鸣组合（查表式：种类 × ms 区间）
    //========================================================================
    reg          ext_buzzer_r;
    always @* begin
        case (buz_kind)
            BZ_SHORT:  ext_buzzer_r = (buz_ms < 11'd80);                                        // 短哔
            BZ_PASS:   ext_buzzer_r = (buz_ms < 11'd80) || ((buz_ms >= 11'd200) && (buz_ms < 11'd280));  // 两短
            BZ_LONG:   ext_buzzer_r = (buz_ms < 11'd600);                                       // 长鸣
            BZ_DLONG:  ext_buzzer_r = (buz_ms < 11'd600) || ((buz_ms >= 11'd800) && (buz_ms < 11'd1400)); // 双长
            default:   ext_buzzer_r = 1'b0;
        endcase
    end

    //---------------- 输出（内部 reg/wire + assign 出端口） ----------------
    assign  led_result  = led_result_r;
    assign  led_busy    = busy_in;
    assign  ext_led     = ext_led_r;
    assign  ext_buzzer  = ext_buzzer_r;

endmodule
