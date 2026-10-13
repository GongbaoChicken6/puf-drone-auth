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
| **①** | **W1 环振比值**（本教程主体，零引脚设计） | 不改任何 RTL；只需加入现成的 `w1_ro_waiver.xdc`（缺它 write_bitstream 被 DRC LUTLP-1 阻断） | VIO 读数 10 次极差 < 100 | 半天 |
| ② | **w3_top 心跳 + 按键**（时钟/复位/LED 三大板级适配） | 新增板级 wrapper（IBUFDS+MMCM，**w3_top 一行不改**）+ wrapper 端口 XDC | 心跳 LED 0.75Hz 闪烁；按键→busy 亮 2s | 1 天 |
| ③ | **PC 串口环路**（协议帧互通） | FMC LPC 转 USB-UART 桥（板载 UART 在 PS 域，PL 够不着；先确认板上有无 PMOD） | PC 发 CHALLENGE → 终端回 RESPONSE_R1 → parse 成功 | 1 天 |
| ④ | **PUF 真实测量**（替换种子直通） | terminal_fsm 接 challenge_decode + ro_array | 上板实测 16 环频率，模板注册后认证 PASS | W4 |
| ⑤ | **完整互认证 + W4 安全包** | P1-5 重放修复 / 熵混合 / 真密钥 | 互认证端到端 + 安全声明如实 | W4 |

> **为什么验证点 ① 仍然是第一颗钉子**：W1 设计**零外部引脚、零时钟约束、只读 VIO**——
> 排除所有板级适配变量，纯粹验证"JTAG 链 → 烧录 → 逻辑运行 → VIO 可观测"这条最小通路。
> 通路通了，后面的每一步才是在验证"设计"，而不是在同时跟"工具链"搏斗。

**当前仿真侧基线（板级未知项的对照组）**：12/12 TB 全绿（含 tb_w3_top 顶层回环、
tb_speck 1175 组全量回放、tb_gap 7 用例含码 4 拒绝）+ 44 Python 单测 + 金丝雀 + 契约同步 7 帧。
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
| **USB 口 A：串口**（J17，用套件的 Mini-B 线） | USB-UART（CP210x）＝ **验证点⓪ 的 BIST / Tera Term 串口** | 装 CP210x 驱动后设备管理器出现 "Silicon Labs CP210x ... (COMx)" |
| **USB 口 B：JTAG**（板上另一个 USB 口；套件同时配了 Mini-B 与 Micro-B 两根线，**以实物丝印为准**） | **Vivado 烧录 + VIO 读数**（Hardware Manager） | Auto Connect 能看到 `xc7z020` 的就是它；**两个口不是同一个**，插错只会找不到芯片，不会损坏板子 |
| **SW16 拨码 = 00010（出厂）** | 启动模式（SD 卡 BIST 镜像） | 保持出厂；动过开关/跳线 → www.xilinx.com/kits/zc702default 恢复 |
| **SW1 按键（POR_B）** | 上电复位 / 重新初始化配置 | 终端空白或配置异常时按一下 |
| **SW15-1/2 ≈ SW13/SW14** | 并联信号（BIST 的 Switch Test 用） | 任选一种 |
| **FMC 连接器** | 扩展接口 | 验证点①不碰（验证点③的 USB-UART 桥/电台会用到） |
| **GPIO_SW_N 按键**（G19） | PL 域复位（验证点②用） | 先认识位置，本课暂不按 |
| **DS15~DS18 LED**（**P17/P18/W10/V7**，已对照 AMD 官方板卡定义核验；位号对应 UG850） | 状态灯（验证点②用） | 先认识位置 |

> ⚠ **两个 board 认知提前打预防针**（验证点②会展开）：
> ① ZC702 的 PL 时钟是 **200MHz 差分**（D18/C19, LVDS_25），而 w3_top 期待 100MHz 单端；
> ② 板载 **PS 域复位键（POR_B，即 SW1）PL 逻辑够不着**——按它是整片复位/重新配置（PL 也会被清），只是不能当 PL 逻辑输入用；PL 复位要用 **GPIO_SW_N（G19, LVCMOS25）**。

---

## 第 0·5 步 · 出厂 BIST 自检（上电第一件事：先证明板子是好的）

> 依据：套件附带官方快速入门指南 **XTP310 (v1.3)** 的 STEP 1~9。
> 在烧我们自己的设计**之前**，先用出厂 SD 卡镜像给板子做一次全面体检——
> 电源/时钟/DDR3/LED/UART 全部健康，之后任何失败都只能是我们设计或约束的问题。

### 0.5.1 准备（一次性，半小时内）

1. 装 **Silicon Labs CP210x USB-UART 驱动**：www.xilinx.com/kits/cp210x
2. 装终端软件 **Tera Term**：www.xilinx.com/kits/teraterm（PuTTY 也可）
3. 盒内物品核对：**SD 卡（出厂 BIST 镜像，插回板上别弄丢）**、USB Hub、HDMI 线、以太网线、两种 USB 线

### 0.5.2 开箱流程（官方 STEP 1~11）

| 步 | 操作 | 关键点 |
|---|---|---|
| 1 | 装驱动 + 终端软件 | CP210x + Tera Term |
| 2 | DIP **SW16 = 00010**（出厂启动模式：SD 卡镜像） | 动过开关/跳线 → www.xilinx.com/kits/zc702default 恢复 |
| 3 | 电脑 ↔ **J17**（Type-A 转 Mini-B） | J17 是**串口**口（CP210x）——BIST 只走串口，本步不需要 JTAG |
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

## 二、新建工程（**路线一 · 全 GUI**，每一下点击）

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
   - *Project location*：改为 `D:\puf-drone-auth\build\vivado`（默认在 C:/Users/你的用户名/ 下——**必须改**：经验做法——工程放纯 ASCII 路径可规避中文/空格引发的工具链与脚本编码问题（非官方明示），仓库路径正好是纯 ASCII）
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

> ⚡ **路线二 · 全脚本（推荐，与路线一互斥）**：仓库自带一键脚本，建工程→综合→实现→比特流全自动：
> ```powershell
> cd D:\puf-drone-auth
> .\build\ps1\run_build.ps1            # 一键构建（工程 build\vivado\w1_auto）
> .\build\ps1\run_build.ps1 -Measure   # 构建 + 自动烧板 + 自动采 10 次 VIO 读数存 CSV
> ```
> **⚠ 只选一条路线**：路线一产生工程 `w1_ratio`、路线二产生 `w1_auto`——两条都走等于白等一次 5~15 分钟构建；
> 而且 GUI 的 Hardware Manager 与脚本的 `connect_hw_server` 会抢同一个 hw_server，跑脚本前先关掉 GUI 的 Hardware Manager。
> 若 PowerShell 报「禁止运行脚本」：改用 `powershell -ExecutionPolicy Bypass -File .\build\ps1\run_build.ps1 -Measure`。
> `-Measure` 调用 `build\tcl\measure_w1.tcl`：连 JTAG → 烧录 → 每 15 秒读一次 `probe_in0` → 写 CSV；
> 产物：`D:\puf-drone-auth\build\vivado\w1_auto\w1_auto.runs\impl_1\ro_ratio_top.bit`、
> 读数：`D:\puf-drone-auth\build\vivado\w1_auto\w1_readings.csv`

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
2. 烧录/读 VIO 要用 **JTAG 口**：板上**另一个** USB 口 ↔ 电脑（用套件里**能插进 JTAG 口的那根线**；别写死 Mini/Micro-B——以实物丝印为准）。
   ⚠ **别把 JTAG 和串口搞混**：J17（Mini-B）是**串口**（CP210x，验证点⓪ 的 BIST/Tera Term 用它）；
   JTAG 是**另一个口**。只插 J17 的话，Hardware Manager 永远 Auto Connect 不到芯片。
   自查：设备管理器出现 "Silicon Labs CP210x ... (COMx)" ⇒ 插的是串口；Vivado Auto Connect 看到 `xc7z020` ⇒ 插的是 JTAG。
3. **SW16 不用改回**：用 JTAG 配置 PL 与启动模式无关（做完验证点⓪ 保持 00010 直接烧即可）；
   SD 卡留不留都行，但**烧录过程中不要按 SW1（POR_B）**。

### 烧录

1. **Flow Navigator** → **PROGRAM & DEBUG** → **Open Hardware Manager**

2. 主窗口切到 **Hardware Manager** 标签
   上方绿色区域 → 点 **Open target** → **Auto Connect**

3. 左侧 Hardware 窗口出现 `localhost` → `xc7z020` 芯片图标
   （看不到？→ 排障表第 1 条）

4. **右键** `xc7z020` → **Program Device...**
   Bitstream 路径已自动填好 → 点 **Program**

5. 等 5~10 秒——板子不会有明显灯变（W1 设计没有 LED，读数在 VIO 里看）

---

## 七、读数

### 打开 VIO 读数面板

1. 在左侧 Hardware 窗口（原来显示 Sources 的位置），**展开** `xc7z020`（点旁边的三角形箭头）
   → 下方出现 **hw_vio_1**（或 vio_0——取决于 Vivado 版本）

2. **单击它** → 主窗口出现 VIO 核心读数视图（VIO Cores View）
   → 应能看到 `probe_in0` 及其 32 位值

### 设置自动刷新

按 AMD 官方 UG908（2026.1）：读数在 **VIO Cores View** 里看（Hardware Manager 中点 `hw_vio_1`）。
1. 在该视图的属性表找到 **Refresh Rate (ms)**
2. 填 `1000`——注意 **0 的含义是「停止自动刷新」**，不是「手动」；
   本课读数 14~43 秒才更新一次，1000 ms 足够且不会拖慢 IDE（UG908 提醒刷新率过小会拖慢界面）
3. 属性表位置因版本略有差异；即使找不到，也可以手动点刷新——读数变化很慢，手动完全够用

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

> 🤖 **路线二用户（脚本）**：`-Measure` 已自动完成本节的烧板+读数，直接看 CSV 即可（GUI 路线一才需要按上面手动操作；不要两条路线交叉跑）。`.\build\ps1\run_build.ps1 -Measure` 把 10 次读数写到
> `build\vivado\w1_auto\w1_readings.csv`（等效于本节手动操作；手动流程的价值在于理解界面与排障）。
> **归档到证据链**（`compare_devices.py` 的 `-d` 是**必填**参数、无默认值，所以要显式传 `data/w1_readings/`；不归档就接不上第八节的换板对比）：
> ```powershell
> Copy-Item build\vivado\w1_auto\w1_readings.csv data\w1_readings\board1.csv
> ```
> **阈值换算**：极差 < 100 ⇔ fB/fA 波动 < 100/262144 = 3.8e-4（0.038%）。

> 📸 **记录模板**：截图（VIO 面板 + 硬件窗口）存 `docs/w1_evidence/`（已建好；若被清掉：`New-Item -ItemType Directory -Force docs\w1_evidence`），读数表填上表；`report/llm_log/w1_session.md` 记三行 AI 协作日志（docs/llm_log/ 已迁走；原第⑨章「收尾」内容已并入）。
> 这个"验证点①达成"的证据在竞赛报告里就是"上板验证第一章"。

---

## 八、换板对比（板 2 到位后）

1. Flow → **Settings** → **General** → 改 Project device 为板 2 型号
2. 重新 **Generate Bitstream**（或对板 2 跑一次 `run_build.ps1 -Measure`）
3. 记 10 次读数，**归档**：`Copy-Item build\vivado\w1_auto\w1_readings.csv data\w1_readings\board2.csv`
4. 跑对比工具（`-d` 必填）：
   ```powershell
   python src\python\evaluation\compare_devices.py -d data\w1_readings\
   ```
   **看什么**：工具输出的是两板间的 **HD%（汉明距离占比）**——同一颗芯片极低、不同芯片接近 50%。
   教程早期说的"中心差 > 数千"是同一件事的原始计数口径（262144 满量程下，数千 ≈ 百分之几），
   以工具的 HD% 为准；若两板 HD% 明显偏高（>~40%）即"两颗芯片两个身份"成立。

---

## ⭐ 验证点 ② · w3_top 心跳 + 按键（时钟 / 复位 / LED 三大板级适配）

> 目标：让 `w3_top`（A1 已集成的 15 模块顶层，含 Speck64/96 密码核与完整协议栈）
> 在真实硅片上跑起来。**验收铁证 = 心跳 LED 按真实时钟频率闪烁**——这一下同时验证了
> 时钟、复位、LED 引脚、以及"12/12 TB 的仿真基线在真实硅片上成立"。

### 2.1 三大适配是什么

| 适配 | 问题 | 方案 |
|---|---|---|
| **时钟** | ZC702 PL 时钟 = 200MHz **差分**（D18=SYSCLK_P / C19=SYSCLK_N，LVDS_25），w3_top 期待 100MHz 单端 `sys_clk` | **板级 wrapper（推荐，见 2.2）**：新建 `w3_top_zc702.v` 放 IBUFDS + MMCM，**w3_top 一行不改**（否则 `tb_w3_top` 与 12/12 CI 会挂）；**备选**：换 FMC 底板的 100MHz 单端时钟源 |
| **复位** | PS 域复位键（POR_B/SW1）按下去是整片复位/重配，**不能当 PL 逻辑输入** | 用 **GPIO_SW_N 按键（G19, LVCMOS25）**接 wrapper 的 `sys_rst_btn_n`（低有效；w3_top 自带 2FF 同步器；消抖只作用于 `auth_btn`） |
| **引脚** | w3_top.xdc 全部引脚被注释（占位） | 按 2.3 的清单逐行取消注释 + UG850 核对 |

### 2.2 时钟适配：板级 wrapper（**不要改 w3_top.v**）

> ⚠ **为什么改 w3_top 端口是错的**：`sim/tb/tb_w3_top.v` 按 `.sys_clk(sys_clk)` 例化它，改端口会让这个 CI 用例 elaborate 失败；
> 而且 Clk Wizard IP 在仓库里没有仿真源（`ci_regression.ps1` 只编译纯 `.v`，全仓 0 个 `.xci`），
> IBUFDS/MMCM 也无法进仿真。**结论：把时钟适配放进一个独立的板级 wrapper，w3_top 保持原样 → 12/12 TB 继续全绿。**

1. **把 wrapper 加入工程并设为顶层**（这一步不做，后面所有约束都会 get_ports 失败）：
   - **Add Sources** → Add Files → 选 `D:\puf-drone-auth\src\rtl\w3_protocol\w3_top_zc702.v`（同时确认 `w3_top.v` 也在工程里）
   - Sources 窗口 **右键 `w3_top_zc702` → Set as Top**（变粗体且带 (top) 才算）
   - wrapper 内容：clk_p/clk_n 差分输入 + `clk_wiz_0` → 100MHz + `rst_n = sys_rst_btn_n & mmcm_locked` + 例化 w3_top（参数与端口一一对应）

2. IP Catalog → 搜索 **Clocking Wizard** → 双击（工程里生成 IP，名字必须 `clk_wiz_0`）：
   - *Input Clock Information* → PRIMARY 选 **Differential clock capable pin**，输入频率 `200` MHz
   - *Output Clocks* → CLK_OUT1 = `100` MHz
   - *Optional Inputs* → 勾选 **locked** 与 **reset**（wrapper 里写成 `.reset(~sys_rst_btn_n)`：IP 高有效 ⇐ 按键低有效取反，你不用另接；**必须勾 reset**，否则生成的 IP 没有该端口、wrapper 例化会报错）
   - OK → Generate

3. 时钟约束（加进 `w3_top.xdc` 或工程自己的 XDC；**w3_top 本身不需要约束**）：
```tcl
set_property -dict {PACKAGE_PIN D18 IOSTANDARD LVDS_25} [get_ports clk_p]
set_property -dict {PACKAGE_PIN C19 IOSTANDARD LVDS_25} [get_ports clk_n]
create_clock -period 5.000 -name sys_clk_p [get_ports clk_p]
```
   （MMCM 输出的 100MHz 由向导自动 `create_generated_clock`，无需手写）

4. 复位：wrapper 已写成 `wire rst_n = sys_rst_btn_n & mmcm_locked;`——按键按下**或** MMCM 未锁定都会复位，两者不冲突（这正是 2.5 测 2 能验的前提）。

> **本 wrapper 不参与仿真/CI**（IP 无仿真源）；它对 CI 的影响为零：`ci_regression.ps1` 编译清单里没有它。

### 2.3 XDC 取消注释清单（逐行，每行都要 UG850/ZC702 原理图核对）

| 行 | 内容 | 核对来源 |
|---|---|---|
| `set_property PACKAGE_PIN G19 [get_ports sys_rst_btn_n]` + `IOSTANDARD LVCMOS25` | 复位 = GPIO_SW_N（**端口名用 wrapper 的 `sys_rst_btn_n`**） | UG850 表 "GPIO SW N" |
| `P17` → led_busy（LED0） | 认证进行灯 | **官方板卡定义: leds_4bits = P17/P18/W10/V7**；⚠ ``Y11/T22/U21`` 是 FMC2 LPC 脚、**不是 LED**（旧底稿错）。每行都要配 `IOSTANDARD LVCMOS25` |
| `P18` → led_heartbeat（LED1，**DS16**） | 心跳灯 | 同上；位号对应已核（UG850）：P17/P18/W10/V7 = DS15/16/17/18 |
| `W10` / `V7` → led_result[1:0]（LED2/LED3） | 结果码灯 | 同上 |
| `W6` / `W7` → term_id_dip[1:0]（wrapper 端口） | 仅 2 位拨码在 PL | 同上 + IOSTANDARD；**wrapper 已把高 6 位 tie 0**（`.term_id_sw({6'h00, term_id_dip})`），无需手工改代码 |
| `auth_btn` → **F19** | PL 按键（GPIO_SW_S，官方板卡定义核验） | 已在 `w3_top.xdc` 补好注释行；不接则 2.5 测 3 跳过 |

> ⚠ 每核对一个引脚就在 XDC 里取消一行注释；**不认识的引脚宁可不接**。
> 顶层是 wrapper 时不需要你改 RTL：`term_id_dip[1:0]` 只占 W6/W7 两颗拨码，**wrapper 内已 tie 高 6 位为 0**（`.term_id_sw({6'h00, term_id_dip})`，故 terminal_id 只有 0~3）。

### 2.4 收尾（**严格按此顺序**，顺序错了 write_bitstream 会被 DRC 阻断）

1. **先把所有端口落定**（这一步做完才能动 DRC）：
   - 每个已用端口都要有 `PACKAGE_PIN` **和** `IOSTANDARD`（LED 四行原来缺电平）
   - `term_id_dip[1:0]` → 板上 W6/W7；**wrapper 已 tie 高 6 位为 0**，不用改代码（terminal_id 只有 0~3）
   - `radio_txd/radio_rxd`：**上板脚本没有豁免，缺约束会直接 UCIO-1 ERROR**，所以必须给它们引脚：
     ① 推荐——按 UG850 选 FMC LPC 的一组 LA 脚对（`LVCMOS25`）填进 `w3_top.xdc`；
     ② 若这一轮（验证点②）暂时还不想定，就在 `build_w3_board.tcl` 里**临时**加一行 `set_property SEVERITY {Warning} [get_drc_checks UCIO-1]` 并在注释里标明「临时期，验证点③ 落定引脚后删除」——不要默认以为脚本已有豁免（只有 dev 脚本 `build_w3.tcl` 有）。
2. **确认约束文件真的被加载**：上板脚本 `build_w3_board.tcl` 已含 `add_files -fileset constrs_1 $SRC/rtl/w3_protocol/w3_top.xdc`；GUI 路线则在 Constraints 里确认 `w3_top.xdc` 已启用。（注意区分：`build_w3.tcl` 是 **dev 模式**设计构建——top=w3_top、无 IP、无引脚约束、带 DRC 豁免，**不要**用它上板。）
3. **然后才是删豁免**：两条豁免只存在于 dev 脚本 `build_w3.tcl`（`set_property SEVERITY {Warning} [get_drc_checks UCIO-1]` 与 `... NSTD-1]`，各自独立一行）。上板脚本 `build_w3_board.tcl` **本来就没有豁免**——所以「删豁免」= 以后不再用 dev 脚本出比特流，而不是去改上板脚本。
4. **CI 回归**：`w3_top` 本体未改动（时钟在 wrapper 里），**12/12 TB 应保持全绿**——`xsim`/`xvlog` 编译清单不含 wrapper，也不需要 IP 仿真源。
   如果你确实改了 `w3_top` 本身（例如加端口），必须先同步改 `sim/tb/tb_w3_top.v` 再跑 `.\scripts\ci_regression.ps1`，否则 CI 必红。
5. **生成比特流**：GUI（把 `w3_top_zc702` 设为顶层后 Generate Bitstream）或上板脚本
   `vivado -mode batch -source build/tcl/build_w3_board.tcl -tclargs xc7z020clg484-1 D:/puf-drone-auth/build/vivado/w3_board D:/puf-drone-auth/src`
   （上板脚本会自动：top=`w3_top_zc702` + 生成 `clk_wiz_0` + 加载 `w3_top.xdc` + 全程无 DRC 豁免；产物 `w3_board/w3_top_zc702.bit`）

### 2.5 验收（无电台也能做的三连测）

| 测 | 操作 | 预期 |
|---|---|---|
| 心跳 | 数 DS16：10 秒内亮/灭**变化次数** | 约 **15 次变化 = 7~8 个完整亮灭来回**（周期 ≈1.34 s，0.75 Hz） |
| 复位 | 按住 GPIO_SW_N 不放 | 按住期间 DS16 停在固定电平（复位生效）；松开后恢复 1.34 s 周期闪烁 |
| 按键协议触发 | 按 auth_btn（无基站） | led_busy（DS15）亮约 **2 秒**（等待基站判定超时）→ 灭，led_result 显示阻断码（两灯同亮 = 11） |

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
| **USB-UART 桥**（推荐先行） | **FMC LPC** 转 USB-UART 模块（CH340/FT232，**3.3V 电平**） | 验证点③纯协议互通 |
| 433MHz 电台一对 | SiK 兼容 ×2 + USB-TTL ×2 | 验证点⑤无线演示 |
| 逻辑分析仪/示波器 | 任意 | 只看波形不回环 |

### 3.2 接线（3.3V！共地！）

> ⚠ **先断电再插 FMC**（或板上 PMOD，若有）：ZC702 官方禁止带电插拔 FMC（见 `board/zc702/README.md`）。
> 顺序：SW11 断电 → 插 FMC/PMOD 转接板 → 接线 → 上电。
> **引脚状态**：`w3_top.xdc` 目前**没有** UART 引脚（只有注释段）——必须先从 UG850 选定 FMC LPC 的 LA 脚对
> （`radio_txd`/`radio_rxd` + `IOSTANDARD LVCMOS25`）填入 XDC，才能做本验证点；**未选定引脚前本步暂缓**。

| w3_top 信号 | XDC 引脚 | 接到 USB-UART 桥 |
|---|---|---|
| radio_txd | **待选**（FMC LPC LA 脚对，查 UG850 后填入） | 桥的 RXD |
| radio_rxd | **待选**（同上） | 桥的 TXD |
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
| Auto Connect 无芯片 | **插的是 J17（串口）而不是 JTAG 口**/充电线/JTAG 驱动缺/没开机 | ①改用**能插进 JTAG 口的那根数据线**（J17 是串口，插它必然找不到芯片） ②装 JTAG 驱动：`D:\vivado\2026.1\Vivado\data\xicom\cable_drivers` ③串口 COM 是另一个驱动：CP210x（xilinx.com/kits/cp210x） ④看电源灯（SW11） |
| vio_0 not defined | IP 没生成或改名 | 回第四节重做，名必须 `vio_0` |
| LUTLP-1 ERROR | XDC 豁免没加 | 回第二节第 7 步补加 |
| VIO 数字恒 0 | ①首窗未满（14~43s，最常见！） ②Refresh Rate = 0（自动刷新被关） ③KEEP 属性被删 | 等满 43s → 把 Refresh Rate 设为 1000 → 查 ro_ring.v 的 KEEP 行 |
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
| DRC NSTD-1 报 ERROR | 已用端口缺 IOSTANDARD（LED 四行原来就没写电平） | 按 2.3 给每个已用端口补 `IOSTANDARD LVCMOS25`，然后删 NSTD-1 豁免 |
| 时序违例 WNS<0 | 约束后真实路径暴露 | 看 report_timing_summary 定位；MMCM 出口时钟确认有 generated_clock |
| Program 成功但全板无反应 | 复位极性 / 时钟未锁定 | JTAG 配置 PL **与 SW16 启动模式无关**（保持 00010 即可）；查 sys_rst_n 是否恒低、mmcm_locked 是否为 1 |
| 收 RESULT 后终端 BLOCKED | ① result 码非零（含码 4 重放拒止，正常）② R2 字节错 ③ 断电后未 c2reset | 对照 tb_gap GH/GF 用例逐项排查；联调期先 c2reset |
| 终端回帧 PC parse 失败 | CRC_EXTRA/帧布局漂移 | 跑 `python tools/check_contract_sync.py`（7 帧）定位 |

---

## W4 安全包对照表（上板相关）

| 项 | 触发条件 | 修复 | 依据 |
|---|---|---|---|
| P1-1 | W4 真密钥 | SpeckHSM.setkey / DeviceKeyStore 通路已就绪 | HANDOFF 遗留表 |
| P1-4 | W4 PUF 接入 | terminal_fsm 三步接入法（w3_top.v 头注释） | 同上 |
| P1-5 | 终端断电重放 | 三选一（nonce 回显 / C2 非易失 / 会话随机数） | build/reviews/a1p4/security_threat.json |
| 44-bit 熵 | W4 真密钥 | K = PUF_out ⊕ station_random / HKDF | project_design「A1 后安全态势」 |
| CI 超时 | W4 首项 | ci_regression.ps1 作业化 | a1p5 CONSENSUS |

---

## 资源

**官方**：UG850（ZC702 板卡手册+引脚）、UG865（Zynq-7000 SoC）、UG908（Vivado Debug/VIO）、
ZC702 原理图 PDF（引脚最终核对）；UG949（UltraFast 方法论，时钟约束章节）
**GitHub**（仓库 `external/` 有四份**源码**：PUF-lab、fpga_puf、c_library_v2、puf-esp32-auth；`pymavlink` 是 pip 安装、不在 external/；逐行分析见 docs/opensource_analysis.md）：
**参考底稿（非源码）**：rithan2001/Xilinx-Zynq-7000-SoC-ZC702 的 master_constraints.xdc —— 注意其 LED 引脚与 AMD 官方板卡定义不符（Y11/T22/U21 实为 FMC2 LPC），已按官方定义为 P17/P18/W10/V7
**中文**：清华《Vivado 使用入门》（最接近本课流程）；CSDN ZYNQ 启动方式/点灯系列
**练习**：HDLBits
**套件官方**：XTP310 快速入门指南（翻译解读版：同目录《ZC702快速入门指南-翻译与解读.md》）；
www.xilinx.com/kits/cp210x（串口驱动）· /kits/teraterm（终端）· /kits/zc702default（恢复出厂）

---

*界面描述基于 Vivado 2026.1；参考清华大学数字逻辑实验课程教程及 AMD 官方文档。如界面不符请截图发我。*
*2026-10-08 扩充：结合 A1 完成后进度新增"上板阶梯"（验证点②③操作细节与排障），并入官方 XTP310 开箱流程（验证点⓪）；工作区已合并至 D:\puf-drone-auth。真相源 = D:\puf-drone-auth（HEAD 1a4d65e+，A1 六阶段完成）。*