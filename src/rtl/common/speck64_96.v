//============================================================================
// speck64_96.v -- Speck64/96 轻量级分组密码（NSA 2013 规范）
//----------------------------------------------------------------------------
// 字长 32 / 块 64 / 密钥 96 / 26 轮 ARX
// 4 态 FSM：IDLE → KEY_EXPAND → ENCRYPT → IDLE
//============================================================================

module speck64_96 (
    input  wire        clk          ,
    input  wire        rst          ,
    input  wire        start        ,
    input  wire [95:0] key_in       ,
    input  wire [63:0] plaintext_in ,
    output wire [63:0] ciphertext_out,
    output wire        done         ,
    output wire        busy
);

    localparam ROUNDS = 26;
    localparam RW     = 5;

    localparam [1:0] S_IDLE = 2'd0;
    localparam [1:0] S_KEY  = 2'd1;
    localparam [1:0] S_ENC  = 2'd2;

    reg [1:0]     state    = S_IDLE;
    reg [RW-1:0]  rd_cnt   = {RW{1'b0}};

    // 轮密钥：26 × 32 = 832 FF（扁平存储，变址读取）
    reg [ROUNDS*32-1:0] rk_flat = {(ROUNDS*32){1'b0}};

    // L 滚动窗口（只需 2 个工作寄存器，不用存 27 个）
    reg [31:0] l_0 = 32'd0;   // l[i]
    reg [31:0] l_1 = 32'd0;   // l[i+1]

    // 加密数据
    reg [31:0] x_r = 32'd0;
    reg [31:0] y_r = 32'd0;

    // 输出
    reg [63:0] ct_r     = 64'd0;
    reg        done_r   = 1'b0;

    assign ciphertext_out = ct_r;
    assign done           = done_r;
    assign busy           = (state != S_IDLE);

    //========================================================================
    // 密钥扩展组合逻辑
    //========================================================================
    wire [31:0] k_cur = rk_flat[rd_cnt*32 +: 32];       // k[i]（当前轮密钥）
    wire [31:0] l_ror = {l_0[7:0], l_0[31:8]};           // ROR(l_0, 8)
    wire [31:0] sum_kl = l_ror + k_cur;                  // ROR(l,8) + k[i]
    wire [31:0] l_new  = sum_kl ^ {27'd0, rd_cnt[RW-1:0]}; // XOR i
    wire [31:0] k_rol  = {k_cur[28:0], k_cur[31:29]};    // ROL(k, 3)
    wire [31:0] k_new  = k_rol ^ l_new;                  // 新轮密钥

    //========================================================================
    // 加密轮组合逻辑
    //========================================================================
    wire [31:0] enc_k  = rk_flat[rd_cnt*32 +: 32];       // 当前轮密钥
    wire [31:0] x_ror  = {x_r[7:0], x_r[31:8]};          // ROR(x, 8)
    wire [31:0] sum_xy = x_ror + y_r;                    // ROR(x,8) + y
    wire [31:0] x_new  = sum_xy ^ enc_k;                 // XOR rk[i]
    wire [31:0] y_rol  = {y_r[28:0], y_r[31:29]};        // ROL(y, 3)
    wire [31:0] y_new  = y_rol ^ x_new;                  // XOR x_new

    //========================================================================
    // 主 FSM
    //========================================================================
    always @(posedge clk) begin
        if (rst) begin
            state   <= S_IDLE;
            rd_cnt  <= {RW{1'b0}};
            rk_flat <= {(ROUNDS*32){1'b0}};
            l_0     <= 32'd0;
            l_1     <= 32'd0;
            x_r     <= 32'd0;
            y_r     <= 32'd0;
            ct_r    <= 64'd0;
            done_r  <= 1'b0;
        end else begin
            done_r <= 1'b0;

            case (state)
                //--------------------------------------------------------------
                S_IDLE: begin
                    if (start) begin
                        rk_flat[31:0] <= key_in[31:0];    // rk[0] = k0
                        l_0           <= key_in[63:32];   // l[0] = l0
                        l_1           <= key_in[95:64];   // l[1] = l1
                        x_r           <= plaintext_in[31:0];
                        y_r           <= plaintext_in[63:32];
                        rd_cnt        <= 5'd0;
                        state         <= S_KEY;
                    end
                end

                //--------------------------------------------------------------
                S_KEY: begin
                    if (rd_cnt < ROUNDS - 1) begin
                        // rk[rd_cnt+1] = k_new, l 窗口滚动
                        rk_flat[(rd_cnt + 5'd1)*32 +: 32] <= k_new;
                        l_0    <= l_1;
                        l_1    <= l_new;
                        rd_cnt <= rd_cnt + 5'd1;
                    end else begin
                        rd_cnt <= 5'd0;
                        state  <= S_ENC;
                    end
                end

                //--------------------------------------------------------------
                S_ENC: begin
                    if (rd_cnt < ROUNDS - 1) begin
                        x_r    <= x_new;
                        y_r    <= y_new;
                        rd_cnt <= rd_cnt + 5'd1;
                    end else begin
                        // 最后一轮
                        ct_r   <= {y_new, x_new};
                        state  <= S_IDLE;
                        done_r <= 1'b1;
                    end
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule
