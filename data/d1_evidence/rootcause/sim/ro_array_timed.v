`timescale 1ns / 1ps
//============================================================================
// ro_array_timed.v -- ROOTCAUSE-ONLY copy of src/rtl/w2_array/ro_array.v
//----------------------------------------------------------------------------
// SINGLE DELTA vs repo ro_array.v: the generate block instantiates
// ro_ring_timed (explicit per-ring half period, ps) instead of the repo
// zero-delay ro_ring, so that silicon variation can be injected as per-ring
// period offsets. Everything else -- window control, ro_div (repo module,
// DIV_STAGES=5 -> /32), 2FF synchronizer, edge detect, window counter,
// freq latch -- is copied VERBATIM from ro_array.v.
// 16 x 16-bit per-ring half periods are passed in HALF_VEC (ring i = HALF_VEC[i*16 +: 16]).
//============================================================================
module ro_array_timed # (
    parameter N_RINGS    = 16    ,
    parameter CNT_W      = 16    ,
    parameter DIV_STAGES = 5     ,
    parameter [N_RINGS*16-1:0] HALF_VEC = {N_RINGS{16'd3000}}
  )
  (
    input                         clk         ,
    input                         rst         ,
    input                         measure_en  ,
    input                         ring_en     ,
    output                        busy        ,
    output                        done        ,
    output  [N_RINGS*CNT_W-1:0]   ring_freq
  );

reg      measure_d1 = 1'b0;
wire     win_fall;
reg      busy_reg = 1'b0;
reg      done_reg = 1'b0;

always @ ( posedge clk ) begin
    if( rst ) begin
        measure_d1 <= 1'b0;
    end
    else begin
        measure_d1 <= measure_en;
    end
end

assign  win_fall = measure_d1 & ( !measure_en );

always @ ( posedge clk ) begin
    if( rst ) begin
        busy_reg <= 1'b0;
    end
    else begin
        busy_reg <= measure_d1 | done_reg;
    end
end

assign  busy = busy_reg;

always @ ( posedge clk ) begin
    if( rst ) begin
        done_reg <= 1'b0;
    end
    else if( win_fall ) begin
        done_reg <= 1'b1;
    end
    else begin
        done_reg <= 1'b0;
    end
end

assign  done = done_reg;

genvar i;
generate
    for( i = 0; i < N_RINGS; i = i + 1 ) begin : gen_ro_ring
        wire                     ro;
        wire                     div;
        (* ASYNC_REG = "true" *) reg  div_meta = 1'b0;
        (* ASYNC_REG = "true" *) reg  div_sync = 1'b0;
        reg                      div_d1 = 1'b0;
        wire                     pos_edge;
        reg  [CNT_W-1:0]         cnt = {CNT_W{1'b0}};
        reg  [CNT_W-1:0]         freq_latch = {CNT_W{1'b0}};

        // ---- ROOTCAUSE DELTA: timed ring instead of zero-delay ro_ring ----
        ro_ring_timed # ( .HALF_PS ( HALF_VEC[i*16 +: 16] ) ) u_ro_ring (
            .en     ( ring_en   ),
            .ro     ( ro        )
        );

        ro_div # ( .STAGES   ( DIV_STAGES )
        ) u_ro_div (
            .ro     ( ro        ),
            .div    ( div       )
        );

        always @ ( posedge clk ) begin
            div_meta <= div;
        end

        always @ ( posedge clk ) begin
            div_sync <= div_meta;
        end

        always @ ( posedge clk ) begin
            div_d1 <= div_sync;
        end

        assign  pos_edge = div_sync & ( !div_d1 );

        always @ ( posedge clk ) begin
            if( rst ) begin
                cnt <= {CNT_W{1'b0}};
            end
            else if( !measure_en ) begin
                cnt <= {CNT_W{1'b0}};
            end
            else if( pos_edge ) begin
                cnt <= cnt + 1'b1;
            end
            else begin
                cnt <= cnt;
            end
        end

        always @ ( posedge clk ) begin
            if( rst ) begin
                freq_latch <= {CNT_W{1'b0}};
            end
            else if( win_fall ) begin
                freq_latch <= cnt;
            end
            else begin
                freq_latch <= freq_latch;
            end
        end

        assign  ring_freq[i*CNT_W +: CNT_W] = freq_latch;
    end
endgenerate

endmodule
