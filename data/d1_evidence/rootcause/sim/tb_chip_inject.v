`timescale 1ns / 1ps
//============================================================================
// tb_chip_inject.v -- ROOTCAUSE E7: silicon-variation injection experiment
//----------------------------------------------------------------------------
// Five "chips" = five ro_array_timed instances (repo ro_div /32 + 2FF sync +
// edge detect + 1 ms @ 100 MHz window counter, VERBATIM repo datapath; only
// the ring primitive is a timed behavioral model):
//   chipA : per-ring half period 3000 + ((37*i) mod 61) - 30 ps   (±1% jitter)
//   chipB : chipA periods x (1 ± 5%  per-ring)  [((53*i) mod 101) - 50 permille]
//   chipC : chipA periods x (1 ± 10% per-ring)  [((79*i) mod 201) - 100 permille]
//   chipM : all rings exactly 3000 ps (frequency-matched array)
//   chipM2: all rings exactly 3150 ps (matched, global +5% like another die lot)
// Same 4 challenge seeds as the board auth round (golden A/B/C/D); R1 is
// computed with the frozen rule bit(r,p) = (freq[B] > freq[A]) (identical to
// terminal_fsm.v:168-198 and puf_model.ideal).
//============================================================================
module tb_chip_inject;

    parameter WIN_CYCLES = 100000;   // 1 ms @ 100 MHz -- production window

    // ---- deterministic per-ring half periods (ps) ----
    function [15:0] hp_a(input integer i); begin
        hp_a = 3000 + ((37 * i) % 61) - 30;
    end endfunction

    function [255:0] vec_a(input integer dummy); integer i; begin
        vec_a = 256'd0;
        for (i = 0; i < 16; i = i + 1) vec_a[i*16 +: 16] = hp_a(i);
    end endfunction

    function [255:0] vec_mul(input [255:0] v, input integer mult, input integer modw);
        integer i; integer d; integer h;
        begin
            vec_mul = 256'd0;
            for (i = 0; i < 16; i = i + 1) begin
                d = ((mult * i) % modw) - (modw - 1) / 2;
                h = (v[i*16 +: 16] * (1000 + d) + 500) / 1000;
                vec_mul[i*16 +: 16] = h[15:0];
            end
        end
    endfunction

    localparam [255:0] V_A  = vec_a(0);
    localparam [255:0] V_B  = vec_mul(V_A, 53, 101);   // ±5%  vs A
    localparam [255:0] V_C  = vec_mul(V_A, 79, 201);   // ±10% vs A
    localparam [255:0] V_M  = {16{16'd3000}};          // matched
    localparam [255:0] V_M2 = {16{16'd3150}};          // matched +5% global

    reg clk = 1'b0;
    reg rst = 1'b1;
    reg measure_en = 1'b0;
    reg ring_en = 1'b1;
    wire busyA, doneA, busyB, doneB, busyC, doneC, busyM, doneM, busyM2, doneM2;
    wire [255:0] fqA, fqB, fqC, fqM, fqM2;
    integer win;

    ro_array_timed # (.N_RINGS(16), .CNT_W(16), .DIV_STAGES(5), .HALF_VEC(V_A )) u_A (
        .clk(clk), .rst(rst), .measure_en(measure_en), .ring_en(ring_en), .busy(busyA), .done(doneA), .ring_freq(fqA));
    ro_array_timed # (.N_RINGS(16), .CNT_W(16), .DIV_STAGES(5), .HALF_VEC(V_B )) u_B (
        .clk(clk), .rst(rst), .measure_en(measure_en), .ring_en(ring_en), .busy(busyB), .done(doneB), .ring_freq(fqB));
    ro_array_timed # (.N_RINGS(16), .CNT_W(16), .DIV_STAGES(5), .HALF_VEC(V_C )) u_C (
        .clk(clk), .rst(rst), .measure_en(measure_en), .ring_en(ring_en), .busy(busyC), .done(doneC), .ring_freq(fqC));
    ro_array_timed # (.N_RINGS(16), .CNT_W(16), .DIV_STAGES(5), .HALF_VEC(V_M )) u_M (
        .clk(clk), .rst(rst), .measure_en(measure_en), .ring_en(ring_en), .busy(busyM), .done(doneM), .ring_freq(fqM));
    ro_array_timed # (.N_RINGS(16), .CNT_W(16), .DIV_STAGES(5), .HALF_VEC(V_M2)) u_M2 (
        .clk(clk), .rst(rst), .measure_en(measure_en), .ring_en(ring_en), .busy(busyM2), .done(doneM2), .ring_freq(fqM2));

    // ---- challenge decode (repo module) ----
    reg cd_start_r = 1'b0;
    reg [63:0] cd_seed_r = 64'd0;
    wire cd_done_w;
    wire [511:0] cd_tbl;
    reg [511:0] tbl0, tbl1, tbl2, tbl3;
    integer seed_idx;

    challenge_decode # (.N_ROUNDS(8), .N_RINGS(16), .IDX_W(4)) u_cd (
        .clk(clk), .rst(rst), .start(cd_start_r), .seed(cd_seed_r),
        .pair_table(cd_tbl), .done(cd_done_w));

    always #5 clk = ~clk;

    task run_seed(input [63:0] s);
        begin
            @(negedge clk); cd_start_r = 1'b1; cd_seed_r = s;
            @(negedge clk); cd_start_r = 1'b0;
            @(posedge cd_done_w);
            @(negedge clk);
        end
    endtask

    // R1 = frozen comparison rule (terminal_fsm.v:168-198 / puf_model.ideal)
    function [63:0] r1_of(input [511:0] tbl, input [255:0] fq);
        integer r, p;
        reg [3:0] a, b;
        begin
            r1_of = 64'd0;
            for (r = 0; r < 8; r = r + 1)
                for (p = 0; p < 8; p = p + 1) begin
                    a = tbl[r*64 + p*8 +: 4];
                    b = tbl[r*64 + p*8 + 4 +: 4];
                    if (fq[{b, 4'd0} +: 16] > fq[{a, 4'd0} +: 16])
                        r1_of[63 - 8*r - p] = 1'b1;
                end
        end
    endfunction

    function [7:0] pop64(input [63:0] x);
        integer k; begin
            pop64 = 8'd0;
            for (k = 0; k < 64; k = k + 1) pop64 = pop64 + x[k];
        end
    endfunction

    reg [63:0] rA0, rA1, rA2, rA3, rB0, rB1, rB2, rB3;
    reg [63:0] rC0, rC1, rC2, rC3, rM0, rM1, rM2_, rM3, rM2b0, rM2b1, rM2b2, rM2b3;
    integer i;

    task print_freqs(input [8*32-1:0] name, input [255:0] fq, input [255:0] hv);
        integer k; integer expect_cnt;
        begin
            $write("E7 %0s half_ps:", name);
            for (k = 0; k < 16; k = k + 1) $write(" %0d", hv[k*16 +: 16]);
            $write("\n   counts:");
            for (k = 0; k < 16; k = k + 1) $write(" %0d", fq[k*16 +: 16]);
            $write("\n   analytic:");
            for (k = 0; k < 16; k = k + 1) begin
                expect_cnt = (WIN_CYCLES * 10000) / (64 * hv[k*16 +: 16]);
                $write(" %0d", expect_cnt);
            end
            $write("\n");
        end
    endtask

    initial begin
        repeat (10) @(negedge clk);
        rst = 1'b0;
        repeat (5) @(negedge clk);

        // four challenges (golden seeds A/B/C/D = board-round challenge set)
        seed_idx = 0; run_seed(64'hC0FF_EEBE_EF12_3456); tbl0 = cd_tbl;
        seed_idx = 1; run_seed(64'h0F1E_2D3C_4B5A_6978); tbl1 = cd_tbl;
        seed_idx = 2; run_seed(64'hFEED_FACE_CAFE_BABE); tbl2 = cd_tbl;
        seed_idx = 3; run_seed(64'h1234_5678_9ABC_DEF0); tbl3 = cd_tbl;

        // one 1 ms production window, all five "chips" measured in parallel
        measure_en = 1'b1;
        for (win = 0; win < WIN_CYCLES; win = win + 1) @(negedge clk);
        measure_en = 1'b0;
        @(posedge doneA); @(negedge clk);

        print_freqs("chipA (±1% jitter) ", fqA, V_A);
        print_freqs("chipB (A ±5%/ring) ", fqB, V_B);
        print_freqs("chipC (A ±10%/ring)", fqC, V_C);
        print_freqs("chipM (matched)    ", fqM, V_M);
        print_freqs("chipM2(matched+5%) ", fqM2, V_M2);

        rA0 = r1_of(tbl0, fqA); rA1 = r1_of(tbl1, fqA); rA2 = r1_of(tbl2, fqA); rA3 = r1_of(tbl3, fqA);
        rB0 = r1_of(tbl0, fqB); rB1 = r1_of(tbl1, fqB); rB2 = r1_of(tbl2, fqB); rB3 = r1_of(tbl3, fqB);
        rC0 = r1_of(tbl0, fqC); rC1 = r1_of(tbl1, fqC); rC2 = r1_of(tbl2, fqC); rC3 = r1_of(tbl3, fqC);
        rM0 = r1_of(tbl0, fqM); rM1 = r1_of(tbl1, fqM); rM2_ = r1_of(tbl2, fqM); rM3 = r1_of(tbl3, fqM);
        rM2b0 = r1_of(tbl0, fqM2); rM2b1 = r1_of(tbl1, fqM2); rM2b2 = r1_of(tbl2, fqM2); rM2b3 = r1_of(tbl3, fqM2);

        $display("E7 R1 chipA : %016h %016h %016h %016h", rA0, rA1, rA2, rA3);
        $display("E7 R1 chipB : %016h %016h %016h %016h", rB0, rB1, rB2, rB3);
        $display("E7 R1 chipC : %016h %016h %016h %016h", rC0, rC1, rC2, rC3);
        $display("E7 R1 chipM : %016h %016h %016h %016h", rM0, rM1, rM2_, rM3);
        $display("E7 R1 chipM2: %016h %016h %016h %016h", rM2b0, rM2b1, rM2b2, rM2b3);

        $display("E7 HD(256bit) chipB vs chipA = %0d", pop64(rA0^rB0)+pop64(rA1^rB1)+pop64(rA2^rB2)+pop64(rA3^rB3));
        $display("E7 HD(256bit) chipC vs chipA = %0d", pop64(rA0^rC0)+pop64(rA1^rC1)+pop64(rA2^rC2)+pop64(rA3^rC3));
        $display("E7 HD(256bit) chipM2 vs chipM = %0d", pop64(rM0^rM2b0)+pop64(rM1^rM2b1)+pop64(rM2_^rM2b2)+pop64(rM3^rM2b3));
        $display("E7 HD(256bit) chipM vs chipA = %0d", pop64(rA0^rM0)+pop64(rA1^rM1)+pop64(rA2^rM2_)+pop64(rA3^rM3));
        $display("TB_CHIP_INJECT_DONE");
        $finish;
    end

    initial begin #50_000_000; $display("TB_CHIP_INJECT watchdog"); $finish; end
endmodule
