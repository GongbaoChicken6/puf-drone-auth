//============================================================================
// w3_top_zc702.v -- ZC702 板级 wrapper（仅综合/实现用，不参与仿真/CI）
//----------------------------------------------------------------------------
// 作用：把 ZC702 的 200MHz 差分时钟（D18/C19, LVDS_25）与 PL 按键复位适配到
//       既有 w3_top；w3_top 端口一并保持不变 -> sim/tb/tb_w3_top.v 与 12/12 CI 全绿。
//
// 注意：
//   1) Clk Wizard IP（clk_wiz_0）不在仓库里 —— 上板前须在 Vivado 工程中生成
//      （200MHz 差分输入 -> 100MHz 输出 + locked），见保姆教程 2.2。
//   2) 本文件不在 ci_regression.ps1 的编译清单内，也不参与仿真。
//   3) ZC702 只有 2 个 PL 侧拨码（W6/W7），terminal_id 高 6 位在此 tie 0。
//============================================================================
module w3_top_zc702 # (
    parameter BAUD      = 115_200,
    parameter TIMEOUT_S = 2
) (
    input  wire        clk_p,          // D18, 200MHz 差分正端 (LVDS_25)
    input  wire        clk_n,          // C19, 200MHz 差分负端 (LVDS_25)
    input  wire        sys_rst_btn_n,  // GPIO_SW_N 按键（低有效）
    input  wire        auth_btn,       // PL 按键（需自行在 XDC 填引脚）
    input  wire [1:0]  term_id_dip,    // W6/W7 —— 仅有的 2 位 PL 拨码
    output wire        radio_txd,
    input  wire        radio_rxd,
    output wire        led_busy,
    output wire [1:0]  led_result,
    output wire        led_heartbeat
);
    // Clk Wizard：200MHz 差分 -> 100MHz 单端 + locked
    wire clk_100m;
    wire mmcm_locked;
    clk_wiz_0 u_mmcm (
        .clk_in1_p (clk_p),
        .clk_in1_n (clk_n),
        .reset     (~sys_rst_btn_n), // IP reset 高有效 <- 按键低有效取反；配合 locked 双保险
        .clk_out1  (clk_100m),
        .locked    (mmcm_locked)
    );

    // 复位组合：按键低有效 AND MMCM 已锁定（锁定前持续复位，按键仍可复位）
    wire rst_n = sys_rst_btn_n & mmcm_locked;

    w3_top # (
        .FREQ_HZ   (100_000_000),
        .BAUD      (BAUD),
        .TIMEOUT_S (TIMEOUT_S)
    ) u_top (
        .sys_clk       (clk_100m),
        .sys_rst_n     (rst_n),
        .radio_txd     (radio_txd),
        .radio_rxd     (radio_rxd),
        .auth_btn      (auth_btn),
        .term_id_sw    ({6'h00, term_id_dip}),   // 高 6 位 tie 0（板上只有 2 位拨码）
        .led_busy      (led_busy),
        .led_result    (led_result),
        .led_heartbeat (led_heartbeat)
    );
endmodule