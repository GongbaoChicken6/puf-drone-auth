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
// PUF（W4 B5a 已接入）：本顶层例化 challenge_decode + ro_array 并互连到
//   terminal_fsm 的 PUF 子接口（decode→热稳定 7 窗→测量→打包，契约 §8）。
//   仿真（xvlog -d PUF_MODEL_SIM）用 ro_array_sim 行为级替身（真环零延迟
//   不可仿，板上才验证物理指标）；上板走真 ro_array + w2_waiver.xdc。
//============================================================================

module w3_top # (
    parameter FREQ_HZ       = 100_000_000 ,  // 系统时钟（ZC702 PL 侧）
    parameter BAUD          = 115_200     ,  // UART 波特率
    parameter TIMEOUT_S     = 2,            // 协议超时（秒，契约 §5 建议 2s）
    parameter MEASURE_CYCLES = FREQ_HZ/1000,// W4：PUF 测量窗（1ms；TB 可缩小加速）
    parameter [4:0] WARMUP_WINS = 5'd7,     // W4：热稳定窗（W2 冻结 7 轮）
    // W4-P4 T1: 密钥派生使能。
    // 默认 0（fail-safe）——启用前站端必须先获得 K，否则终端用派生密钥
    // 算 R2 而站端用公开向量 → R2 不匹配 → 恒 BLOCKED（fail-closed）。
    // 站端 K 下发通道：scripts 侧 enroll 时 derive_device_key() 派生并 setkey，
    // 或 W5 落地 0x0096 KEY_SEED 注册通道（W4_design §5v2 主案）。
    parameter ENABLE_KEY_DERIVE = 0,
    // W4-P4 T2: 上电熵采样窗（默认 1ms；TB 可缩小加速）
    parameter [31:0] ENTROPY_CYCLES = 32'd100_000,
    // Phase 8a: 1=板级 wrapper 用（站端驱动注册：terminal_fsm 在 S_IDLE/
    // S_WAIT_RESULT 受控接受背靠背 0x0091 注册挑战）；0=默认——CI/TB 既有
    // 语义与黄金完全不变（fail-safe，同 ENABLE_KEY_DERIVE 的保守约定）
    parameter ENROLL_EN = 0,
    // 板级 bring-up 修复（ZC706 首烧实测）：1=默认，auth 按键受 re_seed_valid
    // 门控（P1-5 重放修复原语义，CI/TB 不变）；0=旁路门控——真实硅片上环振
    // 阵列若未起振，ro_entropy 的 seed_acc==0 fail-closed 检查会把按键永久
    // 屏蔽（现象：心跳闪但按 SW7 后 L/C/R 无任何反应）。bring-up 先放开主
    // 链路，熵子系统问题单独排查
    parameter SEED_GATE_EN = 1
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
    // 初值=1（板级空闲电平）：ZC706 SW7 空闲=1/按下=0（UG954 Table 1-29）。
    // 原初值 0 会在复位释放约 DEBOUNCE_CYC 拍后产生伪 0→1 上升沿=幽灵认证。
    // M9(auto-review) 症状归位：旧 bitstream 上熵门控若恰好屏蔽（re_seed_valid
    // 恒 0），幽灵沿同样被吞掉——"复位后 L/R 自动亮"只发生在熵正常的构建上，
    // 与本次板故（按键全屏蔽）分属两种不同构建的症状，勿混读；板故期用户
    // 报告的"SW13 灭不掉的灯"实为电源/DONE 灯（见 runbook）。TB 的 auth_btn
    // 初始 0（反极性建模）掩盖了该 bug
    reg        btn_state = 1'b1;   // 消抖后的稳定状态
    reg        btn_prev  = 1'b1;   // 上一拍（边沿检测用）

    always @(posedge sys_clk) begin
        if (rst) begin
            btn_cnt   <= 24'd0;
            btn_state <= 1'b1;     // 见声明处注释：对齐板级空闲电平
            btn_prev  <= 1'b1;
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

    // W4-P4 T2: 上电熵采样子系统声明（前移到脉冲生成之前，避免使用点
    // 先于声明点的编译顺序错误；例化仍在下方 PUF 子系统区）
    wire         re_measure_en, re_ring_en, re_busy, re_done;
    wire [255:0] re_ring_freq;
    wire         re_seed_valid;
    wire         re_seed_fault;                       // M4/M5(auto-review): 零熵被拒独立故障口
    wire [63:0]  re_boot_seed;
    wire         re_start;
    wire         re_start_valid;
    reg          re_started    = 1'b0;
    reg          seed_valid_d  = 1'b0;
    reg          seed_load_r   = 1'b0;

    // C-F2: 熵采样窗（~ENTROPY_CYCLES 拍）内压制认证启动——窗内 c2_counter
    // 尚未装载熵种子（仍为复位 0），C2 确定性=可重放窗口。门控后首个认证
    // 必然发生在 seed_valid 之后（对齐 W4_T1T2_design P2-3 的声明）。
    // SEED_GATE_EN=0（板级 bring-up）时旁路熵门控：防 seed 卡死把按键屏蔽
    wire auth_start_pulse = btn_state & ~btn_prev
                            & (SEED_GATE_EN ? re_seed_valid : 1'b1); // 上升沿(+熵就绪)

    //========================================================================
    // LED 心跳（0.75Hz，实证时钟频率——不闪=时钟有问题）
    //========================================================================
    reg [26:0] hb_cnt = 27'd0;
    always @(posedge sys_clk) begin
        if (rst) hb_cnt <= 27'd0;
        else     hb_cnt <= hb_cnt + 1;
    end
    // M5(auto-review)：心跳兼作熵故障出口——零熵被拒（seed_fault=1）时切换为
    // 快闪（hb_cnt[24]，100MHz/2^25≈3Hz），正常 0.75Hz。SEED_GATE_EN=0 旁路后
    // 死熵与活熵的板上现象靠此区分（runbook 同步记载"快闪=熵子系统零熵被拒"）
    assign led_heartbeat = re_seed_fault ? hb_cnt[24] : hb_cnt[26];

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

    // terminal_fsm ↔ PUF 子系统（W4 B5a）
    wire        cd_start, cd_done;
    wire        fsm_key_valid;             // W4-P4 T1: FSM 内密钥派生完成
    wire [95:0] fsm_key_reg;               // W4-P4 T1: FSM 内派生的 96-bit 密钥
    // W4-P4 T2: 熵子系统声明已前移到按键消抖区（re_* 引用处）
    wire [63:0] cd_seed;
    wire [511:0] cd_pair_table;
    wire        ra_measure_en, ra_ring_en, ra_busy, ra_done;
    wire [255:0] ra_ring_freq;

    //========================================================================
    // 模块例化
    //========================================================================

    //------------------------------------------------------------------------
    // 协议状态机（编排所有模块）
    //------------------------------------------------------------------------
    terminal_fsm # (
        .TIMEOUT_CYCLES (TIMEOUT_CYCLES),
        .WARMUP_WINS    (WARMUP_WINS),
        .MEASURE_CYCLES (MEASURE_CYCLES),
        .ENABLE_KEY_DERIVE (ENABLE_KEY_DERIVE), // W4-P4 T1: 参数传递
        .ENROLL_IDLE_ACCEPT (ENROLL_EN)         // Phase 8a: 注册模式参数传递
    ) u_fsm (
        .clk           (sys_clk       ),
        .rst           (rst           ),
        .auth_start    (auth_start_pulse),
        .terminal_id   (term_id_sw    ),
        .auth_busy     (led_busy      ),
        .auth_result   (led_result    ),
        // W4-P4 T1: key_valid 回环驱动 use_ext_key（派生后自动切换到派生密钥）
        // W4-P4 T2: c2_boot_seed 待接 ro_entropy（当前 tie 常量=旧行为）
        .c2_boot_seed  (re_boot_seed),     // W4-P4 T2: ro_entropy 上电熵种子
        .device_key_in (fsm_key_reg),      // W4-P4 T1: 派生密钥回环
        .use_ext_key   (fsm_key_valid),    // W4-P4 T1: 派生完成自动使能
        .seed_load     (seed_load_r),      // W4-P4 T2: seed_valid 上升沿脉冲
        .key_valid     (fsm_key_valid),   // FIX P0: FSM 输出驱动回环
        .key_reg       (fsm_key_reg),     // FIX P0: FSM 输出驱动回环
        .cd_start      (cd_start     ),
        .cd_seed       (cd_seed      ),
        .cd_pair_table (cd_pair_table),
        .cd_done       (cd_done      ),
        .ra_measure_en (ra_measure_en),
        .ra_ring_en    (ra_ring_en   ),
        .ra_busy       (ra_busy      ),
        .ra_done       (ra_done      ),
        .ra_ring_freq  (ra_ring_freq ),
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
    // PUF 子系统（W4 B5a）：挑战解码器 + 环振阵列
    // 仿真用行为级替身（-d PUF_MODEL_SIM），上板用真阵列（组合环设计使然，
    // 由 build_w3_board.tcl 加载 w2_waiver.xdc 豁免 LUTLP-1）
    //------------------------------------------------------------------------
    challenge_decode # (
        .N_ROUNDS ( 8 ),
        .N_RINGS  ( 16 ),
        .IDX_W    ( 4 )
    ) u_cd (
        .clk         (sys_clk      ),   // 审查 D-P1 修复：原误接未声明的 clk
        .rst         (rst          ),
        .start       (cd_start     ),
        .seed        (cd_seed      ),
        .pair_table  (cd_pair_table),
        .done        (cd_done      )
    );
`ifdef PUF_MODEL_SIM
    ro_array_sim # (
        .N_RINGS ( 16 ),
        .CNT_W   ( 16 )
    ) u_ro_array (
        .clk         (sys_clk      ),   // 审查 D-P1 修复
        .rst         (rst          ),
        .measure_en  (ra_measure_en),
        .ring_en     (ra_ring_en   ),
        .busy        (ra_busy      ),
        .done        (ra_done      ),
        .ring_freq   (ra_ring_freq )
    );
`else
    ro_array # (
        .N_RINGS    ( 16 ),
        .CNT_W      ( 16 ),
        .DIV_STAGES ( 5 )
    ) u_ro_array (
        .clk         (sys_clk      ),   // 审查 D-P1 修复
        .rst         (rst          ),
        .measure_en  (ra_measure_en),
        .ring_en     (ra_ring_en   ),
        .busy        (ra_busy      ),
        .done        (ra_done      ),
        .ring_freq   (ra_ring_freq )
    );
`endif

    //------------------------------------------------------------------------
    // W4-P4 T2: 上电熵采样子系统（P1-5 终端跨断电重放修复）
    // 独立第二 ro_array 实例（不复用认证阵列：认证阵列的 ring_en 受状态机
    // 控制，此处需上电即采样；两阵列互不干扰）
    //------------------------------------------------------------------------
    always @ ( posedge sys_clk ) begin
        if (rst) begin
            re_started    <= 1'b0;
            seed_valid_d  <= 1'b0;
            seed_load_r   <= 1'b0;
        end
        else begin
            // 复位释放后启动一次熵采样
            if (!re_started && !re_start_valid) begin
                re_started <= 1'b1;
            end
            // seed_valid 上升沿 -> seed_load 单拍脉冲
            seed_valid_d <= re_seed_valid;
            seed_load_r  <= re_seed_valid & ~seed_valid_d;
        end
    end
    // re_start 在复位后保持高（ro_entropy 只在 E_IDLE 且 start=1 时启动一次）
    assign re_start_valid = re_started;
    assign re_start       = re_started;

`ifdef PUF_MODEL_SIM
    ro_array_sim # (.N_RINGS(16), .CNT_W(16)) u_ro_entropy_array (
        .clk        (sys_clk       ),
        .rst        (rst           ),
        .measure_en (re_measure_en ),
        .ring_en    (re_ring_en    ),
        .busy       (re_busy       ),
        .done       (re_done       ),
        .ring_freq  (re_ring_freq  )
    );
`else
    ro_array # (.N_RINGS(16), .CNT_W(16), .DIV_STAGES(5)) u_ro_entropy_array (
        .clk        (sys_clk       ),
        .rst        (rst           ),
        .measure_en (re_measure_en ),
        .ring_en    (re_ring_en    ),
        .busy       (re_busy       ),
        .done       (re_done       ),
        .ring_freq  (re_ring_freq  )
    );
`endif

    ro_entropy # (
        .N_RINGS       (16),
        .CNT_W         (16),
        .SAMPLE_CYCLES (ENTROPY_CYCLES)
    ) u_ro_entropy (
        .clk        (sys_clk       ),
        .rst        (rst           ),
        .start      (re_start      ),
        .measure_en (re_measure_en ),
        .ring_en    (re_ring_en    ),
        .busy       (re_busy       ),
        .done       (re_done       ),
        .ring_freq  (re_ring_freq  ),
        .seed_valid (re_seed_valid ),
        .boot_seed  (re_boot_seed  ),
        .seed_fault (re_seed_fault)                  // M5: 板级可观测出口（心跳快闪）
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
