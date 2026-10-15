`timescale 1ns / 1ps
//============================================================================
// tb_key_derive.v -- W4-P4 T1: 密钥派生端到端验证（ENABLE_KEY_DERIVE=1）
//----------------------------------------------------------------------------
// T5: 首次 auth_start → S_KEY_MEASURE → S_KEY_DERIVE → key_valid=1 + key_reg 黄金
// T6: 二次 auth_start → key_valid 保持 1（不重复派生）→ 直接进 S_CALC_R2
// 黄金 K 从 puf_model.derive_device_key(fixture_freqs) 预计算，字节反转后
// 对应 RTL key_reg_r 的 96-bit 位序。
//============================================================================
module tb_key_derive;

    reg clk = 1'b0, rst = 1'b1, auth_start = 1'b0;
    reg [7:0] terminal_id = 8'h01;
    wire auth_busy;
    wire [1:0] auth_result;
    wire key_valid;
    wire [95:0] key_reg;

    // RX 模型（同 tb_puf_path）
    reg [23:0] fp_msg_id = 24'h0;
    reg [7:0] fp_pay_len = 8'd0;
    reg fp_frame_ok = 1'b0, fp_frame_err = 1'b0;
    wire fp_rx_inhibit;
    wire [4:0] fp_rd_addr;
    reg [7:0] fp_rd_data = 8'h00;
    reg [7:0] fp_payload_buf [0:31];

    // TX 模型（同 tb_puf_path）
    wire mf_start;
    wire [23:0] mf_msg_id;
    wire [5:0] mf_pay_len;
    wire [7:0] mf_pay_byte, mf_seq;
    wire mf_pay_valid;
    wire mf_sysid, unused_compid;
    reg mf_busy = 1'b0, mf_pay_phase = 1'b0, mf_frame_done = 1'b0, mf_frame_err = 1'b0;

    integer errors = 0, guard = 0, tx_byte_count = 0;
    reg [7:0] tx_captured [0:63];
    // GJ/GK: 默认种子对应旧行为（A0..A7）；GK 改成另一熵值模拟换电重启
    reg [63:0] c2_seed    = 64'hA7A6_A5A4_A3A2_A1A0;
    reg        seed_pulse = 1'b0;
    // 黄金 R2（Python Speck6496(derive_device_key()).encrypt(C2)）
    localparam [63:0] R2_DEFAULT_K = 64'h730adaa96ee973e9;  // C2=a1..a8
    localparam [63:0] R2_ENT1_K    = 64'hb5873d06281fff7f;  // C2=9358d308709af235
    localparam [63:0] R2_ENT2_K    = 64'h3a57fb2ca0dda68b;  // C2=63b509207f3ec4a6
    reg [95:0] key_reg_snapshot = 96'd0;   // C2: T6 稳定性快照
    reg        reentered_derive  = 1'b0;   // C2: T6 重派生标志
    reg [63:0] r2_obs            = 64'd0;   // GJ: r2_expected 观测值
    reg [63:0] recorded_r2       = 64'd0;   // GK: 攻击者录制的旧 R2
    integer    gk_i              = 0;        // T15: 循环变量
    integer    tw_bits = 0;

    // 黄金 K（fixture 频率 → puf_model → 字节反转到 RTL 位序）
    localparam [95:0] GOLDEN_KEY = 96'h26c4ec61ba319ff325041dee;

    // PUF 子系统
    wire cd_start, cd_done;
    wire [63:0] cd_seed;
    wire [511:0] cd_pair_table;
    wire ra_measure_en, ra_ring_en, ra_busy, ra_done;
    wire [255:0] ra_ring_freq;

    challenge_decode # (.N_ROUNDS(8), .N_RINGS(16), .IDX_W(4)) u_cd (
        .clk(clk), .rst(rst), .start(cd_start), .seed(cd_seed),
        .pair_table(cd_pair_table), .done(cd_done));

    ro_array_sim # (.N_RINGS(16), .CNT_W(16)) u_ro_array (
        .clk(clk), .rst(rst), .measure_en(ra_measure_en), .ring_en(ra_ring_en),
        .busy(ra_busy), .done(ra_done), .ring_freq(ra_ring_freq));

    // DUT: ENABLE_KEY_DERIVE=1
    terminal_fsm # (
        .TIMEOUT_CYCLES(32'd5000),
        .MEASURE_CYCLES(32'd64),
        .PUF_WD_CYCLES(32'd12000),
        .ENABLE_KEY_DERIVE(1)          // <<< 密钥派生启用
    ) dut (
        .clk(clk), .rst(rst),
        .auth_start(auth_start), .terminal_id(terminal_id),
        .auth_busy(auth_busy), .auth_result(auth_result),
        .c2_boot_seed(c2_seed),        // GJ/GK: 可控（模拟换电熵变化）
        .device_key_in(key_reg),       // 回环（同 w3_top）
        .use_ext_key(key_valid),       // 回环
        .seed_load(seed_pulse),        // GJ/GK: 单拍脉冲重装载
        .key_valid(key_valid),
        .key_reg(key_reg),
        .cd_start(cd_start), .cd_seed(cd_seed),
        .cd_pair_table(cd_pair_table), .cd_done(cd_done),
        .ra_measure_en(ra_measure_en), .ra_ring_en(ra_ring_en),
        .ra_busy(ra_busy), .ra_done(ra_done), .ra_ring_freq(ra_ring_freq),
        .fp_msg_id(fp_msg_id), .fp_pay_len(fp_pay_len),
        .fp_frame_ok(fp_frame_ok), .fp_frame_err(fp_frame_err),
        .fp_rd_addr(fp_rd_addr), .fp_rd_data(fp_rd_data),
        .fp_rx_inhibit(fp_rx_inhibit),
        .mf_start(mf_start), .mf_msg_id(mf_msg_id),
        .mf_pay_len(mf_pay_len), .mf_pay_byte(mf_pay_byte),
        .mf_pay_valid(mf_pay_valid), .mf_seq(mf_seq),
        .mf_sysid(mf_sysid), .mf_compid(unused_compid),
        .mf_busy(mf_busy), .mf_pay_phase(mf_pay_phase),
        .mf_frame_done(mf_frame_done), .mf_frame_err(mf_frame_err));

    always #5 clk = ~clk;

    // mavlink 模型（同 tb_puf_path）
    always @(posedge clk) begin
        mf_frame_done <= 1'b0;
        if (mf_start) begin
            mf_busy <= 1'b1; mf_pay_phase <= 1'b0; tx_byte_count <= 0;
        end else if (mf_busy) begin
            if (!mf_pay_phase && tx_byte_count == 0) mf_pay_phase <= 1'b1;
            else if (mf_pay_phase && mf_pay_valid) begin
                tx_captured[tx_byte_count] <= mf_pay_byte;  // 保留供未来 R2 断言
                tw_bits = tw_bits + 1;
                tx_byte_count <= tx_byte_count + 1;
                if (tx_byte_count + 1 >= mf_pay_len) begin
                    mf_pay_phase <= 1'b0; mf_busy <= 1'b0; mf_frame_done <= 1'b1;
                end
            end
        end
    end

    always @* fp_rd_data = fp_payload_buf[fp_rd_addr];

    task feed_frame(input [23:0] msgid, input [7:0] paylen);
        begin
            @(negedge clk); fp_msg_id <= msgid; fp_pay_len <= paylen; fp_frame_ok <= 1'b1;
            @(negedge clk); fp_frame_ok <= 1'b0;
            @(negedge clk);
        end
    endtask

    initial begin
        repeat (5) @(negedge clk); rst = 1'b0;
        repeat (2) @(negedge clk);

        //==================== T5: 首次 auth → 密钥派生 ====================
        @(negedge clk); auth_start = 1'b1;
        @(negedge clk); auth_start = 1'b0;

        // 等 key_valid（S_KEY_MEASURE ~3k 拍 + S_KEY_DERIVE ~200 拍）
        guard = 0;
        while (!key_valid && guard < 20000) begin @(posedge clk); guard = guard + 1; end

        if (key_valid && guard > 100) begin
            // 验证 key_reg 黄金值
            $display("[DEBUG] key_reg=%h k_boot=%h", key_reg, dut.k_boot_reg);
            $display("[DEBUG] kdf_key12=%h", dut.kdf_key12);
            $display("[DEBUG] kdf_ct1=%h ct2_last=%h", dut.kdf_ct1, dut.sp_ciphertext);
            $display("[DEBUG] expected_key12=0df58d745de035700df58d74");
            if (key_reg === GOLDEN_KEY)
                $display("[T5 PASS] key_valid=1 (%0d 拍) + key_reg=黄金值", guard);
            else begin
                errors = errors + 1;
                $display("[T5 FAIL] key_reg=%h != 黄金 %h", key_reg, GOLDEN_KEY);
            end
        end else begin
            errors = errors + 1;
            $display("[T5 FAIL] key_valid=%b guard=%0d", key_valid, guard);
        end

        // 等 ACCESS 帧发完（密钥派生后正常进 S_CALC_R2→S_TX_ACCESS）
        guard = 0;
        while (tx_byte_count < 16 && guard < 5000) begin @(posedge clk); guard = guard + 1; end

        //==================== GJ: 派生密钥认证 R2 黄金锁 ====================
        // 端到端验证 Speck 真的用了派生密钥：S_CALC_R2 锁存的 r2_expected
        // 必须等于 Speck(K, C2) 的黄金值（K=派生密钥, C2=a1..a8）
        r2_obs = {dut.r2_expected[0], dut.r2_expected[1], dut.r2_expected[2], dut.r2_expected[3],
                  dut.r2_expected[4], dut.r2_expected[5], dut.r2_expected[6], dut.r2_expected[7]};
        if (r2_obs === R2_DEFAULT_K)
            $display("[GJ PASS] 派生密钥认证: r2_expected=%h = Speck(K,%h) 黄金", r2_obs, 64'ha1a2a3a4a5a6a7a8);
        else begin
            errors = errors + 1;
            $display("[GJ FAIL] r2_expected=%h != 黄金 %h (派生密钥未参与 Speck 或字节序错)", r2_obs, R2_DEFAULT_K);
        end

        //==================== T6: 二次 auth 不重复派生 ====================
        // 等 FSM 回 IDLE（发 REJECT 帧退出）
        fp_payload_buf[0] = 8'h01;  // REJECT
        feed_frame(24'h0093, 8'd10);
        guard = 0;
        while (auth_busy && guard < 5000) begin @(posedge clk); guard = guard + 1; end

        // 二次 auth_start：key_valid 应保持 1，直接进 S_CALC_R2
        // C2 强化：直接断言 (a) 派生后 key_reg 不变 (b) 状态从未进入 3/9
        // (c) kdf_key12 与冻结常量逐位一致 —— 替代原"计时代理"间接判据
        tx_byte_count = 0;
        key_reg_snapshot = key_reg;
        reentered_derive = 1'b0;
        @(negedge clk); auth_start = 1'b1;
        @(negedge clk); auth_start = 1'b0;
        guard = 0;
        while (tx_byte_count < 16 && guard < 5000) begin
            @(posedge clk);
            guard = guard + 1;
            // 状态采样：S_KEY_MEASURE=3 / S_KEY_DERIVE=9 出现即失败
            if (dut.state === 4'd3 || dut.state === 4'd9) reentered_derive = 1'b1;
        end
        if (!key_valid) begin
            errors = errors + 1; $display("[T6 FAIL] key_valid 丢失");
        end else if (reentered_derive) begin
            errors = errors + 1; $display("[T6 FAIL] 二次 auth 重入了派生路径 (state 3/9)");
        end else if (key_reg !== key_reg_snapshot) begin
            errors = errors + 1;
            $display("[T6 FAIL] key_reg 变化 %h -> %h", key_reg_snapshot, key_reg);
        end else
            $display("[T6 PASS] 二次 auth 未重派生 (%0d 拍), key_reg 稳定=%h", guard, key_reg);

        // T6b: kdf_key12 与冻结常量逐位比对（原为未参与比对的 display）
        if (dut.kdf_key12 === 96'h0df58d745de035700df58d74)
            $display("[T6b PASS] kdf_key12 = 冻结常量 0df58d745de035700df58d74");
        else begin
            errors = errors + 1;
            $display("[T6b FAIL] kdf_key12=%h != 0df58d745de035700df58d74", dut.kdf_key12);
        end

        //==================== T8: S_KEY_MEASURE 看门狗 ====================
        // C3: 派生失败不变式——cd_done 卡死 → PUF_WD → BLOCKED + key_valid 保持 0
        // 先让 FSM 回 S_IDLE（WAIT_CHALL 超时 → BLOCKED → IDLE）
        guard = 0;
        while (dut.state !== 4'd0 && guard < 30000) begin @(posedge clk); guard = guard + 1; end
        if (dut.state !== 4'd0) begin
            errors = errors + 1; $display("[T8 FAIL] FSM 未回 IDLE guard=%0d state=%0d", guard, dut.state);
        end
        repeat (10) @(negedge clk);
        force dut.key_valid_r = 1'b0;    // 复位派生状态以重入 S_KEY_MEASURE
        @(negedge clk); auth_start = 1'b1;
        @(negedge clk); auth_start = 1'b0;
        release dut.key_valid_r;
        guard = 0;
        while (dut.state !== 4'd3 && guard < 10000) begin @(posedge clk); guard = guard + 1; end
        if (dut.state !== 4'd3) begin
            errors = errors + 1; $display("[T8 FAIL] 未进入 S_KEY_MEASURE guard=%0d", guard);
        end else begin
            force dut.cd_done = 1'b0;    // 解码永不完
            guard = 0;
            while (dut.state !== 4'd11 && guard < 40000) begin @(posedge clk); guard = guard + 1; end
            release dut.cd_done;
            if (dut.state === 4'd11 && !key_valid && guard > 500)
                $display("[T8 PASS] cd_done 卡死 → BLOCKED (%0d 拍) + key_valid=0", guard);
            else begin
                errors = errors + 1;
                $display("[T8 FAIL] state=%0d key_valid=%b guard=%0d", dut.state, key_valid, guard);
            end
        end
        while (dut.auth_busy) @(posedge clk);
        repeat (5) @(negedge clk);

        //==================== T9: S_KEY_DERIVE 看门狗 ====================
        // C3: sp_done 卡死 → calc_wd → BLOCKED + key_valid=0
        force dut.key_valid_r = 1'b0;
        @(negedge clk); auth_start = 1'b1;
        @(negedge clk); auth_start = 1'b0;
        release dut.key_valid_r;
        guard = 0;
        while (dut.state !== 4'd9 && guard < 40000) begin @(posedge clk); guard = guard + 1; end
        if (dut.state !== 4'd9) begin
            errors = errors + 1; $display("[T9 FAIL] 未进入 S_KEY_DERIVE guard=%0d", guard);
        end else begin
            force dut.sp_done = 1'b0;    // Speck 永不完成
            guard = 0;
            while (dut.state !== 4'd11 && guard < 10000) begin @(posedge clk); guard = guard + 1; end
            release dut.sp_done;
            if (dut.state === 4'd11 && !key_valid && guard > 100)
                $display("[T9 PASS] sp_done 卡死 → BLOCKED (%0d 拍) + key_valid=0", guard);
            else begin
                errors = errors + 1;
                $display("[T9 FAIL] state=%0d key_valid=%b guard=%0d", dut.state, key_valid, guard);
            end
        end
        while (dut.auth_busy) @(posedge clk);

        //==================== GK: P1-5 换电重启重放拒止 ====================
        // 场景：攻击者录制会话1的 RESULT 帧(含 R2=Speck(K,C2_ent1))；终端换电
        // 重启 -> ro_entropy 给出新种子 -> C2 变 -> 终端期望 R2=Speck(K,C2_ent2)
        // -> 重放旧 R2 必然不匹配 -> S_VERIFY_R2 拒止 -> BLOCKED。
        // 这是 P1-5 的**终端侧**验收（与服务器重放窗 P1-2 无关）。
        guard = 0;
        while (dut.state !== 4'd0 && guard < 40000) begin @(posedge clk); guard = guard + 1; end

        // --- 会话1：熵种子1，跑完整认证拿到 r2_expected（=攻击者录到的 R2） ---
        c2_seed = 64'h34F1996F07D25792;
        @(negedge clk); seed_pulse = 1'b1;
        @(negedge clk); seed_pulse = 1'b0;
        repeat (3) @(negedge clk);
        tx_byte_count = 0;
        @(negedge clk); auth_start = 1'b1;
        @(negedge clk); auth_start = 1'b0;
        guard = 0;
        while (tx_byte_count < 16 && guard < 5000) begin @(posedge clk); guard = guard + 1; end
        r2_obs = {dut.r2_expected[0], dut.r2_expected[1], dut.r2_expected[2], dut.r2_expected[3],
                  dut.r2_expected[4], dut.r2_expected[5], dut.r2_expected[6], dut.r2_expected[7]};
        if (r2_obs !== R2_ENT1_K) begin
            errors = errors + 1;
            $display("[GK FAIL] 会话1 r2_expected=%h != %h（熵种子未生效）", r2_obs, R2_ENT1_K);
        end else
            $display("[GK INFO] 会话1 熵种子1: C2 变 -> R2=%h (攻击者录制值)", r2_obs);
        recorded_r2 = r2_obs;   // 攻击者手里录到的旧 R2

        // 退出发帧态回 IDLE
        fp_payload_buf[0] = 8'h01;
        feed_frame(24'h0093, 8'd10);
        guard = 0;
        while (dut.state !== 4'd0 && guard < 40000) begin @(posedge clk); guard = guard + 1; end

        // --- 换电重启：新熵种子2 ---
        c2_seed = 64'hA5C33D7E1F08B462;
        @(negedge clk); seed_pulse = 1'b1;
        @(negedge clk); seed_pulse = 1'b0;
        repeat (3) @(negedge clk);
        // 新熵种子 0xA5C33D7E1F08B462 -> 低字节 0x62 装载到 c2_counter[0]
        if (dut.c2_counter[0] !== 8'h62) begin
            errors = errors + 1;
            $display("[GK FAIL] 重启后 c2_counter[0]=%h != 8'h62（seed_load 未生效）", dut.c2_counter[0]);
        end else
            $display("[GK INFO] 换电重启后 c2_counter[0]=%h（熵种子2 已装载）", dut.c2_counter[0]);

        // --- 会话2：终端用新 C2 算 R2，攻击者重放旧 R2（完整协议交换）---
        tx_byte_count = 0;
        @(negedge clk); auth_start = 1'b1;
        @(negedge clk); auth_start = 1'b0;
        guard = 0;
        while (tx_byte_count < 16 && guard < 5000) begin @(posedge clk); guard = guard + 1; end
        r2_obs = {dut.r2_expected[0], dut.r2_expected[1], dut.r2_expected[2], dut.r2_expected[3],
                  dut.r2_expected[4], dut.r2_expected[5], dut.r2_expected[6], dut.r2_expected[7]};
        if (r2_obs !== R2_ENT2_K) begin
            errors = errors + 1;
            $display("[GK FAIL] 会话2 r2_expected=%h != %h", r2_obs, R2_ENT2_K);
        end
        // 完整交换：先喂 CHALLENGE 让 FSM 走完 PUF 管线到 WAIT_RESULT
        guard = 0;
        while (dut.state !== 4'd2 && guard < 5000) begin @(posedge clk); guard = guard + 1; end
        @(negedge clk);
        for (gk_i = 0; gk_i < 32; gk_i = gk_i + 1)
            fp_payload_buf[gk_i] = 8'h50 + gk_i[7:0];
        feed_frame(24'h0091, 8'd32);
        guard = 0;
        while (dut.state !== 4'd5 && guard < 30000) begin @(posedge clk); guard = guard + 1; end
        // 现在在 WAIT_RESULT：重放旧 R2 → S_VERIFY_R2 逐字节失配 → BLOCKED
        fp_payload_buf[0] = 8'h00;   // result=PASS
        fp_payload_buf[1] = 8'h05;   // hd
        fp_payload_buf[2] = recorded_r2[63:56]; fp_payload_buf[3] = recorded_r2[55:48];
        fp_payload_buf[4] = recorded_r2[47:40]; fp_payload_buf[5] = recorded_r2[39:32];
        fp_payload_buf[6] = recorded_r2[31:24]; fp_payload_buf[7] = recorded_r2[23:16];
        fp_payload_buf[8] = recorded_r2[15:8];  fp_payload_buf[9] = recorded_r2[7:0];
        feed_frame(24'h0093, 8'd10);
        guard = 0;
        while (dut.state !== 4'd11 && guard < 2000) begin @(posedge clk); guard = guard + 1; end
        if (auth_result === 2'd3 && guard < 100)
            $display("[GK PASS] P1-5 换电重放拒止: 旧R2(%h) R2失配 -> BLOCKED(3) (%0d拍)", recorded_r2, guard);
        else begin
            errors = errors + 1;
            $display("[GK FAIL] auth_result=%0d guard=%0d（guard<100=失配路径; ~5000=超时路径）", auth_result, guard);
        end
        while (dut.auth_busy) @(posedge clk);


        //==================== T14: k_boot 全零退化自检 ====================
        // F6/T1b: force k_boot_reg=0 -> S_KEY_DERIVE step0 拦截 -> BLOCKED
        guard = 0;
        while (dut.state !== 4'd0 && guard < 40000) begin @(posedge clk); guard = guard + 1; end
        // 必须同时清 key_valid 才能重入 S_KEY_MEASURE（否则直走 S_CALC_R2 超时）
        force dut.key_valid_r = 1'b0;
        force dut.k_boot_reg = 64'd0;
        @(negedge clk); auth_start = 1'b1;
        @(negedge clk); auth_start = 1'b0;
        release dut.key_valid_r;   // S_IDLE 已决策，可释放
        // k_boot_reg 保持 forced=0 直到 S_KEY_DERIVE step0 检查
        guard = 0;
        while (dut.state !== 4'd11 && guard < 40000) begin @(posedge clk); guard = guard + 1; end
        release dut.k_boot_reg;
        if (dut.state === 4'd11 && !key_valid)
            $display("[T14 PASS] k_boot 全零 -> BLOCKED (%0d 拍) + key_valid=0", guard);
        else begin
            errors = errors + 1;
            $display("[T14 FAIL] state=%0d key_valid=%b guard=%0d", dut.state, key_valid, guard);
        end
        while (dut.auth_busy) @(posedge clk);

        //==================== T15: 坏 K 自愈 ====================
        // F6/T1c: 完整协议交换中 R2 失配 -> key_valid 清零 -> 下次 auth 重入派生
        guard = 0;
        while (dut.state !== 4'd0 && guard < 40000) begin @(posedge clk); guard = guard + 1; end
        // 若 GK/T14 后 key_valid 仍为 1，走完整交换触发一次明确失配
        if (key_valid) begin
            tx_byte_count = 0;
            @(negedge clk); auth_start = 1'b1;
            @(negedge clk); auth_start = 1'b0;
            guard = 0;
            while (tx_byte_count < 16 && guard < 5000) begin @(posedge clk); guard = guard + 1; end
            // 完整交换：CHALLENGE -> R1 -> 错误 R2 RESULT
            guard = 0;
            while (dut.state !== 4'd2 && guard < 5000) begin @(posedge clk); guard = guard + 1; end
            @(negedge clk);
            for (gk_i = 0; gk_i < 32; gk_i = gk_i + 1)
            fp_payload_buf[gk_i] = 8'h50 + gk_i[7:0];
        feed_frame(24'h0091, 8'd32);
            guard = 0;
            while (dut.state !== 4'd5 && guard < 30000) begin @(posedge clk); guard = guard + 1; end
            fp_payload_buf[0] = 8'h00; fp_payload_buf[1] = 8'h05;
            for (gk_i = 0; gk_i < 8; gk_i = gk_i + 1)
                fp_payload_buf[2+gk_i] = 8'hAA ^ gk_i[7:0];   // 错误 R2
            feed_frame(24'h0093, 8'd10);
            guard = 0;
            while (dut.state !== 4'd11 && guard < 2000) begin @(posedge clk); guard = guard + 1; end
            while (dut.auth_busy) @(posedge clk);
        end
        if (!key_valid)
            $display("[T15a PASS] R2 失配后 key_valid 已清（坏 K 不缓存）");
        else begin
            errors = errors + 1; $display("[T15a FAIL] key_valid=%b", key_valid);
        end
        // 下次 auth 应重入 S_KEY_MEASURE（state=3）
        guard = 0;
        while (dut.state !== 4'd0 && guard < 40000) begin @(posedge clk); guard = guard + 1; end
        @(negedge clk); auth_start = 1'b1;
        @(negedge clk); auth_start = 1'b0;
        guard = 0;
        while (dut.state !== 4'd3 && dut.state !== 4'd11 && guard < 5000) begin @(posedge clk); guard = guard + 1; end
        if (dut.state === 4'd3)
            $display("[T15b PASS] 下次 auth 重入 S_KEY_MEASURE（自愈重派生）");
        else begin
            errors = errors + 1; $display("[T15b FAIL] state=%0d 应=3", dut.state);
        end

        //==================== 汇总 ====================
        if (errors == 0)
            $display("TB_KEY_DERIVE_PASS: T5/T6/T6b/T8/T9/T14/T15 + GJ + GK 全部通过");
        else
            $display("TB_KEY_DERIVE_FAIL: %0d 项错误", errors);
        $finish;
    end

    initial begin
        #5_000_000;
        $display("TB_KEY_DERIVE_FAIL (global watchdog)");
        $finish;
    end
endmodule