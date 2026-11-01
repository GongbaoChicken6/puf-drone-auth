`timescale 1ns / 1ps
//============================================================================
// tb_puf_path_inject.v -- ROOTCAUSE-ONLY modified copy of sim/tb/tb_puf_path.v
//----------------------------------------------------------------------------
// DELTA vs repo TB: the golden-R1 assertions are replaced by PRINTING of the
// four R1 responses, so the SAME full production response datapath
// (terminal_fsm S_PUF_DECODE -> S_PUF_MEASURE -> S_PUF_PACK with repo
// challenge_decode + ro_array_sim) can be run against DIFFERENT frequency
// vectors injected via +PUF_FREQ_FILE=<mem> (ro_array_sim's own plusarg).
// T2/T3/T4 (gray zone + watchdogs) removed -- not needed here.
// Repo files untouched; this copy lives only in rootcause/sim.
//============================================================================
module tb_puf_path_inject;

    reg         clk = 1'b0;
    reg         rst = 1'b1;
    reg         auth_start = 1'b0;
    reg  [7:0]  terminal_id = 8'h2A;
    wire        auth_busy;
    wire [1:0]  auth_result;

    reg  [23:0] fp_msg_id = 24'h0;
    reg  [7:0]  fp_pay_len = 8'd0;
    reg         fp_frame_ok = 1'b0;
    wire        fp_rx_inhibit;
    wire [4:0]  fp_rd_addr;
    reg  [7:0]  fp_rd_data = 8'h00;
    reg  [7:0]  fp_payload_buf [0:31];

    wire        mf_start;
    wire [23:0] mf_msg_id;
    wire [5:0]  mf_pay_len;
    wire [7:0]  mf_pay_byte;
    wire        mf_pay_valid;
    wire [7:0]  mf_seq;
    wire        mf_sysid, unused_compid;
    reg         mf_busy = 1'b0;
    reg         mf_pay_phase = 1'b0;
    reg         mf_frame_done = 1'b0;
    reg         mf_frame_err = 1'b0;

    integer     i;
    integer     tx_byte_count = 0;
    reg [7:0]   tx_captured [0:63];
    integer     guard;
    integer     win_count = 0;
    reg         ra_measure_en_prev = 1'b0;

    wire        cd_start, cd_done;
    wire [63:0] cd_seed;
    wire [511:0] cd_pair_table;
    wire        ra_measure_en, ra_ring_en, ra_busy, ra_done;
    wire [255:0] ra_ring_freq;

    always @(posedge clk) begin
        if (ra_measure_en && !ra_measure_en_prev) win_count = win_count + 1;
        ra_measure_en_prev <= ra_measure_en;
    end

    challenge_decode # ( .N_ROUNDS ( 8 ), .N_RINGS ( 16 ), .IDX_W ( 4 ) ) u_cd (
        .clk(clk), .rst(rst), .start(cd_start), .seed(cd_seed),
        .pair_table(cd_pair_table), .done(cd_done));

    ro_array_sim # ( .N_RINGS ( 16 ), .CNT_W ( 16 ) ) u_ro_array (
        .clk(clk), .rst(rst), .measure_en(ra_measure_en), .ring_en(ra_ring_en),
        .busy(ra_busy), .done(ra_done), .ring_freq(ra_ring_freq));

    terminal_fsm # ( .TIMEOUT_CYCLES(32'd1000), .MEASURE_CYCLES(32'd64),
                     .PUF_WD_CYCLES(32'd12000) ) dut (
        .clk(clk), .rst(rst), .auth_start(auth_start), .terminal_id(terminal_id),
        .auth_busy(auth_busy), .auth_result(auth_result),
        .c2_boot_seed(64'hA7A6_A5A4_A3A2_A1A0),
        .device_key_in(96'h1312_1110_0B0A_0908_0302_0100),
        .use_ext_key(1'b0), .seed_load(1'b0),
        .cd_start(cd_start), .cd_seed(cd_seed), .cd_pair_table(cd_pair_table),
        .cd_done(cd_done), .ra_measure_en(ra_measure_en), .ra_ring_en(ra_ring_en),
        .ra_busy(ra_busy), .ra_done(ra_done), .ra_ring_freq(ra_ring_freq),
        .fp_msg_id(fp_msg_id), .fp_pay_len(fp_pay_len), .fp_frame_ok(fp_frame_ok),
        .fp_frame_err(1'b0), .fp_rd_addr(fp_rd_addr), .fp_rd_data(fp_rd_data),
        .fp_rx_inhibit(fp_rx_inhibit),
        .mf_start(mf_start), .mf_msg_id(mf_msg_id), .mf_pay_len(mf_pay_len),
        .mf_pay_byte(mf_pay_byte), .mf_pay_valid(mf_pay_valid), .mf_seq(mf_seq),
        .mf_sysid(mf_sysid), .mf_compid(unused_compid), .mf_busy(mf_busy),
        .mf_pay_phase(mf_pay_phase), .mf_frame_done(mf_frame_done), .mf_frame_err(mf_frame_err));

    always #5 clk = ~clk;

    always @(posedge clk) begin
        mf_frame_done <= 1'b0;
        if (mf_start) begin
            mf_busy       <= 1'b1;
            mf_pay_phase  <= 1'b0;
            tx_byte_count <= 0;
        end else if (mf_busy) begin
            if (!mf_pay_phase && tx_byte_count == 0) begin
                mf_pay_phase <= 1'b1;
            end else if (mf_pay_phase) begin
                if (mf_pay_valid) begin
                    tx_captured[tx_byte_count] <= mf_pay_byte;
                    tx_byte_count <= tx_byte_count + 1;
                    if (tx_byte_count + 1 >= mf_pay_len) begin
                        mf_pay_phase  <= 1'b0;
                        mf_busy       <= 1'b0;
                        mf_frame_done <= 1'b1;
                    end
                end
            end
        end
    end

    always @* fp_rd_data = fp_payload_buf[fp_rd_addr];

    task feed_frame(input [23:0] msgid, input [7:0] paylen);
        begin
            @(negedge clk);
            fp_msg_id   <= msgid;
            fp_pay_len  <= paylen;
            fp_frame_ok <= 1'b1;
            @(negedge clk);
            fp_frame_ok <= 1'b0;
            @(negedge clk);
        end
    endtask

    task seed_bytes(input [63:0] s, input integer base);
        begin
            fp_payload_buf[base+0] = s[63:56];
            fp_payload_buf[base+1] = s[55:48];
            fp_payload_buf[base+2] = s[47:40];
            fp_payload_buf[base+3] = s[39:32];
            fp_payload_buf[base+4] = s[31:24];
            fp_payload_buf[base+5] = s[23:16];
            fp_payload_buf[base+6] = s[15:8];
            fp_payload_buf[base+7] = s[7:0];
        end
    endtask

    task wait_r1_frame(input integer nbytes);
        begin
            guard = 0;
            while (tx_byte_count < nbytes && guard < 300000) begin
                @(posedge clk);
                guard = guard + 1;
            end
            if (guard >= 300000) begin
                $display("TB_PUF_INJECT_FAIL (R1 frame timeout, %0d bytes)", nbytes);
                $fatal(1, "R1 frame timeout");  // auto-review P3: 错误即停，不再错误打印后继续出 DONE
            end
            repeat (2) @(negedge clk);
        end
    endtask

    initial begin
        repeat (5) @(negedge clk);
        rst = 1'b0;
        repeat (2) @(negedge clk);

        seed_bytes(64'hC0FF_EEBE_EF12_3456, 0);   // A
        seed_bytes(64'h0F1E_2D3C_4B5A_6978, 8);   // B
        seed_bytes(64'hFEED_FACE_CAFE_BABE, 16);  // C
        seed_bytes(64'h1234_5678_9ABC_DEF0, 24);  // D

        @(negedge clk); auth_start = 1'b1;
        @(negedge clk); auth_start = 1'b0;
        guard = 0;
        while (tx_byte_count < 16 && guard < 10000) begin @(posedge clk); guard = guard + 1; end
        repeat (2) @(negedge clk);
        tx_byte_count = 0;

        feed_frame(24'h0091, 8'd32);              // CHALLENGE
        wait_r1_frame(32);

        $write("INJECT_FREQS");
        for (i = 0; i < 16; i = i + 1) $write(" %04h", u_ro_array.sim_freq[i]);
        $write("\n");
        $display("INJECT_R1 A=%016h B=%016h C=%016h D=%016h",
                 {tx_captured[0],tx_captured[1],tx_captured[2],tx_captured[3],
                  tx_captured[4],tx_captured[5],tx_captured[6],tx_captured[7]},
                 {tx_captured[8],tx_captured[9],tx_captured[10],tx_captured[11],
                  tx_captured[12],tx_captured[13],tx_captured[14],tx_captured[15]},
                 {tx_captured[16],tx_captured[17],tx_captured[18],tx_captured[19],
                  tx_captured[20],tx_captured[21],tx_captured[22],tx_captured[23]},
                 {tx_captured[24],tx_captured[25],tx_captured[26],tx_captured[27],
                  tx_captured[28],tx_captured[29],tx_captured[30],tx_captured[31]});
        $display("INJECT_WINCOUNT %0d (warmup 7 + final 1)", win_count);
        $display("TB_PUF_INJECT_DONE");
        $finish;
    end

    initial begin
        #2_000_000;
        $display("TB_PUF_INJECT_FAIL (global watchdog)");
        $finish;
    end

endmodule
