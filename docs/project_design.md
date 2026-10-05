# PUF 无人机认证系统 · 完整可执行设计方案

> 基于开源分析报告（docs/opensource_analysis.md）产出，覆盖 A/B/C 三线 W2~W6 全部工作。
> 每个模块标注：来源（复用/参考/自研）、文件路径、接口定义、验收判据。

---

## 〇、系统总体架构（v2.2 定稿）

```
┌──────────────────────────────┐         ┌──────────────────────────────┐
│     ZC702 (无人机终端)         │  433MHz │       PC (地面基站)           │
│                              │  无线    │                              │
│  PL:                         │         │  Python:                     │
│  ├─ PUF 环振阵列 ×N          │ ◄─────► │  ├─ pymavlink 收发           │
│  ├─ 挑战解码器               │ 电台×2  │  ├─ HF-IDA 状态机            │
│  ├─ XOR-CRO 响应生成         │         │  ├─ 模板库 (CRP pool)        │
│  ├─ 终端 FSM (5态)           │         │  ├─ 双阈值判决               │
│  ├─ MAVLink 帧构造器         │         │  ├─ 性能面板 (web)           │
│  └─ UART ↔ 电台             │         │  └─ ROC/EER/NIST 评估        │
│                              │         │                              │
│  实例0 = 基站 HSM            │ USB     │  (板到手前: 仿真/回环)        │
└──────────────────────────────┘         └──────────────────────────────┘
```

---

## 一、A 线 · RTL 设计（按周交付）

### W2 · 16 环阵列 + XOR 合并 + 挑战解码 [核心创新]

#### 1.1 文件清单

| 文件 | 路径 | 来源 | 说明 |
|---|---|---|---|
| ro_ring.v | src/rtl/w1_ratio/ | ✅ 已有 | 单环（不动） |
| ro_div.v | src/rtl/w1_ratio/ | ✅ 已有 | 分频（不动） |
| **ro_array.v** | src/rtl/w2_array/ | **自研** | 16 环阵列 + 配对选择 |
| **xor_merge.v** | src/rtl/w2_array/ | **自研** | k=4 XOR 合并逻辑 |
| **challenge_decode.v** | src/rtl/w2_array/ | **参考 arbel.v** | 8B 种子→64 对配对表 |
| **w2_top.v** | src/rtl/w2_array/ | **自研** | W2 顶层（16 环版） |
| **uart_tx.v** | src/rtl/common/ | **PUF-lab 复用** | UART 发送 |
| w2_waiver.xdc | src/rtl/w2_array/ | 改自 W1 | 16 环豁免 |
| build_w2.tcl | build/tcl/ | 改自 W1 | W2 构建脚本 |

#### 1.2 ro_array.v 接口设计

```verilog
module ro_array #(
    parameter N_RINGS = 16,        // 环数
    parameter PAIRS   = 8          // 同时比较的对数
  ) (
    input                   clk       ,  // 系统时钟（测量窗用）
    input                   rst       ,  // 同步复位
    input                   en        ,  // 阵列使能
    input  [N_RINGS*4-1:0]  pair_sel  ,  // 配对选择（来自挑战解码器）
    output [PAIRS-1:0]      pair_win  ,  // 每对的胜者（0=A快, 1=B快）
    output                  busy      ,
    output                  done
  );
```

内部：16 个 ro_ring 实例 + 每对一个比较器（计数窗口 → 大小判）。

#### 1.3 xor_merge.v 接口设计

```verilog
module xor_merge #(
    parameter K = 4,               // XOR 路数
    parameter WIDTH = 8            // 每路输出位宽
  ) (
    input  [K*WIDTH-1:0]   responses ,  // K 路原始响应
    output [WIDTH-1:0]     merged      // XOR 合并后
  );
```

assign merged = responses[K*WIDTH-1] ^ responses[(K-1)*WIDTH-1] ^ ... ;
（纯组合逻辑，零时钟需求）

#### 1.4 challenge_decode.v 接口设计

```verilog
module challenge_decode #(
    parameter SEED_W = 64,         // 8 字节种子
    parameter N_RINGS = 16,
    parameter PAIRS   = 8
  ) (
    input                   clk       ,
    input                   rst       ,
    input                   start     ,  // 开始解码
    input  [SEED_W-1:0]    seed      ,  // CSPRNG 产生的挑战种子
    output [N_RINGS*4-1:0] pair_sel  ,  // 输出给 ro_array
    output                  done
  );
```

内部：LFSR 展开种子 → 确定性索引 → 洗牌算法选配对。
参考 PUF-lab arbel.v 的 mux 树结构，但逻辑改为索引寻址。

#### 1.5 验收判据（W2 门禁 G2）

| 指标 | 目标 | 测量方法 |
|---|---|---|
| 常温 reliability | ≥90% | 同板重复 20 次，每 bit 翻转率 |
| 挑战可重复 | 同种子→同响应 100% | 固定种子循环测试 |
| 资源 | ≤5000 LUT（16 环+逻辑） | Vivado report_utilization |

---

### W3 · 完整协议 + 多实例 + UART 输出 [系统整合]

#### 3.1 新增文件

| 文件 | 路径 | 来源 |
|---|---|---|
| **w3_top.v** | src/rtl/w3_protocol/ | 自研 |
| **terminal_fsm.v** | src/rtl/w3_protocol/ | 参考 controller.v |
| **mavlink_frame.v** | src/rtl/common/ | 参考 c_library_v2 |
| **crc16_lfsr.v** | src/rtl/common/ | 翻译自 c_library_v2 |
| uart_rx.v | src/rtl/common/ | PUF-lab 复用 |

#### 3.2 terminal_fsm.v 状态机

```
空闲 ──收到挑战──► 待响应 ──PUF计算完成──► 已响应(发R1+反挑战C2)
  ▲                    │                        │
  │                    │                        ▼
  └──超时/失败── 失败 ◄──验基站R2──► 验基站通过 ──► 会话态
```

#### 3.3 mavlink_frame.v 设计

固定模板帧：STX(0xFD) + LEN + IF + CF + SEQ + SYSID + COMPID + MSGID[3] + PAYLOAD + CRC[2]
- 帧头 10 字节 + 载荷 ≤32 字节 + CRC 2 字节 = 最大 44 字节
- CRC 核：16 级 LFSR，多项式 0x1021，初值 0xFFFF，反射输入/输出
- 序号：4-bit 计数器自动递增

---

### W4 · ML 攻击实验 + 温度实验 [特色演示]

A 线无新 RTL——W4 是 B/C 线的实验周。A 线只做：
- 板级调试支持
- 多实例布局微调（RELATIVE 约束）
- 无线链路联调

---

## 二、B 线 · PC 软件设计（与 A 线并行）

### W1~W2 · 基础设施

#### 2.1 环境搭建（已完成 ✅）
- Python 3.13 + pymavlink 2.4.50 + sklearn + numpy + scipy + matplotlib

#### 2.2 MAVLink 回环测试（W1~W2）

```python
# src/python/tools/loopback_test.py
# 双端回环：自己发 MAVLink v2 帧 → 自己收 → 校验 CRC
# 验证：帧结构正确、CRC 算法正确、sysid/compid 正确
```

#### 2.3 统计分析工具（W2，从 esp32-puf 复用）

| 文件 | 来源 | 修改 |
|---|---|---|
| src/python/evaluation/hamming_analysis.py | esp32-puf 复制 | 改输入位数参数（65536→64） |
| src/python/evaluation/compare_devices.py | esp32-puf 复制 | 零修改 |
| src/python/evaluation/roc_eer.py | 自研 | ~100 行（sklearn ROC 曲线） |

### W3 · 认证服务器

#### 3.1 文件结构

```
src/python/server/
├── main.py            # 入口：启动服务器 + CLI
├── protocol.py        # HF-IDA 五帧状态机
├── crp_pool.py        # 挑战池管理（不重复抽取+余量监控）
├── template_db.py     # 模板存储（JSON 文件）
├── threshold.py       # 双阈值判决（灰区加测）
└── panel.py           # 实时性能面板（终端 UI，W5 升级 web）
```

#### 3.2 protocol.py 核心流程

```python
class HFIDAProtocol:
    """HF-IDA 双向认证协议状态机"""

    def on_connect(self, terminal_id: int):
        """终端发起接入 → 生成挑战 → 下发"""
        challenges = self.pool.draw(terminal_id, count=5)
        return self.pack(MSG_CHALLENGE, payload=challenges)

    def on_response(self, terminal_id: int, r1: bytes, c2: bytes):
        """收到终端响应 R1 + 反挑战 C2"""
        score = self.templates.match(terminal_id, r1)
        if score < TAU_PASS:
            return self.pack(MSG_REJECT, reason="HD too high")
        elif score > TAU_REJECT:
            return self.pack(MSG_REJECT, reason="HD too low (suspicious)")

        # 灰区：加测
        if score > TAU_GRAY_LO and score < TAU_GRAY_HI:
            extra = self.pool.draw(terminal_id, count=3)
            return self.pack(MSG_EXTRA_CHALLENGE, payload=extra)

        # 通过：调 HSM 答反挑战 C2 → 生成 R2
        r2 = self.hsm.respond(c2)
        return self.pack(MSG_RESULT + MSG_R2, result=PASS, r2=r2)
```

#### 3.3 crp_pool.py 设计

```python
class CRPPool:
    """每设备的挑战池管理"""

    def __init__(self, device_id: int, size: int = 500):
        self.used: Set[int] = set()      # 已用挑战索引
        self.pool: List[bytes] = self._generate(size)

    def draw(self, count: int = 5) -> List[bytes]:
        """不重复抽取 count 个挑战"""
        available = set(range(len(self.pool))) - self.used
        if len(available) < count:
            raise PoolExhausted(f"剩余 {len(available)}，需要 {count}")
        chosen = random.sample(list(available), count)
        self.used.update(chosen)
        return [self.pool[i] for i in chosen]

    @property
    def remaining_pct(self) -> float:
        return 1 - len(self.used) / len(self.pool)
```

### W4 · ML 攻击实验

#### 4.1 文件

```
src/python/evaluation/
├── attack_ml.py       # LR/SVM 攻击 notebook
├── gen_dataset.py     # 合成 CRP 数据生成（板到手前用）
└── attack_report.py   # 攻击结果可视化
```

#### 4.2 实验设计

```python
# 攻击模型：逻辑回归
from sklearn.linear_model import LogisticRegression

# 数据：CRP 对 (challenge_bits, response_bit)
# 基础结构：直接用 challenge → response 的线性映射训练
# XOR 结构：4 路异或后的响应 → 线性模型无法拟合

# 预期结果：
#   基础结构 → 攻击准确率 >95%（被攻破）
#   XOR(k=4) → 攻击准确率 ≈50%（等于随机猜）
```

---

## 三、C 线 · 文档与证据（贯穿全程）

### 每周交付

| 周 | 交付物 | 路径 |
|---|---|---|
| W1 | ✅ AI 协作日志开档 | report/llm_log/w1_session.md |
| W2 | W2 实验数据 + 教程更新 | data/w1_readings/, docs/tutorials/ |
| W3 | 系统架构图 (SVG) | docs/architecture/ |
| W4 | 攻击实验报告 + 温度实验数据 | report/figures/ |
| W5 | 性能面板截图 + Skill 脚本 + 报告初稿 | skill/, report/ |
| W6 | 终稿报告 + 复现包 + 视频 | report/report.md |

---

## 四、依赖关系图

```
W1 ✅ ──► W2 RTL (ro_array + xor_merge)
  │              │
  │              ▼
  │         W3 RTL (terminal_fsm + mavlink_frame)
  │              │
  └──► B线 W1-W2 (pymavlink 回环 + 统计工具)
  │              │
  │              ▼
  │         B线 W3 (认证服务器)
  │              │
  │              ▼
  │         B线 W4 (ML 攻击) ◄── A线 W4 (联调)
  │              │
  └──► C线 (持续) ──► W5 冻结 ──► W6 交付
```

关键路径：**A 线 W2 → W3**（RTL 是硬件基础，B/C 依赖它的接口定义）

---

## 五、板到手后的最小验证流程

```powershell
# 前提：ZC702 + 12V + USB JTAG 线
# 1. 构建 W1 比特流
D:\puf-drone-auth\build\ps1\run_build.ps1

# 2. 烧板 + 自动采集 VIO 读数 (10 次)
D:\puf-drone-auth\build\ps1\run_build.ps1 -Measure

# 3. 分析读数（B 线工具）
python src/python/evaluation/hamming_analysis.py -i data/w1_readings/w1_readings.csv

# 4. 判定
#    同板极差 < 100 → 链路稳定 ✓
#    （板2到手后：跨板中心差 > 数千 → 指纹差异确认 ✓✓）
```

---

## 六、风险与降级决策表

| 触发 | 动作 | 影响范围 |
|---|---|---|
| W2 G2 不达标（reliability <90%） | 调布局→加环数→放宽阈值 | A 线延迟 1 周 |
| W3 无线联调失败 | 切有线 USB-UART | 演示叙事不变 |
| W4 ML 攻击异常耗时 | 只保留"基础被攻破"结论 | 报告仍可写 |
| W5 冻结日仍有 bug | 保底四件套优先 | 砍 AI 扩展/多实例 |
| 电台供货延迟 | 有线兜底→ESP32 WiFi | 无线演示改叙事 |

---

## 七、Skill 打包计划（W5，15 分项）

| 工具 | 功能 | 复用来源 |
|---|---|---|
| puf_eval.py | 一键测 uniqueness + reliability + NIST | hamming_analysis.py 改造 |
| mavlink_loopback.py | 电台回环测试（延迟/丢包/吞吐） | 自研 ~50 行 |
| build_automation | 参数化 Vivado Tcl 构建脚本 | build_w1.tcl 泛化 |

---

*本方案基于 2026-10-05 开源代码分析 + 已验证的 W1 工程产出。*
