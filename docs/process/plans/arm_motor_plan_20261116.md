# ARM 核控制电机修改方案（Plan B 提前激活版）

> **v4 附录（2026-11-17 深夜，当前版本）**：网表逻辑锥解剖发现双重根因——
> ① v2/v3 综合器把 OBUFT/I 的 EMIO 多路器折叠成常数路径（连通性≠逻辑实现）；
> ② 板上实测 EMIO GPIO_O 输出不跟随 DATA_2 寄存器写入（写/读全对但硬件输出恒 0）。
> v4 修复：删除 EMIO 多路器，OBUFT 全由 PL 认证结果驱动——T = pass_pl（PASS=释放→转），I = 0（其余=驱动低→停）。
> ARM ELF 降级为监视器（读 auth_pass），答辩叙事保留"PL 认证信任根 + PS 监视"。
> bit = build/board_zc706_arm_v4，网表锥验证：T=led_result 组合逻辑 ✓、I=GND ✓。
> 调试工具链：cone_trace*.tcl（网表锥）、state_*.tcl/toggle_probe.tcl（JTAG 寄存器操作）保留在 sw/arm_fan/ 供复现。

> **v2 附录（2026-11-17，已实施，提交 19490ab）**：外部电源损坏 → 供电改板载 J63.13(5V) 直供；
> PWM 从"DATA 输出高低"升级为**三态释放**（转=OEN=0 释放 Hi-Z→L9110 内部上拉导通；停=驱动低；调速=OEN 软件 PWM），
> 对供电电压不敏感（4.5V/5V 通用）。RTL：ext_led[3:0]→[2:0] + inout ext_fan（AK21，OBUFT）；bit=build/board_zc706_arm_v2。
> 电气可行性 11-17 实证（FPGA 未配置→引脚 Hi-Z→风扇转，TXS0108E 拔河胜出）。
> 部署：demo_start.ps1 已适配（板A=v2 bit+ELF+风扇，板B=旧 seed2 纯认证）。以下为 v1 原方案（已归档）：

> 背景：老师明确要求采用 ARM 核控制电机。此前评估的方案B（PS7+PS 裸机驱动电机，预估 1~2 天）由"赛后做"
> 提前到决赛前执行；原方案A（CH340 板外驱动）降级为回退路径。
> 日期：2026-11-16 晚 ｜ 工具链已核验就绪 ｜ 排期：11-17 全天实现 + 11-18 彩排，11-19 装箱

## 一、架构故事（答辩口径升级）
**PL 承担信任根（认证），PS 承担执行器（飞控）**——软硬件安全分区的完整 SoC 设计：
- PL（不变）：PUF 指纹、五帧认证协议、Speck 密码核、灯语——纯硬件信任根，无软件攻击面
- PS（新增）：Cortex-A9 裸机飞控程序，通过 EMIO 监视 PL 的认证结果，PASS → 驱动电机 PWM 时序
  （怠速→加速→巡航），REJECT/掉认证 → 停转
- 叙事："认证解锁的是机载飞控，而不是地面站遥控"——板上自主，比 PC 遥控更符合无人机故事

## 二、信号架构
```
PL（现有认证链不动）                        PS（Cortex-A9，OCM 裸机，XSDB/JTAG 加载）
terminal_fsm ─led_result_raw[1:0]─┐
                                  ├─ EMIO[2](PL→PS): auth_pass 解码
demo_led ─ext_led[0]原路径─┐      │
                          ▼      ▼
        J58.3 = arm_sel ? arm_pwm : ext_led[0](原灯语路径)
             ▲              ▲
        EMIO[1](PS→PL)   EMIO[0](PS→PL)
        arm_sel(接管选择) arm_pwm(软件PWM)
```
**默认安全**：PS 未上程序时 EMIO 输出复位值=0 → arm_sel=0 → J58.3 走原 demo_led 路径，
bit 行为与当前完全一致（ARM 失败不伤主演示，回退=不加载 ELF 即可）。

## 三、RTL 修改点（最小侵入，仅动 w3_top_zc706.v + 构建脚本）
1. 新增 `ps7_stub.v`：PS7 例化（EMIO GPIO 使能）。来源：临时工程生成最小 BD（PS7+GPIO EMIO）
   导出例化桩——参考既有 `build/qspi_xsa/design_1_ps7_0.xci`（上会话 QSPI 工程已验证本仓库流程能吃 PS7）
2. `w3_top_zc706.v`：
   - 实例化 PS7，引出 GPIO[0..2]（EMIO）
   - auth_pass 解码（led_result_raw 的 PASS 编码实现时从 terminal_fsm 确认）
   - ext_led[0] 二选一 mux（其余 3 位与蜂鸣器不动）
3. `build_w3_board_seed2.tcl`：add_files 加 ps7_stub.v；环振豁免/PBlock/门禁断言全保留（PS7 不碰环振）
4. `verify_wrapper.ps1`：离板语法门禁为 PS7 增加 stub（与 clk_wiz_0 同法）
5. w3_top 与 18 个 TB 完全不动（CI 无感）；仅板B seed2 bit 变更 → **更新预登记 SHA**，板A bit 不动

## 四、PS 软件方案（无需 FSBL/QSPI/Vitis 工程）
- 裸机 C，寄存器级，~200 行：GPIO@0xE000A000（EMIO bank2=输入/bank3=输出）+
  CPU 私有定时器@0xF8F00600 做软件 PWM 节拍（轮询，不用中断→无向量表）
- 链接到 OCM（0xFFFC0000），XSDB 流程：connect → ps7_init(官方 sample_sdt) → dow elf → con
- 编译：`D:\vivado\2026.1\gnu\aarch32\nt\gcc-arm-none-eabi`（已核验存在）
- 逻辑：poll auth_pass → PASS: duty 20%→100% 渐升（2s 起飞时序）→维持；REJECT/掉: 0%
- （扩展位）PS UART 若在板上有引出（实现时查 UG954 UART 节），可接基站串口做 UI 手动调速；
  不引出则演示口径="机载自主飞控时序"（故事反而更顺）

## 五、电气前提（物理不变式，与控制器无关）
J58.3 经 TXS0108E 上限 3.3V → L9110 VCC 须 ≤4.6V。选项按优先序：
1. **实验室可调稳压源 4.5V**（建议向老师/实验室借——老师已要求此功能，配套供电顺理成章）
2. 1N4007 串 J63.13(5V)→4.3V（实验室一颗二极管）
3. 3 节电池+桥接空槽 ≈4.2-4.5V（带载实测，新电池 4.8V 会超）
⚠ J63.13 的 5V 直接做 VCC 不行（阈值回到 3.5V>3.3V）；地一律走 J58.9

## 六、demo 集成
- demo_start.ps1 加一步：PROGRAM_OK 后调 xsdb.bat 跑 `arm_fan.tcl`（ps7_init + dow + con，~5s）
- 断电恢复顺序：demo_start 自动完成 bit+ELF 双加载（均为 JTAG 易失，一致）

## 七、排期与决策点
| 时段 | 任务 | 里程碑 |
|---|---|---|
| 11-16 晚 | 本方案评审/批准（可选：先做 scratch BD 生成 ps7_stub） | stub 就绪 |
| 11-17 上午 | RTL 集成 + seed2 重建（过全部门禁断言） | 新 bit PROGRAM_OK |
| 11-17 下午 | ARM app + XSDB 上板：先 EMIO 闪灯，再接 L9110 闭环 | **D1 18:00 决策点**：风扇闭环成/败 |
| 11-18 | demo_start 集成 + 五步全流程彩排×2 + fake_result_attack 彩排 + 回退演练 + 录像 | 全流程录像 |
| 11-19 | 装箱（新旧两套 bit+elf 标签分装） | 出发 |

**回退线**：D1 18:00 若闭环未通 → 板B 立即回烧当前 bit（2 分钟）+ CH340 方案A 彩排；
ARM 线继续修但不再阻塞主彩排。

## 八、风险表
| 风险 | 概率 | 缓解 |
|---|---|---|
| 非BD流程吃 PS7 例化出问题 | 中 | qspi_xsa 先例 + scratch BD 重生成；>4h 不通即回退 |
| 新 bit SHA/预登记流程滞后 | 低 | 只动板B；构建后立刻更新登记 |
| 4.5V 供电带载不稳 | 中 | 实验室稳压源优先；电池方案带载实测 |
| 起飞时序抖动/看门狗缺失 | 低 | 软件简单轮询；REJECT/掉线均归零 duty |
| demo_start 双加载步骤出错 | 低 | 沿用 PROGRAM_OK 哨兵模式加 ELF_OK 哨兵 |
