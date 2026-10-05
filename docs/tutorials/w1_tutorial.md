# 保姆教程 W1（ZC702 版·界面精确对照版）：从零到"一号验证点"

> **板卡**：ZC702（XC7Z020-1CLG484）· **软件**：Vivado 2026.1（D:\vivado）
> **本文每个步骤都注明了按钮/对话框的英文原文，确保你能在软件里找到完全一样的那个按钮。**

---

## 第 0 步 · 补装 Zynq-7000 器件族（已装好则跳过）

- 路径：`D:\vivado\.xinstall\2026.1\xsetup.exe`
- 双击 → 选 Modify → 勾选 **Zynq-7000** → Next 到底
- 验证：新建工程 → 搜 `xc7z020clg484` 能找到

---

## 一、认识 ZC702 板卡

| 位置 | 作用 | 怎么做 |
|---|---|---|
| **12V 电源口**（圆形 DC 插座） | 供电 | 插 12V 适配器（套件附带） |
| **电源开关**（丝印 ON/OFF） | 通断电 | 拨到 ON |
| **USB JTAG/UART**（micro-USB，丝印 PROG） | 烧录 + VIO 读数 | 用**数据线**（非充电线）连电脑 |
| **SW16 拨码** | 启动模式 | **本课不改** |
| **FMC 连接器** | 扩展接口 | **全程不碰** |

---

## 二、新建工程（每一下点击）

### 暂存源文件（一次性，跳过中文路径坑）

先在 PowerShell 里跑：
```powershell
$stage = "D:\fpga_work\w1_stage"
New-Item -ItemType Directory -Force $stage | Out-Null
Copy-Item "D:\文件\ssssssss\FPGA\w1_project\src\*" $stage -Force
```

### 开始建工程

1. 双击 **Vivado 2026.1** 图标 → 等启动完成

2. Vivado 2026.1 启动后直接看到欢迎页：
   - 欢迎页左侧 **Quick Start** → 点 **New Project**
   -（或菜单栏 **File** → **Project** → **New...**，效果一样）

3. 弹出向导对话框——**2026.1 没有单独的"Next"首页**，直接落在：

4. **"Project Name"** 页（标题栏标有 "Project Name"，底部按钮 Cancel / Back / Next）：
   - *Project name*：改为 `w1_ratio`（默认是 project_1，**必须改**）
   - *Project location*：改为 `D:\fpga_work`（默认是 C:/Users/你的用户名/，**必须改**——含中文用户名的路径会导致综合失败！）
   - ✅ Create project subdirectory（默认已勾选，不动）
   - 点 **Next**

5. **"Project Type"** 页：
   - 选 **RTL Project**（第一项，左侧菱形图标）
   - **不勾** ❌ Do not specify sources at this time（我们要加文件）
   - 点 **Next**

6. **"Add Sources"** 页：
   - 点右上 **Add Files** → 浏览 `D:\fpga_work\w1_stage\`
   - **Ctrl 多选** 3 个：`ro_ring.v`、`ro_div.v`、`ro_ratio_top.v` → OK
   - **不要选** `ro_probe_top.v`（废弃文件）
   - 点 **Next**

7. **"Add Constraints (optional)"** 页：
   - 点 **Add Files** → **只选** `w1_ro_waiver.xdc` → OK
   - **不要选** `w1_probe.xdc`（也是废弃文件！与 w1_ro_waiver.xdc 同目录并排，看清楚后缀）
   - 点 **Next**

8. **"Default Part"** 页：
   - 搜索框输入 `xc7z020clg484`（下方自动筛出 3 个匹配：-1/-2/-3）
   - 选 **xc7z020clg484-1** → 点 **Next**

9. **"New Project Summary"** 页 → 核对信息 → 点 **Finish**

---

## 三、确认顶层

看左栏 **Sources 窗口** → 展开 **Design Sources (3)**：
- `ro_ratio_top` 应显示为粗体并带 **(top)** 标记
- 如果没有：**右键** `ro_ratio_top` → **Set as Top**

---

## 四、添加 VIO IP

1. 左栏 **Flow Navigator** → **PROJECT MANAGER** → 点 **IP Catalog**

2. 顶部标签栏切到 **IP Catalog** 标签

3. 搜索框输入 `vio` → 左侧树展开 **Foundational Elements** → **Debug and Verification**
   → 找到 **VIO (Virtual Input/Output)** → **双击**

4. 弹出 IP 配置对话框（标题栏 "Customize IP"）：
   - *Component name*：保持 `vio_0`（默认值，**不要改！**）
   - *Input Probe Count*：确认是 `1`（默认就是 1，不用改）
   - *Output Probe Count*：**改为 `0`**（默认是 1，必须改！）
   - 切到 **"PROBE_IN Ports(0..0)"** 选项卡：
     - 找到 PROBE_IN0 行，*Probe Width [1-256]* 列：改为 `32`
   - 点 **OK**

5. 弹出 **Generate Output Products** → 点 **Generate**
6. 等 1~2 分钟，Sources 窗口出现 `vio_0`

---

## 五、生成比特流

1. 左栏 **Flow Navigator** → **PROGRAM & DEBUG** → 点 **Generate Bitstream**

2. 弹出 **"...out-of-date..."** → 点 **Yes**（自动跑 综合 → 实现 → 比特流）

3. 等 **5~15 分钟**（右下角进度指示器显示当前步骤名）

4. 弹出 **"Bitstream Generation Completed"** → 点 **Cancel**

### 正常 vs 异常

| 消息 | 含义 | 担心？ |
|---|---|---|
| CRITICAL WARNING: combinational/LUT loop | 环振本体 | ✅ 正常 |
| ~8 条 CRITICAL WARNING: can't read "wr_clk_period" | dbg_hub 噪音 | ✅ 正常 |
| no clocks / unconstrained | 无外部时钟 | ✅ 正常 |
| **ERROR [DRC LUTLP-1] Bitgen not run** | XDC 豁免没加 | ❌ 回第 7 步补 w1_ro_waiver.xdc |

---

## 六、上板（连板 + 烧录）

### 连板

1. 12V 电源 → 开关 ON（板上 LED 亮）
2. micro-USB **数据线** → 板子上的 **USB JTAG** 口 ↔ 电脑
   **注意**：ZC702 板上有**两个** micro-USB 口——一个标 UART（串口），一个标 JTAG。
   **只插 JTAG 那个**（通常旁边有 Digilent/JTAG 丝印）。插错了 Auto Connect 找不到芯片。
   如果不确定是哪个：两个都试一下，能 Auto Connect 到的就是对的（插错不会损坏）。

### 烧录

1. **Flow Navigator** → **PROGRAM & DEBUG** → **Open Hardware Manager**

2. 主窗口切到 **Hardware Manager** 标签
   上方绿色区域 → 点 **Open target** → **Auto Connect**

3. 左侧 Hardware 窗口出现 `localhost` → `xc7z020` 芯片图标
   （看不到？→ 排障表第 1 条）

4. **右键** `xc7z020` → **Program Device...**
   Bitstream 路径已自动填好 → 点 **Program**

5. 等 5~10 秒——板子不会有明显灯变（心跳在 VIO 里看）

---

## 七、读数

### 打开 VIO 读数面板

1. 在左侧 Hardware 窗口（原来显示 Sources 的位置），**展开** `xc7z020`（点旁边的三角形箭头）
   → 下方出现 **hw_vio_1**（或 vio_0——取决于 Vivado 版本）

2. **单击它** → 主窗口出现 VIO 核心读数视图（VIO Cores View）
   → 应能看到 `probe_in0` 及其 32 位值

### 设置自动刷新

按 AMD 官方 UG908（2026.1 版），VIO 输入探针的刷新率设置方法：
1. 在 VIO 读数面板中找到 **Refresh Rate (ms)** 属性/字段
   （可能在属性面板、设置列、或右键菜单中——具体位置因版本而异）
2. 将其从默认值（可能为 0 = 手动）改为 `500`（毫秒）或更大
3. 如果找不到该设置：也可以每次想看时手动**点刷新按钮**——本课读数 14~43 秒才变一次，手动刷完全够用

**如果你在软件中找不到上述控件**：直接截图发给我，我帮你定位。VIO 读数面板的具体布局在不同 Vivado 版本间有差异，实际界面以你看到的为准。

### 读数含义

- `probe_in0` = 32 位十六进制数（如 `0x0004_1A3B`）
- 公式：**N ≈ (fB ÷ fA) × 262,144**（两环全同时 N≈262,144=0x0004_0000）
- **更新周期：约 14~43 秒一跳**
- **⚠️ 上电后首窗结束前，读数一直是 0——正常，不是故障！**

### 记录 10 次

| 次 | hex | dec |
|---|---|---|
| 1~10 | ... | ... |

**验收**：10 次极差 < 100 ⇒ 全链路稳定 ✓

---

## 八、换板对比（板 2 到位后）

1. Flow → **Settings** → **General** → 改 Project device 为板 2 型号
2. 重新 **Generate Bitstream**
3. 烧板 2 → 记 10 次
4. 两板中心差 > 数千 ⇒ "同一份代码、两颗芯片、两个身份"实锤

---

## 九、收尾

- 读数表 + VIO 截图存仓库 `docs/w1_evidence/`
- `docs/llm_log_w1.md` 记三行 AI 协作日志

---

## 十、排障速查

| 症状 | 原因 | 解决 |
|---|---|---|
| Auto Connect 无芯片 | 充电线/**插错 USB 口**/驱动/电源 | ①换数据线 ②确认插的是 JTAG 口（不是 UART 口） ③装驱动：`D:\vivado\2026.1\Vivado\data\xicom\cable_drivers` ④看电源灯 ⑤换口 |
| vio_0 not defined | IP 没生成或改名 | 回第四节重做，名必须 `vio_0` |
| LUTLP-1 ERROR | XDC 豁免没加 | 回第二节第 7 步补加 |
| VIO 数字恒 0 | ①首窗未满（14~43s，最常见！） ② KEEP 属性被删 | 耐心等满 43s → 查 ro_ring.v 的 KEEP 行 |
| Part 搜不到 | 器件族未装 | 回第 0 步 |
| part mismatch | part 选错 | 必须 xc7z020clg484-**1** |
| LUT 异常爆 | 误加废弃文件 | 检查未加 ro_probe_top.v（Sources）和 w1_probe.xdc（Constraints） |

---

## 十一、资源

**官方**：UG850（ZC702 手册）；UG898（Vivado 入门）
**GitHub**：InterPUF；SiMRA-PUF；mavlink/c_library_v2；pymavlink
**中文**：清华《Vivado 使用入门》（最接近本课流程）；CSDN ZYNQ 启动方式/点灯系列
**练习**：HDLBits

---

*界面描述基于 Vivado 2026.1；参考清华大学数字逻辑实验课程教程及 AMD 官方文档。如界面不符请截图发我。*
