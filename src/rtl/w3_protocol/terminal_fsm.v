//============================================================================
// terminal_fsm.v -- HF-IDA 终端协议状态机（W3 收官模块）
//----------------------------------------------------------------------------
// 职责：编排完整双向认证流程（契约 §5 时序）：
//   IDLE → 发ACCESS → 等挑战 → 处理种子 → 发R1 → 等判决
//        → (通过→验R2→发确认→会话 / 灰区→加测→重交 / 拒绝→阻断)
//
// 集成（契约 §6.1 全部 8 条规则）：
//   RX: frame_parser 的 frame_ok 粘滞锁存 + payload_rd_addr 读取
//   TX: mavlink_frame 的 start/payload_phase/frame_done 握手
//   SEQ: frame_done 后自增（§6.1-3）
//   超时: 每个等待态独立计时（§5 的 2s）
//
// W4 B5a：PUF 真实接入。S_PROC_SEEDS/S_PROC_EXTRA（种子直通桩）已由
//   S_PUF_DECODE → S_PUF_MEASURE → S_PUF_PACK 三态取代（契约 §8 语义）：
//   读种子→challenge_decode 配对表→热稳定 7 窗+测量 1 窗（W2 冻结口径）
//   →64 对比较位打包为 R1。时延 ≈ 4×2058 + 8×MEASURE_CYCLES 拍。
//============================================================================

module terminal_fsm # (
    parameter TIMEOUT_CYCLES   = 32'd50_000_000,  // 0.5s @ 100MHz（板上用 200M=2s）
    parameter [4:0] WARMUP_WINS = 5'd7,            // W2 冻结：7 轮热稳定窗（逐窗丢弃）
    parameter MEASURE_CYCLES   = 32'd100_000,     // 1ms 测量窗 @100MHz（TB 缩小加速）
    // S_PUF_* 三态分段看门狗预算（每态入口清零 timeout_cnt，审查 D-P1）：
    // 单段最大 = 测量段 (WARMUP_WINS+1)*MEASURE_CYCLES；解码段 4×~2058；
    // 裕量 65536 覆盖打包与握手抖动
    parameter PUF_WD_CYCLES    = (WARMUP_WINS + 1) * MEASURE_CYCLES + 32'd65536,
    // W4-P4 T1: 0=TB 兼容（DEVICE_KEY 参数，黄金不变），1=板上（PUF 派生密钥）
    parameter ENABLE_KEY_DERIVE = 0
) (
    input  wire        clk       ,
    input  wire        rst       ,
    // -- 外部控制 ------------------------------------------------------------
    input  wire        auth_start,                 // 启动认证（单拍）
    input  wire [7:0]  terminal_id,                // 终端 ID
    output wire        auth_busy ,                 // 认证进行中
    output wire [1:0]  auth_result,                // 0=进行中 1=通过 2=拒绝 3=阻断
    // -- W4 可注入性（P2-T2：tie-off 后行为与 W3 完全一致）---------------
    // V2001 输入端口无默认值：所有例化方必须显式 tie（见 w3_top / TBs）。
    // c2_boot_seed 逐字节展开为 C2 初值（默认 A0..A7）；W4-P4 板上接
    // ro_entropy 上电熵采样（P1-5 修复），TB tie 常量保持黄金不变。
    input  wire [63:0] c2_boot_seed,               // 字节 j = bits[8j+:8]
    input  wire [95:0] device_key_in,              // 运行时密钥（use_ext_key=0 时忽略）
    input  wire        use_ext_key,                // 0=DEVICE_KEY 参数（TB/演示），1=运行时密钥
    input  wire        seed_load,                  // W4-P4 T2: 单拍脉冲，同步重装载 C2（TB 恒 0）
    // -- W4-P4 T1 密钥派生输出（w3_top 回环驱动 use_ext_key）---------------
    output wire        key_valid,                  // 1=派生密钥可用
    output wire [95:0] key_reg,                    // 派生的 96-bit 密钥
    // -- PUF 子系统（W4 B5a：challenge_decode + ro_array 由上层例化互连）---
    output wire        cd_start,                   // 解码启动（单拍）
    output wire [63:0] cd_seed,
    input  wire [511:0] cd_pair_table,             // 8 轮 × 8 对 × 8bit（契约 §8 格式）
    input  wire        cd_done,
    output wire        ra_measure_en,              // 测量窗使能（热窗+末窗）
    output wire        ra_ring_en,                 // 环振使能（功耗管理）
    input  wire        ra_busy,
    input  wire        ra_done,
    input  wire [255:0] ra_ring_freq,              // 16 × 16bit 频率锁存
    // -- RX 接口（frame_parser）----------------------------------------------
    input  wire [23:0] fp_msg_id ,                 // 消息 ID（fp_frame_ok_pulse 时有效）
    input  wire [7:0]  fp_pay_len,
    input  wire        fp_frame_ok,                // 单拍脉冲（本模块粘滞锁存）
    input  wire        fp_frame_err,
    output reg  [4:0]  fp_rd_addr,                 // 载荷读地址（本模块驱动）
    input  wire [7:0]  fp_rd_data ,                // 载荷组合读出
    output wire        fp_rx_inhibit,               // 载荷保护：读载荷期间阻止新帧接收
    // -- TX 接口（mavlink_frame）---------------------------------------------
    output reg         mf_start  ,                 // 启动组帧
    output reg  [23:0] mf_msg_id ,
    output reg  [5:0]  mf_pay_len,
    output reg  [7:0]  mf_pay_byte,                // 载荷字节
    output reg         mf_pay_valid,               // 载荷有效（仅 payload_phase=1 期间）
    output reg  [7:0]  mf_seq    ,                 // 序号（自增）
    output wire [7:0]  mf_sysid  ,                 // 系统 ID（固定 01）
    output wire [7:0]  mf_compid ,                 // 组件 ID（固定 02）
    input  wire        mf_busy   ,
    input  wire        mf_pay_phase,               // 载荷窗口
    input  wire        mf_frame_done,
    input  wire        mf_frame_err
);

    //========================================================================
    // 状态定义（4-bit，最多 16 态）
    //========================================================================
    localparam [3:0] S_IDLE        = 4'd0 ,   // 空闲等 auth_start
                     S_TX_ACCESS   = 4'd1 ,   // 发 ACCESS_REQUEST
                     S_WAIT_CHALL  = 4'd2 ,   // 等 CHALLENGE 帧
                     S_KEY_MEASURE = 4'd3,   // W4-P4 T1: PUF 测 key_seed 响应 → k_boot
                     S_TX_R1       = 4'd4 ,   // 发 RESPONSE_R1（4×8B）
                     S_WAIT_RESULT = 4'd5 ,   // 等 RESULT 或 EXTRA_CHALLENGE
                     S_VERIFY_R2   = 4'd6 ,   // 验证 R2
                     S_TX_CONFIRM  = 4'd7 ,   // 发 CONFIRM
                     S_SESSION     = 4'd8 ,   // 认证通过
                     S_KEY_DERIVE  = 4'd9,   // W4-P4 T1: Speck×2 KDF → key_reg
                     S_TX_R1_EXTRA = 4'd10,   // 发 RESPONSE_R1（3×8B=24B）
                     S_BLOCKED     = 4'd11,   // 认证失败阻断
                     S_CALC_R2     = 4'd12,   // 启动 Speck 计算 R2（共享起始状态）
                     S_PUF_DECODE  = 4'd13,   // W4：读种子 → 解码配对表 ×4/×3
                     S_PUF_MEASURE = 4'd14,   // W4：热稳定 7 窗 + 测量 1 窗
                     S_PUF_PACK    = 4'd15;   // W4：64 对比较位 → resp_buf

    reg [3:0] state = S_IDLE;

    //========================================================================
    // 内部寄存器
    //========================================================================
    reg [7:0]  seq_cnt      = 8'h00;            // SEQ 自增计数器
    reg [31:0] timeout_cnt  = 32'd0;            // 超时计数（32-bit：板上 200M 需要 28-bit）
    reg        rx_ok_latch  = 1'b0;             // frame_ok 粘滞
    reg [1:0]  result_r     = 2'd0;             // auth_result 寄存

    // 发送载荷缓冲（最大 32B，发 ACCESS/R1/CONFIRM 前预填）
    reg [7:0]  tx_buf [0:31];
    reg [5:0]  tx_len  = 6'd0;                   // 本次发送载荷长度
    reg [5:0]  tx_idx  = 6'd0;                   // 发送索引

    // PUF 响应缓冲（4 种子 → 4×8B = 32B；W4 B5a = 真实比较位打包）
    reg [7:0]  resp_buf [0:31];

    // -- W4 B5a PUF 子流程寄存器 ------------------------------------------
    reg [2:0]   puf_seed_idx  = 3'd0;     // 当前种子（0..3 / 灰区 0..2）
    reg [63:0]  puf_seed_asym = 64'd0;    // 种子逐字节装配暂存
    reg         puf_dec_busy  = 1'b0;     // challenge_decode 在飞
    reg         puf_extra     = 1'b0;     // 灰区轮（3 种子 / 24B）
    reg [511:0] puf_tbl_0 = 512'd0;       // 4 张配对表捕获
    reg [511:0] puf_tbl_1 = 512'd0;
    reg [511:0] puf_tbl_2 = 512'd0;
    reg [511:0] puf_tbl_3 = 512'd0;
    reg [255:0] puf_freqs = 256'd0;       // 末窗频率锁存
    reg [4:0]   puf_win_idx  = 5'd0;      // 热稳定窗计数（0..WARMUP_WINS）
    reg [31:0]  puf_win_cnt  = 32'd0;     // 窗内拍计数
    reg         puf_win_wait = 1'b0;      // 窗已关，等 ra_done
    reg [5:0]   puf_pack_idx = 6'd0;      // 打包字节索引（0..31 / 0..23）
    reg         puf_cd_start_r = 1'b0;    // cd_start 单拍
    reg [63:0]  puf_cd_seed_r  = 64'd0;
    reg         puf_measure_r  = 1'b0;    // ra_measure_en 寄存输出
    reg         puf_ring_en_r  = 1'b0;    // ra_ring_en 寄存输出

    assign cd_start     = puf_cd_start_r;
    assign cd_seed      = puf_cd_seed_r;
    assign ra_measure_en= puf_measure_r;
    assign ra_ring_en   = puf_ring_en_r;

    // 打包组合逻辑：byte = seed s 的 round j 8 个比较位（契约 §8 位映射）
    // pack_idx[5:3] = 种子 s，pack_idx[2:0] = 轮 j；bit(7-p) = bit(j,p)
    // = (freq[B] > freq[A])。表选择 + 变基索引部分选择（+: 语法）。
    reg [511:0] puf_tbl_sel;
    reg [3:0]   puf_nib_a, puf_nib_b;
    reg [7:0]   puf_pack_byte;
    always @* begin
        case (puf_pack_idx[5:3])
            3'd0:    puf_tbl_sel = puf_tbl_0;
            3'd1:    puf_tbl_sel = puf_tbl_1;
            3'd2:    puf_tbl_sel = puf_tbl_2;
            default: puf_tbl_sel = puf_tbl_3;
        endcase
        puf_pack_byte = 8'd0;
        puf_nib_a = 4'd0;
        puf_nib_b = 4'd0;
        // 轮 j 的配对表基址 = j*64；对 p 的条目 = [j*64 + p*8 +: 8]
        puf_nib_a = puf_tbl_sel[{puf_pack_idx[2:0], 6'd0} +: 4];               // 环 A（低 4bit）
        puf_nib_b = puf_tbl_sel[{puf_pack_idx[2:0], 6'd0} + 4 +: 4];           // 环 B（高 4bit）
        if (puf_freqs[{puf_nib_b, 4'd0} +: 16] > puf_freqs[{puf_nib_a, 4'd0} +: 16])
            puf_pack_byte[7] = 1'b1;   // pair 0 → MSB（R1[63-8j-0]）
        // 其余 7 对需逐对展开（组合块内不可变址循环——用展开式）
        puf_nib_a = puf_tbl_sel[{puf_pack_idx[2:0], 6'd0} + 8  +: 4];
        puf_nib_b = puf_tbl_sel[{puf_pack_idx[2:0], 6'd0} + 12 +: 4];
        if (puf_freqs[{puf_nib_b, 4'd0} +: 16] > puf_freqs[{puf_nib_a, 4'd0} +: 16])
            puf_pack_byte[6] = 1'b1;
        puf_nib_a = puf_tbl_sel[{puf_pack_idx[2:0], 6'd0} + 16 +: 4];
        puf_nib_b = puf_tbl_sel[{puf_pack_idx[2:0], 6'd0} + 20 +: 4];
        if (puf_freqs[{puf_nib_b, 4'd0} +: 16] > puf_freqs[{puf_nib_a, 4'd0} +: 16])
            puf_pack_byte[5] = 1'b1;
        puf_nib_a = puf_tbl_sel[{puf_pack_idx[2:0], 6'd0} + 24 +: 4];
        puf_nib_b = puf_tbl_sel[{puf_pack_idx[2:0], 6'd0} + 28 +: 4];
        if (puf_freqs[{puf_nib_b, 4'd0} +: 16] > puf_freqs[{puf_nib_a, 4'd0} +: 16])
            puf_pack_byte[4] = 1'b1;
        puf_nib_a = puf_tbl_sel[{puf_pack_idx[2:0], 6'd0} + 32 +: 4];
        puf_nib_b = puf_tbl_sel[{puf_pack_idx[2:0], 6'd0} + 36 +: 4];
        if (puf_freqs[{puf_nib_b, 4'd0} +: 16] > puf_freqs[{puf_nib_a, 4'd0} +: 16])
            puf_pack_byte[3] = 1'b1;
        puf_nib_a = puf_tbl_sel[{puf_pack_idx[2:0], 6'd0} + 40 +: 4];
        puf_nib_b = puf_tbl_sel[{puf_pack_idx[2:0], 6'd0} + 44 +: 4];
        if (puf_freqs[{puf_nib_b, 4'd0} +: 16] > puf_freqs[{puf_nib_a, 4'd0} +: 16])
            puf_pack_byte[2] = 1'b1;
        puf_nib_a = puf_tbl_sel[{puf_pack_idx[2:0], 6'd0} + 48 +: 4];
        puf_nib_b = puf_tbl_sel[{puf_pack_idx[2:0], 6'd0} + 52 +: 4];
        if (puf_freqs[{puf_nib_b, 4'd0} +: 16] > puf_freqs[{puf_nib_a, 4'd0} +: 16])
            puf_pack_byte[1] = 1'b1;
        puf_nib_a = puf_tbl_sel[{puf_pack_idx[2:0], 6'd0} + 56 +: 4];
        puf_nib_b = puf_tbl_sel[{puf_pack_idx[2:0], 6'd0} + 60 +: 4];
        if (puf_freqs[{puf_nib_b, 4'd0} +: 16] > puf_freqs[{puf_nib_a, 4'd0} +: 16])
            puf_pack_byte[0] = 1'b1;
    end

    // C2 反挑战计数器 + Speck R2（防重放）
    // C2 每次 auth_start 递增 → R2 = Speck(K,C2) 也变 → 旧 R2 无法重放
    reg [7:0]  c2_counter [0:7];
    reg [7:0]  r2_expected [0:7];

    // Speck64/96 密码核（R2 = Speck_encrypt(device_key, C2)）
    parameter [95:0] DEVICE_KEY = 96'h13121110_0b0a0908_03020100;  // W3 测试值，W4 从 PUF 提取

    wire [95:0] sp_key;
    wire [63:0] sp_plaintext;
    wire [63:0] sp_ciphertext;
    wire        sp_start;     // 门控后输出到 Speck
    wire        sp_done;
    wire        sp_busy;

    reg  [7:0]  calc_wd_cnt = 8'd0;             // S_CALC_R2 看门狗计数器
    reg         calc_done_flag = 1'b0;          // W4-P4 P2-1: Speck 完成旗标

    // W4-P4 T1 密钥派生寄存器
    reg [95:0]  key_reg_r   = 96'd0;   // 派生密钥 K（_r 后缀避免端口冲突）
    reg         key_valid_r = 1'b0;    // 1=K 已派生（每次上电重置）
    reg [63:0]  k_boot_reg  = 64'd0;   // K_boot = PUF 响应 key_seed
    reg [63:0]  kdf_ct1     = 64'd0;   // KDF 第一步密文
    reg [1:0]   kdf_step    = 2'd0;    // KDF 子步（0=idle, 1=ct1, 2=ct2）
    reg [1:0]   km_substate = 2'd0;    // S_KEY_MEASURE 子态

    assign key_valid = key_valid_r;                // W4-P4 T1: 输出到 w3_top
    assign key_reg   = key_reg_r;                  // W4-P4 T1: 输出到 w3_top
    reg         sp_start_w  = 1'b0;              // Speck 启动脉冲（内部）
    localparam  CALC_WD_MAX = 8'd255;            // 256 周期看门狗

    // W4-P4 T1 KDF 冻结常量（与 puf_model.derive_device_key 逐字节一致）
    localparam [63:0] KDF_KEY_SEED_C = 64'h6B65_7973_6565_6431;  // "keyseed1"
    localparam [63:0] KDF_MASK_C     = 64'hA5A5_5A5A_A5A5_5A5A;
    // Speck plaintext 字节映射（pt[i] → plaintext_in[8*(i%4)+39-32*(i<4) +: 8]）
    // KEY_SEED 大端字节 6B 65 79 73 65 65 64 31 → 预换算为 wire 位序
    localparam [63:0] KDF_PT1 = 64'h7379_656B_3164_6565;  // KEY_SEED 逐字节映射
    localparam [63:0] KDF_PT2 = 64'h2923_C0CE_6B3E_C0C0;  // (KEY_SEED^MASK) 映射（修正 5B→6B）

    // W4-T2 密钥选择 + W4-P4 T1 KDF mux
    // S_KEY_DERIVE 态：用 kdf_key12（从 k_boot_reg 派生 12B）
    // 其他态：use_ext_key=0 走参数（TB 黄金），1 走运行时输入
    wire [95:0] kdf_key12;
    // key12 = K_boot(8B)+K_boot[0:3](4B)，逐字节映射到 key_in[8*i +: 8]
    assign kdf_key12 = {
        k_boot_reg[39:32], k_boot_reg[47:40], k_boot_reg[55:48], k_boot_reg[63:56],  // bytes 11-8（= 3-0 重复）
        k_boot_reg[7:0],   k_boot_reg[15:8],  k_boot_reg[23:16],  k_boot_reg[31:24],  // bytes 7-4
        k_boot_reg[39:32], k_boot_reg[47:40], k_boot_reg[55:48], k_boot_reg[63:56]   // bytes 3-0（同组序）
    };
    assign sp_key = (state == S_KEY_DERIVE) ? kdf_key12 :
                    use_ext_key ? device_key_in : DEVICE_KEY;

    // C2 字节重排 → c2_pt wire（NSA 小端约定）
    wire [63:0] c2_pt;
    assign c2_pt[39:32] = c2_counter[0];
    assign c2_pt[47:40] = c2_counter[1];
    assign c2_pt[55:48] = c2_counter[2];
    assign c2_pt[63:56] = c2_counter[3];
    assign c2_pt[7:0]   = c2_counter[4];
    assign c2_pt[15:8]  = c2_counter[5];
    assign c2_pt[23:16] = c2_counter[6];
    assign c2_pt[31:24] = c2_counter[7];

    // W4-P4 T1: Speck plaintext mux（KDF 态切换到冻结常量）
    wire [63:0] kdf_pt = (kdf_step == 2'd1) ? KDF_PT1 : KDF_PT2;
    assign sp_plaintext = (state == S_KEY_DERIVE) ? kdf_pt : c2_pt;

    // Speck 密文 → R2 字节（NSA 小端拆包）
    // r2[0]=y LSB → ct[39:32], r2[1] → ct[47:40], r2[2] → ct[55:48], r2[3]=y MSB → ct[63:56]
    // r2[4]=x LSB → ct[7:0],   r2[5] → ct[15:8],  r2[6] → ct[23:16], r2[7]=x MSB → ct[31:24]
    // 注意：这些 wire 用于 S_CALC_R2 中锁存 r2_expected
    wire [7:0] r2_byte_0 = sp_ciphertext[39:32];
    wire [7:0] r2_byte_1 = sp_ciphertext[47:40];
    wire [7:0] r2_byte_2 = sp_ciphertext[55:48];
    wire [7:0] r2_byte_3 = sp_ciphertext[63:56];
    wire [7:0] r2_byte_4 = sp_ciphertext[7:0];
    wire [7:0] r2_byte_5 = sp_ciphertext[15:8];
    wire [7:0] r2_byte_6 = sp_ciphertext[23:16];
    wire [7:0] r2_byte_7 = sp_ciphertext[31:24];

    assign sp_start = sp_start_w & ~sp_busy;  // B 代理建议：忙时不启动

    //--------------------------------------------------------------------
    // Speck64/96 密码核实例
    //--------------------------------------------------------------------
    speck64_96 u_speck (
        .clk            (clk           ),
        .rst            (rst           ),
        .start          (sp_start      ),
        .key_in         (sp_key        ),
        .plaintext_in   (sp_plaintext  ),
        .ciphertext_out (sp_ciphertext ),
        .done           (sp_done       ),
        .busy           (sp_busy       )
    );
    integer    j;
    // B-P3 修复：c2_counter 初始化已移入主 FSM always 块的 rst 分支。
    // 原 initial 块在 t=0 采样 c2_boot_seed 端口，与 TB 声明初始化器存在
    // IEEE1364 未定义次序（iverilog 下 c2_counter=X -> GJ/T6 假失败）。
    // rst 分支装载跨仿真器确定，且 TB 均先置 rst 后释放（行为等价）。

    assign auth_busy  = (state != S_IDLE) && (state != S_SESSION);
    // 载荷保护：S_PROC_SEEDS/S_PROC_EXTRA/S_VERIFY_R2 期间读 fp 载荷缓冲，
    // 阻止 frame_parser 接收新帧覆盖缓冲（并发竞态修复）
    assign fp_rx_inhibit = (state == S_CALC_R2) || (state == S_PUF_DECODE)
                        || (state == S_PUF_MEASURE) || (state == S_PUF_PACK)
                        || (state == S_KEY_MEASURE) || (state == S_KEY_DERIVE)
                        || (state == S_VERIFY_R2);
    assign auth_result = result_r;
    assign mf_sysid  = 8'h01;
    assign mf_compid = 8'h02;

    //========================================================================
    // frame_ok 粘滞锁存（契约 §6.1-7）
    //========================================================================
    always @(posedge clk) begin
        if (rst)                       rx_ok_latch <= 1'b0;
        else if (fp_frame_ok)          rx_ok_latch <= 1'b1;
        else if (state == S_PUF_DECODE || state == S_PUF_MEASURE || state == S_PUF_PACK ||
                 state == S_KEY_MEASURE || state == S_KEY_DERIVE ||
                 state == S_WAIT_CHALL || state == S_WAIT_RESULT)
            ; // 在等待态保持
        else                           rx_ok_latch <= 1'b0;  // 处理完自动清
    end

    //========================================================================
    // SEQ 自增（契约 §6.1-3：frame_done 之后才自增）
    //========================================================================
    always @(posedge clk) begin
        if (rst)                    seq_cnt <= 8'h00;
        else if (mf_frame_done)      seq_cnt <= seq_cnt + 8'd1;
    end

    //========================================================================
    // 主状态机
    //========================================================================
    integer k;
    // synth translate_off
    reg [3:0] state_prev = S_IDLE;              // 调试用：前态跟踪
    always @(posedge clk) begin
        if (state != state_prev) begin
            $display("[FSM] %0d -> %0d @%0t", state_prev, state, $time);
            state_prev <= state;
        end
    end
    // synth translate_on

    always @(posedge clk) begin
        if (rst) begin
            state       <= S_IDLE;
            timeout_cnt <= 32'd0;
            result_r    <= 2'd0;
            // B-P3: C2 初值装载（原 initial 块，跨仿真器确定性修复）
            for (j = 0; j < 8; j = j + 1)
                c2_counter[j] <= c2_boot_seed[8*j +: 8];
            mf_start    <= 1'b0;
            mf_msg_id   <= 24'h0;
            mf_pay_len  <= 6'd0;
            mf_pay_byte <= 8'h00;
            mf_pay_valid<= 1'b0;
            mf_seq      <= 8'h00;
            fp_rd_addr  <= 5'd0;
            tx_idx      <= 6'd0;
        end else begin
            // 默认单拍脉冲清零
            mf_start     <= 1'b0;
            mf_pay_valid <= 1'b0;

            // 超时计数：WAIT 态对 TIMEOUT_CYCLES；S_PUF_* 态对 PUF_WD_CYCLES
            // （W4-P2 审查 P2R-F4：原 2s 只挂等待态，PUF 三态自带看门狗）
            if (state == S_WAIT_CHALL || state == S_WAIT_RESULT ||
                state == S_PUF_DECODE || state == S_PUF_MEASURE || state == S_PUF_PACK ||
                state == S_KEY_MEASURE || state == S_KEY_DERIVE) begin
                timeout_cnt <= timeout_cnt + 32'd1;
            end else begin
                timeout_cnt <= 32'd0;
            end

            case (state)
                //====================================================
                S_IDLE: begin
                    // result_r 不在此清零——BLOCKED 的结果需要被外部读到
                    // 只在新一轮认证启动时才清
                    if (auth_start) begin
                        result_r <= 2'd0;
                        calc_done_flag <= 1'b0;   // B-P2: 每会话重置
                        if (ENABLE_KEY_DERIVE && !key_valid_r) begin
                            // W4-P4 T1: 首次上电需派生密钥
                            state <= S_KEY_MEASURE;
                            km_substate <= 2'd0;
                            timeout_cnt <= 32'd0;
                        end else begin
                            state <= S_CALC_R2;
                        end
                    end
                end

                //====================================================
                // 发送帧（共用逻辑：start → 等窗口 → 喂载荷 → 等 done）
                //====================================================
                S_TX_ACCESS, S_TX_R1, S_TX_CONFIRM, S_TX_R1_EXTRA: begin
                    // ⚠ 优先级：frame_done > frame_err > 启动新帧 > 喂载荷
                    // frame_done 必须最先检查：帧完成拍 mf_busy 同步拉低，
                    // 若先查 !mf_busy 会误入"启动新帧"分支（实际 bug#3）
                    if (mf_frame_done) begin
                        // 帧发完：转下一态
                        case (state)
                            S_TX_ACCESS:   state <= S_WAIT_CHALL;
                            S_TX_R1:       state <= S_WAIT_RESULT;
                            S_TX_R1_EXTRA: state <= S_WAIT_RESULT;
                            S_TX_CONFIRM:  state <= S_SESSION;
                            default:       state <= S_IDLE;
                        endcase
                    end else if (mf_frame_err) begin
                        state <= S_BLOCKED;         // 组帧失败
                        result_r <= 2'd3;
                    end else if (!mf_busy && !mf_start) begin
                        // 尚未启动：发 start
                        mf_start   <= 1'b1;
                        mf_seq     <= seq_cnt;
                        tx_idx     <= 6'd0;
                        case (state)
                            S_TX_ACCESS: begin
                                mf_msg_id  <= 24'h0090;  // ACCESS_REQUEST
                                mf_pay_len <= tx_len;    // 16B
                            end
                            S_TX_R1: begin
                                mf_msg_id  <= 24'h0092;  // RESPONSE_R1
                                mf_pay_len <= 6'd32;     // 4×8B
                                for (k = 0; k < 32; k = k + 1)
                                    tx_buf[k] <= resp_buf[k];
                            end
                            S_TX_R1_EXTRA: begin
                                mf_msg_id  <= 24'h0092;  // RESPONSE_R1
                                mf_pay_len <= 6'd24;     // 3×8B
                                for (k = 0; k < 24; k = k + 1)
                                    tx_buf[k] <= resp_buf[k];
                            end
                            S_TX_CONFIRM: begin
                                mf_msg_id  <= 24'h0094;  // CONFIRM
                                mf_pay_len <= 6'd5;      // tid(4)+status(1)
                            end
                        endcase
                    end else if (mf_pay_phase && tx_idx < mf_pay_len) begin
                        // 载荷窗口内：逐字节喂
                        mf_pay_byte  <= tx_buf[tx_idx[4:0]];
                        mf_pay_valid <= 1'b1;
                        tx_idx       <= tx_idx + 6'd1;
                    end
                end

                //====================================================
                S_WAIT_CHALL: begin
                    if (rx_ok_latch && fp_msg_id == 24'h0091 && fp_pay_len == 8'd32) begin
                        // rx_ok_latch 不在此清零——锁存块的"非等待态清零"已覆盖
                        // （消除多驱动：A-P0-1 修复）
                        fp_rd_addr  <= 5'd0;
                        puf_extra   <= 1'b0;         // W4：首轮 4 种子
                        puf_seed_idx<= 3'd0;
                        puf_dec_busy<= 1'b0;
                        timeout_cnt <= 32'd0;        // 审查 D-P1：等待帧时间不吃 PUF 预算
                        state       <= S_PUF_DECODE;
                    end else if (timeout_cnt >= TIMEOUT_CYCLES) begin
                        state    <= S_BLOCKED;
                        result_r <= 2'd3;
                    end
                end

                //====================================================
                // W4 B5a：读种子 → 解码配对表（首轮 4 种子 / 灰区 3 种子）
                //   阶段 A：逐字节读 fp 载荷装配 64-bit 种子（第 8 字节
                //           拍触发 cd_start；字节序 = 载荷序，MSB 在前，
                //           与 puf_model 大端装配一致）
                //   阶段 B：等 cd_done 捕获 512-bit 配对表（~2058 拍/种子）
                //====================================================
                S_PUF_DECODE: begin
                    if (timeout_cnt >= PUF_WD_CYCLES) begin
                        puf_dec_busy  <= 1'b0;
                        puf_ring_en_r <= 1'b0;
                        state    <= S_BLOCKED;
                        result_r <= 2'd3;
                    end else if (!puf_dec_busy) begin
                        // 阶段 A：装配 + 启动解码
                        puf_seed_asym <= {puf_seed_asym[55:0], fp_rd_data};
                        if (fp_rd_addr[2:0] == 3'd7) begin
                            puf_cd_seed_r <= {puf_seed_asym[55:0], fp_rd_data};
                            puf_cd_start_r<= 1'b1;
                            puf_dec_busy  <= 1'b1;
                        end
                        fp_rd_addr <= fp_rd_addr + 5'd1;
                    end else begin
                        // 阶段 B：解码在飞，等 done 捕表
                        puf_cd_start_r <= 1'b0;
                        if (cd_done) begin
                            case (puf_seed_idx[1:0])
                                2'd0:    puf_tbl_0 <= cd_pair_table;
                                2'd1:    puf_tbl_1 <= cd_pair_table;
                                2'd2:    puf_tbl_2 <= cd_pair_table;
                                default: puf_tbl_3 <= cd_pair_table;
                            endcase
                            puf_dec_busy <= 1'b0;
                            puf_seed_idx <= puf_seed_idx + 3'd1;
                            if (( puf_extra && puf_seed_idx == 3'd2) ||
                                (!puf_extra && puf_seed_idx == 3'd3)) begin
                                // 全部配对表就绪 → 热稳定 + 测量
                                state         <= S_PUF_MEASURE;
                                timeout_cnt   <= 32'd0;   // 分段预算：解码段清零
                                puf_win_idx   <= 5'd0;
                                puf_win_cnt   <= 32'd0;
                                puf_win_wait  <= 1'b0;
                                puf_ring_en_r <= 1'b1;
                                puf_measure_r <= 1'b0;
                            end
                        end
                    end
                end

                //====================================================
                // W4 B5a：热稳定 WARMUP_WINS 窗（丢弃）+ 末窗测量
                // （W2 冻结口径 w2_top.v:17-19；开振即测会威胁 G2 ≥97%）
                //====================================================
                S_PUF_MEASURE: begin
                    if (timeout_cnt >= PUF_WD_CYCLES) begin
                        puf_measure_r <= 1'b0;
                        puf_ring_en_r <= 1'b0;
                        state    <= S_BLOCKED;
                        result_r <= 2'd3;
                    end else if (!puf_win_wait) begin
                        // 窗内计数（ra_measure_en 高）
                        puf_measure_r <= 1'b1;
                        if (puf_win_cnt >= MEASURE_CYCLES - 32'd1) begin
                            puf_measure_r <= 1'b0;      // 关窗：ro_array 窗末锁存
                            puf_win_cnt   <= 32'd0;
                            puf_win_wait  <= 1'b1;
                        end else begin
                            puf_win_cnt <= puf_win_cnt + 32'd1;
                        end
                    end else begin
                        // 窗已关，等 ra_done 单拍（窗计数=末窗则锁存频率）
                        if (ra_done) begin
                            if (puf_win_idx >= WARMUP_WINS) begin
                                puf_freqs     <= ra_ring_freq;  // 末窗频率
                                puf_ring_en_r <= 1'b0;           // 功耗：测量完停振
                                puf_pack_idx  <= 6'd0;
                                timeout_cnt   <= 32'd0;         // 分段预算：测量段清零
                                state         <= S_PUF_PACK;
                            end else begin
                                puf_win_idx  <= puf_win_idx + 5'd1;
                                puf_win_wait <= 1'b0;            // 开下一热窗
                            end
                        end
                    end
                end

                //====================================================
                // W4 B5a：64 对比较位打包 → resp_buf（契约 §8 位映射）
                //   首轮 32B → S_TX_R1；灰区 24B → S_TX_R1_EXTRA
                //====================================================
                S_PUF_PACK: begin
                    if (timeout_cnt >= PUF_WD_CYCLES) begin
                        puf_dec_busy  <= 1'b0;   // 审查 D-P2：与其他两态对齐
                        puf_ring_en_r <= 1'b0;
                        puf_measure_r <= 1'b0;
                        state    <= S_BLOCKED;
                        result_r <= 2'd3;
                    end else begin
                        resp_buf[puf_pack_idx[4:0]] <= puf_pack_byte;
                        if (puf_extra ? (puf_pack_idx == 6'd23) : (puf_pack_idx == 6'd31)) begin
                            state <= puf_extra ? S_TX_R1_EXTRA : S_TX_R1;
                        end else begin
                            puf_pack_idx <= puf_pack_idx + 6'd1;
                        end
                    end
                end

                //====================================================
                S_WAIT_RESULT: begin
                    if (rx_ok_latch && fp_msg_id == 24'h0093 && fp_pay_len == 8'd10) begin
                        // RESULT 帧 → 转验证态（不在本拍读数据！
                        // fp_rd_addr 同拍 NBA，读到的会是旧地址）
                        fp_rd_addr  <= 5'd0;
                        state       <= S_VERIFY_R2;
                    end else if (rx_ok_latch && fp_msg_id == 24'h0095 && fp_pay_len == 8'd24) begin
                        // EXTRA_CHALLENGE：灰区加测（W4：3 种子同 PUF 管线）
                        fp_rd_addr  <= 5'd0;
                        puf_extra   <= 1'b1;
                        puf_seed_idx<= 3'd0;
                        puf_dec_busy<= 1'b0;
                        timeout_cnt <= 32'd0;        // 审查 D-P1：同上
                        state       <= S_PUF_DECODE;
                    end else if (timeout_cnt >= TIMEOUT_CYCLES) begin
                        state    <= S_BLOCKED;
                        result_r <= 2'd3;
                    end
                end

                //====================================================
                // （原 S_PROC_EXTRA 灰区桩已由 S_PUF_DECODE/MEASURE/PACK
                //   复用路径取代——puf_extra=1 时 3 种子 24B → S_TX_R1_EXTRA）
                //====================================================

                //====================================================
                // 验证 R2（比较载荷 [2..9] 与期望值）
                //====================================================
                S_VERIFY_R2: begin
                    // W4-P4 P2-1: 未经过 S_CALC_R2 的路径在此被拦截
                    if (!calc_done_flag) begin
                        state    <= S_BLOCKED;
                        result_r <= 2'd3;
                    end

                    // 载荷布局：result(1)+hd(1)+r2(8) = 地址 [0]=result, [1]=hd, [2..9]=r2
                    else if (fp_rd_addr == 5'd0) begin
                        // 第一拍：读 result 码
                        if (fp_rd_data == 8'h00) begin
                            fp_rd_addr <= 5'd2;     // PASS → 跳到 R2 字节
                        end else begin
                            state    <= S_BLOCKED;  // REJECT
                            result_r <= 2'd2;
                            calc_done_flag <= 1'b0; // P3: 拒绝路径也清旗标
                        end
                    end else if (fp_rd_addr >= 5'd2 && fp_rd_addr < 5'd10) begin
                        // 读 r2 字节 [2..9]
                        if (fp_rd_data != r2_expected[fp_rd_addr[3:0] - 5'd2]) begin
                            state    <= S_BLOCKED;  // R2 不匹配
                            result_r <= 2'd3;
                            calc_done_flag <= 1'b0; // P3: 阻断路径也清
                            // C4: 清 key_valid_r 触发下次认证重派生（坏 K 不永久缓存）
                            key_valid_r <= 1'b0;
                        end
                        fp_rd_addr <= fp_rd_addr + 5'd1;
                    end else if (fp_rd_addr >= 5'd10) begin
                        // 8 字节全部匹配 → 通过 → 发 CONFIRM
                        tx_buf[0] <= terminal_id;
                        tx_buf[1] <= 8'h00;
                        tx_buf[2] <= 8'h00;
                        tx_buf[3] <= 8'h00;
                        tx_buf[4] <= 8'h00;         // status = OK (protocol.py CONFIRM_OK=0)
                        tx_len    <= 6'd5;
                        state     <= S_TX_CONFIRM;
                        result_r  <= 2'd1;         // PASS
                        calc_done_flag <= 1'b0;    // P2-1: 验证完清旗标
                    end
                end

                //====================================================
                S_SESSION: begin
                    // 认证通过。auth_start 直接启动新一轮（不经过 IDLE——
                    // 否则 auth_start 脉冲被本态消费后 IDLE 看不到）
                    if (auth_start) begin
                        result_r <= 2'd0;
                        calc_done_flag <= 1'b0;   // B-P2: 每会话重置
                        if (ENABLE_KEY_DERIVE && !key_valid_r) begin
                            state <= S_KEY_MEASURE;
                            km_substate <= 2'd0;
                            timeout_cnt <= 32'd0;
                        end else begin
                            state <= S_CALC_R2;
                        end
                    end
                end

                //====================================================
                S_CALC_R2: begin
                    // 共享认证起始状态：C2++ → 预填载荷 → 启动 Speck → 等 done
                    if (calc_wd_cnt == 8'd0) begin
                        // 第一拍：递增 C2 + 预填载荷 + 启动 Speck
                        tx_buf[0]  <= terminal_id;
                        tx_buf[1]  <= 8'h00;
                        tx_buf[2]  <= 8'h00;
                        tx_buf[3]  <= 8'h00;
                        tx_buf[4]  <= 8'hDE;
                        tx_buf[5]  <= 8'hAD;
                        tx_buf[6]  <= 8'hBE;
                        tx_buf[7]  <= 8'hEF;
                        for (k = 0; k < 8; k = k + 1) begin
                            c2_counter[k] <= c2_counter[k] + 8'd1;
                            tx_buf[8+k]   <= c2_counter[k] + 8'd1;
                        end
                        tx_len     <= 6'd16;
                        sp_start_w <= 1'b1;
                        calc_wd_cnt <= 8'd1;
                    end else begin
                        sp_start_w <= 1'b0;

                        if (sp_done) begin
                            // B-P2-1: 密文 x 兜底——sp_key 若为 x/z（如回环未接）
                            // 则密文全 x，下游 '!=' 比对在 x 下走 else 分支 =
                            // "恒接受"，可被伪造 RESULT 冒充站端。此处源头拒绝。
                            if (^sp_ciphertext === 1'bx) begin
                                state       <= S_BLOCKED;
                                result_r    <= 2'd3;
                                calc_wd_cnt <= 8'd0;
                                key_valid_r <= 1'b0;
                            end else begin
                            // Speck 完成：置旗标 + 锁存 R2 + 进入 TX_ACCESS
                            calc_done_flag <= 1'b1;
                            r2_expected[0] <= r2_byte_0;
                            r2_expected[1] <= r2_byte_1;
                            r2_expected[2] <= r2_byte_2;
                            r2_expected[3] <= r2_byte_3;
                            r2_expected[4] <= r2_byte_4;
                            r2_expected[5] <= r2_byte_5;
                            r2_expected[6] <= r2_byte_6;
                            r2_expected[7] <= r2_byte_7;
                            calc_wd_cnt <= 8'd0;
                            state <= S_TX_ACCESS;
                            end
                        end else if (calc_wd_cnt >= CALC_WD_MAX) begin
                            // 看门狗超时 → 阻断
                            calc_wd_cnt <= 8'd0;
                            result_r    <= 2'd3;
                            state       <= S_BLOCKED;
                        end else begin
                            calc_wd_cnt <= calc_wd_cnt + 8'd1;
                        end
                    end
                end

                //====================================================
                // W4-P4 T1: S_KEY_MEASURE——PUF 测 key_seed 响应 → k_boot
                // 子态: 0=启动解码, 1=等cd_done, 2=测量窗, 3=打包k_boot
                // 复用 PUF 接口信号(cd_*/ra_*)和 puf_tbl_0/puf_freqs
                //====================================================
                S_KEY_MEASURE: begin
                    if (timeout_cnt >= PUF_WD_CYCLES) begin
                        key_valid_r <= 1'b0;
                        puf_ring_en_r <= 1'b0;
                        puf_measure_r <= 1'b0;
                        state    <= S_BLOCKED;
                        result_r <= 2'd3;
                    end else begin
                        case (km_substate)
                            2'd0: begin
                                // 启动 challenge_decode（固定 KEY_SEED）
                                puf_cd_seed_r  <= KDF_KEY_SEED_C;
                                puf_cd_start_r <= 1'b1;
                                km_substate    <= 2'd1;
                            end
                            2'd1: begin
                                // 等解码完成，捕获配对表
                                puf_cd_start_r <= 1'b0;
                                if (cd_done) begin
                                    puf_tbl_0    <= cd_pair_table;
                                    km_substate  <= 2'd2;
                                    puf_ring_en_r <= 1'b1;
                                    puf_win_idx  <= 5'd0;
                                    puf_win_cnt  <= 32'd0;
                                    puf_win_wait <= 1'b0;
                                    puf_measure_r <= 1'b0;
                                end
                            end
                            2'd2: begin
                                // 测量窗（热稳定+末窗，复用 S_PUF_MEASURE 逻辑）
                                if (!puf_win_wait) begin
                                    puf_measure_r <= 1'b1;
                                    if (puf_win_cnt >= MEASURE_CYCLES - 32'd1) begin
                                        puf_measure_r <= 1'b0;
                                        puf_win_cnt   <= 32'd0;
                                        puf_win_wait  <= 1'b1;
                                    end else begin
                                        puf_win_cnt <= puf_win_cnt + 32'd1;
                                    end
                                end else begin
                                    if (ra_done) begin
                                        if (puf_win_idx >= WARMUP_WINS) begin
                                            puf_freqs     <= ra_ring_freq;
                                            puf_ring_en_r <= 1'b0;
                                            puf_pack_idx  <= 6'd0;  // 从 byte 0 开始
                                            km_substate   <= 2'd3;
                                        end else begin
                                            puf_win_idx  <= puf_win_idx + 5'd1;
                                            puf_win_wait <= 1'b0;
                                        end
                                    end
                                end
                            end
                            2'd3: begin
                                // 打包 k_boot（8B = 1 种子的 64 比较位）
                                // 复用 puf_pack_byte（puf_pack_idx[5:3]=0 选 puf_tbl_0）
                                case (puf_pack_idx[2:0])
                                    3'd0: k_boot_reg[63:56] <= puf_pack_byte;
                                    3'd1: k_boot_reg[55:48] <= puf_pack_byte;
                                    3'd2: k_boot_reg[47:40] <= puf_pack_byte;
                                    3'd3: k_boot_reg[39:32] <= puf_pack_byte;
                                    3'd4: k_boot_reg[31:24] <= puf_pack_byte;
                                    3'd5: k_boot_reg[23:16] <= puf_pack_byte;
                                    3'd6: k_boot_reg[15:8]  <= puf_pack_byte;
                                    3'd7: k_boot_reg[7:0]   <= puf_pack_byte;
                                endcase
                                if (puf_pack_idx[2:0] == 3'd7) begin
                                    km_substate <= 2'd0;
                                    state       <= S_KEY_DERIVE;
                                    kdf_step    <= 2'd0;
                                    calc_wd_cnt <= 8'd0;
                                    timeout_cnt <= 32'd0;  // 分段预算
                                end else begin
                                    puf_pack_idx <= puf_pack_idx + 6'd1;
                                end
                            end
                        endcase
                    end
                end

                //====================================================
                // W4-P4 T1: S_KEY_DERIVE——Speck×2 KDF → key_reg
                // step 0=启动ct1, 1=等ct1+启动ct2, 2=等ct2+锁K
                //====================================================
                S_KEY_DERIVE: begin
                    if (timeout_cnt >= PUF_WD_CYCLES) begin
                        key_valid_r <= 1'b0;
                        state    <= S_BLOCKED;
                        result_r <= 2'd3;
                    end else begin
                        case (kdf_step)
                            2'd0: begin
                                // C4: k_boot 退化自检（全 0/全 1 = PUF 读数失效）
                                // 派生出的"看似合法"的坏 K 会被永久缓存，
                                // 故在此拒绝并保持 key_valid=0（下次 auth 重试）
                                if (k_boot_reg == 64'd0 ||
                                    k_boot_reg == 64'hFFFF_FFFF_FFFF_FFFF) begin
                                    key_valid_r <= 1'b0;
                                    state       <= S_BLOCKED;
                                    result_r    <= 2'd3;
                                end else begin
                                    // 启动第一次 Speck: key12 加密 KDF_PT1
                                    sp_start_w  <= 1'b1;
                                    kdf_step    <= 2'd1;
                                    calc_wd_cnt <= 8'd1;
                                end
                            end
                            2'd1: begin
                                sp_start_w <= 1'b0;
                                if (sp_done) begin
                                    kdf_ct1     <= sp_ciphertext;
                                    sp_start_w  <= 1'b1;  // 立即启动第二次
                                    kdf_step    <= 2'd2;
                                    calc_wd_cnt <= 8'd1;
                                end else if (calc_wd_cnt >= CALC_WD_MAX) begin
                                    key_valid_r <= 1'b0;
                                    state <= S_BLOCKED; result_r <= 2'd3;
                                    calc_wd_cnt <= 8'd0;
                                end else begin
                                    calc_wd_cnt <= calc_wd_cnt + 8'd1;
                                end
                            end
                            2'd2: begin
                                sp_start_w <= 1'b0;
                                if (sp_done) begin
                                    // K = ct1(8B) + ct2[0:3](4B) = 12B
                                    // 字节映射: key_reg_r[8*i +: 8] = K_byte[i]
                                    // ct byte 0 = ct[39:32], ct byte 1 = ct[47:40]...
                                    key_reg_r[7:0]   <= kdf_ct1[39:32];
                                    key_reg_r[15:8]  <= kdf_ct1[47:40];
                                    key_reg_r[23:16] <= kdf_ct1[55:48];
                                    key_reg_r[31:24] <= kdf_ct1[63:56];
                                    key_reg_r[39:32] <= kdf_ct1[7:0];
                                    key_reg_r[47:40] <= kdf_ct1[15:8];
                                    key_reg_r[55:48] <= kdf_ct1[23:16];
                                    key_reg_r[63:56] <= kdf_ct1[31:24];
                                    key_reg_r[71:64] <= sp_ciphertext[39:32];
                                    key_reg_r[79:72] <= sp_ciphertext[47:40];
                                    key_reg_r[87:80] <= sp_ciphertext[55:48];
                                    key_reg_r[95:88] <= sp_ciphertext[63:56];
                                    key_valid_r <= 1'b1;
                                    kdf_step    <= 2'd0;
                                    calc_wd_cnt <= 8'd0;
                                    state       <= S_CALC_R2;  // 派生完成，进正常认证
                                end else if (calc_wd_cnt >= CALC_WD_MAX) begin
                                    key_valid_r <= 1'b0;
                                    state <= S_BLOCKED; result_r <= 2'd3;
                                    calc_wd_cnt <= 8'd0;
                                end else begin
                                    calc_wd_cnt <= calc_wd_cnt + 8'd1;
                                end
                            end
                        endcase
                    end
                end

                //====================================================
                S_BLOCKED: begin
                    // 阻断冷却（W3 简化：立即回 IDLE；W3+ 加冷却计数器）
                    state <= S_IDLE;
                end

                default: state <= S_IDLE;
            endcase

            // W4-P4 T2: seed_load 单拍脉冲同步重装载（ro_entropy 完成后由
            // w3_top 触发）。必须住在主 FSM always 块内——c2_counter 被两个
            // 独立过程块驱动 = multi-driven net（Vivado Synth 8-6859 CRITICAL，
            // 硬件行为未定义；由 AMD Vivado MCP 综合检查发现）。放在 case 之后
            // 确保同拍优先于 S_CALC_R2 的递增。TB 恒 0 → initial 值保持。
            if (seed_load) begin
                for (j = 0; j < 8; j = j + 1)
                    c2_counter[j] <= c2_boot_seed[8*j +: 8];
            end
        end
    end

endmodule