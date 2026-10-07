`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Design Name: puf-auth-w2
// Module Name: tb_challenge_decode
// Description: 
//  challenge_decode 自校验 testbench（W2 验收判据"解码确定性"的仿真实现）：
//    1. 确定性：固定种子连续解码 100 次，pair_table 必须逐 bit 相同；
//    2. 排列性质：每一轮 16 个 4-bit 环号中，0~15 各出现恰好一次
//       （Fisher-Yates 构造保证，逐轮逐值复核，100 次全部检查）；
//    3. 延迟测量：统计 start 脉冲采样沿到 done 置位的时钟周期数；
//    4. 边界用例：全零种子（LFSR 停 0、j 恒 0）仍须输出合法排列。
//  全部通过打印 TB_CHALLENGE_DECODE_PASS，否则打印 TB_CHALLENGE_DECODE_FAIL
//  并列出错项（CI 门禁约定 TB_<模块名>_PASS）。
//////////////////////////////////////////////////////////////////////////////////
module tb_challenge_decode;

    //---------------- DUT 接口 ---------------//
    reg          clk;
    reg          rst;
    reg          start;
    reg  [63:0]  seed;
    wire [511:0] pair_table;
    wire         done;

    //---------------- 统计与控制 ---------------//
    integer      run_cnt;                          // 已跑次数
    integer      err_cnt;                          // 累计错误数
    integer      lat_cycle;                        // 单次延迟（时钟数）
    integer      lat_guard;                        // 单次超时保护计数
    integer      lat_min;                          // 100 次中最小延迟
    integer      lat_max;                          // 100 次中最大延迟
    reg [511:0]  ref_table;                        // 首次结果（确定性参考）
    reg [511:0]  cur_table;                        // 本次结果
    reg          perm_ok;                          // 单轮排列检查结果
    reg [3:0]    nibble;                           // 轮内取出的环号
    integer      round_idx;                        // 轮号（0~7）
    integer      slot_idx;                         // 轮内槽位号（0~15）
    integer      value_idx;                        // 被统计的环号（0~15）
    integer      hit_cnt;                          // 环号出现次数

    localparam [63:0] SEED_FIX = 64'hC0FF_EEBE_EF12_3456;    // 固定测试种子

    //---------------- 100MHz 时钟 ---------------//
    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    //---------------- DUT 例化 ---------------//
    challenge_decode # (
        .N_ROUNDS ( 8 ),
        .N_RINGS  ( 16 ),
        .IDX_W    ( 4 )
    ) u_dut (
        .clk         ( clk        ),
        .rst         ( rst        ),
        .start       ( start      ),
        .seed        ( seed       ),
        .pair_table  ( pair_table ),
        .done        ( done       )
    );

    //------------------------------------------------------------------
    // 一次解码：发 start 单拍脉冲，等 done，测延迟（带超时保护）
    //------------------------------------------------------------------
    task do_decode(input [63:0] s);
        begin
            seed      = s;
            start     = 1'b1;
            lat_cycle = 0;
            lat_guard = 0;
            @(posedge clk);
            start = 1'b0;                       // start 恰覆盖一个采样沿
            while ((done !== 1'b1) && (lat_guard < 20000)) begin
                @(posedge clk);
                lat_cycle = lat_cycle + 1;
                lat_guard = lat_guard + 1;
            end
            if (lat_guard >= 20000) begin
                err_cnt = err_cnt + 1;
                $display("[TB] ERROR: 等待 done 超时（20000 拍）");
            end
            cur_table = pair_table;
        end
    endtask

    //------------------------------------------------------------------
    // 排列检查：一轮内 16 个环号槽位，0~15 各出现恰好一次
    //------------------------------------------------------------------
    task check_round(input [511:0] tbl, input integer r);
        begin
            perm_ok = 1'b1;
            for (value_idx = 0; value_idx < 16; value_idx = value_idx + 1) begin
                hit_cnt = 0;
                nibble  = value_idx;            // 隐式截断到 4 bit
                for (slot_idx = 0; slot_idx < 16; slot_idx = slot_idx + 1) begin
                    if (tbl[r*64 + slot_idx*4 +: 4] == nibble) begin
                        hit_cnt = hit_cnt + 1;
                    end
                end
                if (hit_cnt != 1) begin
                    perm_ok = 1'b0;
                    $display("[TB] ERROR: round %0d 中环号 %0d 出现 %0d 次（应为 1 次）",
                             r, value_idx, hit_cnt);
                end
            end
        end
    endtask

    //------------------------------------------------------------------
    // 主序列
    //------------------------------------------------------------------
    initial begin
        rst = 1'b1;
        start = 1'b0;
        seed = 64'd0;
        err_cnt = 0;
        lat_min = 32'h7FFF_FFFF;
        lat_max = 0;
        repeat (5) @(posedge clk);
        rst = 1'b0;
        @(posedge clk);

        // ---- 第 1 次：建立确定性参考表 + 排列检查 + 延迟 ----
        do_decode(SEED_FIX);
        ref_table = cur_table;
        for (round_idx = 0; round_idx < 8; round_idx = round_idx + 1) begin
            check_round(cur_table, round_idx);
            if (!perm_ok) begin
                err_cnt = err_cnt + 1;
                $display("[TB] ERROR: 首次解码 round %0d 排列性质不满足", round_idx);
            end
        end
        $display("[TB] 固定种子 %h 首次 pair_table = %h", SEED_FIX, cur_table);
        $display("[TB] 首次解码延迟 = %0d 个时钟周期（理论值约 2050）", lat_cycle);
        lat_min = lat_cycle;
        lat_max = lat_cycle;

        // ---- 第 2~100 次：确定性 + 排列复检 ----
        for (run_cnt = 2; run_cnt <= 100; run_cnt = run_cnt + 1) begin
            do_decode(SEED_FIX);
            if (cur_table !== ref_table) begin
                err_cnt = err_cnt + 1;
                $display("[TB] ERROR: 第 %0d 次解码与首次结果不一致", run_cnt);
            end
            for (round_idx = 0; round_idx < 8; round_idx = round_idx + 1) begin
                check_round(cur_table, round_idx);
                if (!perm_ok) begin
                    err_cnt = err_cnt + 1;
                    $display("[TB] ERROR: 第 %0d 次 round %0d 排列性质不满足", run_cnt, round_idx);
                end
            end
            if (lat_cycle < lat_min) lat_min = lat_cycle;
            if (lat_cycle > lat_max) lat_max = lat_cycle;
        end

        // ---- 边界用例：全零种子仍须给出合法排列 ----
        do_decode(64'd0);
        for (round_idx = 0; round_idx < 8; round_idx = round_idx + 1) begin
            check_round(cur_table, round_idx);
            if (!perm_ok) begin
                err_cnt = err_cnt + 1;
                $display("[TB] ERROR: 全零种子 round %0d 排列性质不满足", round_idx);
            end
        end
        $display("[TB] 全零种子（LFSR 停 0 边界）pair_table = %h", cur_table);

        // ---- 汇总 ----
        $display("[TB] 延迟统计（固定种子 100 次）：min = %0d，max = %0d", lat_min, lat_max);
        if (err_cnt == 0) begin
            // CI 门禁约定：TB_<模块名>_PASS（与 tb_byte_fifo/tb_crc16 等一致；
        // 旧标记 "TB_PASS" 不匹配 ci_regression.ps1 的 TB_.*_PASS 正则）
        $display("TB_CHALLENGE_DECODE_PASS: 100 次确定性 + 每轮排列性质 + 全零边界 用例全部通过");
        end
        else begin
            $display("TB_CHALLENGE_DECODE_FAIL: 共 %0d 项错误", err_cnt);
        end
        $finish;
    end

endmodule
