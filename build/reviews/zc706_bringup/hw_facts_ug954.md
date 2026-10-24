# ZC706 硬件事实核查（UG954 v1.8 官方全文）— 迁移计划 §0.5/Phase 5-7 的证据底稿

> ⚠ **【勘误 banner 2026-10-23】本文档 L50/L66/L72（banner 插入前编号 L45/L61/L67）的"按键空闲=1（上拉）/按下=0"结论已被板上实测推翻**：
> health 灯语固件实证 SW13(A8)/SW7(AK25) 真实极性 = **空闲0/按下=1**（2026-10-22 23:27，证据见 `HANDOFF_20261023_根因翻案.md`）。
> 该错误解读源自 UG954 Table 1-29 图纸推断，波及全项目（wrapper 极性/消抖复位值/教程叙述），已于 2026-10-23 全量修复。
> **本文档其余结论未翻案、仍有效**（DIP ON=1、LED 高有效、时钟 DIFF_SSTL15、bank 电平、JTAG/电源事实等）。

> 采集：2026-10-19，web 研究子代理（10 问全答）；主源 = UG954 (v1.8) Aug 6 2019 官方 PDF 全文
> （docs.amd.com 页面 JS 不可抓取，Mouser 镜像同一官方文件，页脚 "www.xilinx.com UG954 (v1.8) August 6, 2019"）。
> 本地全文缓存：D:\文件\ssssssss\FPGA\ug954_text.txt（162KB，可持续 grep）。
> 交叉验证：板卡文件 part0_pins.xml（引脚/IOSTANDARD）+ xc7z045_ffg900.pkg（bank 号）+ zc706/1.5/new.ucf（时钟标准）。

## 来源
- S1 主源 UG954 v1.8 PDF：https://www.mouser.com/datasheet/2/903/ug954-zc706-eval-board-xc7z045-ap-soc-1596272.pdf
- S2 fpgadeveloper JTAG 排障：https://www.fpgadeveloper.com/2013/10/jtag-problems-with-the-zc706.html
- S3 AMD 论坛 VADJ 1.8V 讨论：https://adaptivesupport.amd.com/s/question/0D52E00006hpTOySAM/
- S4 AMD 论坛双 JTAG：https://adaptivesupport.amd.com/s/question/0D52E00006hpkhUSAQ/
- S5 AR#67507 电源信息：https://adaptivesupport.amd.com/s/article/67507
- S6 AR#54013 ZC706 套件：https://adaptivesupport.amd.com/s/article/54013
- S7 产品简报（universal 12V）：https://www.xilinx.com/publications/prod_mktg/Zynq_ZC706_Prod_Brief.pdf
- S8 Digilent 电缆驱动：https://digilent.com/reference/programmable-logic/guides/install-cable-drivers
- S9 TI E2E UCD90120A：https://e2e.ti.com/support/power-management-group/power-management/f/power-management-forum/1231287/
- S10 Avnet PB（12V wall adapter）：https://www.avnet.com/opasdata/d120001/medias/docus/139/PB-AES-Z7-JESD3-G-v4a.pdf

## 关键结论（对应迁移计划条目）

### VADJ（计划 R2，已关闭）
- Table 1-3 注1："The ZC706 evaluation board is shipped with VADJ set to 2.5V."
- VADJ_FPGA(2.5V) 供 PL bank9-13：bank10=FMC_LPC/PL_JTAG/GPIO、bank11=FMC_HPC/GPIO_LED/HDMI、bank12/13=FMC/HDMI、bank9=PMOD/SMA 等。
- bank0=VCC3V3_FPGA；**bank33/34/35=VCC1V5_PL 1.5V 固定**（时钟 H9/G9=bank34、G2=bank33、A17/K15=bank35 与之一致）。
- 无电压选择跳线：档位(1.8/2.5/3.3V)只能 PMBus 写 TI UCD90120A(U48)；J18(FMC_VADJ_ON_B) 仅决定上电使能，**默认 1-2 安装**。
- **纯 PL 设计无需 PS**：Table 1-38 时序"Turn on at board power-on"——J18 默认装时 UCD90120A 硬件时序器上电自动拉起 VADJ 2.5V。
- FMC LPC LA02 = AE12/AF12 LVCMOS25 在默认 VADJ 下合法（UG954 Table 1-33 原文即标 LVCMOS25）。

### JTAG/编程（计划 R4，已关闭）
- 板载 Digilent USB-JTAG 模块 U30，面板 Micro-B「JTAG」口；线缆 Standard-A↔Micro-B；驱动随 Vivado（Digilent/FTDI cable drivers）。
- **SW4（2 位）选择 JTAG 源：01=板载 USB(U30)；10=J3 14pin 排针（出厂默认！）；11=J62 20pin**。USB 编程必改 SW4=01。
- SW11（5 位，PS boot，MIO[6:2]）：**00000=JTAG=出厂默认**，无需动。
- 双板一 PC：Vivado 同一 hw_server 枚举两个 target 逐个编程（AMD 论坛 S4 + 标准行为，置信中高）。
- FMC 卡会经 U31/U32 自动串入 JTAG 链：卡内需 TDI-TDO 旁路，否则 SoC 无法编程（p.35）。

### 电源（Phase 5 自检项）
- J22 = 6-pin Mini-Fit（MOLEX-39-30-1060）12V 输入；SW1 滑动开关；DS22=12V 在位。
- **严禁 ATX 6-pin 插 J22**（引脚不同，损坏+失保，UG954 p.65 CAUTION）；套件含 12V 适配器（AR#67507：12V/5A，PN 6003-300-000，置信中）+ ATX 4-pin 转接缆 PN 2600304。
- 时序（UCD90120A 硬件）：VCCINT(1.0)→VCCAUX(1.8)→VCC3V3_FPGA→VCC1V5_PL→VADJ_FPGA(2.5)，各 5ms。J66 PL_PWR_ON 保持 OPEN。
- 电源 LED：DS24=CTRL1_PWRGOOD、DS11=VCCINT、DS13=VCC1V5_PL、**DS15=VADJ**、DS16=VCC3V3、DS22=12V、DS23=FMC PG、DS1=POR(红)。

### DIP/按键/LED（计划 §0.5）
- **SW12 = 4 位用户拨码**（SW13 是 CPU 复位按键，勿混）：pin1..4 → GPIO_DIP_SW0..3 = AB17/AC16/AC17/AJ13；**ON=1（接 VADJ）/OFF=0（4.7k 下拉 R68-71）**；出厂全 OFF；直连 PL。
- 按键 Table 1-29：AK25=GPIO_SW_LEFT(SW7, LVCMOS25)、K15=GPIO_SW_CENTER(SW9, LVCMOS15)、R27=GPIO_SW_RIGHT(SW8, LVCMOS25)、A8=PL_CPU_RESET(SW13, LVCMOS15)。**空闲=1（上拉）/按下=0**；无板上 RC 去抖（RTL 消抖）；SW10=PROG_B 清配置。
- LED Table 1-28：Y21=GPIO_LED_LEFT=**DS8**、G2=CENTER=**DS9**、W21=RIGHT=**DS10**、A17=GPIO_LED_0=**DS35**；高电平点亮（VCC3V3→261Ω→LED→NDS331，图 1-26）；DONE=DS3、INIT=DS2。
- ⚠ UG954 内部矛盾：Table 1-28 把 4 颗 LED 全标 LVCMOS25，正文又称跨 bank 11/33/35。**以板卡文件 part0_pins.xml + 封装 bank 数据为准：G2/A17=LVCMOS15**（Vivado DRC 最终裁决）。

### USB-UART / FMC（Phase 7）
- USB-UART = 独立 Mini-B 口 J21（CP2103GM, U52），只连 PS Bank 501(MIO)——**PL 不可用**；需 SiLabs VCP 驱动（本项目不用）。
- FMC HPC=J37（400pin）/ **LPC=J5（160pin 部分贴装，Samtec SEAF）**；LPC 提供 68 单端/34 差分 + 1 GTX；LA02_P/N=H7/H8 针位=AE12/AF12。
- FMC VADJ 无保险丝/跳线，唯一控制=J18 使能（默认装）；HPC/LPC 共用 VADJ_FPGA。

### 纯 PL（无 FSBL）bring-up 陷阱清单
1. VADJ 上电即起（J18 默认）——无需 PS 启动 ✅（本项目关键前提）。
2. SW4 出厂 10 → 必改 01，否则 "No devices found"。
3. SW11 默认 00000 已是 JTAG。
4. FMC 卡无 TDI-TDO 旁路会断 JTAG 链。
5. DONE 不亮：查 DS2(INIT 红=配置中)、SW10 误按、J66 误动。
6. UART PL 侧只能走 FMC/PMOD（J58 PMOD1 经 TXS0108E 电平移位 3.3↔VADJ——备选 UART 引出方案）。
7. 按键空闲=1（与 w3_top 上升沿触发组合=松开启动，见计划 Phase 1 决策）。
8. ATX 6-pin 禁插 J22。
9. 若将来改 VADJ=1.8V：FMC 约束须换 LVCMOS18 且 bank11 LED 超标——本项目保持 2.5V 默认。

## 置信度与缺口
- 高：全部 S1 直接引用（表号/页码）。
- 中高（图 1-26/27/28 电路推断）：DIP ON=1/OFF=0、按键空闲 1/按下 0、LED 高有效。
- 中（论坛/摘要）：双板编程(S4)、适配器 12V/5A PN(S5)、JTAG-SMT2 型号(S2)。
- 缺口：适配器确切安时数未从官方表核实；AMD/TI 论坛帖全文未读；UG954 LED 表自相矛盾处以上游板卡文件裁决。
