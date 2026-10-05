//============================================================================
// byte_fifo.v -- TX 速率匹配 FIFO（契约 §6.1 第 1 条强制）
//----------------------------------------------------------------------------
// mavlink_frame 以每拍 1 字节速率输出，uart_tx 每字节需 ~8680 拍且忙时
// 静默丢弃 tx_valid。本 FIFO 缓冲整帧字节，由集成方按 uart_tx 节拍弹出。
//
// 集成接线（terminal_fsm 胶水逻辑）：
//   wire fifo_pop = ~fifo_empty & ~uart_tx_active;      // uart 空闲且有数据
//   assign tx_valid = fifo_pop;
//   assign tx_byte  = fifo_rd_data;                     // 组合读，当拍有效
//   // fifo 端：rd_en = fifo_pop; wr_en = frame_valid; wr_data = frame_byte;
//
// 特性：
//   - 组合读（rd_data 当拍有效，适配 uart_tx 同拍锁存）
//   - 同拍读写（独立指针，天然流水线）
//   - 深度 64（最大帧 44B + 20B 余量）
//   - 空/满标志 + 字节计数（集成方可监控排空状态）
//============================================================================

module byte_fifo # (
    parameter DEPTH = 64                                  // 深度（>= 44B 最大帧）
) (
    input  wire          clk       ,                       // 系统时钟
    input  wire          rst       ,                       // 高有效同步复位
    // -- 写侧（接 mavlink_frame 的 frame_valid / frame_byte）--------------
    input  wire [7:0]    wr_data   ,                       // 写数据
    input  wire          wr_en     ,                       // 写使能
    // -- 读侧（接 terminal_fsm 胶水 → uart_tx）----------------------------
    input  wire          rd_en     ,                       // 读使能（指针前移）
    output wire [7:0]    rd_data   ,                       // 组合读出（当拍有效）
    output wire          empty     ,                       // FIFO 空
    output wire          full      ,                       // FIFO 满
    // -- 监控 ---------------------------------------------------------------
    output wire [6:0]    count                             // 当前字节数
);

    //------------------------------------------------------------------------
    // 参数推导与 elaboration 自检
    //------------------------------------------------------------------------
    localparam ADDR_W = 6;                                // log2(64)，冻结 64 深度
    // 自检：DEPTH 必须是 2 的幂且 <= 64（指针方案限制）
    generate
        if (DEPTH != 64) begin : gen_depth_check
            // 非 64 深度需要修改 ADDR_W 和指针位宽——当前冻结 64
            non_supported_depth_for_byte_fifo u_err ();
        end
    endgenerate

    //------------------------------------------------------------------------
    // 存储与指针（指针多 1 bit 用于区分空/满）
    //------------------------------------------------------------------------
    reg [7:0]        mem [0:DEPTH-1];                      // 环形缓冲
    reg [ADDR_W:0]   wr_ptr = {ADDR_W+1{1'b0}};            // 写指针（7-bit）
    reg [ADDR_W:0]   rd_ptr = {ADDR_W+1{1'b0}};            // 读指针（7-bit）

    integer k;
    initial for (k = 0; k < DEPTH; k = k + 1) mem[k] = 8'h00;

    //------------------------------------------------------------------------
    // 标志与输出
    //------------------------------------------------------------------------
    assign empty    = (wr_ptr == rd_ptr);                   // 指针全等 = 空
    assign full     = (wr_ptr[ADDR_W] != rd_ptr[ADDR_W])    // MSB 不同
                   && (wr_ptr[ADDR_W-1:0] == rd_ptr[ADDR_W-1:0]); // 低位同 = 满
    assign count    = wr_ptr - rd_ptr;                      // 7-bit 差值
    assign rd_data  = mem[rd_ptr[ADDR_W-1:0]];              // 组合读（当拍有效）

    //------------------------------------------------------------------------
    // 指针推进（同拍读写互不干扰）
    //------------------------------------------------------------------------
    always @(posedge clk) begin
        if (rst) begin
            wr_ptr <= {ADDR_W+1{1'b0}};
            rd_ptr <= {ADDR_W+1{1'b0}};
        end else begin
            if (wr_en && !full) begin
                mem[wr_ptr[ADDR_W-1:0]] <= wr_data;
                wr_ptr <= wr_ptr + 1'b1;
            end
            if (rd_en && !empty) begin
                rd_ptr <= rd_ptr + 1'b1;
            end
        end
    end

endmodule
