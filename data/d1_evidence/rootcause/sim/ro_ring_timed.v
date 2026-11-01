`timescale 1ps / 1ps
//============================================================================
// ro_ring_timed.v -- ROOTCAUSE-ONLY behavioral timed ring oscillator
//----------------------------------------------------------------------------
// Purpose: the repo primitive ro_ring.v is a zero-delay combinational loop
// (no period/frequency parameter). An event-driven simulator either resolves
// it to X (en=1 from t0) or falls into a zero-delay oscillation (en 0->1).
// To inject *physical* silicon variation into the REAL measurement datapath
// (repo ro_div + 2FF sync + edge detect + window counter), this model gives
// the ring an explicit half period HALF_PS (picoseconds). It replaces ONLY
// the oscillator primitive inside the rootcause/sim copy ro_array_timed.v;
// everything downstream is the unmodified repo RTL.
// This file lives only in data/d1_evidence/rootcause/sim (repo untouched).
//============================================================================
module ro_ring_timed #(
    parameter [15:0] HALF_PS = 16'd3000   // half oscillation period in ps
) (
    input  wire en,
    output reg  ro
);
    initial ro = 1'b0;
    always begin
        #(HALF_PS);
        if (en) ro = ~ro;
        else    ro = 1'b0;   // stopped ring: constant output, no edges
    end
endmodule
