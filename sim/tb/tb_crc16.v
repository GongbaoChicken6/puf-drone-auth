`timescale 1ns / 1ps
//============================================================================
// tb_crc16.v — crc16_mcrf4xx 自校验 testbench
//----------------------------------------------------------------------------
// 测试用例：
//   T1: 复位行为 — crc=FFFF, busy=0，din_valid 被忽略
//   T2: init 载入 — crc=FFFF, busy=1
//   T3: 单字节 0xFD -> 0x23ED          (契约 §2 黄金向量)
//   T4: 单字节 0xAA -> 0x05D7          (契约 §2 黄金向量)
//   T5: 全帧域累积 — CHALLENGE 帧 42 字节 CRC 域 -> 0xF7F2
//       (帧字节见契约 §4，CRC 计算域 = 帧[1..41] + CRC_EXTRA 0x5B)
//   T6: 错误注入 — 同域但翻转 1 字节，CRC 必须不等于 0xF7F2
//============================================================================
module tb_crc16;

    reg         clk   = 1'b0;
    reg         rst   = 1'b1;
    reg         init  = 1'b0;
    reg  [7:0]  din   = 8'h00;
    reg         dv    = 1'b0;
    wire [15:0] crc;
    wire        busy;

    integer errors = 0;
    integer i;

    // DUT
    crc16_mcrf4xx dut (
        .clk       (clk  ),
        .rst       (rst  ),
        .init      (init ),
        .din       (din  ),
        .din_valid (dv   ),
        .crc       (crc  ),
        .busy      (busy )
    );

    // 100 MHz 时钟
    always #5 clk = ~clk;

    // 便捷任务：送 1 字节
    task send_byte(input [7:0] b);
        begin
            @(negedge clk);
            din <= b;
            dv  <= 1'b1;
            @(negedge clk);
            dv  <= 1'b0;
        end
    endtask

    // 便捷任务：帧初始化脉冲
    task do_init;
        begin
            @(negedge clk);
            init <= 1'b1;
            @(negedge clk);
            init <= 1'b0;
            @(negedge clk);   // 等 init 生效一拍
        end
    endtask

    // CHALLENGE 帧 CRC 计算域（42 字节：帧[1..41] + 0x5B）
    reg [7:0] chall_domain [0:41];
    initial begin
        // 帧头[1..9]
        chall_domain[ 0]=8'h20; chall_domain[ 1]=8'h00; chall_domain[ 2]=8'h00;
        chall_domain[ 3]=8'h43; chall_domain[ 4]=8'h01; chall_domain[ 5]=8'h02;
        chall_domain[ 6]=8'h91; chall_domain[ 7]=8'h00; chall_domain[ 8]=8'h00;
        // 载荷 32B：种子 A0 00*7 / A1 01*7 / A2 02*7 / A3 03*7
        chall_domain[ 9]=8'hA0;
        for (i=0;i<7;i=i+1) chall_domain[10+i]=8'h00;
        chall_domain[17]=8'hA1;
        for (i=0;i<7;i=i+1) chall_domain[18+i]=8'h01;
        chall_domain[25]=8'hA2;
        for (i=0;i<7;i=i+1) chall_domain[26+i]=8'h02;
        chall_domain[33]=8'hA3;
        for (i=0;i<7;i=i+1) chall_domain[34+i]=8'h03;
        // CRC_EXTRA
        chall_domain[41]=8'h5B;
    end

    initial begin
        // ---------------- T1: 复位行为 ----------------
        repeat (3) @(negedge clk);
        rst = 1'b0;
        repeat (2) @(negedge clk);
        if (crc !== 16'hFFFF) begin errors=errors+1; $display("[T1 FAIL] reset crc=%h", crc); end
        if (busy !== 1'b0)    begin errors=errors+1; $display("[T1 FAIL] reset busy=%b", busy); end
        // 未 init 时喂字节应被忽略
        send_byte(8'hAA);
        if (crc !== 16'hFFFF) begin errors=errors+1; $display("[T1 FAIL] uninit byte changed crc=%h", crc); end
        $display("[T1 PASS] reset behavior");

        // ---------------- T2+T3: init 后吃 0xFD ----------------
        do_init;
        if (crc !== 16'hFFFF) begin errors=errors+1; $display("[T2 FAIL] init crc=%h", crc); end
        if (busy !== 1'b1)    begin errors=errors+1; $display("[T2 FAIL] init busy=%b", busy); end
        $display("[T2 PASS] init loads FFFF");

        send_byte(8'hFD);
        @(negedge clk);
        if (crc !== 16'h23ED) begin errors=errors+1; $display("[T3 FAIL] FD crc=%h expect 23ED", crc); end
        else                  $display("[T3 PASS] 0xFD -> 0x23ED");

        // ---------------- T4: 重新 init 吃 0xAA ----------------
        do_init;
        send_byte(8'hAA);
        @(negedge clk);
        if (crc !== 16'h05D7) begin errors=errors+1; $display("[T4 FAIL] AA crc=%h expect 05D7", crc); end
        else                  $display("[T4 PASS] 0xAA -> 0x05D7");

        // ---------------- T5: 全帧域 42 字节 ----------------
        do_init;
        for (i=0;i<42;i=i+1) send_byte(chall_domain[i]);
        @(negedge clk);
        if (crc !== 16'hF7F2) begin errors=errors+1; $display("[T5 FAIL] frame crc=%h expect F7F2", crc); end
        else                  $display("[T5 PASS] CHALLENGE CRC domain -> 0xF7F2");

        // ---------------- T6: 错误注入（翻转载荷 1 字节）----------------
        chall_domain[20] = chall_domain[20] ^ 8'h01;   // 翻转 1 bit
        do_init;
        for (i=0;i<42;i=i+1) send_byte(chall_domain[i]);
        @(negedge clk);
        if (crc === 16'hF7F2) begin errors=errors+1; $display("[T6 FAIL] corrupted frame matched!"); end
        else                  $display("[T6 PASS] corrupted frame -> %h (differs)", crc);

        // ---------------- T7: init 与 dv 同拍 —— init 优先，字节被丢 ----------------
        do_init;                              // 此任务内部 init 与 dv 从不同拍
        @(negedge clk);
        init <= 1'b1; din <= 8'hAA; dv <= 1'b1;   // 构造同拍
        @(negedge clk);
        init <= 1'b0; dv <= 1'b0;
        @(negedge clk);
        if (crc !== 16'hFFFF) begin
            errors = errors + 1; $display("[T7 FAIL] init&&dv same cycle: crc=%h expect FFFF (byte should drop)", crc);
        end else
            $display("[T7 PASS] init&&dv same cycle: byte dropped (init priority)");

        // ---------------- 总结 ----------------
        repeat (5) @(negedge clk);
        if (errors == 0) $display("TB_CRC16_PASS");
        else             $display("TB_CRC16_FAIL errors=%0d", errors);
        $finish;
    end

endmodule