//============================================================================
// frame_parser.v -- HF-IDA MAVLink v2 帧解析器（接收侧）
//----------------------------------------------------------------------------
// 职责：从字节流中提取完整 MAVLink v2 帧，CRC 校验后上报 msg_id + 载荷。
//   是 mavlink_frame.v（发送侧）的镜像，共享 crc16_mcrf4xx 核与契约。
//
// 容错设计（契约 §6.1 第 6 条，审查 B-F12）：
//   - S_SEARCH 态忽略一切非 STX 字节（电台噪声天然容忍）
//   - LEN > MAX_PAYLOAD 或未知 msgid → frame_err + 回 S_SEARCH
//   - CRC 不匹配 → frame_err + 回 S_SEARCH（重新同步）
//   - 超时（PARSER_TIMEOUT 拍无字节）→ 回 S_SEARCH（防截断帧挂死）
//
// 载荷缓冲读法（CRC 通过后才可读）：
//   frame_ok 脉冲后，用 payload_rd_addr 读 payload_rd_data（组合逻辑）
//   载荷在下一帧开始前保持有效（帧中不复位缓冲）。
//============================================================================

module frame_parser # (
    parameter MAX_PAYLOAD   = 32   ,  // 载荷上限（契约 §1）
    parameter PARSER_TIMEOUT = 4096   // 非搜索态无字节超时（拍）
) (
    input  wire        clk       ,   // 系统时钟
    input  wire        rst       ,   // 高有效同步复位
    // -- 字节输入（接 uart_rx 的 rx_byte / rx_valid）------------------------
    input  wire [7:0]  rx_byte   ,   // 收到的字节
    input  wire        rx_valid  ,   // 字节有效（单拍脉冲）
    // -- 帧结果输出 --------------------------------------------------------
    output reg  [23:0] msg_id    ,   // 消息 ID（frame_ok 时有效）
    output reg  [7:0]  pay_len   ,   // 载荷长度（frame_ok 时有效）
    output reg         frame_ok  ,   // 完整合法帧（单拍脉冲）
    output reg         frame_err ,   // CRC 错 / LEN 超限 / 未知 ID（单拍脉冲）
    output wire        busy      ,   // 解析进行中（=1 表示帧未完成）
    // -- 载荷缓冲读口（frame_ok 后有效，组合逻辑）---------------------------
    input  wire [4:0]  payload_rd_addr,  // 字节地址 0~31
    output wire [7:0]  payload_rd_data  // 组合读出
);

    //------------------------------------------------------------------------
    // localparam：消息 ID（与 mavlink_frame 共享，契约 §3）
    //------------------------------------------------------------------------
    localparam [23:0] ID_ACCESS_REQ = 24'h0090;
    localparam [23:0] ID_CHALLENGE  = 24'h0091;
    localparam [23:0] ID_RESPONSE   = 24'h0092;
    localparam [23:0] ID_RESULT     = 24'h0093;
    localparam [23:0] ID_CONFIRM    = 24'h0094;
    localparam [23:0] ID_EXTRA      = 24'h0095;

    //------------------------------------------------------------------------
    // 状态机
    //------------------------------------------------------------------------
    localparam [2:0] S_SEARCH  = 3'd0,   // 搜 STX，忽略一切其他字节
                     S_HEADER  = 3'd1,   // 收帧头 9 字节（STX 后）
                     S_PAYLOAD = 3'd2,   // 收载荷（LEN 字节）
                     S_RX_CRC  = 3'd3,   // 收帧尾 2 字节 CRC
                     S_CHECK   = 3'd4;   // 本地 CRC vs 收到 CRC

    reg [2:0]  state   = S_SEARCH;
    reg [3:0]  hdr_cnt = 4'd0;           // 帧头计数 0..8（9 字节）
    reg [5:0]  pay_cnt = 6'd0;           // 已收载荷字节
    reg [7:0]  len_r   = 8'd0;           // 从帧头提取的 LEN（完整 8-bit）
    reg [23:0] msgid_r = 24'h0;          // 从帧头提取的 MSGID
    reg [1:0]  crc_cnt = 2'd0;           // 收到几个 CRC 字节
    reg [7:0]  rx_crc_lo = 8'h00;        // 收到的 CRC 低字节
    reg [7:0]  rx_crc_hi = 8'h00;        // 收到的 CRC 高字节
    reg [12:0] to_cnt   = 13'd0;         // 无字节超时计数

    //------------------------------------------------------------------------
    // 载荷缓冲（32 字节寄存器阵列）
    //------------------------------------------------------------------------
    reg [7:0] pay_buf [0:31];
    integer   k;
    initial for (k = 0; k < 32; k = k + 1) pay_buf[k] = 8'h00;

    assign payload_rd_data = pay_buf[payload_rd_addr[4:0]];

    //------------------------------------------------------------------------
    // CRC 核例化：帧头[1..9] + 载荷 + EXTRA 逐字节喂入
    //------------------------------------------------------------------------
    reg        crc_init = 1'b0;
    reg        crc_dv   = 1'b0;
    reg  [7:0] crc_din  = 8'h00;
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
    // CRC_EXTRA 查表（与 mavlink_frame 相同，契约 §3）
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

    wire id_legal = (msgid_r == ID_ACCESS_REQ) || (msgid_r == ID_CHALLENGE)
                 || (msgid_r == ID_RESPONSE  ) || (msgid_r == ID_RESULT  )
                 || (msgid_r == ID_CONFIRM   ) || (msgid_r == ID_EXTRA   );

    assign busy = (state != S_SEARCH);

    //------------------------------------------------------------------------
    // 帧头字节暂存（逐字节收，不并行输出）
    //   hdr[0]=LEN  hdr[1]=IFLAG  hdr[2]=CFLAG  hdr[3]=SEQ
    //   hdr[4]=SYSID  hdr[5]=COMPID  hdr[6..8]=MSGID 小端
    //------------------------------------------------------------------------
    reg [7:0] hdr_buf [0:8];

    // 提取 msgid（三个字节收齐后拼接）
    wire hdr_msgid_ready = (hdr_cnt == 4'd8);   // 已收完 MSGID MSB

    //========================================================================
    // 主状态机
    //========================================================================
    always @(posedge clk) begin
        if (rst) begin
            state      <= S_SEARCH;
            hdr_cnt    <= 4'd0;
            pay_cnt    <= 6'd0;
            len_r      <= 6'd0;
            msgid_r    <= 24'h0;
            crc_cnt    <= 2'd0;
            rx_crc_lo  <= 8'h00;
            rx_crc_hi  <= 8'h00;
            to_cnt     <= 13'd0;
            msg_id     <= 24'h0;
            pay_len    <= 6'd0;
            frame_ok   <= 1'b0;
            frame_err  <= 1'b0;
            crc_init   <= 1'b0;
            crc_dv     <= 1'b0;
            crc_din    <= 8'h00;
        end else begin
            // 默认单拍脉冲清零
            frame_ok  <= 1'b0;
            frame_err <= 1'b0;
            crc_init  <= 1'b0;
            crc_dv    <= 1'b0;

            // 超时计数：非搜索态且无字节 → 递增；有字节或搜索态 → 清零
            if (state != S_SEARCH && !rx_valid) begin
                to_cnt <= to_cnt + 13'd1;
                if (to_cnt >= PARSER_TIMEOUT - 13'd1) begin
                    frame_err <= 1'b1;             // 超时：帧不完整
                    state     <= S_SEARCH;
                    to_cnt    <= 13'd0;
                end
            end else begin
                to_cnt <= 13'd0;
            end

            case (state)
                //------------------------------------------------
                // 搜索 STX。所有非 0xFD 字节被静默丢弃（噪声容忍）。
                //------------------------------------------------
                S_SEARCH: begin
                    if (rx_valid && rx_byte == 8'hFD) begin
                        crc_init <= 1'b1;           // CRC 载入 FFFF
                        hdr_cnt  <= 4'd0;
                        pay_cnt  <= 6'd0;
                        crc_cnt  <= 2'd0;
                        state    <= S_HEADER;
                    end
                end

                //------------------------------------------------
                // 帧头 9 字节（STX 后）：全部喂 CRC + 提取字段
                //------------------------------------------------
                S_HEADER: begin
                    if (rx_valid) begin
                        hdr_buf[hdr_cnt] <= rx_byte;
                        crc_din <= rx_byte;         // 帧[1..9] 全进 CRC
                        crc_dv  <= 1'b1;

                        case (hdr_cnt)
                            4'd0: len_r <= rx_byte;               // LEN（完整 8-bit）
                            4'd6: msgid_r[7:0]   <= rx_byte;       // MSGID LSB
                            4'd7: msgid_r[15:8]  <= rx_byte;       // MSGID MID
                            4'd8: msgid_r[23:16] <= rx_byte;       // MSGID MSB
                            default: ;                              // flags/seq/id 忽略
                        endcase

                        if (hdr_cnt == 4'd8) begin
                            hdr_cnt <= 4'd0;
                            // LEN 合法性：用 len_r（hdr_cnt==0 时锁存，此刻已有效 7 拍）
                            // 本协议所有消息载荷 5~32B，LEN==0 或 >32 均非法
                            if (len_r == 8'd0 || len_r > 8'd32) begin
                                frame_err <= 1'b1;
                                state     <= S_SEARCH;
                            end else begin
                                state <= S_PAYLOAD;
                            end
                        end else begin
                            hdr_cnt <= hdr_cnt + 4'd1;
                        end
                    end
                end

                //------------------------------------------------
                // 载荷：存缓冲 + 喂 CRC
                //------------------------------------------------
                S_PAYLOAD: begin
                    if (rx_valid) begin
                        pay_buf[pay_cnt[4:0]] <= rx_byte;
                        crc_din <= rx_byte;
                        crc_dv  <= 1'b1;
                        pay_cnt <= pay_cnt + 6'd1;
                        if (pay_cnt + 6'd1 == len_r) begin
                            // 最后一个载荷字节 → 下一态收 CRC
                            state <= S_RX_CRC;
                        end
                    end
                end

                //------------------------------------------------
                // 收帧尾 2 字节 CRC + 同时补喂 CRC_EXTRA
                // 时序：第 1 拍收低字节 & 喂 EXTRA；第 2 拍收高字节 & CRC 已更新
                //------------------------------------------------
                S_RX_CRC: begin
                    if (rx_valid) begin
                        if (crc_cnt == 2'd0) begin
                            rx_crc_lo <= rx_byte;       // 存低字节
                            crc_din   <= crc_extra;     // 同时喂 EXTRA
                            crc_dv    <= 1'b1;
                            crc_cnt   <= 2'd1;
                        end else begin
                            rx_crc_hi <= rx_byte;       // 存高字节
                            crc_cnt   <= 2'd2;
                            state     <= S_CHECK;       // 转校验
                        end
                    end
                end

                //------------------------------------------------
                // 校验：本地 CRC vs 收到 CRC（此刻 crc_val 已含 EXTRA）
                //------------------------------------------------
                S_CHECK: begin
                    if (crc_val[7:0]  == rx_crc_lo &&
                        crc_val[15:8] == rx_crc_hi && id_legal) begin
                        msg_id   <= msgid_r;
                        pay_len  <= len_r;
                        frame_ok <= 1'b1;
                    end else begin
                        frame_err <= 1'b1;              // CRC 不匹配或未知 ID
                    end
                    state <= S_SEARCH;                  // 无论成败回搜索
                end

                default: state <= S_SEARCH;
            endcase
        end
    end

endmodule
