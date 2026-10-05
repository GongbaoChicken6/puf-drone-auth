//============================================================================
// mavlink_frame.v -- HF-IDA MAVLink v2 帧构造器
//----------------------------------------------------------------------------
// 职责（docs/protocol_contract.md §6）：
//   把 8-bit 载荷字节流组装成完整 MAVLink v2 帧：
//     [STX][LEN][IFLAG][CFLAG][SEQ][SYSID][COMPID][MSGIDx3][PAYLOAD][CRC16LE]
//   CRC 由内嵌 crc16_mcrf4xx 边发边算（计算域 = 帧[1..9]+载荷+CRC_EXTRA）。
//
// ⚠ 集成红线（审查 F1/P0，违反必丢字节）：
//   本模块 frame_valid 以每拍 1 字节速率输出（44B 帧 44 拍发完），
//   而 uart_tx 每字节需 ~8680 拍（115200@100MHz）且忙时静默丢弃 tx_valid。
//   **禁止 frame_valid 直连 tx_valid** —— 必须经 ≥12B（建议 64B）FIFO：
//     FIFO 写使能 = frame_valid；FIFO 读节奏 = uart_tx 每完成 1 字节取 1 字节。
//
// 握手契约（审查 F2/F3，详见契约 §6）：
//   1. start 仅在 IDLE 采样（busy=0 时），单拍；帧中 start 被静默忽略
//   2. msg_id/payload_len 在 start 拍锁存；seq_num/sys_id/comp_id 从 start
//      前一拍到 frame_done 必须保持稳定
//   3. payload_valid 只允许在 payload_phase=1 期间断言——窗口外字节被
//      静默丢弃（并有 payload_phase 输出供上游同步，TB 不再需要数拍）
//   4. S_PAYLOAD 超时（PAYLOAD_TIMEOUT 拍无字节）→ frame_err 脉冲 + 回
//      IDLE，杜绝"载荷短缺永久挂死"
//   5. frame_done 滞后最后字节 1 拍；frame_err 是单拍脉冲，上游必须粘滞捕获
//
// 参数化：
//   - PAYLOAD_TIMEOUT：载荷段无字节超时阈值（拍）。挂上游仿真可调小。
//============================================================================

module mavlink_frame # (
    parameter MAX_PAYLOAD     = 32    ,  // 载荷上限（契约 §1）
    parameter PAYLOAD_TIMEOUT = 1024     // 载荷段无字节超时（拍）
) (
    input  wire        clk          ,                 // 系统时钟
    input  wire        rst          ,                 // 高有效同步复位
    // -- 上层命令接口 ------------------------------------------------------
    input  wire        start        ,                 // 启动组帧（单拍，仅 busy=0 时被采样）
    input  wire [23:0] msg_id       ,                 // 消息 ID（契约 §3 六个合法值）
    input  wire [5:0]  payload_len  ,                 // 载荷字节数（0~32，6-bit 才能装下 32）
    input  wire [7:0]  payload_byte ,                 // 载荷字节流（仅 payload_phase=1 期间采样）
    input  wire        payload_valid,                 // 载荷字节有效
    input  wire [7:0]  seq_num      ,                 // 序号（上层维护；start→frame_done 保持稳定）
    input  wire [7:0]  sys_id       ,                 // 系统 ID（上层显式驱动，本模块无默认值）
    input  wire [7:0]  comp_id      ,                 // 组件 ID（同上）
    // -- 状态指示（给 terminal_fsm 的握手信号）------------------------------
    output wire        busy         ,                 // 组帧进行中（start 被接受后到回 IDLE 前）
    output wire        payload_phase,                 // 载荷采样窗口（=1 时 payload_valid 才有效）
    // -- 帧输出接口（→ FIFO → uart_tx，禁止直连！）--------------------------
    output reg  [7:0]  frame_byte   ,                 // 帧字节流输出
    output reg         frame_valid  ,                 // 帧字节有效（单拍）
    output reg         frame_done   ,                 // 全帧完成脉冲（滞后最后字节 1 拍）
    output wire [15:0] frame_crc    ,                 // 本帧 CRC 值（frame_done 时有效）
    output reg         frame_err                       // 参数非法/载荷超时（单拍，上游粘滞捕获）
);

    //------------------------------------------------------------------------
    // localparam：契约 §3 的六个合法消息 ID
    // ⚠ CRC_EXTRA 占位表（0x5A~0x5F）由 tools/check_contract_sync.py 与
    //   protocol.py._CRC_EXTRA 联动校验——hfida.xml 生成后须两侧同步更新。
    //------------------------------------------------------------------------
    localparam [23:0] ID_ACCESS_REQ = 24'h0090;       // ACCESS_REQUEST
    localparam [23:0] ID_CHALLENGE  = 24'h0091;       // CHALLENGE
    localparam [23:0] ID_RESPONSE   = 24'h0092;       // RESPONSE_R1
    localparam [23:0] ID_RESULT     = 24'h0093;       // RESULT
    localparam [23:0] ID_CONFIRM    = 24'h0094;       // CONFIRM
    localparam [23:0] ID_EXTRA      = 24'h0095;       // EXTRA_CHALLENGE

    //------------------------------------------------------------------------
    // 状态机（3-bit 恰好 8 态）
    //------------------------------------------------------------------------
    localparam [2:0] S_IDLE     = 3'd0,               // 等待 start
                     S_HEADER  = 3'd1,               // 发 10 字节帧头
                     S_PAYLOAD = 3'd2,               // 收载荷并透传
                     S_CRC_LO  = 3'd3,               // 补喂 CRC_EXTRA
                     S_CRC_WAIT= 3'd4,               // 等 1 拍让 EXTRA 完成累积
                     S_CRC_EMIT= 3'd5,               // 发 CRC 低字节（此时值已含 EXTRA）
                     S_CRC_HI  = 3'd6,               // 发 CRC 高字节
                     S_DONE    = 3'd7;               // frame_done 滞后最后字节 1 拍（防竞态）

    reg [2:0]  state    = S_IDLE;
    reg [3:0]  hdr_cnt  = 4'd0;                       // 帧头字节计数 0..9
    reg [5:0]  pay_cnt  = 6'd0;                       // 已收载荷字节计数
    reg [23:0] msgid_r  = 24'h0;                      // 锁存的 msgid
    reg [5:0]  len_r    = 6'd0;                       // 锁存的载荷长度
    reg [10:0] to_cnt   = 11'd0;                      // S_PAYLOAD 超时计数器

    //------------------------------------------------------------------------
    // CRC_EXTRA 查表（契约 §3；default 0x00 不可达——IDLE 期已拒绝未知 ID）
    //------------------------------------------------------------------------
    reg [7:0] crc_extra;
    always @(*) begin
        case (msgid_r)
            ID_ACCESS_REQ: crc_extra = 8'h5A;
            ID_CHALLENGE : crc_extra = 8'h5B;
            ID_RESPONSE  : crc_extra = 8'h5C;
            ID_RESULT    : crc_extra = 8'h5D;
            ID_CONFIRM   : crc_extra = 8'h5E;
            ID_EXTRA     : crc_extra = 8'h5F;
            default      : crc_extra = 8'h00;
        endcase
    end

    //------------------------------------------------------------------------
    // msgid 合法性（IDLE 期用 start 当拍值判定）
    //------------------------------------------------------------------------
    wire id_legal = (msg_id == ID_ACCESS_REQ) || (msg_id == ID_CHALLENGE)
                 || (msg_id == ID_RESPONSE ) || (msg_id == ID_RESULT   )
                 || (msg_id == ID_CONFIRM  ) || (msg_id == ID_EXTRA    );
    wire len_ok   = (payload_len <= MAX_PAYLOAD);  // 整数比较（勿对参数位切片：32[4:0]==0 陷阱）
    wire cmd_ok   = id_legal && len_ok;

    //------------------------------------------------------------------------
    // CRC 核例化：帧[1..9] 与载荷、CRC_EXTRA 按帧序逐字节喂入
    //------------------------------------------------------------------------
    reg         crc_init = 1'b0;
    reg         crc_dv   = 1'b0;
    reg  [7:0]  crc_din  = 8'h00;
    wire [15:0] crc_val;

    crc16_mcrf4xx u_crc (
        .clk       (clk      ),
        .rst       (rst      ),
        .init      (crc_init ),
        .din       (crc_din  ),
        .din_valid (crc_dv   ),
        .crc       (crc_val  ),
        .busy      (         )  // output，未使用
    );

    //------------------------------------------------------------------------
    // 帧头字节生成（组合：按 hdr_cnt 选择当前头字节）
    //------------------------------------------------------------------------
    reg [7:0] hdr_byte;
    always @(*) begin
        case (hdr_cnt)
            4'd0:    hdr_byte = 8'hFD;                      // STX
            4'd1:    hdr_byte = {2'h0, len_r};              // LEN（2+6=8-bit，无截断）
            4'd2:    hdr_byte = 8'h00;                      // incompat flags
            4'd3:    hdr_byte = 8'h00;                      // compat flags
            4'd4:    hdr_byte = seq_num;                    // SEQ（上层给，start 期须稳定）
            4'd5:    hdr_byte = sys_id;                     // SYSID
            4'd6:    hdr_byte = comp_id;                    // COMPID
            4'd7:    hdr_byte = msgid_r[7:0];               // MSGID LSB
            4'd8:    hdr_byte = msgid_r[15:8];              // MSGID MID
            4'd9:    hdr_byte = msgid_r[23:16];             // MSGID MSB
            default: hdr_byte = 8'h00;
        endcase
    end

    //------------------------------------------------------------------------
    // 帧尾 CRC 字节（小端：低字节在前）
    //------------------------------------------------------------------------
    wire [7:0] crc_byte_lo = crc_val[7:0];
    wire [7:0] crc_byte_hi = crc_val[15:8];

    assign frame_crc = crc_val;                         // S_DONE 时即最终 CRC 值
    assign busy      = (state != S_IDLE);
    assign payload_phase = (state == S_PAYLOAD);        // 上游同步窗口

    //========================================================================
    // 主状态机
    //========================================================================
    always @(posedge clk) begin
        if (rst) begin
            state       <= S_IDLE;
            hdr_cnt     <= 4'd0;
            pay_cnt     <= 6'd0;
            msgid_r     <= 24'h0;
            len_r       <= 6'd0;
            to_cnt      <= 11'd0;
            frame_byte  <= 8'h00;
            frame_valid <= 1'b0;
            frame_done  <= 1'b0;
            frame_err   <= 1'b0;
            crc_init    <= 1'b0;
            crc_dv      <= 1'b0;
            crc_din     <= 8'h00;
        end else begin
            // 默认单拍脉冲清零
            frame_valid <= 1'b0;
            frame_done  <= 1'b0;
            frame_err   <= 1'b0;
            crc_init    <= 1'b0;
            crc_dv      <= 1'b0;

            case (state)
                //------------------------------------------------
                S_IDLE: begin
                    if (start) begin
                        if (!cmd_ok) begin
                            frame_err <= 1'b1;        // 非法参数：拒绝并报错
                        end else begin
                            msgid_r  <= msg_id;       // 锁存参数
                            len_r    <= payload_len;
                            hdr_cnt  <= 4'd0;
                            pay_cnt  <= 6'd0;
                            to_cnt   <= 11'd0;
                            crc_init <= 1'b1;         // CRC 载入 FFFF
                            state    <= S_HEADER;
                        end
                    end
                end
                //------------------------------------------------
                // HEADER 态：发 10 字节帧头。STX 不进 CRC（hdr_cnt==0 只发不喂）
                //------------------------------------------------
                S_HEADER: begin
                    frame_byte  <= hdr_byte;
                    frame_valid <= 1'b1;
                    if (hdr_cnt != 4'd0) begin          // 帧[1..9] 进 CRC
                        crc_din <= hdr_byte;
                        crc_dv  <= 1'b1;
                    end
                    if (hdr_cnt == 4'd9) begin
                        hdr_cnt <= 4'd0;
                        state   <= (len_r == 6'd0) ? S_CRC_LO : S_PAYLOAD;
                    end else begin
                        hdr_cnt <= hdr_cnt + 4'd1;
                    end
                end
                //------------------------------------------------
                // PAYLOAD 态：payload_phase=1 窗口。超时保护杜绝挂死。
                //------------------------------------------------
                S_PAYLOAD: begin
                    if (payload_valid) begin
                        to_cnt      <= 11'd0;          // 有字节就清超时
                        frame_byte  <= payload_byte;
                        frame_valid <= 1'b1;
                        crc_din     <= payload_byte;
                        crc_dv      <= 1'b1;
                        pay_cnt     <= pay_cnt + 6'd1;
                        if (pay_cnt + 6'd1 == len_r) begin
                            state <= S_CRC_LO;         // 最后 1 字节已锁存
                        end
                    end else begin
                        to_cnt <= to_cnt + 11'd1;
                        if (to_cnt >= PAYLOAD_TIMEOUT - 11'd1) begin
                            frame_err <= 1'b1;         // 载荷短缺：报错而非挂死
                            state     <= S_IDLE;
                        end
                    end
                end
                //------------------------------------------------
                // 载荷收完 -> 补喂 CRC_EXTRA（1 拍）
                //------------------------------------------------
                S_CRC_LO: begin
                    crc_din     <= crc_extra;
                    crc_dv      <= 1'b1;
                    state       <= S_CRC_WAIT;
                end
                //------------------------------------------------
                // CRC_WAIT: 本拍内 CRC 核完成 EXTRA 累积（末沿生效）
                //------------------------------------------------
                S_CRC_WAIT: begin
                    state       <= S_CRC_EMIT;
                end
                //------------------------------------------------
                // CRC_EMIT: 采样 CRC 低字节（此刻 crc_val 已含 EXTRA）
                //------------------------------------------------
                S_CRC_EMIT: begin
                    frame_byte  <= crc_byte_lo;
                    frame_valid <= 1'b1;
                    state       <= S_CRC_HI;
                end
                S_CRC_HI: begin
                    frame_byte  <= crc_byte_hi;
                    frame_valid <= 1'b1;
                    state       <= S_DONE;
                end
                //------------------------------------------------
                // DONE: 滞后最后字节 1 拍再报完成（收集器先记账）
                //------------------------------------------------
                S_DONE: begin
                    frame_done  <= 1'b1;
                    state       <= S_IDLE;
                end
                //------------------------------------------------
                default: state <= S_IDLE;
            endcase
        end
    end

endmodule
