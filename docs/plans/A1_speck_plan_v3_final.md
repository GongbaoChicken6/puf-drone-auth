
# A1 共识综合（B+C+D 三代理审查 → 最终计划 v3）

## 高置信度发现（≥2 个代理独立确认）

| # | 发现 | 确认方 | 行动 |
|---|---|---|---|
| 1 | 字节序/打包必须在契约中冻结 | B+C+D | 写入 protocol_contract.md + 生成器双格式输出 |
| 2 | 加密输入矛盾（⊕C2 vs 纯C2） | B+C+D | 定稿：plaintext=C2, key=device_key, 无预异或 |
| 3 | TB 黄金向量必须程序化生成 | C+D | gen_speck_vectors.py 单源生成 |
| 4 | 密钥不能硬编码且必须持久化 | B+C+D | DeviceKeyStore + 参数传入 + #define 共用 |
| 5 | S_CALC_R2 需要看门狗 + fp_rx_inhibit | C+D | ~1024 周期看门狗 + 加入 inhibit 表达式 |
| 6 | 输出用 wire 不用 reg（guardrails） | B | output wire + 内部 reg + assign |
| 7 | LUT 估算 100→250-300 | B | 更新预算为 ~950 总 LUT |
| 8 | 资源选 Option A（扁平寄存器 ~1010 FF） | B | 保守方案，易验证 |

## 最终决策清单

### 算法接口（定稿）
- plaintext_in = C2（64位，不预异或）
- key_in = device_key（96位，参数传入）
- 输出 = ciphertext_out（64位 = R2）
- 字节序：线上序大端（bytes[0] = key_in[95:88] 高位）

### FSM 架构（定稿）
- 4 状态：S_IDLE → S_KEY_EXPAND → S_ENC → S_IDLE
- done = 寄存器单拍脉冲（无 S_DONE 状态）
- start = 单拍脉冲，只在 S_IDLE 接受
- busy = 输出线
- 轮计数器 5 位

### 集成方案（定稿）
- terminal_fsm 增加共享 S_CALC_R2 状态（解决 S_IDLE/S_SESSION 重复）
- S_CALC_R2 负责：C2++、tx_buf 预填、speck_start、等 done
- S_CALC_R2 加入 fp_rx_inhibit 表达式
- 加 1024 周期看门狗（超时→S_BLOCKED）
- device_key = terminal_fsm 的 96 位参数（W3 测试值，W4 PUF 提取）

### 测试策略（定稿）
- tb_speck.v：10 类用例（T1 复位/T2 KAT/T3 边角/T4 随机1000/T5 背靠背/T6 忙中start/T7 运行中复位/T8 done单拍/T9 输入毛刺/T10 时延上界）
- tb_terminal_fsm.v：例化第二个 speck64_96 参考应答器（与 DUT 实发 C2 解耦）
- tb_level3_protocol.v：RESULT 帧 R2+CRC 由生成器原子再生成
- 向量：NSA KAT（双源核对）+ 边角（全0/全FF/交替/单比特游走/进位链）+ 随机 1000（固定种子）
- CI 加：tb_speck + speck64_96.v + Python 测试段 + --check 新鲜度 + 线性金丝雀

### Python 侧（定稿）
- speck.py：Speck6496 类，encrypt(pt)->ct，key/c2 长度校验
- hsm.py：SpeckHSM 包装 speck.py，per-terminal 密钥
- protocol.py：_finish_pass 加 terminal_id 传递
- main.py：DeviceKeyStore（JSON, 0600, 持久化）
- 修复：main.py 当前每次运行生成随机密钥不持久化

### 文件清单（更新后）

| 文件 | 操作 | 行数 | 说明 |
|---|---|---|---|
| src/rtl/common/speck64_96.v | 新建 | ~150 | Speck 密码核 |
| src/python/common/speck.py | 新建 | ~50 | Python 参考实现 |
| src/rtl/w3_protocol/terminal_fsm.v | 修改 | +40/-25 | S_CALC_R2 + Speck 实例 + inhibit 扩展 |
| src/python/server/hsm.py | 修改 | +20/-25 | SpeckHSM + per-terminal key |
| src/python/server/protocol.py | 修改 | +5 | _finish_pass 加 terminal_id |
| src/python/server/main.py | 修改 | +15 | DeviceKeyStore 持久化 |
| sim/tb/tb_speck.v | 新建 | ~200 | 10 类用例 |
| sim/testvectors/speck_random.mem | 新建 | 数据 | 1000 组随机向量 |
| sim/tb/tb_terminal_fsm.v | 修改 | +30 | 参考 Speck 应答器 |
| sim/tb/tb_level3_protocol.v | 修改 | +10 | 用生成的 R2+CRC |
| scripts/gen_speck_vectors.py | 新建 | ~80 | 单源向量生成器 |
| scripts/test_r2_nonlinearity.py | 新建 | ~40 | 线性金丝雀 |
| docs/protocol_contract.md | 修改 | ~40 | 字节序+算法定义+黄金帧 |
| scripts/ci_regression.ps1 | 修改 | +10 | tb_speck + Python 段 |

### 更新工期（7h → 10h）

| 步骤 | 内容 | 预计 |
|---|---|---|
| 1 | speck64_96.v + tb_speck.v（10 用例） | 3h |
| 2 | Python speck.py + 单测 | 1h |
| 3 | gen_speck_vectors.py（双格式+KAT自检+--check） | 1h |
| 4 | terminal_fsm 集成（S_CALC_R2+看门狗+inhibit） | 1h |
| 5 | hsm.py + protocol.py + main.py | 1h |
| 6 | TB 更新 + 全量回归 + CI | 2h |
| 7 | 文档 + 线性金丝雀 + 提交 | 1h |
| **合计** | | **~10h** |
