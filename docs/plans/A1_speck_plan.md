> **[SUPERSEDED]** 本中间版已被 docs/plans/A1_speck_plan_v3_final.md（三代理共识终版）取代，仅作历史存档。

# A1 实施计划 v2：Speck64/96 轻量级密码统一 R2 算法

## 调研结论

### 1. 算法选择确认
- Speck64/96：NSA 2013 年发布的轻量级分组密码
- 字长 32 位，块 64 位（= 8 字节 = R2 长度），密钥 96 位（= 12 字节）
- 26 轮 ARX 结构（加法-旋转-异或），无 S 盒，天然免疫缓存时序攻击
- 密码分析现状：最好攻击只到 19 轮（我们用 26 轮，有 35% 安全余量）
- 已被 Linux 内核（2018年加入，后因政治原因移除但技术无问题）和多个 IoT 平台采用

### 2. 现成实现调研结果
| 来源 | 语言 | 状态 | 可用性 |
|------|------|------|--------|
| github.com/markcusRichardson/Speck64-96 | VHDL | 170 行 FSM | ✅ 可参考转换为 Verilog |
| Wikipedia 参考实现 | C | 完整可运行 | ✅ Python 端可直接翻译 |
| nsacyber.github.io 官方指南 | C | 含测试向量 | ✅ 测试向量来源 |
| Linux 内核 crypto/speck.c | C | 生产级 | 参考 |
| 自写 Python | Python | 需从规范实现 | ~30 行 |

### 3. VHDL 参考实现分析（我们转换为 Verilog）
- 架构：简单 FSM（IDLE→KEY_GEN→LOAD→ENCRYPT→DONE），每时钟 1 轮
- 接口：clk, reset, start, key_in[95:0], x_in[31:0], y_in[31:0], done, x_out, y_out
- 密钥扩展：26 个轮密钥预先计算存储在寄存器阵列
- 加密：26 轮迭代，每轮 1 个时钟
- 总周期：~55 个时钟（密钥扩展 26 + 加密 26 + 状态切换 3）
- 在 100MHz 下 = 0.55 微秒（协议超时 2 秒，余量 3.6 百万倍）

## 详细实施步骤

### 步骤 1：创建 speck64_96.v 模块（~150 行 Verilog）

接口设计（匹配我们的 rtl-guardrails 风格）：
```verilog
module speck64_96 (
    input  wire        clk,
    input  wire        rst,
    input  wire        start,        // 上升沿启动
    input  wire [95:0] key_in,       // 12 字节设备密钥
    input  wire [63:0] plaintext_in, // 8 字节明文（=C2）
    output reg  [63:0] ciphertext_out, // 8 字节密文（=R2）
    output reg         done          // 完成脉冲
);
```

内部结构：
- 5 状态 FSM：S_IDLE → S_KEY_EXPAND → S_ENCRYPT → S_DONE → S_IDLE
- 密钥扩展：26 个 32 位轮密钥 + 27 个 32 位 L 值（可优化为即时计算）
- 加密轮：x = (ROR(x,8) + y) ^ rk[i]; y = ROL(y,3) ^ x;
- 资源估算：~200 FF（密钥阵列+数据+计数器）+ ~100 LUT（运算逻辑）

### 步骤 2：创建 Python speck.py（~40 行）

```python
class Speck6496:
    def __init__(self, key: bytes):  # 12 字节密钥
    def encrypt(self, plaintext: bytes) -> bytes:  # 8 字节 → 8 字节
    def _key_schedule(self) -> list[int]:  # 生成 26 个轮密钥
    def _round(self, x, y, k) -> tuple:  # ARX 轮函数
```

### 步骤 3：修改 terminal_fsm.v

改动点：
a) 删除旧的 r2_expected 计算（~C2 公式）
b) 添加 speck64_96 实例
c) 在 S_TX_ACCESS 之前插入 S_CALC_R2 状态：
   - 启动 Speck 加密 device_key ⊕ C2
   - 等待 done（~55 周期）
   - 将结果存入 r2_expected
d) device_key 来源：W3 用测试常量，W4 从 PUF 提取

### 步骤 4：修改 hsm.py

改动点：
a) 删除 HMAC-SHA256 逻辑
b) SimulatedHSM.__init__ 接受 device_key（12 字节）
c) respond(c2) 调用 Speck6496.encrypt(c2)
d) 添加 C2 输入验证（长度=8）

### 步骤 5：生成测试向量

用 Python 生成黄金向量：
- 已知答案测试（NSA 官方向量）
- 随机 (key, plaintext, ciphertext) 三元组 × 100 组
- 存入 sim/testvectors/speck_golden.vh（Verilog $readmemh 格式）

### 步骤 6：创建 tb_speck.v

- 读入黄金向量文件
- 驱动 DUT 加密每组 (key, plaintext)
- 逐位比较输出与期望密文
- 报告 PASS/FAIL

### 步骤 7：更新 tb_terminal_fsm.v 和 tb_level3_protocol.v

- RESULT 帧中的 R2 字节改为用 Python 计算的 Speck 密文
- 更新黄金向量

### 步骤 8：全量回归 + 文档更新

- 跑全部 TB（原有 10 套 + 新增 tb_speck = 11 套）
- 更新 protocol_contract.md（R2 算法定义 + Speck 参数）
- 更新 project_design.md（安全分析 + 资源变化）

## 文件改动清单

| 文件 | 操作 | 行数估算 |
|------|------|----------|
| src/rtl/common/speck64_96.v | 新建 | ~150 |
| src/python/common/speck.py | 新建 | ~40 |
| src/rtl/w3_protocol/terminal_fsm.v | 修改 | +30/-15 |
| src/python/server/hsm.py | 修改 | +15/-20 |
| sim/tb/tb_speck.v | 新建 | ~80 |
| sim/testvectors/speck_golden.mem | 新建 | 数据 |
| sim/tb/tb_terminal_fsm.v | 修改 | ~20 |
| sim/tb/tb_level3_protocol.v | 修改 | ~10 |
| docs/protocol_contract.md | 修改 | ~30 |
| docs/project_design.md | 修改 | ~20 |
| scripts/gen_speck_vectors.py | 新建 | ~30 |

## 资源预算

| 项目 | 估算 | 备注 |
|------|------|------|
| Speck 轮密钥存储 | 26×32 = 832 FF | 可优化为即时计算（省 576 FF）|
| Speck L 值存储 | 27×32 = 864 FF | 同上（可省）|
| Speck 数据寄存器 | 64 FF | x/y 各 32 |
| Speck 控制逻辑 | ~20 FF | FSM + 计数器 |
| Speck 运算逻辑 | ~100 LUT | 加法器+旋转+异或 |
| **总计（保守）** | **~1780 FF + 100 LUT** | 存储全部中间值 |
| **总计（优化后）** | **~85 FF + 100 LUT** | 即时计算轮密钥 |

对比当前设计：653 LUT + 1033 FF
加 Speck 后（保守）：~753 LUT + ~2813 FF（Z7020 0.97% → 2.6%）

选择保守方案（全存储轮密钥）：更简单、更容易验证正确性。
FF 不是瓶颈（Z7020 有 106,400 个 FF），LUT 才是。100 LUT 增量完全可承受。

## 时序预算

- 密钥扩展：26 周期
- 加密：26 周期
- 状态切换：~3 周期
- 总计：~55 周期 @ 100MHz = 0.55 µs
- 协议超时：2 秒 = 200,000,000 周期
- 余量：363 万倍 ✅

## 安全声明（更新后）

1. R2 使用 Speck64/96 分组密码（NSA 发布，经过国际密码学界广泛分析）
2. 设备密钥 96 位，从 PUF 稳定位在注册时提取（非制造时写入）
3. 块大小 64 位 = 8 字节 = R2 长度，完美匹配
4. 26 轮提供 35% 安全余量（最好攻击只到 19 轮）
5. ARX 结构无 S 盘无查找表 → 无缓存时序泄露
6. 密钥不在比特流中硬编码 → 上板后从 PUF 运行时提取

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| VHDL→Verilog 转换引入错误 | 用 NSA 官方测试向量逐字节验证 |
| Verilog 和 Python 结果不一致 | 生成 100 组随机向量交叉验证 |
| 密钥扩展占太多 FF | 先用保守方案，如果资源不够再优化 |
| device_key 硬编码在 RTL 中 | 用参数传入+注释标记测试值，W4 替换 |

## 工期估算

| 步骤 | 内容 | 预计 |
|------|------|------|
| 1 | speck64_96.v 编写+单元TB | 2 小时 |
| 2 | Python speck.py | 1 小时 |
| 3 | 测试向量生成+交叉验证 | 1 小时 |
| 4 | terminal_fsm.v 集成 | 1 小时 |
| 5 | hsm.py 集成 | 30 分钟 |
| 6 | TB 更新+全量回归 | 1 小时 |
| 7 | 文档更新 | 30 分钟 |
| **合计** | | **~7 小时** |

## 验证清单

- [ ] tb_speck：NSA 官方测试向量通过
- [ ] tb_speck：100 组随机向量通过
- [ ] Python speck.py 与 Verilog speck64_96.v 交叉一致
- [ ] tb_terminal_fsm：完整通过流（新 R2）
- [ ] tb_terminal_fsm：拒绝流（错误 R2）
- [ ] tb_level3：全链路协议（新 R2）
- [ ] 全量 11 套 TB 回归
- [ ] 综合资源在预算内（<800 LUT）
- [ ] protocol_contract.md 更新
- [ ] 提交 git