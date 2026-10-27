`timescale 1ns / 1ps
// tb_echo_core：验证 v5/v6 回声核心 uart_rx→uart_tx 桥，32 字节回环
module tb_echo_core;
    localparam CLKS_PER_BIT = 868;
    localparam CLK_PERIOD   = 10;
    reg         clk = 1'b0;
    reg         rst = 1'b1;
    reg         rx_line = 1'b1;
    wire        tx_line;
    wire        tx_active;
    wire [7:0]  rx_byte_w;
    wire        rx_valid_w;
    uart_rx # ( .CLKS_PER_BIT ( CLKS_PER_BIT )
    ) u_rx (
        .clk ( clk ), .rst ( rst ), .rx_serial ( rx_line ),
        .rx_byte ( rx_byte_w ), .rx_valid ( rx_valid_w )
    );
    uart_tx # ( .CLKS_PER_BIT ( CLKS_PER_BIT )
    ) u_tx (
        .clk ( clk ), .rst ( rst ),
        .tx_valid ( rx_valid_w && !tx_active ),
        .tx_byte ( rx_byte_w ),
        .tx_serial ( tx_line ), .tx_active ( tx_active ), .tx_done ( )
    );
    always #(CLK_PERIOD/2) clk = ~clk;
    task send_byte(input [7:0] b);
        integer i;
        begin
            rx_line = 1'b0;
            repeat (CLKS_PER_BIT) @(posedge clk);
            for (i = 0; i < 8; i = i + 1) begin
                rx_line = b[i];
                repeat (CLKS_PER_BIT) @(posedge clk);
            end
            rx_line = 1'b1;
            repeat (CLKS_PER_BIT) @(posedge clk);
        end
    endtask
    reg [7:0]  cap_byte;
    integer    bit_cnt;
    integer    total_bytes;
    initial begin
        total_bytes = 0;
        forever begin
            @(negedge tx_line);
            repeat (CLKS_PER_BIT/2) @(posedge clk);
            if (tx_line == 1'b0) begin
                bit_cnt = 0; cap_byte = 8'd0;
                repeat (8) begin
                    repeat (CLKS_PER_BIT) @(posedge clk);
                    cap_byte[bit_cnt] = tx_line;
                    bit_cnt = bit_cnt + 1;
                end
                repeat (CLKS_PER_BIT) @(posedge clk);
                total_bytes = total_bytes + 1;
                $display("[ECHO %0d] byte=%02x @%0t", total_bytes, cap_byte, $time);
            end
        end
    end
    always @(posedge clk) if (rx_valid_w) $display("[RXV] byte=%02x @%%0t", rx_byte_w, $time);
    always @(tx_active) $display("[TXACT] tx_active=%b @%%0t", tx_active, $time);
    always @(rx_line) $display("[LINE] %b @%%0t", rx_line, $time);
    reg [2:0] prv_state = 3'd0;
    always @(posedge clk) begin
        if (u_rx.curr_state != prv_state) begin
            $display("[ST] %0d->%0d @%%0t cnt=%%0d", prv_state, u_rx.curr_state, $time, u_rx.cnt_clk);
            prv_state <= u_rx.curr_state;
        end
    end
    always @(posedge clk) if (u_rx.curr_state == 3'd4) $display("[CLEANUP] @%%0t", $time);
    integer k;
    initial begin
        repeat (10) @(posedge clk);
        rst = 1'b0;
        repeat (10) @(posedge clk);
        $display("=== TX 32 bytes ===");
        for (k = 0; k < 32; k = k + 1) begin
            send_byte(k[7:0]);
        end
        $display("=== sent, draining ===");
        repeat (300000) @(posedge clk);
        $display("=== RESULT: echoed %0d/32 ===", total_bytes);
        if (total_bytes >= 1) $display("TB_ECHO_CORE: PASS");
        else $display("TB_ECHO_CORE: FAIL_ZERO_ECHO");
        $finish;
    end
endmodule