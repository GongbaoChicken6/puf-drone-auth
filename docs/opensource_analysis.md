# 开源项目深度分析报告

> 基于实际克隆代码的逐文件分析，非 README 摘要。目的：确定每个项目的精确复用策略。
> 分析日期：2026-10-05

---

## 一、stnolting/fpga_puf（145★，VHDL，BSD-3）

### 1.1 它做了什么

用 **单比特锁存 PUF**（不是 RO-PUF！）生成 96-bit 芯片唯一 ID。核心机制：
- 每个 PUF cell 是一个带复位和使能的锁存器
- FSM 逐个使能锁存器 → 振荡一个时钟周期 → 冻结并采样
- 制造偏差决定锁存器最终停在 0 还是 1

### 1.2 代码结构（仅 2 个文件）

| 文件 | 行数 | 内容 |
|---|---|---|
| rtl/fpga_puf.vhd | 233 | 顶层 + 96 个 PUF cell 例化 + 采样 FSM（S_IDLE→S_RUN→S_SAMPLE） |
| rtl/neorv32_cfs.vhd | ~50 | NEORV32 CPU 总线接口封装（我们用不到） |

### 1.3 与我们项目的关系

| 维度 | 它的方案 | 我们的方案 | 差异 |
|---|---|---|---|
| PUF 类型 | 单比特锁存 | 环振对比较（RO-PUF） | **原理不同** |
| 响应生成 | 冻结采样 | 频率差计数 | 完全不同的硬件结构 |
| 挑战-应答 | 无（固定 ID） | 有（种子→配对选择） | 它是弱 PUF，我们是强 PUF |
| 抗 ML 攻击 | N/A（无 CRP） | XOR 混淆 | 它没有这个维度 |
| 工艺跨平台 | 是（跨 Intel/Xilinx） | 仅 Xilinx 7 系 | 它更通用 |

### 1.4 可复用内容

| 内容 | 复用方式 | 工作量 |
|---|---|---|
| 采样 FSM 设计模式（S_IDLE→S_RUN→S_SAMPLE） | **参考状态机结构**，用于我们的注册流程 | 低（改写为 Verilog） |
| 防综合优化策略（逐个使能而非同时使能） | **参考**：我们的 RO 用 KEEP/DONT_TOUCH，思路不同但目标一致 | N/A |
| README 中的可靠性数据（不同 FPGA 的实测） | **论文引用**：作为"同类基线"写入报告 | 零工作量 |

### 1.5 结论

**复用价值：低-中。** 原理不同（锁存 vs 环振），代码不可直接移植。价值在于：
- 报告中的"相关工作"引用（145★ + Zenodo DOI，学术可信度高）
- FSM 设计模式参考

---

## 二、eriksargent/PUF-lab（34★，Verilog）

### 2.1 它做了什么

64 个并行 **Arbiter PUF** + UART 接口 + 控制器 FSM。收 64-bit 挑战 → 产生 64-bit 响应 → UART 发回。

### 2.2 代码结构（9 个文件，共约 500 行）

| 文件 | 内容 | 质量 |
|---|---|---|
| arbiterpuf.v | 顶层：64 个 arbiter 例化（位置连接，非具名） | 差（大量重复代码） |
| arbiter.v | 单个 arbiter：双路径 DFF 竞争 | 可用 |
| arbel.v | 路径交换网络（挑战位控制上下路径） | **核心**：这是我们需要的"挑战→选路"逻辑 |
| 2x1mux.v / dflipflop.v | 基础单元 | 可用 |
| controller.v | UART 驱动的协议状态机 | 参考价值 |
| uart_tx.v / uart_rx.v | UART 收发 | **直接复用候选** |

### 2.3 与我们项目的关系

这是 **最接近我们需求的已有实现**——它实现了"挑战→响应→UART 回传"完整链路。

| 维度 | 它的方案 | 我们的方案 | 可复用程度 |
|---|---|---|---|
| PUF 类型 | Arbiter PUF | RO-PUF + XOR | 核心不同，外围相同 |
| 挑战机制 | 64-bit 路径选择 | 8-byte 种子→配对展开 | 不同实现，相同概念 |
| UART | 有（tx/rx 模块） | 有（相同需求） | **高**：uart_tx/uart_rx 可直接复用 |
| 协议 FSM | 简单收发 | HF-IDA 五帧双向 | 结构参考 |
| 抗攻击 | 无 | XOR(k=4) 混淆 | 我们的创新点 |

### 2.4 可复用内容

| 文件 | 复用策略 | 修改量 |
|---|---|---|
| **uart_tx.v** | **直接复制到 src/rtl/common/**，改端口风格 | 微调（加注释、适配编码规范） |
| **uart_rx.v** | **直接复制到 src/rtl/common/**，同上 | 微调 |
| **arbel.v（路径交换）** | **参考设计**：我们的"种子→配对表展开"可借鉴其 mux 树结构 | 重写（逻辑不同但结构相似） |
| **controller.v** | **参考 FSM 骨架**：空闲→收→算→发的流程 | 重写（我们的协议更复杂） |
| arbiterpuf.v / arbiter.v | **不适用**：Arbiter PUF 与 RO-PUF 原理不同 | 不复用 |

### 2.5 结论

**复用价值：高。** UART 模块可直接拿来用（省 ~200 行自写代码），协议 FSM 骨架可参考。arbel.v 的路径交换网络是"挑战→选路"的现成参考。

---

## 三、mavlink/c_library_v2（官方，C 头文件）

### 3.1 它是什么

MAVLink v2 协议的官方 C 语言实现——232 个消息类型的头文件（mavlink_msg_*.h），每个文件含 pack/unpack 函数。

### 3.2 与我们项目的关系

我们**不用 C 语言**，但需要：

| 需求 | 从这个仓库获取什么 | 怎么获取 |
|---|---|---|
| 帧结构精确定义 | mavlink_helpers.h 中的 MAVLINK_V2_FRAME 常量 | 读取头文件 |
| CRC-16/MCRF4XX 算法 | checksum.h 中的 crc_calculate / crc_accumulate | **翻译为 Verilog LFSR** |
| 自定义消息格式 | message_definitions/*.xml | 参考 XML 定义格式 |
| sysid/compid 惯例 | 各消息头中的默认值 | 直接引用 |

### 3.3 可复用内容

| 内容 | 复用策略 |
|---|---|
| CRC-16 算法（C 代码） | **翻译为 Verilog**：~50 行移位 LFSR，直接对照 C 写 |
| 帧字段偏移量定义 | 提取为 Python dict 常量（B 线用）+ Verilog localparam（A 线用） |
| 消息 XML 格式 | 定义我们的自定义 HF-IDA 消息（msgid 0x0090+） |

### 3.4 结论

**复用价值：中。** 不直接编译使用，但作为"协议规格的代码级表达"——CRC 算法和帧结构从这翻译。

---

## 四、xtncl/esp32-sram-puf-authentication（49★）

### 4.1 它做了什么

ESP32 的 SRAM PUF 认证 PoC，含硬件端（Arduino .ino）和服务器端（Node.js），以及 **统计分析 Python 工具**。

### 4.2 代码结构

| 目录 | 文件 | 价值 |
|---|---|---|
| tools/analysis/hamming_analysis.py | 241 行，单设备 HD/HW 分析 | **★★★ 直接复用** |
| tools/analysis/compare_devices.py | 154 行，跨设备 HD 对比 | **★★★ 直接复用** |
| tools/puf-challenge-generator/pufchallenge.py | 挑战生成器 | **★★ 参考** |
| server/auth-server/app.js | Node.js 认证服务器 | ★ 参考协议流 |
| hardware/*.ino | ESP32 固件 | 不适用（平台不同） |

### 4.3 可复用内容——这是 B 线的金矿

| 工具 | 它做什么 | 我们怎么用 | 修改量 |
|---|---|---|---|
| **hamming_analysis.py** | 读 hex 文件 → 算 HD 矩阵 + HW 分布 + 绘图 | **改数据源**：从 VIO 读数（hex）→ 同样分析 | 改 3 行（文件路径+位数参数） |
| **compare_devices.py** | 多设备目录 → 跨设备 HD 表 | **直接用**：板 A vs 板 B 的 uniqueness 验证 | 零修改 |
| **pufchallenge.py** | 随机挑战生成 | **改输出格式**：适配我们的 8-byte 种子 | 改 10 行 |

### 4.4 结论

**复用价值：极高（B 线）。** hamming_analysis.py 和 compare_devices.py 几乎零修改就能用于我们的 ROC/EER 评估。这个项目 44,778 次测量的统计方法论也可以直接引用到我们的报告中。

---

## 五、pymavlink（pip 安装，v2.4.50）

### 5.1 实测验证结果

```python
# 已安装并可导入
import pymavlink  # v2.4.50 ✓

# 帧封装验证（需注意 v1/v2 切换）
# ⚠️ 重要发现：默认可能使用 v1 帧（STX=0xFE）
# 必须设置 force_mavlink1 = False 确保使用 v2（STX=0xFD）
```

### 5.2 可复用内容

| 功能 | B 线用法 | 工作量 |
|---|---|---|
| mavutil.mavlink_connection() | 创建虚拟回环连接（自发自收测试） | 直接用 |
| msg.pack() / m.decode() | 帧封装/解析（认证报文收发） | 直接用 |
| CRC 校验 | 内置，无需手写 | 直接用 |
| 自定义消息 | 需要生成自定义 dialect XML → pymavlink 编译 | ~1h（定义 XML + 重新生成） |

### 5.3 关键注意事项

1. **v1/v2 帧切换**：必须显式设置 `force_mavlink1 = False`
2. **自定义消息**：需创建 .xml 定义文件 → 用 mavgen 编译为 Python 模块
3. **sysid 惯例**：地面站=255，飞行器=1~254

---

## 六、综合复用策略总表

| 我们要写的模块 | 来源 | 复用率 | 自主工作量 |
|---|---|---|---|
| **ro_ring.v（环振）** | 已完成 ✅ | — | — |
| **ro_div.v（分频）** | 已完成 ✅ | — | — |
| **ro_ratio_top.v（顶层）** | 已完成 ✅ | — | — |
| **uart_tx.v** | PUF-lab 直接复制 | ~90% | 改注释+端口风格 |
| **uart_rx.v** | PUF-lab 直接复制 | ~90% | 同上 |
| **crc16_mcrf4xx.v** | c_library_v2 翻译 | ~70% | C→Verilog 翻译 |
| **mavlink_frame.v** | c_library_v2 结构参考 | ~40% | 帧模板+字段拼接 |
| **挑战解码器** | PUF-lab arbel.v 参考 | ~20% | 结构参考，逻辑重写 |
| **16 环阵列** | 自研（创新点） | 0% | 全自写 |
| **XOR 合并** | 自研（创新点） | 0% | 全自写 |
| **PC 认证服务器** | pymavlink + 自研 | pymavlink 100% | 状态机+模板库 ~500 行 |
| **hamming_analysis** | esp32-puf 直接复制 | ~95% | 改数据源 3 行 |
| **compare_devices** | esp32-puf 直接复制 | ~100% | 零修改 |
| **ML 攻击 notebook** | 自研（sklearn） | 框架参考 PUF-lab | ~200 行 |

## 七、预计代码量节省

| 不用开源 | 用开源 | 节省 |
|---|---|---|
| ~3500 行 RTL + ~2000 行 Python | ~2200 行 RTL + ~800 行 Python | **~2500 行（~45%）** |

---

*本报告基于 D:\puf-drone-auth\external\ 下四个仓库的实际源码分析产出。*
