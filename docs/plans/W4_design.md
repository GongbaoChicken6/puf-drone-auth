# W4 设计书 v1.1

> 配套：docs/plans/W4_plan.md。冻结 W4 技术决策；与 project_design.md v3.0 冲突处以本文为准并回写。
> v1.1：纳入 3 代理计划审查（热稳定窗/看门狗/上板脚本扩源/tie-off/KDF 全规格/熵声明 2^96/灰区打包/对拍种子口径/P1-5 机制/温度判据）。

## 1. R1 响应语义（位级冻结，契约 §8）

seed → challenge_decode.pair_table（8 轮×8 对；条目 [p*8+:8] 低 4bit=A 高 4bit=B，既有格式）；测量后 bit(r,p) = (freq[B] > freq[A]) ? 1 : 0（=design.md pair_win"1=B 环快"；相等取 0，stub 频率生成时保证无相等）。
**组装**：R1[63]=bit(0,0) … R1[0]=bit(7,7)（round-major，pair 序 MSB→LSB）；byte_j = R1[63-8j -: 8]。灰区每种子同管线产 64bit（3×8B=24B 与契约 §3 吻合）。
**时延（含热稳定）**：热稳定 7 窗×1ms + 4×2050 拍解码 + 1ms 测量窗 + 打包 <100 拍 ≈ **8.1ms** ≪ 2s（注：2s 超时原语义覆盖等待态，S_PUF_* 已自带看门狗，见 §2.2）。熵：单路总排序 16!≈2^44。

## 2. RTL 集成

### 2.1 terminal_fsm 新增端口（**tie-off 策略**：V2001 输入端口无默认值，既有 TB 各补两行 tie-off：`.c2_boot_seed(64'hA7A6A5A4A3A2A1A0), .device_key_in(96'h1312...0100), .use_ext_key(1'b0)`——黄金 C2/R2 期望值零改动）
```
output wire         cd_start;  output wire [63:0] cd_seed;
input  wire [511:0] cd_pair_table;  input wire cd_done;
output wire         ra_measure_en;  output wire ra_ring_en;
input  wire         ra_busy, ra_done;  input wire [255:0] ra_ring_freq;
input  wire [63:0]  c2_boot_seed;   // TB tie 常量；板上接 ro_entropy
input  wire [95:0]  device_key_in;  // TB tie 参数密钥
input  wire         use_ext_key;    // TB 显式 0；板上接内部 key_valid（§5）
```
### 2.2 状态机（编码 13/14/15 空闲已核）
- S_PUF_DECODE(13)：逐种子 cd_start→cd_done，缓存 pair_table×4（灰区×3）
- S_PUF_MEASURE(14)：ra_ring_en=1 → **WARMUP_WINS=7 轮热稳定窗（W2 冻结口径，w2_top.v:17-19 / project_design.md:201-203，逐窗丢弃）** → 第 8 窗测量锁存 ring_freq
- **ring_en 占空比差异（审查 C-P2 记录）**：W2 w2_top.v:373 ring_en 恒 1（环自上电常开，G2≥97% 基线在此条件建立）；本设计仅测量期开振（认证期 ~8ms），每次从冷环起步靠 7 窗热稳定逼近——**该差异未论证等效**，W4-P6 板上可靠性判据须在冷启动条件下实测验证（若不达标回退方案：decode 期间提前开振）
- S_PUF_PACK(15)：比较位打包——4 种子填 resp_buf[0..31]→S_TX_R1；**灰区 3 种子填 resp_buf[0..23]、tx_len=24→S_TX_R1_EXTRA**（4'd10 既有态）
- **S_PUF_* 看门狗**：三态共用超时计数（预算 = (WARMUP_WINS+1)×MEASURE_CYCLES + 10^5 拍余量；超时→S_BLOCKED，auth_result=3）——修正 v1.0"2s 超时覆盖"的错误归因（原超时只挂等待态，terminal_fsm.v:217-218）
- **同步功能条件（P2R-P3）**：fp_rx_inhibit（terminal_fsm.v:158）与 rx_ok_latch 条件（:170-171）中的 S_PROC_SEEDS/S_PROC_EXTRA 引用需替换为 S_PUF_* 三态——这是功能条件非注释，漏改则载荷保护失效；tb_gap GA inhibit 用例为回归锚点
- P2-1 加固：calc_done_flag 由 sp_done 置位，**S_VERIFY_R2 入口校验、校验完成后清零**（与任何帧无关，防"发帧清零"误伤合法流）；default→S_BLOCKED 保留为 **X 态/位宽扩展防护**（13-15 启用后 16 编码全占用，陷阱不再是可达路径，措辞诚实化）
### 2.3 w3_top 集成与上板脚本
- 例化 challenge_decode + ro_array；MEASURE_CYCLES=FREQ_HZ/1000；`PUF_MODEL_SIM` ifdef 下 ro_array 换 ro_array_sim stub（可编程 ring_freq，.mem 注入）
- **build_w3_board.tcl 必须扩**（v1.0"既有/不受影响"为事实错误）：add_files 补 `w1_ratio/ro_ring.v、w1_ratio/ro_div.v、w2_array/ro_array.v、w2_array/challenge_decode.v`（对齐 synth_w3.tcl:17-20 既有清单）；constrs_1 补 w2_waiver.xdc；脚本头注释改"全引脚约束；DRC 豁免仅设计使然的环振组合环（LUTLP-1）"
- ro_entropy（§6）与注册模式（§5）在 w3_top 顶层接线

## 3. TB 与对拍口径

- **对拍种子**：tb_challenge_decode 现仅 SEED_FIX+全零（v1.0"3 个已验证种子"失实）→ P1 任务中先扩 TB 3 个新冻结种子 + puf_model 逐 bit 对拍，hex 写入契约 §8
- 期望 R1：scripts/gen_puf_fixtures.py 生成 .mem → 4 个既有 TB 注入；黄金 R2 七用例不变（C2 语义未动）
- 新 tb_puf_path：decode/热窗/测量/打包全链 + **看门狗超时** + 窗口边界 + 输入毛刺 + 灰区 24B
- tb_speck 补输入毛刺用例（HANDOFF 计划偏差）；CI 12→14 TB（+tb_puf_path，tb_challenge_decode 既有）

## 4. PC 侧

- puf_model.ROPairingPUF/decode_pair_table/golden_fixtures 接口同 v1.0
- SimulatedTerminal 改薄壳（保留 impostor/counter_challenge 语义）
- interop：复用 **tests/test_serial_server.py 已有的 WireTerminal/WireTransport 模式**（v1.0 误写为主.py 资产；如跨文件复用则提取 tests/wire_helpers.py）
- 评估工具对齐 R1 64bit + reliability 统计（单路 ≥97% 为 G2 口径）

## 5. 密钥派生与熵混合（P1-1，v2 全规格冻结）

**常量**：key_seed = 64'h6B657973_65656431（ASCII "keyseed1" 全 8B，修正 v1.0 的 56bit 字面量）；MASK = 64'hA5A5_5A5A_A5A5_5A5A。
**派生**（终端每次上电）：K_boot = respond(key_seed)（8B，PUF 自派生无需上行）。
**混合**：K16 = SpeckEnc(key=station_random[0:12], pt=K_boot) ‖ SpeckEnc(key=station_random[0:12], pt=K_boot⊕MASK)；**K = K16[0:12]**（96bit；RTL 复用 Speck 核两次，PC 用 speck.py；黄金向量双侧冻结）。
**station_random 通道（主案）**：新增帧 **0x0096 KEY_SEED**（server→terminal，载荷 16B=station_random；契约 §3 扩展 + §7 变更控制 + check_contract_sync 扩展）。触发：**term_id_dip==2'b11（拨码 W6/W7 双 1）上电进注册模式**——S_ENROLL_WAIT：先测 K_boot，等 KEY_SEED 帧→两次 Speck 得 K→key_valid=1→回 CONFIRM(status=ENROLL_OK)；超时 30s 退出并拒绝认证。
**断电语义**：K 无 NVM，每次上电重派生；**key_valid 旗标驱动 use_ext_key**——未派生/派生失败时认证直接 BLOCKED，**绝不静默回退参数 NSA 密钥**（v1.0 未声明，P2R 指出）；参数 DEVICE_KEY 仅存于 TB tie-off 路径。
**信任边界与安全声明（报告口径）**：station_random 明文仅出现在注册信道（物理近距受控假设，条件化声明）；**离线穷举上界 = 2^96（K 空间），非 2^128**（修正 v1.0 过度声明）；实际增益 = 消除"公开向量密钥"与 2^44 低熵穷举，"抗离线穷举"仍不可声明。
**降级路径（时间紧，已实现为 W4-P4 T1）**：不做 0x0096 帧；`key12 = K_boot + K_boot[:4]`（8B+4B **拼接**，非折叠），`pt1 = key_seed`、`pt2 = key_seed ⊕ MASK`（均为公开常量），`K = Speck(key12, pt1) ‖ Speck(key12, pt2)[:4]`（96bit，**熵 ≈44bit**）。
- **诚实口径**：P1-1"非公开向量"在 RTL 层成立；熵混合目标未达成（无 station_random）。
- **部署前置（2026-10-14 审查 B-P1-1 补记）**：站端必须先获得 K 才能启用（`w3_top.ENABLE_KEY_DERIVE` 默认 0 = fail-safe）。缺失通道 = 0x0096 KEY_SEED 注册模式（主案）或站端注册期派生；且单次测量型 K_boot 存在噪声可靠性问题（需纠错或多数表决），未解决前**不得声明板上 P1-1 达成**。

## 6. P1-5 C2 上电随机化

ro_entropy（~40 行）：上电开环 10ms 窗，ring_freq[16] 各计数低 4bit 折叠异或 → 64bit c2_boot_seed 锁存。terminal_fsm 的 c2_counter 初始化 = c2_boot_seed 按字节展开（TB tie 常量=旧行为，黄金不变）。
**验收机制（v1.1 纠正）**：换电重启后重放旧 RESULT 帧 → 终端以**新 C2** 重算 R2 期望 → S_VERIFY_R2 比对失败 → BLOCKED（**服务器重放窗只防上行重放，与本路径无关**）。有效熵诚实口径 ~16-32bit/次上电 + 128 深服务端窗兜底（R6）。nonce 随机化列 stretch。

## 7. ML 实验（同 v1.0，口径=design.md:385-401 冻结文案）
入口 `python -m src.python.evaluation.ml_attack --exp A|B --out data/ml_attack/`；实验 A：合成 arbiter + sklearn LR（训练集 1k~100k 准确率曲线）；实验 B：puf_model 带噪 CRP → 比胜关系恢复 → 拓扑排序重构成功率（50~400 CRP）；matplotlib 3.11 已装；种子固定可复现。

## 8. 板上实验口径（含判据冻结）

| 项 | 操作 | **判据** | 数据落点 |
|---|---|---|---|
| 唯一性 | 板 A/B 或跨实例同种子集 | HD/64 均值 ≈32 | data/w4_readings/uniqueness/ |
| 可靠性(常温) | 同种子 20 次 | 单路 bit 稳定率 ≥97%（G2） | data/w4_readings/reliability/ |
| 温度 | 暖手宝 ΔT≤30°C，XADC 70°C 硬停，每 5°C 一组（每点 5 次） | **全温区 reliability ≥85%（允许比常温降 5%，project_design.md:251）** | data/w4_readings/temp/ |
| 多终端 | 实例 0~3 并发注册+认证+互斥 | 全部互斥演示成立 | data/w4_readings/multi/ |
| 无线 | air rate 64k/ECC/NETID；半双工 1-2ms 实测适配 | 端到端认证 PASS | data/w4_readings/radio/ |

## 9. 实施顺序（每步 CI 全绿）
P0（CI 作业化）→ P1（模型+契约）→ P2-T2（tie-off 端口，行为不变）→ P2-T1/T3（状态机+热窗+看门狗+集成+脚本扩源）→ P2-T4（黄金再生+毛刺）→ P3（PC 适配+interop）→ P4-T2/T3（RTL 安全）→ P4-T1/T4/T5/T6（密钥/DoS/运维/PoC harness）→ P5（ML）→ P6（板上）→ P7（W5 前置穿插）。
不变式：①CI 数量单调不减 ②参数默认/tie-off=旧行为、黄金值零改动 ③黄金变更必有再生脚本+证据 ④上板脚本同步扩、豁免口径诚实 ⑤每里程碑审查轮+bundle 备份。
