# PUF 无人机认证系统 · 完整可执行设计方案（v3.0 修订版）

> 基于 auto-review Round 1 报告修复：P0×3 + P1×9 + P2×6 + P3×8 全部处置。
> 修复日期：2026-10-05

---

## 〇、数据通路规格表（P0-3 修复——全链接口冻结）

**这是本文档的核心**——A/B 两线所有模块的位宽、格式、时序均以此为唯一依据。

### 挑战-响应完整数据流

```
PC 服务器                        ZC702 终端 (PL)
─────────                       ───────────────
                                ┌─────────────────────────────┐
8 字节挑战种子                   │ challenge_decode            │
(64-bit, CSPRNG 生成)  ──────►  │  LFSR 展开 → Fisher-Yates   │
                                │  洗牌 → 8 轮 × 8 对配对表    │
                                └──────────┬──────────────────┘
                                           │ 8 轮,每轮 8 对 (每环
                                           │ 恰好参与 4 轮中的 1 对)
                                           ▼
                                ┌─────────────────────────────┐
                                │ ro_array (16 环)            │
                                │  每轮: 8 对同时比较          │
                                │  输出: pair_win[7:0]        │
                                │  (每对 1 bit 胜者标志)       │
                                └──────────┬──────────────────┘
                                           │ 8 轮 × 8 bit = 64 bit
                                           ▼
                                ┌─────────────────────────────┐
                                │ resp_buffer                 │
                                │  累积 8 轮的 pair_win       │
                                │  最终: R1[63:0]             │
                                └──────────┬──────────────────┘
                                           │ 64 bit (8 字节)
                                           ▼
                                ┌─────────────────────────────┐
                                │ mavlink_frame               │
                                │  R1[63:0] → MAVLink v2 帧   │
                                │  → UART TX → 电台 → 无线    │
                                └─────────────────────────────┘
R1 (64 bit, MAVLink 帧) ◄────────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────┐
│ template_db (PC)             │
│  HD(R1, template) ≤ τ_pass  │
│  → 认证通过                  │
└─────────────────────────────┘
```

### 位宽规格总表（A/B 线冻结依据）

| 信号/参数 | 位宽 | 产生方 | 消费方 | 说明 |
|---|---|---|---|---|
| 挑战种子 seed | 64 bit (8B) | PC CSPRNG | challenge_decode | MAVLink payload 传输 |
| 配对表 (每轮) | PAIRS×2×IDX_W bit (16环=64bit) | challenge_decode | ro_array mux | IDX_W = $clog2(N_RINGS) |
| 配对表 (全部 8 轮) | 8 轮 × 32 bit | challenge_decode | 轮控 FSM | 存储在寄存器组中 |
| pair_win (每轮) | 8 bit | ro_array 比较器 | resp_buffer | 1 = B 环快, 0 = A 环快 |
| R1 (最终响应) | **64 bit (8B)** | resp_buffer 累积 | mavlink_frame → PC | 8 轮 × 8 bit |
| 模板 | 64 bit | 注册流程采集 | template_db.match() | 与 R1 同宽 |
| HD (海明距离) | 0~64 | template_db | threshold | 整数 |
| XOR 合并响应 (W3+) | 64 bit | 4 组 64-bit XOR | MAVLink frame | W2 不含 XOR, W3 加入 |

### XOR 升级路径（W3 加入，W2 不含）

W2 用原始 64-bit R1 直接认证。W3 将 16 环扩到 64 环，分 4 组各 16 环独立产生 64-bit 响应，XOR 后仍为 64-bit：

```
W2: R1 = round1_win ∥ round2_win ∥ ... ∥ round8_win    (64 bit, 无 XOR)
W3: R1 = (group1_resp ⊕ group2_resp ⊕ group3_resp ⊕ group4_resp)  (64 bit, XOR k=4)
```

**Reliability 口径（P1-5 修复）**：
- W2 门禁 G2 的 "reliability ≥90%" 指**单路（未 XOR）响应**的逐 bit 稳定性
- W3 加入 XOR 后，合并响应 reliability = p⁴ + 6p²(1-p)² + (1-p)⁴（p = 单路 reliability）
- 若需合并后 ≥90%，则单路需 ≥97.5%——通过增加环数和差分布局实现
- **G2 验收口径：单路 reliability ≥90%（W2），单路 ≥97%（W3+）**

---

## 〇.5、HSM 架构定义（P0-2 修复）

### 物理部署（真实场景 vs 竞赛演示）

```
真实部署（论文/报告画这个）:
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│ 无人机终端    │ 无线  │  地面基站    │  USB  │  基站 HSM    │
│ (PUF 实例1-3)│◄─────►│  (PC 服务器) │◄─────►│  (独立硬件)   │
│             │ 电台  │             │ 专线  │  (PUF 实例0) │
└─────────────┘       └─────────────┘       └─────────────┘

竞赛演示（代码实现的是这个）:
┌──────────────────────────────────────────────┐
│ ZC702 单板                                    │
│  ┌─────────────────┐  ┌────────────────────┐ │
│  │ 终端 PUF 实例 1-3 │  │ HSM PUF 实例 0     │ │
│  │ (逻辑隔离)       │  │ (UART 通道,非无线) │ │
│  └────────┬────────┘  └────────┬───────────┘ │
│           │ 无线电台            │ USB-JTAG    │
│           ▼                    ▼             │
└─────────────────┬──────────────────────────── ┘
                  │
                  ▼
          ┌─────────────┐
          │  PC 服务器   │
          │  (Python)   │
          └─────────────┘
```

### hsm.py 接口定义

```python
# src/python/server/hsm.py
class HSM:
    """基站硬件安全模块 — 通过 UART 与 ZC702 实例 0 通信"""

    def __init__(self, port: str, baud: int = 115200):
        self.serial = serial.Serial(port, baud)

    def respond(self, c2: bytes) -> bytes:
        """接收终端反挑战 C2,调用实例 0 生成 R2"""
        self.serial.write(c2)
        r2 = self.serial.read(8)  # 64-bit response
        return r2

    def enroll(self, n_challenges: int = 100) -> dict:
        """注册模式:采集实例 0 的 CRP 作为基站模板"""
        ...
```

### 终端验证 R2 的凭据来源

终端在**注册阶段**接收并存储基站模板（实例 0 的期望响应集），存于 PL 的 BRAM 中（只读寄存器组，运行期不可修改）。验证时：终端将收到的 R2 与存储的模板做 HD 比对。

---

## 一、A 线 · RTL 设计

### W2 · 16 环阵列 + 挑战解码 + UART 输出

#### 文件清单

| 文件 | 路径 | 来源 | 说明 |
|---|---|---|---|
| ro_ring.v | src/rtl/w1_ratio/ | ✅ 已有 | 复用 |
| ro_div.v | src/rtl/w1_ratio/ | ✅ 已有 | 复用（测量窗用） |
| **ro_array.v** | src/rtl/w2_array/ | 自研 | 16 环 + 8 对 mux + 比较器 |
| **challenge_decode.v** | src/rtl/w2_array/ | 自研 | 种子→配对表（见下文算法） |
| **w2_top.v** | src/rtl/w2_array/ | 自研 | 顶层：轮控 FSM + 响应缓冲 |
| uart_tx.v | src/rtl/common/ | PUF-lab 复用 | 改端口命名+加复位 |
| w2_waiver.xdc | src/rtl/w2_array/ | 改自 W1 | 16 环豁免 |
| w2_pins.xdc | src/rtl/w2_array/ | **新增** | UART TX 引脚 |
| **tb_ro_array.v** | sim/tb/ | 自研 | 仿真 testbench |
| **tb_challenge_decode.v** | sim/tb/ | 自研 | 解码器 testbench |
| build_w2.tcl | build/tcl/ | 改自 W1 | W2 构建 |

#### challenge_decode.v 算法规格（P1-2 修复）

```verilog
// 输入: seed[63:0]
// 输出: pair_table[7:0][7:0]  (8 轮 × 8 对 × 每对 2 个 4-bit 环号)
//        即 pair_table[round][pair][0] = ring_A_index (4 bit)
//            pair_table[round][pair][1] = ring_B_index (4 bit)

// 算法:
// 1. 初始化 ring_order = {0,1,2,...,15}  (16 个环的排列)
// 2. Fisher-Yates 洗牌:
//    for i = 15 downto 1:
//      j = LFSR_next() % (i+1)    // LFSR 产生伪随机数
//      swap(ring_order[i], ring_order[j])
// 3. 切分: ring_order[0]↔ring_order[1] = 第 1 对, ...
//          ring_order[14]↔ring_order[15] = 第 8 对 → 第 1 轮
// 4. 重复步骤 2-3 共 8 次（每次 LFSR 状态不同 → 不同排列）→ 8 轮
//
// LFSR 规格: 64-bit, 多项式 x^64+x^63+x^61+x^60+1 (最大长度)
// 初始值 = seed, 每次调用输出 8 bit
// 同一 seed → 确定性输出同一配对表（黄金模型对拍基础）
```

**黄金模型任务**（P2-1 减负）：先写 Python 版本（~50 行），生成期望配对表 → 与 RTL 仿真输出对拍。

#### 测量域适配（P1-3 补丁）

W1 用固定不对称分频防混叠，W2 动态配对后不能预分配。**推荐方案：W2 用"UART 发频率值"而非"PL 内比较胜者"**——PL 只做每环独立计数器（复用 W1 架构），频率值经 UART 发 PC，比较逻辑在 Python 端完成。混叠问题完全消失，PL 逻辑量减半，板到手前可纯仿真验证。W3 才把比较器移入 PL（届时用参考环法防混叠）。

#### W2 验收判据（P1-4 修复：拆分为两条）

| 判据 | 定义 | 测量方法 |
|---|---|---|
| **解码确定性** | 同 seed → 同配对表 100% | 仿真：固定 seed 循环 100 次 |
| **单路 reliability** | 8 轮 × 8 bit = 64 bit 响应，同挑战重复 20 次，逐 bit 翻转率 ≤10% | 板上：同 seed 测 20 次 |
| 资源 | ≤3000 LUT（不含 VIO） | Vivado report |

#### W2 时钟方案（P1-3 修复）

W2 需要外部时钟驱动 UART 和轮控 FSM：
- **时钟源**：ZC702 板载 200MHz 差分时钟（引脚见 UG850）→ IBUFDS → BUFG → 100MHz（MMCM 二分频）
- **测量窗**：每环对比较用 1ms 窗（同 W1 的 ro_div 架构），8 对并行 → 单轮 1ms
- **8 轮总时长**：8 × 1ms = 8ms + 轮间切换开销 ≈ 10ms
- **认证延迟**：10ms（PUF 测量）+ 20ms（MAVLink 帧传输）≪ 1s 目标 ✓

---

### W3 · 完整协议 + MAVLink + 多实例

#### 新增文件

| 文件 | 路径 | 说明 |
|---|---|---|
| **w3_top.v** | src/rtl/w3_protocol/ | 完整协议顶层 |
| **terminal_fsm.v** | src/rtl/w3_protocol/ | 终端状态机（见下） |
| **mavlink_frame.v** | src/rtl/common/ | MAVLink v2 帧构造器 |
| **crc16_mcrf4xx.v** | src/rtl/common/ | CRC 核（统一命名，P3-1 修复） |
| uart_rx.v | src/rtl/common/ | PUF-lab 复用 |
| **dialect/hfida.xml** | src/ | MAVLink 自定义消息定义（P1-7） |

#### MAVLink 帧修正（P1-7 修复）

| 参数 | 正确值 | 方案旧值 | 状态 |
|---|---|---|---|
| SEQ 位宽 | **8-bit** (1 字节, 0~255 循环) | ~~4-bit~~ | ✅ 已修正 |
| CRC 初值 | 0xFFFF **⊕ CRC_EXTRA** | ~~0xFFFF~~ | ✅ 已修正 |
| CRC_EXTRA | 每消息类型固定 1 字节（从 XML 生成） | 未提及 | ✅ 已补 |
| dialect XML | 必须先生成，再编译两端 | 未排任务 | ✅ 已排入 W3 B 线 |

#### terminal_fsm.v 状态机（P3-3 修复：统一为 6 态）

```
S_IDLE ──收到挑战──► S_CHALLENGED
S_CHALLENGED ──PUF 计算完成──► S_RESPONDED (发 R1 + 反挑战 C2)
S_RESPONDED ──收到基站 R2──► S_VERIFY
S_VERIFY ──R2 匹配──► S_SESSION
S_VERIFY ──R2 不匹配──► S_BLOCKED
S_SESSION ──超时/再挑战──► S_IDLE (或 S_CHALLENGED)
S_BLOCKED ──冷却 5min──► S_IDLE
任何状态 ──致命错误──► S_BLOCKED
```

---

### W4 · 实验周（P2-3 修复：温度实验方法）

**温度实验方案**：
- 加热：暖手宝贴 PL 侧散热区，目标 ΔT = +20~30°C
- 监测：XADC 实时读结温，70°C 硬停（安全窗口）
- 采样：每 5°C 记录一组完整认证（20 次同挑战）
- 指标：单路 reliability 随温度变化曲线
- 判定：全温区 reliability ≥85%（允许比常温降 5%）
- 责任人：C 线执行，A 线提供比特流支持

---

### W5 · 冻结周（P0-1 修复：新增完整定义）

#### 保底四件套（最终定义）

| # | 交付物 | 验收标准 | 缺失后果 |
|---|---|---|---|
| ① | 互斥演示 | 真板/假板（或软仿冒者）双向拒绝 | 无核心演示 |
| ② | CRP 全流程 | 注册→认证→灰区加测→阻断 完整走通 | 无协议证据 |
| ③ | ROC/EER 数据 | 合法/非法/边界样本集 → 曲线+数值 | 无量化指标 |
| ④ | 报告+视频 | 报告终稿 + ≤3 分钟视频 | 无提交物 |

#### W5 任务分解

| 天 | A 线 | B 线 | C 线 |
|---|---|---|---|
| 周一 | 功能冻结令发布 | 冻结代码版本 | 报告骨架定稿 |
| 周二 | 全量指标实测（板上） | ROC/EER 曲线生成 | 录制视频 v1 |
| 周三 | 资源/时序报告导出 | NIST 子集测试 | Skill 脚本打包 |
| 周四 | 与纯 PC 软件基线对比 | 性能面板截图 | 复现文档初稿 |
| 周五 | G5 门禁评审 | G5 门禁评审 | G5 门禁评审 |

**G5 门禁判据**：
- 指标表全满（无空格）：uniqueness / reliability / ROC-EER / 时延分解 / 资源 / NIST
- 报告初稿完整（含失败分析章节）
- 视频 v1 存在
- Skill 包含 ≥2 个可运行脚本

### W6 · 交付周（P0-1 修复）

| 天 | 任务 | 交付物 |
|---|---|---|
| 周一 | 报告终稿（含大模型协作记录） | report/report.md |
| 周二 | 复现包（从零跑通文档） | README.md 更新 |
| 周三 | 视频终版（≤3 分钟） | video.mp4 |
| 周四 | 开源仓库整理 + **11-03 晚提交** | GitHub/Gitee push |
| 周五 | 缓冲日（11-04） | — |

---

## 二、B 线 · PC 软件设计（P1-6 修复）

### protocol.py 修正版

```python
class HFIDAProtocol:
    # 消息类型定义（msgid 从 0x0090 起）
    MSG_ACCESS_REQUEST  = 0x0090  # 终端→基站
    MSG_CHALLENGE       = 0x0091  # 基站→终端
    MSG_RESPONSE_R1     = 0x0092  # 终端→基站 (含反挑战 C2)
    MSG_RESULT          = 0x0093  # 基站→终端 (含 R2)
    MSG_CONFIRM         = 0x0094  # 终端→基站
    MSG_EXTRA_CHALLENGE = 0x0095  # 基站→终端 (灰区加测)

    # 双阈值（简化为两个，非四个）
    TAU_PASS   = 6    # HD ≤ 6 → 通过 (64-bit 响应, ~9.4%)
    TAU_REJECT = 16   # HD ≥ 16 → 拒绝 (~25%)

    # 挑战数量：4 个（非 5 个）——P1-R5 修复
    # 原因：5×8B=40B 超过 MAVLink 自限 32B 载荷（帧 52B>44B 上限）
    # 4×8B=32B 恰好合规，帧 = 10+32+2 = 44B（自洽）
    N_CHALLENGES = 4

    def __init__(self):
        self.pools: dict[int, CRPPool] = {}   # P1-R6: 每设备一个池
        self.lock = threading.Lock()          # P1-R7: 线程安全

    def on_response(self, terminal_id: int, r1: bytes, c2: bytes):
        hd = self.templates.hamming_distance(terminal_id, r1)
        if hd <= self.TAU_PASS:
            r2 = self.hsm.respond(c2)  # hsm.py 已定义
            return self.pack(self.MSG_RESULT, result=PASS, r2=r2)
        elif hd >= self.TAU_REJECT:
            return self.pack(self.MSG_RESULT, result=REJECT)
        else:
            # 灰区: 加测 3 个挑战,合并评分
            extra = self.pools[terminal_id].draw(count=3)  # P1-R6: 签名统一
            return self.pack(self.MSG_EXTRA_CHALLENGE,
                           payload=extra)

    def on_extra_response(self, terminal_id: int,
                          r1_extra: bytes, c2: bytes):
        """灰区加测后的合并评分（P1-6 修复）"""
        hd_extra = self.templates.hamming_distance(terminal_id, r1_extra)
        total_hd = self.pending_hd[terminal_id] + hd_extra
        # 用更宽的阈值（更多比特 → 更好的统计分辨力）
        if total_hd <= self.TAU_PASS * 2:  # 8 挑战 × 8 bit = 128 bit
            r2 = self.hsm.respond(c2)
            return self.pack(self.MSG_RESULT, result=PASS, r2=r2)
        else:
            return self.pack(self.MSG_RESULT, result=REJECT)
```

### 注册流程（P1-6 修复：补齐）

```python
# src/python/server/enroll.py（新增文件）
def enroll_device(terminal_id: int, serial_port: str, n_challenges: int = 100):
    """注册新设备：采集 N 个 CRP，建立模板"""
    templates = {}
    for i in range(n_challenges):
        seed = secrets.token_bytes(8)   # CSPRNG 生成挑战
        r1 = send_and_receive(serial_port, seed)  # 通过 UART/电台
        templates[seed] = r1             # 存储 CRP 对
    # 计算每个 bit 的稳定性掩码（复用 esp32-puf 的 find_stable_bits 概念）
    stable_mask = compute_stability(templates)
    save_template(terminal_id, templates, stable_mask)
```

### hamming_analysis 适配层（P1-9 修复）

原工具吃逐行 hex 比特流，我们的 VIO 输出是 32-bit 比值计数器。需要新增适配层：

```python
# src/python/evaluation/quantizer.py
def ratio_to_bits(readings: list[int], n_bits: int = 64) -> list[str]:
    """将 VIO 比值读数量化为 bit 流"""
    # W1: 每个读数 → 1 bit（阈值判决：读数 > 理论中心值 → 1, 否则 → 0）
    # W2+: 直接使用 64-bit 响应，无需量化
    ...
```

### W4 ML 攻击实验设计（P1-R8 修复：叙事与设计结构对齐）

**关键认知**：我们的设计是 **RO 配对比较 PUF**（非 arbiter PUF），设备秘密本质是 16 个环频的总排序（有效熵 ≈ log2(16!) ≈ 44 bit）。有效 CRP 空间 = C(16,2)=120 种配对比较，而非 2^64。

**两组实验**：

**实验 A：合成 Arbiter PUF 基线（文献复现，证明方法论）**
- 生成合成 arbiter PUF 数据（加性延迟模型，64 级）
- LR 攻击：64-bit 挑战 → 1-bit 响应（线性模型）
- 预期：>95% 准确率（Rührmair et al. 2010 共识）
- 结论表述："文献基线在我们的评估框架中复现成功"

**实验 B：自家 RO 结构的排序重构攻击（诚实评估）**
- 攻击者积累 CRP（每条 = 挑战种子 + 64-bit 响应）
- 目标：恢复 16 个环的频率排序（≈44 bit 秘密）
- 方法：从响应反推每对比胜关系 → 拓扑排序
- 预期：~120 条带噪 CRP 即可高概率重构
- 结论表述："CRP 空间坍缩至 ~2×10^6 种配对构型，排序重构攻击在 ~120 次观测内可恢复完整排序——这是我们设计的已知边界，在报告中如实讨论"

**安全声明口径**：
- ✅ 可声明："抗逻辑回归建模攻击"（对 XOR 合并后的响应）
- ❌ 不可声明："抗机器学习攻击"（排序重构对 RO 结构有效）
- ✅ 可声明："已量化安全边界：有效熵 ≈44 bit，排序重构需 ~120 CRP"
- ✅ 可声明（未来工作）："增加环数至 64+ 可将有效熵提升至 ~296 bit"

---

## 三、修订后的风险表（P2-4 修复）

| 触发 | 动作 | 影响 |
|---|---|---|
| W2 解码器做不出来 | 退回固定配对（无挑战），纯频率认证 | 演示降级但可交付 |
| W2 整体失败 | W1 双环比值 + 软件仿真挑战集 | 叙事改为"原理验证" |
| 板 2 始终未到位 | 单板 + 多实例 + 软仿冒者 | 跨芯片互斥改预录视频 |
| CRP 池耗尽 | 池余量 <20% 触发重注册流程 | 分钟级，对应维护窗口 |
| dialect 生成失败 | 用 RAW bytes + 自研 CRC | 与 pymavlink 不互通，需双端适配 |
| 板卡到货延迟 | 全部仿真先行，板到后只做验证 | W2/W3 仿真版本先交付 |
| Vivado 许可到期 11-23 | 提前生成全部比特流存档 | 决赛前不再需要综合 |
| 温度实验超安全窗 | XADC 70°C 硬停 → 降温后继续 | 实验中断，数据仍可用 |

---

## 四、依赖图（P2-2 修复：补边）

```
A线 W1 ✅ ──► A线 W2 RTL ──► [接口冻结评审] ──► A线 W3 协议
                │                                    │
                │  响应格式(64bit) ──────────────────►│
                │                                    │
B线 W1-W2 ──► B线 W3 服务器 ◄── 接口冻结 ──► B线 W4 ML攻击
  (pymavlink     │    ↑                                  ↑
   + 统计工具)    │    └── A线 W2/W3 响应格式 ────────────┘
                │
C线 (持续) ──────────────────────────────────► W5 冻结 ──► W6 交付
```

**接口冻结评审节点**（W2 周五）：A 线提交最终 R1 格式 + MAVLink 消息定义 → B 线按此实现，之后不允许单方面变更。

---

*本方案 v3.0 修复了 auto-review Round 1 的全部 3 P0 + 9 P1 + 6 P2。*


---

## W3 Implementation Status (2026-10-05)

Differences between v3.0 design and actual implementation (code is source of truth):

| Item | v3.0 Design | Actual | Reason |
|---|---|---|---|
| C2 generation | Fixed value | Incrementing counter | Anti-replay (blindspot #2); counter resets deterministically at power-on, so freshness holds within one power session only (cross-power-cycle replay = W4, HANDOFF P1-5) |
| R2 expected | Fixed C0..C7 | Speck64/96(K,C2) recompute (A1) | Unify with PC SpeckHSM (golden 7b45b0545e59aa94); anti-replay within a power session (cross-cycle = W4, HANDOFF P1-5) |
| CONFIRM status | 0x01 | 0x00 | protocol.py CONFIRM_OK=0 |
| frame_parser | No payload protection | rx_inhibit input | Concurrent buffer overwrite prevention (#1) |
| ro_array ring_en | Always-on 1b1 | ring_en input port | Power management (#6) |
| fp_pay_len | Not checked | Strict validation | Anti-truncation fake PASS |
| PUF response | Real computation | Seed passthrough stub | W3 protocol closure first |

### New test levels
- Level 2: tb_tx_chain.v (real mavlink_frame + byte_fifo + uart_tx)
- Level 3: tb_level3_protocol.v (real terminal_fsm + mavlink_frame + frame_parser)
- Total: 8 TB suites, 45 test cases, 100% pass

### Synthesis data
- terminal_fsm OOC: 253 LUT / 592 FF (0.48% of Z7020)
- Full stack estimate: ~780 LUT

