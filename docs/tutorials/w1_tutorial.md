# 保姆教程 W1+（ZC702 上板阶梯版）：从零到"一号验证点"，再点亮整个 A1

> **板卡**：ZC702（XC7Z020-1CLG484）· **软件**：Vivado 2026.1（D:\vivado）
> **本文每个步骤都注明了按钮/对话框的英文原文，确保你能在软件里找到完全一样的那个按钮。**
>
> **2026-10-08 更新（结合 A1 完成后的最新进度）**：
> - A1（Speck64/96 统一 R2）六阶段已全部完成：15 个 RTL 模块、12/12 TB、44 个 Python 单测、
>   线性金丝雀、契约同步 7 帧，CI-EXIT=0（证据 build/reviews/a1p4~a1full/）
> - 本教程从"W1 单点"扩充为**上板阶梯**：验证点 1（W1 VIO）→ 验证点 2（w3_top 心跳/按键）
>   → 验证点 3（PC 串口环路）→ 验证点 4/5（W4：PUF 真接入 + 完整互认证）
> - 新增：三大板级适配的逐行操作（时钟/复位/引脚）、排障速查板级扩充、W4 安全包对照
> - 并入：套件官方快速入门指南 XTP310（v1.3）开箱流程 → 新增「验证点⓪ 出厂 BIST 自检」——上电第一件事，先证明板子是好的

---

## ⭐ 上板阶梯总览（先读这一节）

| 验证点 | 内容 | 要改什么 | 验收标准 | 预计 |
|---|---|---|---|---|
| **⓪** | **出厂 BIST 自检**（板健康自证，官方 XTP310 流程） | 装 CP210x 驱动 + Tera Term；SW16=00010；连线 J17 | BIST 菜单出现且 LED/DDR3 等项通过 | 半小时 |
| **①** | **W1 环振比值**（本教程主体，零引脚设计） | 不改任何 RTL/XDC | VIO 读数 10 次极差 < 100 | 半天 |
| ② | **w3_top 心跳 + 按键**（时钟/复位/LED 三大板级适配） | 时钟端口 + IBUFDS/MMCM + XDC 引脚 | 心跳 LED 0.75Hz 闪烁；按键→busy 亮 2s | 1 天 |
| ③ | **PC 串口环路**（协议帧互通） | FMC/PMOD USB-UART 桥（ZC702 板载 UART 在 PS 域，PL 够不着） | PC 发 CHALLENGE → 终端回 RESPONSE_R1 → parse 成功 | 1 天 |
| ④ | **PUF 真实测量**（替换种子直通） | terminal_fsm 接 challenge_decode + ro_array | 上板实测 16 环频率，模板注册后认证 PASS | W4 |
| ⑤ | **完整互认证 + W4 安全包** | P1-5 重放修复 / 熵混合 / 真密钥 | 互认证端到端 + 安全声明如实 | W4 |

> **为什么验证点 ① 仍然是第一颗钉子**：W1 设计**零外部引脚、零时钟约束、只读 VIO**——
> 排除所有板级适配变量，纯粹验证"JTAG 链 → 烧录 → 逻辑运行 → VIO 可观测"这条最小通路。
> 通路通了，后面的每一步才是在验证"设计"，而不是在同时跟"工具链"搏斗。

**当前仿真侧基线（板级未知项的对照组）**：12/12 TB 全绿（含 tb_w3_top 顶层回环、
tb_speck 1175 组全量回放、tb_gap 8 用例含码 4 拒绝）+ 44 Python 单测 + 金丝雀 + 契约同步 7 帧。
**上板的本质 = 验证真实硅片行为是否与这份全绿基线一致。**

---

## 第 0 步 · 补装 Zynq-7000 器件族（已装好则跳过）

- 路径：`D:\vivado\.xinstall\2026.1\xsetup.exe`
- 双击 → 选 Modify → 勾选 **Zynq-7000** → Next 到底
- 验证：新建工程 → 搜 `xc7z020clg484` 能找到

---

## 一、认识 ZC702 板卡

| 位置 | 作用 | 怎么做 |
|---|---|---|
| **6 针电源插头 → J60** | 供电 | 插紧——官方套件的电源线就是这种 6 针插头（**不是圆形 DC 插座**） |
| **电源开关 SW11** | 通断电 | 拨到 ON |
| **USB 口 J17**（Mini-B） | **JTAG + USB-UART COM 二合一**：烧录、VIO、BIST 串口全走它 | 用套件附带的 **Type-A 转 Mini-B** 数据线；装 CP210x 驱动后会出现 COM 口 |
| **SW16 拨码 = 00010（出厂）** | 启动模式（SD 卡 BIST 镜像） | 保持出厂；动过开关/跳线 → www.xilinx.com/kits/zc702default 恢复 |
| **SW1 按键（POR_B）** | 上电复位 / 重新初始化配置 | 终端空白或配置异常时按一下 |
| **SW15-1/2 ≈ SW13/SW14** | 并联信号（BIST 的 Switch Test 用） | 任选一种 |
| **FMC 连接器** | 扩展接口 | 验证点①不碰（验证点③的 USB-UART 桥/电台会用到） |
| **GPIO_SW_N 按键**（G19） | PL 域复位（验证点②用） | 先认识位置，本课暂不按 |
| **DS9~DS12 LED**（Y11/T22/W21/U21，待核对） | 状态灯（验证点②用） | 先认识位置 |

> ⚠ **两个 board 认知提前打预防针**（验证点②会展开）：
> ① ZC702 的 PL 时钟是 **200MHz 差分**（D18/C19, LVDS_25），而 w3_top 期待 100MHz 单端；
> ② 板载 **CPU_RESET 按键在 PS 域**，PL 逻辑够不着——复位要用 **GPIO_SW_N（G19, LVCMOS25）**。

---

## 第 0·5 步 · 出厂 BIST 自检（上电第一件事：先证明板子是好的）

> 依据：套件附带官方快速入门指南 **XTP310 (v1.3)** 的 STEP 1~9。
> 在烧我们自己的设计**之前**，先用出厂 SD 卡镜像给板子做一次全面体检——
> 电源/时钟/DDR3/LED/UART 全部健康，之后任何失败都只能是我们设计或约束的问题。

### 0.5.1 准备（一次性，半小时内）

1. 装 **Silicon Labs CP210x USB-UART 驱动**：www.xilinx.com/kits/cp210x
2. 装终端软件 **Tera Term**：www.xilinx.com/kits/teraterm（PuTTY 也可）
3. 盒内物品核对：**SD 卡（出厂 BIST 镜像，插回板上别弄丢）**、USB Hub、HDMI 线、以太网线、两种 USB 线

### 0.5.2 开箱流程（官方 STEP 1~9）

| 步 | 操作 | 关键点 |
|---|---|---|
| 1 | 装驱动 + 终端软件 | CP210x + Tera Term |
| 2 | DIP **SW16 = 00010**（出厂启动模式：SD 卡镜像） | 动过开关/跳线 → www.xilinx.com/kits/zc702default 恢复 |
| 3 | 电脑 ↔ 板上 **J17**（Type-A 转 Mini-B） | 这一个口同时提供 JTAG 和 USB-UART COM |
| 4 | **6 针电源插头 → J60**，**SW11** 开机 | 不是圆形 DC 插座 |
| 5 | Tera Term 选 **Serial** → 选 CP210x 对应 **COM 口** | 记下 COM 号 |
| 6 | Setup → Serial port | 进设置 |
| 7 | **115200 / 8 / none / 1 / none** | 设错 = 乱码 |
| 8 | 按 **SW1（POR_B）** 重新初始化 | 终端空白就按它 |
| 9 | 终端出现 BIST 菜单 → 输入编号跑测试 | 2=LED、7=DDR3 最直观 |
| 10~11 | Vivado 授权兑换/安装 | 2026.1 标准版对 Zynq-7000 免费；套件凭证（一次性/一年内）拍照存档即可 |

### 0.5.3 BIST 菜单速查

输入编号：1=UART / 2=LED / 3=Timer / 4=IIC / 5=SCUGIC / 6=DCFG / **7=DDR3** / 8=Interrupt / 9=Watchdog；e 或 q 退出。
建议至少跑：**2（LED，眼睛能直接对账）** 和 **7（DDR3，最容易翻车的大件）**。

### 0.5.4 验收

- BIST 全绿 ⇒ 板子本体（电源/时钟/DDR3/LED/UART）健康
- ⇒ 之后任何失败都只能指向**我们的设计或约束**——这正是把它列为验证点⓪的意义
- 顺手记录：CP210x 分配的 COM 号（后续 Tera Term 调试习惯从此建立）

> ⓪小排障：COM 口找不到 = 驱动/线没插 J17/没开机；乱码 = 115200-8-N-1 没设对；
> 终端空白 = 按 SW1；某项 FAIL = 先按 zc702default 恢复出厂再重跑。

---

## 二、新建工程（每一下点击）

### 源文件就在仓库里（无需暂存拷贝）

源目录：`D:\puf-drone-auth\src\rtl\w1_ratio\`（纯 ASCII 路径，Vivado **直接添加**，不要拷贝副本——仓库就是唯一真相源）：
- `ro_ring.v` — 环振本体
- `ro_div.v` — 分频/计数
- `ro_ratio_top.v` — 顶层（内含 `vio_0`）
- `w1_ro_waiver.xdc` — 组合环豁免（必须与 .v 一起加入）

### 开始建工程

1. 双击 **Vivado 2026.1** 图标 → 等启动完成

2. Vivado 2026.1 启动后直接看到欢迎页：
   - 欢迎页左侧 **Quick Start** → 点 **New Project**
   -（或菜单栏 **File** → **Project** → **New...**，效果一样）

3. 弹出向导对话框——**2026.1 没有单独的"Next"首页**，直接落在：

4. **"Project Name"** 页（标题栏标有 "Project Name"，底部按钮 Cancel / Back / Next）：
   - *Project name*：改为 `w1_ratio`（默认是 project_1，**必须改**）
   - *Project location*：改为 `D:\puf-drone-auth\build\vivado`（默认在 C:/Users/你的用户名/ 下——**必须改**：Vivado 对非 ASCII 路径敏感，仓库路径是纯 ASCII，安全）
   - ✅ Create project subdirectory（默认已勾选，不动）
   - 点 **Next**

5. **"Project Type"** 页：
   - 选 **RTL Project**（第一项，左侧菱形图标）
   - **不勾** ❌ Do not specify sources at this time（我们要加文件）
   - 点 **Next**

6. **"Add Sources"** 页：
   - 点右上 **Add Files** → 浏览 `D:\puf-drone-auth\src\rtl\w1_ratio\`
   - **Ctrl 多选** 3 个：`ro_ring.v`、`ro_div.v`、`ro_ratio_top.v` → OK
   - 点 **Next**

7. **"Add Constraints (optional)"** 页：
   - 点 **Add Files** → **只选** `w1_ro_waiver.xdc` → OK
   - 点 **Next**

8. **"Default Part"** 页：
   - 搜索框输入 `xc7z020clg484`（下方自动筛出 3 个匹配：-1/-2/-3）
   - 选 **xc7z020clg484-1** → 点 **Next**

9. **"New Project Summary"** 页 → 核对信息 → 点 **Finish**

> ⚡ **快车道（第二次起可跳过 GUI——推荐）**：仓库自带一键脚本，建工程→综合→实现→比特流全自动：
> ```powershell
> cd D:\puf-drone-auth
> .\build\ps1\run_build.ps1            # 一键构建
> .\build\ps1\run_build.ps1 -Measure   # 构建 + 自动烧板 + 自动采 10 次 VIO 读数存 CSV
> ```
> `-Measure` 调用 `build\tcl\measure_w1.tcl`：连 JTAG → 烧录 → 每 15 秒读一次 `probe_in0` → 写 `w1_readings.csv`
> （**验证点①可全自动完成**；第七节的手动读数流程只用于理解界面）。
> 产物：`D:\puf-drone-auth\build\vivado\w1_auto\w1_auto.runs\impl_1\ro_ratio_top.bit`

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

1. 6 针电源插头（J60）→ SW11 拨到 ON（板上电源指示灯亮）
2. 套件的 **Type-A 转 Mini-B** 线 → 板上 **J17** 口 ↔ 电脑
   J17 一个口同时提供 **JTAG**（烧录）和 **CP210x USB-UART COM**（串口）。
   装好 CP210x 驱动后，设备管理器会出现 "Silicon Labs CP210x USB to UART Bridge (COMx)"。

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

> 🤖 **想省事**：`.\build\ps1\run_build.ps1 -Measure` 自动烧板并采集 10 次读数到 `w1_readings.csv`（等效于本节手动操作；手动流程的价值在于理解界面与排障）。

> 📸 **记录模板**：截图（VIO 面板 + 硬件窗口）存 `docs/w1_evidence/`，读数表填上表；`docs/llm_log_w1.md` 记三行 AI 协作日志（原第⑨章「收尾」内容已并入）。
> 这个"验证点①达成"的证据在竞赛报告里就是"上板验证第一章"。

---

## 八、换板对比（板 2 到位后）

1. Flow → **Settings** → **General** → 改 Project device 为板 2 型号
2. 重新 **Generate Bitstream**
3. 烧板 2 → 记 10 次
4. 两板中心差 > 数千 ⇒ "同一份代码、两颗芯片、两个身份"实锤

---

## ⭐ 验证点 ② · w3_top 心跳 + 按键（时钟 / 复位 / LED 三大板级适配）

> 目标：让 `w3_top`（A1 已集成的 15 模块顶层，含 Speck64/96 密码核与完整协议栈）
> 在真实硅片上跑起来。**验收铁证 = 心跳 LED 按真实时钟频率闪烁**——这一下同时验证了
> 时钟、复位、LED 引脚、以及"12/12 TB 的仿真基线在真实硅片上成立"。

### 2.1 三大适配是什么

| 适配 | 问题 | 方案 |
|---|---|---|
| **时钟** | ZC702 PL 时钟 = 200MHz **差分**（D18=SYSCLK_P / C19=SYSCLK_N，LVDS_25），w3_top 期待 100MHz 单端 `sys_clk` | **Option A（推荐）**：w3_top 加 `clk_p/clk_n` 差分端口 + IBUFDS + MMCM 分频到 100MHz；**Option B**：换 FMC 底板的 100MHz 单端时钟源 |
| **复位** | 板上 CPU_RESET 在 **PS 域**，PL 逻辑够不着 | 用 **GPIO_SW_N 按键（G19, LVCMOS25）**接 `sys_rst_n`（低有效，w3_top 已带 2FF 同步器 + 按键消抖） |
| **引脚** | w3_top.xdc 全部引脚被注释（占位） | 按 2.3 的清单逐行取消注释 + UG850 核对 |

### 2.2 时钟 Option A 逐行操作

1. w3_top.v 端口改动：
```verilog
   input  wire clk_p,      // 200MHz 差分正端（D18, LVDS_25）
   input  wire clk_n,      // 200MHz 差分负端（C19, LVDS_25）
```
（原 `sys_clk` 删除；内部新增 `wire sys_clk_100M;` 作为全局时钟，
所有 `posedge sys_clk` 改为 `posedge sys_clk_100M`——全文件替换即可，
参数 FREQ_HZ 保持 100_000_000 不变）

2. IP Catalog → 搜索 **Clocking Wizard** → 双击：
   - *Input Clock Information* → PRIMARY 下拉选 **Differential clock capable pin**，输入频率 `200` MHz
   - *Output Clocks* → CLK_OUT1 频率 `100` MHz
   - *Optional Inputs* → 勾选 **reset**（接按键复位）、勾选 **locked**
   - 点 OK → Generate

3. w3_top.v 例化向导生成的 `clk_wiz_0`：
```verilog
   wire sys_clk_100M, mmcm_locked;
   clk_wiz_0 u_mmcm (
       .clk_in1_p (clk_p),
       .clk_in1_n (clk_n),
       .reset     (1'b0),            // MMCM 先不接按键复位，用 locked 作软复位条件
       .clk_out1  (sys_clk_100M),
       .locked    (mmcm_locked)
   );
```
   并把复位同步器的异步复位源改为 `!mmcm_locked`（时钟没锁住前保持复位）。

4. XDC 追加（时钟约束——**w3_top 与 W1 不同，这次必须约束时钟**）：
```tcl
set_property -dict {PACKAGE_PIN D18 IOSTANDARD LVDS_25} [get_ports clk_p]
set_property -dict {PACKAGE_PIN C19 IOSTANDARD LVDS_25} [get_ports clk_n]
create_clock -period 5.000 -name sys_clk_p [get_ports clk_p]
```
   （MMCM 输出的 100MHz 由向导自动 create_generated_clock，无需手写）

### 2.3 XDC 取消注释清单（逐行，每行都要 UG850/ZC702 原理图核对）

| 行 | 内容 | 核对来源 |
|---|---|---|
| `set_property PACKAGE_PIN G19 [get_ports sys_rst_n]` + `set_property IOSTANDARD LVCMOS25` | 复位 = GPIO_SW_N | UG850 表 "GPIO SW N" |
| `Y11` → led_busy（DS9） | 认证进行灯 | UG850 表 "LEDs" |
| `T22` → led_heartbeat（DS10） | 心跳灯 | 同上 |
| `W21` / `U21` → led_result[1:0]（DS11/DS12） | 结果码灯 | 同上 |
| `W6` / `W7` → term_id_sw[1:0] | 仅 2 位拨码在 PL | 同上；term_id_sw[7:2] 在 w3_top 里接常量 |
| auth_btn | 另一个 GPIO_SW 按键 | UG850 查 GPIO_SW_S/E/W 的 PL 引脚 |

> ⚠ 每核对一个引脚就在 XDC 里取消一行注释；**不认识的引脚宁可不接**。
> `term_id_sw[7:2]` 若无物理开关，在 w3_top 中改接常量（如 8'h01）。

### 2.4 收尾三件事

1. **DRC 口径升级**：w3_top.xdc 引脚填齐后，把 build_w3.tcl 里的两行
   `set_property SEVERITY {Warning} [get_drc_checks UCIO-1/NSTD-1]` **删除**——
   开发模式的豁免期结束，让 DRC 重新全量把关
2. **重跑 12/12 TB**：时钟端口改动后必须全量回归（`.\scripts\ci_regression.ps1`）——
   CI 纪律上板期同样生效
3. **生成比特流**：GUI（Generate Bitstream）或脚本
   `vivado -mode batch -source build/tcl/build_w3.tcl`
   （注意：当前 build_w3.tcl 停在 route_design，需在末尾加一行
   `write_bitstream -force $OD/w3_top.bit`）

### 2.5 验收（无电台也能做的三连测）

| 测 | 操作 | 预期 |
|---|---|---|
| 心跳 | 数 DS10：10 秒内翻转次数 | 约 **15 次**（0.75Hz——hb_cnt[26] 每 0.67s 翻转） |
| 复位 | 按 GPIO_SW_N | 心跳计数归零重启（看不出的话配合 auth 测） |
| 按键协议触发 | 按 auth_btn（无基站） | led_busy（DS9）亮约 **2 秒**（等待基站判定超时）→ 灭，led_result 显示阻断码（两灯同亮 = 11） |

> 心跳闪烁 = 时钟 ✓ + 复位 ✓ + 引脚 ✓ + 计数逻辑 ✓，四件事一次全验。
> 任何一项不符 → 见排障速查"验证点②"段。

---

## ⭐ 验证点 ③ · PC 串口环路（协议帧互通）

> 目标：PC 发 CHALLENGE 黄金帧 → w3_top 的 frame_parser 正确解析（fp_frame_ok）
> → 终端回 RESPONSE_R1 → PC parse 成功。**这一步开始，"跨阶段配合"变成物理现实。**

### 3.1 关键硬件认知（决定买什么线）

**ZC702 的板载 USB-UART 接在 PS 域（MIO），PL 的 radio_txd 物理上到不了它。**
所以要打通 PL ↔ PC，三选一：

| 方案 | 需要什么 | 适合 |
|---|---|---|
| **USB-UART 桥**（推荐先行） | FMC/PMOD 转 USB-UART 模块（CH340/FT232，**3.3V 电平**） | 验证点③纯协议互通 |
| 433MHz 电台一对 | SiK 兼容 ×2 + USB-TTL ×2 | 验证点⑤无线演示 |
| 逻辑分析仪/示波器 | 任意 | 只看波形不回环 |

### 3.2 接线（3.3V！共地！）

| w3_top 信号 | XDC 引脚 | 接到 USB-UART 桥 |
|---|---|---|
| radio_txd | FMC/PMOD 待填 | 桥的 RXD |
| radio_rxd | FMC/PMOD 待填 | 桥的 TXD |
| GND | — | 桥的 GND（**必须共地**） |

### 3.3 PC 侧对接（都在仓库里现成）

- 帧构造/解析：`src/python/server/protocol.py`（pack/parse，已与契约 7 帧同步）
- CHALLENGE 黄金帧：`docs/protocol_contract.md` §4（seq=0x43 帧，工具已验证逐字节一致）
- 串口读写字节：SerialTransport 类骨架已在 `main.py`（需把"随机 C2 占位"替换为真实接收环路）

### 3.4 两个必须提前知道的坑

1. **注册语义配对**：loopback 终端响应 = HMAC(Secret, 种子)；RTL W3 占位 = **种子直通**。
   串口联调时 enroll 必须用与终端一致的语义（或直接对真实终端注册），
   否则 PUF 评分必 REJECT——这是语义配对问题，不是协议缺陷
2. **断电重放运维**：终端每次换电重启 C2 归位 → 服务器重放窗会拒（fail-closed，正确行为）。
   联调时在 REPL 执行 `c2reset <terminal_id>` 即可恢复（HANDOFF P1-5，W4 修复后消失）

### 3.5 验收

| 测 | 操作 | 预期 |
|---|---|---|
| 帧解析 | PC 发 CHALLENGE 黄金帧 | 终端 S_PROC_SEEDS 正确收到 4 种子（可暂用 LED/VIO 观测） |
| 回帧 | 终端回 RESPONSE_R1 | PC `HFIDAProtocol.parse()` 无异常且 `r1s` 字段正确 |
| 码 4 | PC 发 result=4 的 RESULT 帧 | 终端进 BLOCKED（tb_gap GH 用例已在仿真锁定该语义） |

---

## ⭐ 验证点 ④/⑤ · W4 速览（本教程只给地图）

| 项 | 内容 | 依据 |
|---|---|---|
| P1-4 | terminal_fsm 接 challenge_decode + ro_array（替换种子直通） | w3_top.v 头注释已写好三步接入法 |
| P1-1 | 真密钥替换 NSA 公开向量 | SpeckHSM setkey / DeviceKeyStore 通路已就绪 |
| P1-5 | 终端重放修复（三选一） | HANDOFF P1-5 |
| 熵混合 | K = PUF_out ⊕ station_random（抗 44-bit 离线穷举） | project_design「A1 后安全态势」 |
| ML 攻击 | 合成 arbiter 基线 + 排序重构（B6，20 分） | project_design §W4 |

---

## 排障速查（全阶梯合并版）

### W1（验证点①）

| 症状 | 原因 | 解决 |
|---|---|---|
| Auto Connect 无芯片 | 充电线/没插 J17/驱动缺/没开机 | ①换数据线 ②确认插 **J17（Mini-B）** ③装驱动：JTAG 用 `D:\vivado\2026.1\Vivado\data\xicom\cable_drivers`，串口 COM 用 CP210x（xilinx.com/kits/cp210x） ④看电源灯（SW11） |
| vio_0 not defined | IP 没生成或改名 | 回第四节重做，名必须 `vio_0` |
| LUTLP-1 ERROR | XDC 豁免没加 | 回第二节第 7 步补加 |
| VIO 数字恒 0 | ①首窗未满（14~43s，最常见！） ② KEEP 属性被删 | 耐心等满 43s → 查 ro_ring.v 的 KEEP 行 |
| Part 搜不到 | 器件族未装 | 回第 0 步 |
| part mismatch | part 选错 | 必须 xc7z020clg484-**1** |
| LUT 异常爆 | 误加废弃文件（仅旧 w1_project 目录存在） | 仓库 w1_ratio 路径已无废弃文件；确认源来自 D:\puf-drone-auth\src\rtl\w1_ratio |

### 验证点②③（w3_top 上板）

| 症状 | 最可能原因 | 处理 |
|---|---|---|
| 心跳 LED 不闪 | 时钟没起（MMCM 未 locked）/ 复位挂住 / LED 引脚错 | 先查 `mmcm_locked`（可暂接 LED 观察）；再查 G19 复位极性 |
| 心跳太快/太慢 | 实际时钟 ≠ FREQ_HZ 假设 | 数频率反推实际时钟，修正 MMCM 或 FREQ_HZ |
| UART 全乱码/无输出 | **时钟差 2 倍**（200 vs 100M 经典错）或波特率参数错 | 示波器测位宽（868 拍 @100M=8.68us） |
| 按 auth_btn 无反应 | 按键接在 PS 域 / 消抖参数 / 极性反 | 核对引脚域；w3_top 消抖 10ms；auth_btn 接按键常开 |
| DRC NSTD-1 / UCIO-1 报 ERROR | 验证点②起不再允许豁免 | 补 create_clock / 补引脚约束（这是升级，不是退步） |
| 时序违例 WNS<0 | 约束后真实路径暴露 | 看 report_timing_summary 定位；MMCM 出口时钟确认有 generated_clock |
| Program 成功但全板无反应 | SW16 启动模式 / 复位极性 | JTAG 模式 Program 不依赖 SW16；查 sys_rst_n 是否恒低 |
| 收 RESULT 后终端 BLOCKED | ① result 码非零（含码 4 重放拒止，正常）② R2 字节错 ③ 断电后未 c2reset | 对照 tb_gap GH/GF 用例逐项排查；联调期先 c2reset |
| 终端回帧 PC parse 失败 | CRC_EXTRA/帧布局漂移 | 跑 `python tools/check_contract_sync.py`（7 帧）定位 |

---

## W4 安全包对照表（上板相关）

| 项 | 触发条件 | 修复 | 依据 |
|---|---|---|---|
| P1-1 | W4 真密钥 | SpeckHSM.setkey / DeviceKeyStore 通路已就绪 | HANDOFF 遗留表 |
| P1-4 | W4 PUF 接入 | terminal_fsm 三步接入法（w3_top.v 头注释） | 同上 |
| P1-5 | 终端断电重放 | 三选一（nonce 回显 / C2 非易失 / 会话随机数） | build/reviews/a1full/security_threat.json |
| 44-bit 熵 | W4 真密钥 | K = PUF_out ⊕ station_random / HKDF | project_design「A1 后安全态势」 |
| CI 超时 | W4 首项 | ci_regression.ps1 作业化 | a1p5 CONSENSUS |

---

## 资源

**官方**：UG850（ZC702 板卡手册+引脚）、UG865（Zynq-7000 SoC）、UG908（Vivado Debug/VIO）、
ZC702 原理图 PDF（引脚最终核对）；UG949（UltraFast 方法论，时钟约束章节）
**GitHub**：InterPUF；SiMRA-PUF；mavlink/c_library_v2；pymavlink；
rithan2001/Xilinx-Zynq-7000-SoC-ZC702（master_constraints.xdc——w3_top.xdc 引脚的核对底稿）
**中文**：清华《Vivado 使用入门》（最接近本课流程）；CSDN ZYNQ 启动方式/点灯系列
**练习**：HDLBits
**套件官方**：XTP310 快速入门指南（翻译解读版：同目录《ZC702快速入门指南-翻译与解读.md》）；
www.xilinx.com/kits/cp210x（串口驱动）· /kits/teraterm（终端）· /kits/zc702default（恢复出厂）

---

*界面描述基于 Vivado 2026.1；参考清华大学数字逻辑实验课程教程及 AMD 官方文档。如界面不符请截图发我。*
*2026-10-08 扩充：结合 A1 完成后进度新增"上板阶梯"（验证点②③操作细节与排障），并入官方 XTP310 开箱流程（验证点⓪）；工作区已合并至 D:\puf-drone-auth。真相源 = D:\puf-drone-auth（HEAD 1a4d65e+，A1 六阶段完成）。*