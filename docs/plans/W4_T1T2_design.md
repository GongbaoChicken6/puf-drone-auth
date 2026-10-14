# W4-P4 T1/T2 修订执行方案 v2（审查 T1T2R 闭环后）

## 0. 审查修复摘要

| 发现 | 修复 |
|---|---|
| P0-1 fold 三侧矛盾 | 冻结单一构造（§1.1），双侧字节序对齐 NSA 小端 wire-byte |
| P0-2 sp_key mux 毁黄金 | mux 不动；新增 ENABLE_KEY_DERIVE 参数（默认 0=旧行为） |
| P0-3 ro_entropy 到不了 c2_counter | c2_counter 加同步装载（seed_load 脉冲门控） |
| P1-1 KDF 偏离设计书 | 对齐 §5v2 降级路径：key=fold(K_boot⊕MASK), pt=fold(key_seed) |
| P1-2 新态无看门狗 | 纳入 timeout_cnt 门控清单 + PUF_WD 预算 |
| P1-3 Speck 时分缺通路 | sp_plaintext 加状态 mux（KDF 态时切换源） |
| P2-1 第二 ro_array ifdef | 镜像 PUF_MODEL_SIM 分支 |
| P2-2 折叠 XOR vs 拼接 | 冻结拼接（低 4bit × 16 环 = 64bit） |
| P2-3 seed_valid 前 auth 未门控 | S_IDLE 加 seed_valid 门控 |
| P2-4 key_valid=0 时 CHALLENGE 丢弃 | rx_ok_latch 保持清单加新态 |

## 1. T1 密钥派生（修订版）

### 1.1 冻结 KDF 构造（唯一权威定义）

```python
# 常量（双侧冻结）
KEY_SEED_INT = 0x6B65797365656431    # ASCII "keyseed1" 8B
KDF_MASK_INT = 0xA5A55A5AA5A55A5A

def derive_device_key(puf) -> bytes:
    """降级路径 KDF（W4_design §5v2:59 对齐版）
    
    key12 = K_boot + K_boot[:4]           # 8B→12B（拼接，非折叠）
    pt1   = key_seed_packed               # 公开常数
    pt2   = key_seed_packed ^ KDF_MASK    # 公开常数
    ct1   = Speck6496(key12).encrypt(pt1) # 8B
    ct2   = Speck6496(key12).encrypt(pt2) # 8B
    K     = ct1 + ct2[:4]                 # 12B = 96bit
    """
    from src.python.common.speck import Speck6496
    
    k_boot = puf.ideal(KEY_SEED_INT.to_bytes(8, "big"))  # 8B
    key12 = k_boot + k_boot[:4]  # 12B key
    
    pt1 = KEY_SEED_INT.to_bytes(8, "big")
    pt2 = (KEY_SEED_INT ^ KDF_MASK_INT).to_bytes(8, "big")
    
    ct1 = Speck6496(key12).encrypt(pt1)
    ct2 = Speck6496(key12).encrypt(pt2)
    
    return ct1 + ct2[:4]  # 12B
```

**RTL 对应：**
```verilog
// key12 = {k_boot_reg[63:0], k_boot_reg[31:0]}  — 96bit
// pt1 = KEY_SEED（冻结常量）
// pt2 = KEY_SEED ^ KDF_MASK
// ct1/ct2 = Speck(key12, pt)  — 时分复用
// K = {ct1_reg[63:0], ct2_reg[63:32]}  — 96bit
```

**字节序（双侧一致）：**
- key_in[95:0]：Python bytes → int.from_bytes(key, "big") → Verilog 96-bit 向量
- plaintext_in[63:0]：同上
- 密钥 K 存储：ct1[0:8] + ct2[0:4]，大端拼接

### 1.2 RTL 架构（P0-2 修复版）

**不变式：参数 ENABLE_KEY_DERIVE=0 时行为与当前完全一致（所有 TB 黄金零改动）**

```verilog
parameter ENABLE_KEY_DERIVE = 0  // 0=TB 兼容（用 DEVICE_KEY），1=板上（用 PUF 派生）

// key 派生寄存器
reg [95:0]  key_reg = 96'd0;
reg         key_valid = 1'b0;
reg [63:0]  k_boot_reg = 64'd0;
reg [63:0]  kdf_ct1 = 64'd0;
reg [1:0]   kdf_step = 2'd0;  // 0=idle, 1=encrypt1, 2=encrypt2

// sp_key mux 保持不变（P0-2 修复）:
assign sp_key = use_ext_key ? device_key_in : DEVICE_KEY;
// 板上: w3_top 接 .use_ext_key(key_valid & ENABLE_KEY_DERIVE),
//              .device_key_in(key_reg)
// TB:   .use_ext_key(1'b0)  — 不变, 黄金不变

// S_IDLE 门控（P2-3 修复）:
if (auth_start) begin
    if (ENABLE_KEY_DERIVE && !key_valid) begin
        state <= S_KEY_MEASURE;  // 首次: 先派生密钥
    end else begin
        state <= S_CALC_R2;      // 正常: 已有密钥或 TB 模式
    end
end
```

**S_KEY_MEASURE (4'd3)：**
- 与 S_PUF_DECODE/MEASURE/PACK 相同管线但 seed=KEY_SEED 固定
- **纳入看门狗**（P1-2 修复）：timeout_cnt 门控清单加入此态
- 完成后 k_boot_reg ← 8B 响应 → S_KEY_DERIVE

**S_KEY_DERIVE (4'd9)：**
- **纳入看门狗**
- kdf_step 0→1→2：
  - step1: sp_start_w=1, key=key12, pt=KEY_SEED → sp_done → kdf_ct1 锁存
  - step2: sp_start_w=1, key=key12, pt=KEY_SEED^KDF_MASK → sp_done → key_reg 锁存
- key_valid <= 1 → S_CALC_R2
- **sp_plaintext mux（P1-3 修复）**：
  ```verilog
  assign sp_plaintext = (state == S_KEY_DERIVE) ? kdf_plaintext : c2_plaintext;
  ```

**rx_ok_latch 保持清单（P2-4 修复）：**
- 新增 S_KEY_MEASURE/S_KEY_DERIVE 到保持条件（防止 KEY_SEED 帧丢失）

### 1.3 w3_top 接线

```verilog
// 板上（ENABLE_KEY_DERIVE=1）:
terminal_fsm # (
    .ENABLE_KEY_DERIVE(1)
) u_fsm (
    .use_ext_key   (key_valid & ENABLE_KEY_DERIVE),  // P0-2: 不改 mux
    .device_key_in (key_reg),
    ...
);
```

### 1.4 seed_load 脉冲（P0-3 修复）

```verilog
// terminal_fsm 新增:
input wire seed_load,  // 单拍脉冲：同步重装载 C2

// c2_counter 从 initial 改为同步装载:
// (保留 initial 作为上电默认/TB 兼容; seed_load 脉冲时同步覆盖)
always @(posedge clk) begin
    if (seed_load) begin
        for (j = 0; j < 8; j = j + 1)
            c2_counter[j] <= c2_boot_seed[8*j +: 8];
    end
end
// TB: seed_load=0 → initial 值不变（黄金不变）
// 板上: ro_entropy.seed_valid 上升沿产生 seed_load 脉冲
```

## 2. T2 ro_entropy（修订版）

### 2.1 折叠方式冻结（P2-2 修复）

**拼接（非 XOR）**：boot_seed[4*i +: 4] = ring_freq[i*CNT_W +: 4]
即：16 个环各取低 4bit，直接拼接成 64bit。

### 2.2 模块接口

```verilog
module ro_entropy # (
    parameter [4:0] SAMPLE_WINS  = 5'd1,      // 采样 1 窗（不需要热稳定）
    parameter       SAMPLE_CYCLES = 32'd1_000_000  // 10ms @100MHz
) (
    input  wire clk, rst,
    input  wire start,                    // 上电后触发（可接 rst 释放）
    output wire ra_measure_en, ra_ring_en,
    input  wire ra_done,
    input  wire [255:0] ra_ring_freq,
    output reg  seed_valid,               // 1 = boot_seed 已锁存
    output reg [63:0] boot_seed           // 拼接的低 4bit × 16
);
```

### 2.3 w3_top 集成（P2-1 修复：ifdef 镜像）

```verilog
// 独立例化第二个 ro_array（镜像 ifdef PUF_MODEL_SIM）
`ifdef PUF_MODEL_SIM
    ro_array_sim # (.N_RINGS(16), .CNT_W(16)) u_ro_entropy_array (...);
`else
    ro_array # (.N_RINGS(16), .CNT_W(16), .DIV_STAGES(5)) u_ro_entropy_array (...);
`endif

// seed 装载脉冲
reg seed_load_pulse = 1'b0;
always @(posedge sys_clk) begin
    if (ro_entropy_seed_valid && !seed_load_prev) seed_load_pulse <= 1'b1;
    else seed_load_pulse <= 1'b0;
    seed_load_prev <= ro_entropy_seed_valid;
end
```

### 2.4 CI/脚本登记（P2-1 修复）

- ci_regression.ps1: ro_entropy.v 加入编译清单
- build_w3_board.tcl: ro_entropy.v + 第二 ro_array 源文件
- synth_w3.tcl: 同步

## 3. 修订执行步骤（8 步 → 含审查修复）

| # | 内容 | 修复引用 | 预估 |
|---|---|---|---|
| S1 | derive_device_key() + 单测 + 黄金向量 | P0-1 | 45min |
| S2 | terminal_fsm: 参数+新态+看门狗+mux+seed_load | P0-2/P0-3/P1-2/P1-3/P2-3/P2-4 | 3h |
| S3 | w3_top: 接线+ifdef+ro_entropy 例化 | P2-1 | 45min |
| S4 | TB: GJ(派生密钥认证)+GK(P1-5 重放拒止)+interop 自动 setkey | | 1h |
| S5 | ro_entropy.v 模块 + 独立 TB | P0-3 | 1h |
| S6 | CI/build 脚本登记 | P2-1 | 15min |
| S7 | 契约+HANDOFF+看板 | | 15min |
| S8 | 全量 CI + 审查 | | 30min |

**总计 ~7.5h（一个工作日，含审查返工预算）**
