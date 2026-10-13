//============================================================================
// ro_array_sim.v -- ro_array 的行为级仿真替身（W4-P2，仅仿真用，不上板）
//----------------------------------------------------------------------------
// 真实 ro_array 的 16 个环振是零延迟纯组合环，事件驱动仿真器不振荡
// （W1/W2 从未仿真过真环，12 套 TB 无 ro 用例为证）。CI 通过
// xvlog -d PUF_MODEL_SIM 让 w3_top 例化本 stub：接口契约与真模块一致
// （measure_en 开窗计数、窗末锁存、done 单拍），频率来自 $readmemh 文件
// （puf_model 生成的 fixture，默认 sim/testvectors/puf_tb_freqs.mem，
// 可用 +PUF_FREQ_FILE=... 覆盖），真环物理行为（唯一性/可靠性/温度）
// 只在板上验证——这是设计书 §2.4 冻结的诚实边界。
//============================================================================
`timescale 1ns / 1ps
module ro_array_sim # (
    parameter N_RINGS = 16,
    parameter CNT_W   = 16
) (
    input  wire                       clk         ,
    input  wire                       rst         ,
    input  wire                       measure_en  ,
    input  wire                       ring_en     ,
    output wire                       busy        ,
    output wire                       done        ,
    output wire [N_RINGS*CNT_W-1:0]   ring_freq
);

    reg [CNT_W-1:0] sim_freq [0:N_RINGS-1];
    reg [N_RINGS*CNT_W-1:0] latch_freqs = {(N_RINGS*CNT_W){1'b0}};
    reg busy_r = 1'b0;
    reg done_r = 1'b0;
    reg measure_d = 1'b0;

    // 频率文件：+PUF_FREQ_FILE=<path> 可覆盖；默认 fixture 由
    // scripts/gen_puf_fixtures.py --tb-mem 生成（puf_model 同源对拍）
    reg [8*256:1] freq_file;
    integer fi;
    initial begin
        for (fi = 0; fi < N_RINGS; fi = fi + 1)
            sim_freq[fi] = 16'h1000 + fi * 16;   // 兜底：互不相同（若文件缺失）
        if ($value$plusargs("PUF_FREQ_FILE=%s", freq_file)
        ) begin
            $readmemh(freq_file, sim_freq);
        end else begin
            $readmemh("sim/testvectors/puf_tb_freqs.mem", sim_freq);
        end
    end

    // 窗末检测（镜像真模块时序：measure_en 下降后一拍 done 脉冲 + 锁存）
    always @(posedge clk) begin
        if (rst) begin
            measure_d <= 1'b0;
            done_r    <= 1'b0;
            busy_r    <= 1'b0;
        end else begin
            measure_d <= measure_en;
            done_r    <= 1'b0;
            if (measure_d && !measure_en) begin
                for (fi = 0; fi < N_RINGS; fi = fi + 1)
                    latch_freqs[fi*CNT_W +: CNT_W] <= sim_freq[fi];
                done_r <= 1'b1;
            end
            busy_r <= measure_d | done_r;
        end
    end

    assign ring_freq = latch_freqs;
    assign done      = done_r;
    assign busy      = busy_r;

endmodule
