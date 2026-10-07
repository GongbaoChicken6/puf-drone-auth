# PUF 无人机认证项目 · 交接摘要
生成时间：2026-10-08（A1 阶段 4 完成后；上版 2026-10-07 为阶段 3 后）
项目路径：D:\puf-drone-auth
Git：51 commits · 111 files · tag w3-complete

## 一、项目概况

**竞赛**：2026 全国大学生嵌入式芯片与系统设计竞赛（FPGA 创新赛道，AMD 初级组）
**截止**：11-04 18:00（距现在约 28 天）
**平台**：ZC702 (XC7Z020-1CLG484)
**项目**：XOR-CRO-PUF 硬件指纹无人机认证系统（HF-IDA 双向认证协议）
**教师要求**：回归 PUF 本体、协议不加密、论文多实现少的 FPGA 实现、扩展无人机 AI 应用、突出特色

## 二、当前进度（A1 任务）

### A1 = 统一 R2 算法（用 Speck64/96 替换不安全的 ~C2）

**已完成：**
- ✅ 阶段 1：密码核基础
  - src/python/common/speck.py（~180 行，双实现+NSA KAT）
  - src/rtl/common/speck64_96.v（133 行，4 态 FSM，53 周期）
  - sim/tb/tb_speck.v（8 用例全过）
  - NSA 官方测试向量验证通过（字节序修复后）

- ✅ 阶段 2：向量基础设施
  - scripts/gen_speck_vectors.py（5 类向量，--check 模式）
  - sim/testvectors/speck_random.mem（1175 组）
  - CI 已接入（ci_regression.ps1 含 11 TB）

- ✅ 阶段 3：FPGA 集成
  - terminal_fsm.v：新增 S_CALC_R2 状态（4'd12），Speck 实例化
  - C2 字节重排（NSA 约定）：c2[0..3]→y→pt[63:32], c2[4..7]→x→pt[31:0]
  - R2 解包：ct[39:32..]→r2[0..7]
  - 256 周期看门狗 + fp_rx_inhibit 扩展
  - DEVICE_KEY 参数：96'h13121110_0b0a0908_03020100（W3 测试值）
  - tb_terminal_fsm.v + tb_level3_protocol.v 黄金值更新
  - tb_gap_regression.v（6 安全测试：伪造R2/重放/灰区）
  - 11/11 TB 全 PASS

- ✅ 阶段 4：PC 集成（2026-10-08，经 5 轮 auto-review 共识 PASS：P0/P1/P2=0）
    - hsm.py：SpeckHSM 类（R2 = Speck64/96(K_term, C2)，per-terminal 12B 密钥；保留 SimulatedHSM）
    - protocol.py：_finish_pass 传 terminal_id；C2 防重放窗口（P1-2 修复，持久化跨重启）+ RESULT_REPLAY=4；迟到/冲突 C2 在评分前验证；HSM 故障转 RESULT_ERROR 帧
    - main.py：DeviceKeyStore（JSON 0600 原子写 + 失败回滚 + RLock）修复密钥不持久化；REPL setkey/c2reset；loopback C2 计数器对齐 RTL 语义
    - tests/test_a1_phase4.py：44 个单测（黄金向量/重启防重放 E2E/灰区路径/回滚）；CI 接入 Python 段（fail-closed 门禁）
    - 审查证据：build/reviews/a1p4/（CONSENSUS.md 终审报告 + FIXLIST.md 四轮修复轨迹 + 7 份审查 JSON）
    - 黄金对齐：REPL setkey W3 密钥后首次认证 R2 = 7b45b0545e59aa94（与 tb_terminal_fsm 逐位一致）

**未完成：**
    
- ⬜ 阶段 5：集成测试（~1.5h）
    - 全量 11 TB 回归
    - Python 单测（speck.py + hsm.py 新路径）
    - 线性金丝雀（scripts/test_r2_nonlinearity.py——验证 R2 不可被线性拟合）
    
- ⬜ 阶段 6：文档 + 提交（~1h）
    - protocol_contract.md：R2 算法定义 + 字节序约定 + 新黄金帧
    - project_design.md：安全分析更新 + 熵值诚实声明
    - check_contract_sync.py 重跑

## 三、关键技术决策（已定稿）

### Speck64/96 参数
- 字长 32 bit / 块 64 bit（=8B=R2）/ 密钥 96 bit（=12B=PUF 稳定位）/ 26 轮
- ARX 结构（无 S 盒），NSA 2013 规范
- 最好攻击只到 19/26 轮（73%），安全余量 27%

### 字节序（NSA 官方约定，已冻结）
- plaintext bytes[0:4] → y → plaintext_in[63:32]
- plaintext bytes[4:8] → x → plaintext_in[31:0]
- ciphertext 先序列化 y 再 x
- key bytes[0:4]→k0→key_in[31:0], [4:8]→l0→[63:32], [8:12]→l1→[95:64]
- 全部小端（little-endian）

### DEVICE_KEY
- 当前：96'h13121110_0b0a0908_03020100 = NSA 公开测试向量（安全=零，仅 W3 演示）
- W4 计划：从 PUF 稳定位运行时提取（16 环信息论上限 ~44 bit 根熵）

### CRC 计算域
- MAVLink v2：header[1:10]（9 字节，含 MSGID 第 3 字节）+ payload + CRC_EXTRA
- CRC_EXTRA for RESULT(0x0093) = 0x5D
- 首次认证 R2 = Speck(K, C2=a1..a8) = 7b45b0545e59aa94
- RESULT 帧 CRC = ff 1d（seq=0x50 时）

## 四、三代理审查遗留问题

### 安全类（Agent C 发现）
| ID | 问题 | 严重度 | 归属 |
|---|---|---|---|
| P1-1 | DEVICE_KEY 是公开向量 | P1 | W4 修复 |
| P1-2 | 重放窗口=现在（断电+C2回绕+服务器无检查） | P1 | ✅ 阶段 4 已修（服务器侧窗口检查+持久化；C2 回绕为 W4 已知限制，断电恢复走 c2reset） |
| P1-3 | hsm.py 仍用 HMAC | P1 | ✅ 阶段 4 已修（SpeckHSM 为默认后端，黄金向量与 RTL 一致） |
| P1-4 | PUF 占位（种子直通） | P1 | W4 修复 |
| P2-1 | 跳过 S_CALC_R2 的故障注入→安全绕过 | P2 | W4 加固 |

### 覆盖类（Agent B 发现——已修复）
- ✅ 伪造 R2 测试 → tb_gap_regression GF
- ✅ 二次认证测试 → tb_gap_regression GD1/GD2  
- ✅ 灰区测试 → tb_gap_regression GE1/GE2

### 集成类（Agent A 发现——已修复）
- ✅ speck.py 文档字符串字节序写反 → 已修
- ✅ terminal_fsm 死代码 ~C2 → 已删

## 五、项目全景

### 文件结构
- src/rtl/ — 15 个 Verilog 模块（~2400 行）
  - common/：crc16, mavlink_frame, frame_parser, byte_fifo, uart_tx/rx, speck64_96
  - w1_ratio/：ro_ring, ro_div, ro_ratio_top
  - w2_array/：ro_array, challenge_decode, w2_top
  - w3_protocol/：terminal_fsm, w3_top, w3_top.xdc
- src/python/ — 11 个 Python 文件（~2600 行）
  - common/：speck.py
  - server/：protocol, crp_pool, template_db, threshold, hsm, main
  - evaluation/：hamming_analysis, compare_devices, quantizer
- sim/tb/ — 11 套 TB（~2100 行）
- sim/testvectors/ — speck_random.mem（1175 组）
- scripts/ — ci_regression, setup_external, gen_speck_vectors
- build/tcl/ — synth_w3.tcl, build_w3.tcl
- docs/ — protocol_contract, project_design, architecture.html, plans/

### 六周排期
- ✅ W1 信号验证（ro_ring + Artix-7 综合）
- ✅ W2 阵列 + B 线 Python 全套
- ✅ W3 协议栈 + 顶层 + 比特流（A1 进行中）
- ⬜ W4 实验周（ML 攻击 + 温度 + PUF 接入——纯 Python 部分可提前）
- ⬜ W5 冻结周（报告 + Skill + 视频）
- ⬜ W6 交付周（11-03 提交）

### 上板前必做清单
1. 填入 ZC702 真实引脚（查 UG850 + 主 XDC）
2. 时钟适配（200MHz 差分→100MHz：IBUFDS+MMCM）
3. 复位源改用 GPIO_SW_N（G19, LVCMOS25）
4. 购买 433MHz 电台一对
5. PC 串口通信循环
6. 拨码开关不够 8 位（用常量）

### 纯电脑端可做的 21 项任务
详见对话中的盘点，优先级最高的剩余项：
- A1 阶段 4-6（当前进行中）
- B5 PUF 真实接入（W4 核心创新）
- B6 ML 攻击实验（W4 交付物，20 分）
- D14 Skill 打包（15 分）
- D13 报告初稿（15 分）

## 六、工作方式约定

- 所有 RTL 遵循 rtl-guardrails（Verilog-2001，无 output reg，同步复位，声明时初始化）
- 每个阶段完成后用 auto-review 派遣多代理审查
- 审查发现按 P0→P1→P2→P3 修复，修复后跑全量回归
- CI：scripts/ci_regression.ps1 跑 11 TB
- 提交信息详细描述改动内容和原因

## 七、下一步（新会话直接从这里开始）

1. 执行 A1 阶段 5：全量回归 + 金丝雀
   - scripts/ci_regression.ps1 跑全量（11 TB + Python 段 44 测试）
   - scripts/test_r2_nonlinearity.py 线性金丝雀（R2 不可被线性拟合）
2. 执行 A1 阶段 6：文档 + 提交
   - protocol_contract.md：R2 算法定义 + 字节序约定 + 新黄金帧 + RESULT 码 4 已登记
   - project_design.md：安全分析更新 + 熵值诚实声明（防重放窗口 128 权衡见 protocol.py 注释与 CONSENSUS.md deferred 裁决）
   - check_contract_sync.py 重跑
3. 执行 A1 阶段 6：文档更新 + 提交
4. A1 完成后：选择下一任务（B5 PUF 接入 / B6 ML 攻击 / D14 Skill / D13 报告）
