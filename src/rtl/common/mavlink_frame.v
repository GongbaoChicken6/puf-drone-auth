//============================================================================
// mavlink_frame.v -- HF-IDA MAVLink v2 帧构造器
//----------------------------------------------------------------------------
// 职责（docs/protocol_contract.md §6）：
//   把 8-bit 载荷字节流组装成完整 MAVLink v2 帧：
//     [STX][LEN][IFLAG][CFLAG][SEQ][SYSID][COMPID][MSGIDx3][PAYLOAD][CRC16LE]
//   CRC 由内嵌 crc16_mcrf4xx 边发边算（计算域 = 帧[1..9]+载荷+CRC_EXTRA）。
//
// 使用时序（握手）：
//   1. 上层置 start=1 一拍，同时给出 msg_id/payload_len/payload 首字节准备
//   2. 本模块逐字节输出 frame_byte + frame_valid，上层（或 uart_tx）按 valid 收
//   3. 全帧发完 frame_done 拉高一拍；frame_crc 给出本帧 CRC 值（调试/自检用）
//
// 约束：
//   - 载荷 <= 32B（MAX_PAYLOAD）；MSGID 必须在契约表内，未知 msgid 拒绝启动
//   - SEQ 由本模块内部自增（8-bit 回绕），与 protocol.py 独立计数对齐语义
//   - 字节序：msgid 3B 小端拆分；CRC 2B 小端输出（低字节先发）
//
// 黄金验证（tb_mavlink_frame.v）：
//   构造 msgid=0x0092 RESPONSE_R1（seq=0x44, sysid=1, compid=2, 4x8B 载荷）
//   输出必须逐字节等于契约 §4 黄金帧（44B，含 CRC a7 15）
//============================================================================

module mavlink_frame # (
    parameter MAX_PAYLOAD = 32                        // 载荷上限（契约 §1）
) (
    input  wire        clk          ,                 // 系统时钟
    input  wire        rst          ,                 // 高有效同步复位
    // -- 上层命令接口 ------------------------------------------------------
    input  wire        start        ,                 // 启动组帧（单拍，载荷首字节须已就位）
    input  wire [23:0] msg_id       ,                 // 消息 ID（契约 §3 六个合法值）
    input  wire [5:0]  payload_len  ,                 // 载荷字节数（0~32，6-bit 才能装下 32）
    input  wire [7:0]  payload_byte ,                 // 载荷字节流（发拍给 1 字节）
    input  wire        payload_valid,                 // 载荷字节有效
    input  wire [7:0]  seq_num      ,                 // 序号（上层维护，8-bit 回绕）
    input  wire [7:0]  sys_id       ,                 // 系统 ID（默认 8'h01）
    input  wire [7:0]  comp_id      ,                 // 组件 ID（默认 8'h02）
    // -- 帧输出接口（喂 uart_tx: frame_valid->tx_valid）---------------------
    output reg  [7:0]  frame_byte   ,                 // 帧字节流输出
    output reg         frame_valid  ,                 // 帧字节有效（单拍）
    output reg         frame_done   ,                 // 全帧完成脉冲
    output wire [15:0] frame_crc    ,                 // 本帧 CRC 值（完成时有效）
    output reg         frame_err                      // 参数非法（未知 msgid/载荷超限）
);

    //------------------------------------------------------------------------
    // localparam：契约 §3 的六个合法消息 ID 与对应 CRC_EXTRA
    //------------------------------------------------------------------------
    localparam [23:0] ID_ACCESS_REQ = 24'h0090;       // ACCESS_REQUEST
    localparam [23:0] ID_CHALLENGE  = 24'h0091;       // CHALLENGE
    localparam [23:0] ID_RESPONSE   = 24'h0092;       // RESPONSE_R1
    localparam [23:0] ID_RESULT     = 24'h0093;       // RESULT
    localparam [23:0] ID_CONFIRM    = 24'h0094;       // CONFIRM
    localparam [23:0] ID_EXTRA      = 24'h0095;       // EXTRA_CHALLENGE

    //------------------------------------------------------------------------
    // 状态机
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

    //------------------------------------------------------------------------
    // CRC_EXTRA 查表（契约 §6，未知 msgid -> 0x00 由 IDLE 期拒绝兜底）
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
    // msgid 合法性（IDLE 期用 start 时的组合值判定）
    //------------------------------------------------------------------------
    wire id_legal = (msg_id == ID_ACCESS_REQ) || (msg_id == ID_CHALLENGE)
                 || (msg_id == ID_RESPONSE ) || (msg_id == ID_RESULT   )
                 || (msg_id == ID_CONFIRM  ) || (msg_id == ID_EXTRA    );
    wire len_ok   = (payload_len <= MAX_PAYLOAD);  // 整数比较（勿对参数位切片：32[4:0]==0 陷阱）
    wire cmd_ok   = id_legal && len_ok;

    //------------------------------------------------------------------------
    // CRC 核例化：帧头 9 字节由本模块在 HEADER 态逐字节喂入，
    // 载荷字节透传给 UART 的同时同拍喂入，CRC_EXTRA 在进入 CRC_LO 前补喂。
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
            4'd1:    hdr_byte = {3'h0, len_r};              // LEN
            4'd2:    hdr_byte = 8'h00;                      // incompat flags
            4'd3:    hdr_byte = 8'h00;                      // compat flags
            4'd4:    hdr_byte = seq_num;                    // SEQ（上层给）
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
    assign frame_crc = crc_val;                         // S_DONE 时即最终 CRC 值

    wire [7:0] crc_byte_lo = crc_val[7:0];
    wire [7:0] crc_byte_hi = crc_val[15:8];

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
                            crc_init <= 1'b1;         // CRC 载入 FFFF（下一拍发头[0]外的首域字节）
                            state    <= S_HEADER;
                        end
                    end
                end
                //------------------------------------------------
                // HEADER 态：发 10 字节帧头。
                // 注意 STX 不进 CRC，故 hdr_cnt==0 时只发不喂 CRC。
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
                // PAYLOAD 态：上游给 1 字节透传 1 字节，同时喂 CRC
                //------------------------------------------------
                S_PAYLOAD: begin
                    if (payload_valid) begin
                        frame_byte  <= payload_byte;
                        frame_valid <= 1'b1;
                        crc_din     <= payload_byte;
                        crc_dv      <= 1'b1;
                        pay_cnt     <= pay_cnt + 6'd1;
                        if (pay_cnt + 6'd1 == len_r) begin
                            state <= S_CRC_LO;         // 最后 1 字节已锁存
                        end
                    end
                end
                //------------------------------------------------
                // 载荷收完 -> 补喂 CRC_EXTRA（1 拍）
                //------------------------------------------------
                S_CRC_LO: begin
                    crc_din     <= crc_extra;           // 补喂 CRC_EXTRA
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
