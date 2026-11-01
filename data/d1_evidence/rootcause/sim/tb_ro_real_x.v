`timescale 1ns / 1ps
//============================================================================
// tb_ro_real_x.v -- ROOTCAUSE E5: REAL repo ro_array (zero-delay ro_ring),
// ring_en held 1 from t=0. Expected event-driven behavior: the combinational
// loop settles to X (no events), ro_div never toggles, all 16 window
// counters latch 0 -> ring_freq == 0 -> R1 would be all-zero CONSTANT.
//============================================================================
module tb_ro_real_x;
    reg clk = 1'b0;
    reg rst = 1'b1;
    reg measure_en = 1'b0;
    reg ring_en = 1'b1;
    wire busy, done;
    wire [255:0] ring_freq;
    integer i;

    ro_array # ( .N_RINGS(16), .CNT_W(16), .DIV_STAGES(5) ) u_arr (
        .clk(clk), .rst(rst), .measure_en(measure_en), .ring_en(ring_en),
        .busy(busy), .done(done), .ring_freq(ring_freq)
    );

    always #5 clk = ~clk;

    initial begin
        repeat (10) @(negedge clk);
        rst = 1'b0;
        repeat (5) @(negedge clk);
        measure_en = 1'b1;
        repeat (2000) @(negedge clk);   // 2 us window
        measure_en = 1'b0;
        @(posedge done);
        repeat (2) @(negedge clk);
        $display("E5 ring_freq (real zero-delay ring, en=1 from t0):");
        for (i = 0; i < 16; i = i + 1)
            $display("  ring[%0d] freq = 0x%04h (%0d)", i, ring_freq[i*16 +: 16], ring_freq[i*16 +: 16]);
        if (ring_freq === 256'd0)
            $display("E5 RESULT: all 16 counters = 0 -> any freq[B]>freq[A] is false -> R1 == 64'h0 for EVERY challenge (chip-independent constant)");
        else
            $display("E5 RESULT: nonzero counters (unexpected): %h", ring_freq);
        $display("TB_RO_REAL_X_DONE");
        $finish;
    end

    initial begin #1_000_000; $display("TB_RO_REAL_X_FAIL watchdog"); $finish; end
endmodule
