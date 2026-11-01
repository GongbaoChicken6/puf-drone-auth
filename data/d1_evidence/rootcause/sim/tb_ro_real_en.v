`timescale 1ns / 1ps
//============================================================================
// tb_ro_real_en.v -- ROOTCAUSE E6: REAL repo ro_array, ring_en starts 0
// (loop resolves ro=1 statically), then 0->1. In an event-driven simulator
// the zero-delay inverter loop has no time advance -> infinite delta-cycle
// oscillation (simulator iteration limit). Proves the RO primitive has no
// simulatable frequency: oscillation is a transport-delay phenomenon.
//============================================================================
module tb_ro_real_en;
    reg clk = 1'b0;
    reg rst = 1'b1;
    reg measure_en = 1'b0;
    reg ring_en = 1'b0;
    wire busy, done;
    wire [255:0] ring_freq;

    ro_array # ( .N_RINGS(16), .CNT_W(16), .DIV_STAGES(5) ) u_arr (
        .clk(clk), .rst(rst), .measure_en(measure_en), .ring_en(ring_en),
        .busy(busy), .done(done), .ring_freq(ring_freq)
    );

    always #5 clk = ~clk;

    initial begin
        repeat (10) @(negedge clk);
        rst = 1'b0;
        repeat (5) @(negedge clk);
        $display("E6: ring_en=0 phase; sample ring0 ro wire = %b (loop statically resolved)", u_arr.gen_ro_ring[0].ro);
        $display("E6: enabling ring_en 0->1 now (expect zero-delay oscillation / iteration limit)");
        ring_en = 1'b1;
        repeat (100) @(negedge clk);   // if the simulator survives, count window
        measure_en = 1'b1;
        repeat (2000) @(negedge clk);
        measure_en = 1'b0;
        @(posedge done);
        $display("E6 RESULT: survived; ring_freq = %h", ring_freq);
        $display("TB_RO_REAL_EN_DONE");
        $finish;
    end

    initial begin #1_000_000; $display("TB_RO_REAL_EN watchdog"); $finish; end
endmodule
