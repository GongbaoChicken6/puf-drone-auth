//============================================================================
// w3_top.v -- W3 顶层集成模块（ZC702 上板入口）
//----------------------------------------------------------------------------
// 例化全部 W3 通信栈模块并互连，提供板级接口：
//   时钟/复位 → terminal_fsm ↔ mavlink_frame ↔ byte_fifo ↔ uart_tx → 电台
//              frame_parser ← uart_rx ← 电台
//
// 契约 §6.2 板级前置全部满足：
//   - FREQ_HZ 单点参数推导 CLKS_PER_BIT 和 PARSER_TIMEOUT（禁止散落硬编码）
//   - 复位同步器：异步断言/同步释放（2FF）
//   - LED 心跳：实证时钟频率
//   - UART 引脚：radio_txd/radio_rxd（XDC 待板级连接确认后填入）
//
// PUF：W3 桩（terminal_fsm 内部种子直通）。W4 集成 ro_array 时：
//   1. 在此例化 ro_array + challenge_decode
//   2. 替换 terminal_fsm 的 S_PROC_SEEDS 为真实测量调用
//   3. 添加 w2_waiver.xdc 组合环豁免
//============================================================================

module w3_top # (
    parameter FREQ_HZ       = 100_000_000 ,  // 系统时钟（ZC702 PL 侧）
    parameter BAUD          = 115_200     ,  // UART 波特率
    parameter TIMEOUT_S     = 2             // 协议超时（秒，契约 §5 建议 2s）
) (
    input  wire        sys_clk      ,   // 系统时钟（100MHz，XDC 约束待填）
    input  wire        sys_rst_n    ,   // 复位按键（低有效，需消抖）

    // UART 连电台
    output wire        radio_txd    ,   // UART TX → 电台 RX
    input  wire        radio_rxd    ,   // UART RX ← 电台 TX

    // 控制
    input  wire        auth_btn     ,   // 认证启动按键（需消抖）
    input  wire [7:0]  term_id_sw   ,   // 终端 ID（拨码开关或常量）

    // 状态 LED
    output wire        led_busy     ,   // 认证进行中
    output wire [1:0]  led_result   ,   // 01=通过 10=拒绝 11=阻断
    output wire        led_heartbeat    // ~0.75Hz 时钟心跳（hb_cnt[26] @100MHz）
);

    //========================================================================
    // 参数推导（契约 §6.2：单点 FREQ_HZ，禁止散落硬编码）
    //========================================================================
    localparam CLKS_PER_BIT   = FREQ_HZ / BAUD;          // 868 @100M/115.2k
    localparam TIMEOUT_CYCLES = TIMEOUT_S * FREQ_HZ;      // 2s @100MHz
    localparam PARSER_TIMEOUT = FREQ_HZ / 10;             // 100ms 字节间超时
    localparam DEBOUNCE_CYC   = FREQ_HZ / 100;            // 10ms 按键消抖

    //========================================================================
    // 复位同步器（异步断言/同步释放，契约 §6.2）
    // sys_rst_n 低有效 → 内部 rst 高有效同步复位
    //========================================================================
    reg rst_ff1 = 1'b1;
    reg rst_ff2 = 1'b1;

    always @(posedge sys_clk or negedge sys_rst_n) begin
        if (!sys_rst_n) begin
            rst_ff1 <= 1'b1;     // 异步断言：立刻复位
            rst_ff2 <= 1'b1;
        end else begin
            rst_ff1 <= 1'b0;     // 同步释放：过 2 拍后撤销
            rst_ff2 <= rst_ff1;
        end
    end

    wire rst = rst_ff2;          // 高有效同步复位，送全部子模块

    //========================================================================
    // 按键消抖（auth_btn：需稳定 DEBOUNCE_CYC 拍才认）
    //========================================================================
    reg [23:0] btn_cnt   = 24'd0;
    reg        btn_state = 1'b0;   // 消抖后的稳定状态
    reg        btn_prev  = 1'b0;   // 上一拍（边沿检测用）

    always @(posedge sys_clk) begin
        if (rst) begin
            btn_cnt   <= 24'd0;
            btn_state <= 1'b0;
            btn_prev  <= 1'b0;
        end else begin
            btn_prev <= btn_state;
            if (auth_btn != btn_state) begin
                if (btn_cnt >= DEBOUNCE_CYC - 1) begin
                    btn_state <= auth_btn;   // 稳定足够久，接受新状态
                    btn_cnt   <= 24'd0;
                end else begin
                    btn_cnt <= btn_cnt + 1;
                end
            end else begin
                btn_cnt <= 24'd0;             // 稳定一致，重置计数
            end
        end
    end

    wire auth_start_pulse = btn_state & ~btn_prev;   // 上升沿单拍

    //========================================================================
    // LED 心跳（~1Hz，实证时钟频率——不闪=时钟有问题）
    //========================================================================
    reg [26:0] hb_cnt = 27'd0;
    always @(posedge sys_clk) begin
        if (rst) hb_cnt <= 27'd0;
        else     hb_cnt <= hb_cnt + 1;
    end
    assign led_heartbeat = hb_cnt[26];    // 100MHz / 2^27 ≈ 0.75Hz

    //========================================================================
    // 内部互连信号
    //========================================================================
    // terminal_fsm ↔ mavlink_frame
    wire        mf_start, mf_busy, mf_phase, mf_done, mf_err;
    wire [23:0] mf_msg_id;
    wire [5:0]  mf_pay_len;
    wire [7:0]  mf_pay_byte, mf_seq;
    wire        mf_pay_valid;
    wire [7:0]  mf_frame_byte;
    wire        mf_frame_valid;
    wire [15:0] mf_frame_crc;

    // terminal_fsm ↔ frame_parser
    wire [23:0] fp_msg_id;
    wire [7:0]  fp_pay_len;
    wire        fp_frame_ok, fp_frame_err, fp_rx_inhibit;
    wire [4:0]  fp_rd_addr;
    wire [7:0]  fp_rd_data;

    // byte_fifo ↔ uart_tx
    wire [7:0]  fifo_rd_data;
    wire        fifo_empty, fifo_full;
    wire [6:0]  fifo_count;
    wire        fifo_pop;
    wire        uart_tx_active, uart_tx_done;

    // uart_rx
    wire [7:0]  uart_rx_byte;
    wire        uart_rx_valid;

    //========================================================================
    // 模块例化
    //========================================================================

    //------------------------------------------------------------------------
    // 协议状态机（编排所有模块）
    //------------------------------------------------------------------------
    terminal_fsm # (
        .TIMEOUT_CYCLES (TIMEOUT_CYCLES)
    ) u_fsm (
        .clk           (sys_clk       ),
        .rst           (rst           ),
        .auth_start    (auth_start_pulse),
        .terminal_id   (term_id_sw    ),
        .auth_busy     (led_busy      ),
        .auth_result   (led_result    ),
        .fp_msg_id     (fp_msg_id     ),
        .fp_pay_len    (fp_pay_len    ),
        .fp_frame_ok   (fp_frame_ok   ),
        .fp_frame_err  (fp_frame_err  ),
        .fp_rd_addr    (fp_rd_addr    ),
        .fp_rd_data    (fp_rd_data    ),
        .fp_rx_inhibit (fp_rx_inhibit ),
        .mf_start      (mf_start      ),
        .mf_msg_id     (mf_msg_id     ),
        .mf_pay_len    (mf_pay_len    ),
        .mf_pay_byte   (mf_pay_byte   ),
        .mf_pay_valid  (mf_pay_valid  ),
        .mf_seq        (mf_seq        ),
        .mf_sysid      (              ),  // output，未使用
        .mf_compid     (              ),  // output，未使用
        .mf_busy       (mf_busy       ),
        .mf_pay_phase  (mf_phase      ),
        .mf_frame_done (mf_done       ),
        .mf_frame_err  (mf_err        )
    );

    //------------------------------------------------------------------------
    // TX 帧构造器
    //------------------------------------------------------------------------
    mavlink_frame u_mf (
        .clk           (sys_clk       ),
        .rst           (rst           ),
        .start         (mf_start      ),
        .msg_id        (mf_msg_id     ),
        .payload_len   (mf_pay_len    ),
        .payload_byte  (mf_pay_byte   ),
        .payload_valid (mf_pay_valid  ),
        .seq_num       (mf_seq        ),
        .sys_id        (8'h01         ),  // 契约 §1 默认
        .comp_id       (8'h02         ),
        .busy          (mf_busy       ),
        .payload_phase (mf_phase      ),
        .frame_byte    (mf_frame_byte ),
        .frame_valid   (mf_frame_valid),
        .frame_done    (mf_done       ),
        .frame_crc     (mf_frame_crc  ),
        .frame_err     (mf_err        )
    );

    //------------------------------------------------------------------------
    // TX 速率匹配 FIFO（契约 §6.1-1 强制）
    //------------------------------------------------------------------------
    byte_fifo u_fifo (
        .clk     (sys_clk        ),
        .rst     (rst            ),
        .wr_data (mf_frame_byte  ),   // mavlink_frame 输出直写
        .wr_en   (mf_frame_valid ),
        .rd_en   (fifo_pop       ),
        .rd_data (fifo_rd_data   ),
        .empty   (fifo_empty     ),
        .full    (fifo_full      ),
        .count   (fifo_count     )
    );

    //------------------------------------------------------------------------
    // FIFO 弹出胶水（契约 §6.1-1：uart_tx 空闲且有数据时弹 1 字节）
    // 前提：uart_tx 的 tx_active 覆盖 START~CLEANUP（P0-2 修复后成立）
    //------------------------------------------------------------------------
    assign fifo_pop = ~fifo_empty & ~uart_tx_active;

    //------------------------------------------------------------------------
    // UART 发送器
    //------------------------------------------------------------------------
    uart_tx # (
        .CLKS_PER_BIT (CLKS_PER_BIT)
    ) u_tx (
        .clk       (sys_clk       ),
        .rst       (rst           ),
        .tx_valid  (fifo_pop      ),
        .tx_byte   (fifo_rd_data  ),
        .tx_serial (radio_txd     ),
        .tx_active (uart_tx_active),
        .tx_done   (uart_tx_done  )
    );

    //------------------------------------------------------------------------
    // UART 接收器
    //------------------------------------------------------------------------
    uart_rx # (
        .CLKS_PER_BIT (CLKS_PER_BIT)
    ) u_rx (
        .clk       (sys_clk      ),
        .rst       (rst          ),
        .rx_serial (radio_rxd    ),
        .rx_byte   (uart_rx_byte ),
        .rx_valid  (uart_rx_valid)
    );

    //------------------------------------------------------------------------
    // RX 帧解析器
    //------------------------------------------------------------------------
    frame_parser # (
        .PARSER_TIMEOUT (PARSER_TIMEOUT)
    ) u_fp (
        .clk            (sys_clk      ),
        .rst            (rst          ),
        .rx_inhibit     (fp_rx_inhibit),
        .rx_byte        (uart_rx_byte ),
        .rx_valid       (uart_rx_valid),
        .msg_id         (fp_msg_id    ),
        .pay_len        (fp_pay_len   ),
        .frame_ok       (fp_frame_ok  ),
        .frame_err      (fp_frame_err ),
        .payload_rd_addr(fp_rd_addr   ),
        .payload_rd_data(fp_rd_data   )
    );

endmodule
