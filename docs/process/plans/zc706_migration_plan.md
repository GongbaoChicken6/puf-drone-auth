# ZC706 板卡迁移执行计划（w3_top · 双 ZC706 终端编队）· 审查修订版 R2

> 生成：2026-10-19（make-plan）· **R2 修订：2026-10-19 auto-review 三视角交叉审查后**
> （amd-ross 官方文档校对 / plan-reviewer 一致性 / hw-ops 板级运维；P0×1+P1×2+P2×7+P3×7 全部修复）。
> 依据：docs/HANDOFF_SUMMARY.md「板卡迁移交接记录」+ build/reviews/handoff_check/FINAL_SUMMARY.md
> + UG954 v1.8 全文（缓存 D:\文件\ssssssss\FPGA\ug954_text.txt）+ 本机 Vivado 2026.1 DRC 实测。
> 截止：**2026-11-04 18:00**。W5 冻结最迟 10-27 启动 → 硬件 bring-up 窗口 ~8 天。

## 0. 基线状态（启动前必须全真，已核验 ✅）

| 项 | 状态 | 证据 |
|---|---|---|
| 工作区干净 | ✅ 2026-10-19 | HEAD=`9ab052a`；凭据脚本 cred*.ps1 已 gitignore（在磁盘未入库） |
| CI 全绿基线 | ✅ 2026-10-19 | `scripts/ci_regression.ps1` → **16/16 TB PASS** + Python 门禁全过，exit 0 |
| 参考模板 | ✅ | w3_top_zc702.v（57 行）+ w3_top.xdc（底稿）+ build_w3_board.tcl |
| W4 状态 | ✅ 已收官 | d8d44c5：P0–P5 完成（PUF 已入 w3_top、T1/T2 已实现、P1-5 已修）。HANDOFF **Step 9**（板上 enrollment）≠ 从零接入——但审查发现需先补 RTL 注册支持（见 Phase 8a，P0 级发现） |
| ZC706 板卡文件 | ✅ | D:\vivado\2026.1\data\xhub\...\zc706\1.5\（part0_pins.xml/board.xml/new.ucf/preset.xml） |

**执行约定**：每 Phase 单独提交；CI 保持 16/16 绿；证据入 build/reviews/zc706_bringup/。

## 0.5 已冻结事实卡（引脚 × Bank × 电平；三方核验：UG954 + 板卡文件 + IBIS pkg，XDC 已过本机 Vivado 2026.1 synth/opt/place 初版实测 0 错 0 警 WNS=3.724）

| 信号 | wrapper 端口 | 引脚 | Bank/轨 | IOSTANDARD | 丝印/组件 |
|---|---|---|---|---|---|
| 差分时钟 200MHz | clk_p / clk_n | **H9 / G9** | **34 = VCC1V5_PL 1.5V 固定** | **DIFF_SSTL15** | sys_diff_clock（SiT9102，MRCC 脚） |
| 复位(低有效) | sys_rst_btn_n | **A8** | 34 | **LVCMOS15** | **SW13** PL_CPU_RESET（PUDC_B 复用脚，普通输入 OK，实测 place 过） |
| 认证按键 | auth_btn | **AK25** | 11 (VADJ) | LVCMOS25 | **SW7** GPIO_SW_LEFT（空闲1/按下0） |
| DIP bit0..3 | term_id_dip[3:0] | **AB17/AC16/AC17/AJ13** | 10 (VADJ) | LVCMOS25 | **SW12** pin1..4；**ON=1/OFF=0**（4.7k 下拉，出厂全 OFF） |
| UART 发 | radio_txd | **AJ21** | 11 (VADJ) | LVCMOS25 | **PMOD1_0 = J58 pin1**（经 TXS0108E 移位） |
| UART 收 | radio_rxd | **AB21** | 11 (VADJ) | LVCMOS25 | **PMOD1_2 = J58 pin5**（经 TXS0108E 移位） |
| LED 结果0 | led_result[0] | **Y21** | 11 (VADJ) | LVCMOS25 | **DS8** GPIO_LED_LEFT（亮——结果码放亮灯） |
| LED 结果1 | led_result[1] | **W21** | 11 (VADJ) | LVCMOS25 | **DS10** GPIO_LED_RIGHT（亮） |
| LED 认证中 | led_busy | **G2** | 33 = 1.5V 固定 | **LVCMOS15!** | **DS9** GPIO_LED_CENTER（偏暗可接受） |
| LED 心跳 | led_heartbeat | **A17** | 35 = 1.5V 固定 | **LVCMOS15!** | **DS35** GPIO_LED_0（偏暗可接受） |

- ⚠ **J57/J58 勿插错（Round-2）**：UG954 器件清单把 J57 标 "PMOD1"、J58 标 "PMOD2"，但**信号名 PMOD1_[0:7] 在 J58**（Table 1-31 电气权威）——UART 用 **J58**（直连 FPGA+TXS0108E）；**J57 走 TCA6416 I2C 扩展器，PL UART 不可用**。
- **UART 走 PMOD1(J58) 而非 FMC**（审查决策，替代交接摘要的 AE12/AF12 方案）：J58 是 2×6 标准 0.1" 排针——杜邦线直插**零采购**；板上 TI TXS0108E(U40) 自动完成 3.3V↔VADJ(2.5V) 电平移位——**无需分压电阻**；且不碰 FMC ⇒ 无 JTAG 链串入风险。FMC LPC LA02（AE12/AF12，bank10 LVCMOS25）降级为注释备选（若用需转接板+1k/2.2k 分压+JTAG 旁路确认）。AJ21/AB21 分属两个独立差分对（L3P/L19P），避免同对单端疑虑。
- **LED 重映射依据（amd-ross P2）**：所有用户 LED = VCC3V3→261Ω→LED→NDS331 NMOS→GND，栅极接 GPIO。NDS331 VGS(th)=0.5/0.7/1.0V，RDS(on) 仅在 VGS=2.7V 规格化 ⇒ **1.5V bank 驱动（DS9/DS35）偏暗且非手册保证**，2.5V bank（DS8/DS10）正常亮。故**承载判定显示的 2bit 结果码放 DS8/DS10（亮）**，busy/心跳放暗位（可见即可）。bring-up 第一步目检 DS9/DS35 可见性；不可见则 XDC 换灯重综合（~10min）。
- **时钟口径注记（amd-ross P3）**：AMD 一手材料三处不一——new.ucf=DIFF_SSTL15、part0_pins.xml=LVDS、UG954 Table 1-13=LVDS。本机 Vivado 2026.1 实测：DIFF_SSTL15 与 LVDS 在 bank34 **均过 DRC**；LVDS_25 → ERROR BIVB-1（HP bank 不支持，**ZC702 禁抄实锤**）；LVDS_15 → Invalid I/O Standard（7 系无此标准）。取 DIFF_SSTL15（与 AMD 自家 MIG 约束一致）。**不要**向 part0_pins.xml 的"LVDS"字面回改。
- ⚠ **共 4 颗 LVCMOS15**（G2/A17/K15/A8）：写成 25 → 实测 ERROR BIVB-1。**电源轨（UG954 Table 1-3）：bank9-13=VADJ 出厂 2.5V（J18 默认装+UCD90120A 硬件时序器上电自动拉起，**纯 PL 无需 PS 启动**）；bank33/34/35=VCC1V5_PL 1.5V 固定**。UG954 Table 1-28 全标 LVCMOS25 系官方自身错误（与其 Table 1-3/1-29 矛盾），以板卡文件+DRC 为准。
- term_id 通路（w3_top.v:44,190）：`term_id_sw[7:0]` 原样喂 `terminal_id` 无取反；SW12 ON=1 ⇒ ID1=**0001**、ID2=**0010**。
- clk_wiz_0 零改动：zc706 preset.xml（200MHz 差分→100MHz）与 build_w3_board.tcl 参数完全匹配（amd-ross 核）。

---

## Phase 1 · 创建 w3_top_zc706.v（纯软件）

**做什么**：COPY w3_top_zc702.v → w3_top_zc706.v，**7 处改动**（比初版多 3 处——审查 P2：模板行内注释残留 ZC702 专属内容）：
1. 模块名 → `w3_top_zc706`（含头注释标题）。
2. `input wire [1:0] term_id_dip` → `[3:0]`，行尾注释改「SW12 pin1..4，ON=1」。
3. `.term_id_sw({6'h00, term_id_dip})` → `{4'h00, ...}`，注释改「高 4 位 tie 0（SW12 有 4 位）」。
4. clk_p 行注释：D18/LVDS_25 → 「H9, 200MHz 差分 (DIFF_SSTL15)」；clk_n 行同理 C19→G9。
5. sys_rst_btn_n 行注释：GPIO_SW_N → 「SW13 PL_CPU_RESET（低有效）」。
6. 头注释整体重写：贴 0.5 节引脚表 + 「4 颗 LVCMOS15」+「时钟 bank34=1.5V 用 DIFF_SSTL15」+「UART 走 PMOD1(J58)」+「ENROLL_EN=1（见 Phase 8a）」。
7. **w3_top 例化加参数 `.ENROLL_EN(1)`**（Phase 8a 的 RTL 注册支持，见下）。

**auth_btn 极性**（审查确认项）：按键空闲=1/按下=0，w3_top.v:121 上升沿触发 ⇒ 语义=「按下并**松开**后启动」。默认直通（与模板一致），教程叙述写「按一下并松开」。
**其余一律不动**：clk_wiz_0 实例、`rst_n = sys_rst_btn_n & mmcm_locked`、BAUD/TIMEOUT_S。w3_top.v **端口**不改（参数新增见 8a，向后兼容）。
**验证清单**：`grep -nE "zc702|D18|C19|LVDS_25|GPIO_SW_N|W6|W7|6'h00" w3_top_zc706.v` **零命中**（初版只查 zc702，抓不到注释残留——审查 P2 修正）；Phase 4 xvlog/xelab 过。
**反模式**：❌ 改 w3_top 端口/顺手优化；❌ wrapper 进 CI 清单。
**提交**：`feat(board): add w3_top_zc706 wrapper (PMOD UART, 4-bit DIP, ENROLL_EN=1)`

## Phase 2 · 创建 w3_top_zc706.xdc

**做什么**：整块照抄（初版已过 Vivado 2026.1 实测；本版改了 UART/LED 行——仍在已验证 bank 内，Phase 5 复跑 DRC 即终验）：

```tcl
# w3_top_zc706.xdc -- ZC706 (xc7z045ffg900-2)。顶层 = w3_top_zc706。禁抄 ZC702 任何引脚。
# 时钟：bank34=VCC1V5_PL 1.5V；LVDS_25 实测 BIVB-1 ERROR；取 AMD new.ucf 原生 DIFF_SSTL15。
set_property -dict {PACKAGE_PIN H9 IOSTANDARD DIFF_SSTL15} [get_ports clk_p]
set_property -dict {PACKAGE_PIN G9 IOSTANDARD DIFF_SSTL15} [get_ports clk_n]
create_clock -period 5.000 -name sys_clk_p [get_ports clk_p]

# 异步 I/O false_path
set_false_path -from [get_ports sys_rst_btn_n]
set_false_path -from [get_ports auth_btn]
set_false_path -from [get_ports {term_id_dip[*]}]
set_false_path -to [get_ports led_*]

# RESET：SW13（A8，bank34，LVCMOS15！低有效）
set_property -dict {PACKAGE_PIN A8 IOSTANDARD LVCMOS15} [get_ports sys_rst_btn_n]
# AUTH：SW7（AK25，bank11，空闲1/按下0）
set_property -dict {PACKAGE_PIN AK25 IOSTANDARD LVCMOS25} [get_ports auth_btn]

# UART：PMOD1(J58) 经 TXS0108E 3.3V<->2.5V 移位——3.3V USB-TTL 直插，无需分压
set_property -dict {PACKAGE_PIN AJ21 IOSTANDARD LVCMOS25} [get_ports radio_txd]  ;# PMOD1_0=J58.1
set_property -dict {PACKAGE_PIN AB21 IOSTANDARD LVCMOS25} [get_ports radio_rxd]  ;# PMOD1_2=J58.5
# 备选（FMC LPC LA02，需转接板+rxd 1k/2.2k 分压+JTAG 旁路确认）：
# set_property -dict {PACKAGE_PIN AE12 IOSTANDARD LVCMOS25} [get_ports radio_txd]
# set_property -dict {PACKAGE_PIN AF12 IOSTANDARD LVCMOS25} [get_ports radio_rxd]

# LED：结果码=亮灯（DS8/DS10, bank11 2.5V）；busy/心跳=暗位（1.5V bank，NDS331 裕量）
set_property -dict {PACKAGE_PIN Y21 IOSTANDARD LVCMOS25} [get_ports {led_result[0]}]  ;# DS8 亮
set_property -dict {PACKAGE_PIN W21 IOSTANDARD LVCMOS25} [get_ports {led_result[1]}]  ;# DS10 亮
set_property -dict {PACKAGE_PIN G2  IOSTANDARD LVCMOS15} [get_ports led_busy]        ;# DS9 偏暗
set_property -dict {PACKAGE_PIN A17 IOSTANDARD LVCMOS15} [get_ports led_heartbeat]   ;# DS35 偏暗

# DIP SW12（ON=1，板上 4.7k 下拉；ID1=0001、ID2=0010）
set_property -dict {PACKAGE_PIN AB17 IOSTANDARD LVCMOS25} [get_ports {term_id_dip[0]}]
set_property -dict {PACKAGE_PIN AC16 IOSTANDARD LVCMOS25} [get_ports {term_id_dip[1]}]
set_property -dict {PACKAGE_PIN AC17 IOSTANDARD LVCMOS25} [get_ports {term_id_dip[2]}]
set_property -dict {PACKAGE_PIN AJ13 IOSTANDARD LVCMOS25} [get_ports {term_id_dip[3]}]
```

**注意**：w2_waiver.xdc（LUTLP-1）由 build_w3_board.tcl 单独加载，不得丢失。
**验证清单**：Phase 5 DRC 无 NSTD-1/UCIO-1/BIVB-1；LED/UART 行已改，若 DRC 报错按 0.5 节表核对。
**反模式**：❌ ZC702 引脚；❌ clk 用 LVDS_25（实测 BIVB-1）；❌ G2/A17/K15/A8 写 25（实测 BIVB-1）；❌ 向 part0_pins.xml 的"LVDS"字面回改时钟。
**提交**：`feat(board): zc706 constraints (PMOD UART, bright result LEDs, bank-aware)`

## Phase 3 · 更新 build_w3_board.tcl

4 处替换（审查核实穷尽，共 5 处 zc702 字样全覆盖）：zc702.v→zc706.v、w3_top.xdc→w3_top_zc706.xdc、top×2、bit 名；头注释改 ZC706。**不动**：part 传参、15 文件清单（含 ro_entropy.v）、w2_waiver 行、clk_wiz 配置。
**验证**：`grep -n zc702 build/tcl/build_w3_board.tcl` 零命中。
**提交**：`build(tcl): retarget to xc7z045ffg900-2 / w3_top_zc706`

## Phase 4 · 离板验证 xvlog + xelab

1. %TEMP%\clk_wiz_0_stub.v（不入 src/）：
```verilog
module clk_wiz_0 (input wire clk_in1_p, input wire clk_in1_n, input wire reset,
                  output wire clk_out1, output wire locked);
  assign clk_out1 = clk_in1_p;
  assign locked   = ~reset;
endmodule
```
2. 编译（**不带** `-d PUF_MODEL_SIM`——走真 ro_array 板级网表；组合环仅 WARNING）：
```powershell
cd D:\puf-drone-auth
$vw = 'D:\vivado\2026.1\Vivado\bin'
& "$vw\xvlog.bat" src\rtl\w1_ratio\ro_ring.v src\rtl\w1_ratio\ro_div.v `
  src\rtl\w2_array\ro_array.v src\rtl\w2_array\challenge_decode.v src\rtl\w2_array\ro_entropy.v `
  src\rtl\common\crc16_mcrf4xx.v src\rtl\common\mavlink_frame.v src\rtl\common\frame_parser.v `
  src\rtl\common\byte_fifo.v src\rtl\common\uart_tx.v src\rtl\common\uart_rx.v `
  src\rtl\common\speck64_96.v src\rtl\w3_protocol\terminal_fsm.v src\rtl\w3_protocol\w3_top.v `
  src\rtl\w3_protocol\w3_top_zc706.v $env:TEMP\clk_wiz_0_stub.v
& "$vw\xelab.bat" -debug typical w3_top_zc706 -s w3_zc706_chk
```
（审查核实：无需 w2_top.v——w3_top 不例化它；清单与 build_w3_board.tcl 一致。）
3. 交付：build/ps1/verify_wrapper.ps1 脚本化入库（CI 不接入）。
**验证**：xvlog/xelab exit 0，无 ERROR。
**提交**：`build(ps1): verify_wrapper.ps1 gate`

## Phase 5 · 比特流 + 双板烧写

1. 生成：`vivado -mode batch -source build\tcl\build_w3_board.tcl -tclargs xc7z045ffg900-2 build\board_zc706 .` → `BITSTREAM_SUCCESS`；核对 utilization/timing（基线 4190 LUT/7.88%@ZC702；ZC706 ~2% 正常）。**rpt 归档**：utilization.rpt/timing.rpt 拷入 build/reviews/zc706_bringup/ 后提交，`build/board_zc706/` 加 .gitignore（审查 P3：rpt 无忽略规则会污染 status）。
2. DRC 记录：LUTLP-1/NSTD-1/UCIO-1 → 回 Phase 2/3 修。
3. 烧写脚本 build/tcl/program_zc706.tcl（COPY measure_w1.tcl 骨架去 VIO 段；**审查 P2 加固**——空参检查/多 target 防御/PART 校验）：
```tcl
# 用法: vivado -mode batch -source program_zc706.tcl -tclargs <bit> [hw_target_serial]
set BIT [lindex $argv 0]
set SN  [lindex $argv 1]
if {$BIT eq ""} { puts "ERROR: 用法 program_zc706.tcl <bit> [serial]"; exit 2 }
open_hw_manager
connect_hw_server -url localhost:3121
set ts [get_hw_targets -quiet]
if {[llength $ts] == 0} { puts "ERROR: 未找到 JTAG 目标（电源/USB/驱动/SW4=01?）"; exit 3 }
if {$SN ne ""} { set ts [lsearch -all -inline -glob $ts */$SN/*] }
if {[llength $ts] == 0} { puts "ERROR: 序列号 $SN 无匹配 target"; exit 4 }
if {[llength $ts] > 1} { puts "ERROR: 多个 target（传序列号二选一）: $ts"; exit 5 }
open_hw_target [lindex $ts 0]
set dev [lindex [get_hw_devices] 0]
if {[get_property PART $dev] ne "xc7z045ffg900"} { puts "ERROR: PART 不符: [get_property PART $dev]"; exit 6 }
set_property PROGRAM.FILE $BIT $dev
program_hw_devices $dev
refresh_hw_device $dev
close_hw_target
disconnect_hw_server
puts "PROGRAM_OK"
```
线缆：Standard-A↔Micro-B 插面板「JTAG」口（板载 Digilent 模块 U30；Vivado 自带驱动；"JTAG-SMT2" 系第三方口径，UG954 原文只写 Digilent module——审查 P3）。两板同 PC：逐块上电烧最稳；同接时按序列号传参。
4. 板级自检（UG954 实证）：J22=6pin Mini-Fit 12V（套件含 universal 12V 适配器；AR#67507 称 12V/5A PN 6003-300-000——**中置信，UG954 无此 PN**，以适配器标签为准）；**严禁 ATX 6 针**（引脚不同烧板失保）；SW1→On，DS22=12V；DS24=PWRGOOD、DS15=VADJ；**SW4 拨 01**（出厂 10=J3，USB 不通头号原因）；SW11 出厂 00000=JTAG；J18 默认装、J66 OPEN、SW10 勿误按；DONE=DS3、INIT=DS2（红=配置中）。
**验证**：BITSTREAM_SUCCESS；WNS≥0；**DS3 亮 + 心跳 DS35 ~0.75Hz 闪**（DS35 偏暗——第一眼看不到先凑近/遮光看，真不可见才换灯重综合）；排障序 DS15→DS24→DS3→J18/SW4/SW11→SW10。
**反模式**：❌ 两板盲烧（无 SN）；❌ 动 w2_waiver 之外豁免。
**提交**：`build(tcl): program_zc706.tcl (hardened) + bringup evidence`

## Phase 6 · 拨码 ID + 按键/LED 行为验证

SW12（ON=1）：板 A=**0001**、板 B=**0010**。功能自证：发起一次认证，PC 日志读 ACCESS_REQUEST 的 terminal_id = 期望值。auth_btn=SW7「按一下并松开」触发；led_busy(DS9，偏暗) 亮 → **DS8/DS10 给结果码**（01=通过）。拍照留证。
**验证**：terminal_id 回读=1/2；两板一致；心跳正常。
**提交**：`docs(evidence): zc706 dip/led bringup records`

## Phase 7 · 双 COM 串口联调（PC = 基站）

**硬件（PMOD 路径，零分压零转接）**：每板 3 根杜邦线：J58 **pin1(PMOD1_0/AJ21, txd)→USB-TTL RX**、**pin5(PMOD1_2/AB21, rxd)←USB-TTL TX**、**pin11 或 12(GND)↔GND**（GND 脚号系 Figure 1-29 残片弱证据——接线前万用表通断对板 GND 确认）；USB-TTL 用 3.3V 逻辑（**接线前万用表测 TX 空闲电平=3.3V**——市售 CH340 模块常 5V/跳线，5V 会经 TXS0108E 直怼 2.5V 侧）。适配器 VCC 不接。**自环预检**（验证 TXS0108E OE 拉带）：杜邦短接 J58 pin1↔pin5，PC 侧串口助手发字节看回显。
**软件**：`pip install pyserial`。
**正确顺序（审查 P1/P2 修正版）**：
```
:: ① 串行配置期（单实例，严禁双实例并发写库）
python -m src.python.server.main --port COM3 --baud 115200
puf-server> setkey 1 0001020308090a0b10111213
puf-server> status
puf-server> quit
# ⚠ 密钥是字节反序的：RTL 96'h13121110_0b0a0908_03020100 的 Python 等效 = 0001020308090a0b10111213（main.py:681 实证）。写成 131211100b0a090803020100 会恒 BLOCKED。
（换 COM4 重复：setkey 2 0001020308090a0b10111213）
:: ② 并发 serve 期（分目录，规避 device_keys.json mtime 互斥）
robocopy data\device_keys data\stB\device_keys /E   （概念示意：为实例B 备份独立密钥库）
python -m src.python.server.main --port COM3 --device-keys data\device_keys\device_keys.json
python -m src.python.server.main --port COM4 --device-keys data\stB\device_keys\device_keys.json
```
**R9 说明（审查精化）**：serve **不是只读**（每 ACCESS_REQUEST 更新 C2 窗并持久化池）；池文件按 tid 分文件不互踩；device_keys.json 整文件+mtime 检测 ⇒ 共库时后退出者**必然** [ERROR]（external-change）且其 C2 窗不落盘——分目录即规避。REPL 会在 CWD 写 audit.log（main.py:715）——已被 .gitignore 的 `*.log` 规则覆盖（实测 git check-ignore 命中 .gitignore:8），无需额外动作；注意 audit.log 含密钥操作记录，不离实验室机。
**验收（审查 P1 修正：黄金值法作废，改闭环法）**：⚠ W4-T2 后真板上电 C2=ro_entropy 随机种子 ⇒ 首次 R2 **不再是** 7b45b0545e59aa94（该黄金值只在 TB tie 常量语义成立，CI 已锚定）。板上验收=①serve 日志读 ACCESS_REQUEST 的实际 C2 → 站端用已装密钥算 R2 → 终端 **PASS+CONFIRM_OK**（键/C2/RTL 三方一致的功能证明）；②断电重启终端 → 首帧 C2 与上次不同、旧 RESULT 重放被拒（P1-5 板级实证）。
**反模式**：❌ setkey 用 131211100b0a090803020100（字节序反，恒 BLOCKED 且像硬件故障）；❌ 波特率非 115200；❌ 不共地。
**提交**：`feat(server): dual-COM bring-up (split key stores, PMOD wiring) + evidence`

## Phase 8a · 【新增，P0 修复】RTL 注册支持（纯软件，今天与 Phase 1-4 同批做）

**问题（hw-ops P0，已亲自复核）**：terminal_fsm 的 0x0091 只在 S_WAIT_CHALL 处理（terminal_fsm.v:449），该态只能由按键进入；S_IDLE 无 RX 分支（:376-391）、S_WAIT_RESULT 只认 0x0093/0x0095（:573-578）⇒ `enroll` 的 75 次背靠背 CHALLENGE→R1 交换在真板上**必然 3s 超时→release 回滚**，注册不可能完成（W3 以来该流程只有测试替身 WireTerminal 走通过）。
**修复设计（CI 安全）**：
1. terminal_fsm.v 新参数 `parameter ENROLL_IDLE_ACCEPT = 0`；在 **S_IDLE** 与 **S_WAIT_RESULT** 各加一个受控分支：`if (rx_ok_latch && fp_msg_id==24'h0091 && fp_pay_len==8'd32 && ENROLL_IDLE_ACCEPT)` → 复用 S_WAIT_CHALL 的接受体（fp_rd_addr=0、puf_extra=0、puf_seed_idx=0、puf_dec_busy=0 → S_PUF_DECODE）。S_WAIT_RESULT 内 0x0093/0x0095 判定**保持在前**（认证语义不变）。
2. w3_top.v 新参数 `parameter ENROLL_EN = 0` 透传给 terminal_fsm 例化（.ENROLL_IDLE_ACCEPT(ENROLL_EN)）——**只加参数不动端口**，tb_w3_top 零影响。
3. w3_top_zc706.v 例化 `.ENROLL_EN(1)`（Phase 1 改动 #7）。默认 0 ⇒ CI 16/ TB 语义不变。
4. tb_terminal_fsm.v 加参数=1 用例：a) S_IDLE 收 0x0091 直接纳（无按键）→R1→再收 0x0091（S_WAIT_RESULT 内）→ 再 R1（背靠背两轮）；b) 参数=0 时 S_IDLE 收 0x0091 忽略（回归锁）。CI 清单不变（tb_terminal_fsm 已在）。
   **实现注记（Round-2）**：S_IDLE 不在 rx_ok_latch 保持列表（terminal_fsm.v:316）——锁存块在非等待态每拍清零，新增 0x0091 分支是 **1 拍采样窗口**，同沿 NBA 语义下功能成立；实现时**勿"顺手整理"锁存块**；TB 直接用既有 feed_frame 任务（tb_terminal_fsm.v:157）打 fp_frame_ok 脉冲。
5. **门禁：全量 CI 复跑 16/16 + Python 全绿才许提交。**
6. 安全注记：使能位=站方可主动发起 PUF 查询（注册语义本就如此，物理近邻假设）；W5 报告如实声明。
7. **S_SESSION 盲区（Round-2）**：认证 PASS 后 FSM 驻留 S_SESSION（仅 auth_start 离开、无超时），该态忽略 0x0091——**每次 enroll 前先按 SW13 复位终端**。首次注册无模板→REJECT→S_BLOCKED→S_IDLE 自愈不受影响；但 Phase 8 步骤 1 的自证认证若已 PASS（再注册场景），终端会停在 S_SESSION 使 enroll 停滞退种。
**备案 Plan B**（不动 RTL）：站端改逐轮全认证流采集（每轮 4 CRP、每轮一次按键，25 轮×3 测量=75 次按键+新采集驱动代码）——仅当 8a 补丁出意外时用。
**工作量**：RTL+TB+CI ≈ 3~5h（含重综合 ~10min）。
**提交**：`feat(rtl): ENROLL_IDLE_ACCEPT -- station-driven enrollment (param-gated, CI-neutral)`

## Phase 8 · PUF 板上注册（W4 收官；前置=Phase 8a 已合并）

**做什么**（顺序勿颠倒）：
1. **接线前自证**：COM↔板映射贴标签；先发起一次认证确认 ACCESS_REQUEST 的 terminal_id 与所插板一致（REPL enroll 不校验线序，防模板-tid 错配——审查 P3）。
2. 板 A（单实例串行）：`enroll 1 100`（100 CRP×3 测量 majority；reserve→逐批→模板，中断自动回滚）。池语义：代码默认 500（crp_pool.py:36；SOP 文本写 100 已过时，顺手修）；每认证耗 4+灰区 3；失败/停滞 30s 退种。**总线耗时分钟级**（审查 P2：原"8~12h/板"无依据已删——真实成本是 8a 的 RTL 工作）。
3. 阈值复核：threshold.decide_scaled 灰区宽度 + hamming_analysis 跨板区分度过一遍。
4. 板 B 重复（换口 `enroll 2 100`）。
5. **交叉验证（演示卖点，操作要写明）**：把板 B 的 SW12 拨成板 A 的 ID（0001）→ 发起认证 → 必 REJECT（板 A 模板对板 B 的 PUF）→ **拨回 0010**。
6. 断电重启重放测试：录一次 RESULT 帧 → 终端断电重启 → 重放 → 被拒（P1-5 板级实证）。**验后恢复**：REPL `c2reset <tid>`（不清窗会把后续正常认证误判 RESULT_REPLAY——审查 P3）。
7. T1 使能（ENABLE_KEY_DERIVE=1）：**板上必败**——站端读不到真设备 PUF 频率，KEY_SEED 0x0096 通道未实现（enroll.py:108-112 诚实边界）⇒ 标注"仅仿真语义，不投板时"（审查 P3）。
**验证**：两板各自首认证 PASS；交叉 REJECT；重放被拒+c2reset 恢复；池/模板按 SOP 归档（data/ 已 gitignore）。
**反模式**：❌ 用 --loopback 语义模板认证真板（恒 REJECT）；❌ 未过 8a 就上板 enroll；❌ 密钥/模板误提交。
**提交**：`feat(w4): on-board enrollment x2 + cross-reject + replay evidence`

## Phase 9 · E2E 收官 + 文档冻结（对接 W5）

**做什么**：双终端编队演示走通（ACCESS→CHALLENGE→R2→RESULT→CONFIRM×2 板并发）；CI 全绿复跑；**文档更新全清单（审查 P3 补全，grep 实测计数）**：w1_tutorial.md(11 处)、architecture.html(7)、README.md(1)、project_design.md(4)、project_status.html(4)、process/handoff_summary.md(4)、mindmap.html(3)、project_flow.html(3)、DIRECTORY_STRUCTURE.md(1)、HANDOFF_SUMMARY 状态节；证据归档 build/reviews/zc706_bringup/；进 W5。
**验证**：CI exit 0；演示 3 连跑；`grep -rn ZC702 docs/ README.md` 逐处人工判（历史叙述保留）。
**提交**：`docs: zc706 migration complete -- freeze`

---

## 风险登记表（R2 修订）

| # | 风险 | 影响 | 缓解 | 状态 |
|---|---|---|---|---|
| R1 | 时钟 IOSTANDARD | DRC 失败 | ✅ DIFF_SSTL15；**本机实测**：LVDS_25→BIVB-1 ERROR、LVDS_15→Invalid；初版 XDC place 0 错 WNS 3.724 | 已关闭 |
| R2 | VADJ/电轨不明 | bank 电平错 | ✅ UG954 Table 1-3：bank9-13=VADJ 2.5V 出厂（J18+UCD90120A 上电自动，纯 PL 免 PS）；33/34/35=1.5V 固定 | 已关闭 |
| R3 | USB-TTL 电平 | 烧脚/不通 | ✅ PMOD 经 TXS0108E 移位（3.3↔2.5V），免分压；仍须测适配器=3.3V 逻辑（防 5V 模块）；FMC 备选路径才需 1k/2.2k 分压 | 已关闭（PMOD 主路径） |
| R4 | JTAG 口/驱动 | 无法烧写 | ✅ U30 面板 Micro-B；**SW4=01**（出厂 10=J3）；SW11 默认 00000；脚本含 SN 过滤+PART 校验 | 已关闭 |
| R5 | 电台未购 | 无线缺失 | USB-TTL 直连；报告注明 | 已接受 |
| R6 | DIP 极性 | ID 错 | ✅ SW12 ON=1（4.7k 下拉）；terminal_id 回读自证 | 已关闭 |
| R7 | ~~8~12h/板~~ → **真实工作量=Phase 8a RTL 注册补丁** | 挤压排期 | 8a 与 Phase 1-4 同日完成（3~5h）；enroll 本身分钟级 | 已排程（R2 重写） |
| R8 | 第二块板也故障 | 单终端降级 | 上电自检首批；降级=单终端演示（loopback 不可用于跨重启演示——SimulatedTerminal 密钥进程级随机） | 开放 |
| R9 | 双实例共库 | 密钥/窗丢失 | ✅ R2 精化：串行期单实例；并发期分 --device-keys 目录；共库时后退出者必 [ERROR] 属预期（分目录即无） | 已缓解 |
| R10 | JTAG 双 target 混淆 | 烧错板 | ✅ 脚本 SN 过滤+多 target 报错列出序列号+PART 校验 | 已关闭 |
| R11 | FMC 转接板采购 | 阻塞 Phase 7 | ✅ **改走 PMOD1(J58) 零采购**；FMC 降为注释备选 | 已关闭（R2 决策） |
| R12 | NDS331 1.5V 驱动裕量（DS9/DS35 偏暗） | 结果读不出 | ✅ 结果码换 DS8/DS10（2.5V 亮）；busy/心跳留暗位；bring-up 首查+换灯预案 | 已缓解 |
| R13 | TXS0108E OE 拉带未证 | UART 不通 | 现场 J58 pin1↔pin5 自环回显测试；不通则查 U40 供电/OE | 开放（现场关闭） |
| R14 | 8a 补丁破坏 CI | 回归 | 参数默认 0+tb 双向用例+全量 CI 门禁 | 已缓解 |

## 现场核对清单（拿到板子第一分钟；ESD 先行：UG954 Discharge Caution——腕带/防静电垫/先摸放电）

- [ ] ESD 装备就位后再开箱；板卡放防静电垫上操作
- [ ] J22 电源口+套件 12V 适配器（以标签实参为准）；上电 DS22/DS24/DS15 全亮；**ATX 6 针禁插**
- [ ] **SW4 拨 01**；SW11 确认 00000；J18 默认装、J66 OPEN、SW1 On
- [ ] 「JTAG」Micro-B 口 ×2 + Standard-A↔Micro-B 线 ×2；两板序列号登记（A=ID1/B=ID2 贴标签）
- [ ] SW12 ON 方向丝印确认；SW7/SW13/SW10 位号
- [ ] DS8/9/10/35 + DS3/DS2 位号拍照；**首查 DS9/DS35 可见性**（R12）
- [ ] USB-TTL ×2：万用表测 TX 空闲电平=3.3V（5V 模块禁用）；线序丝印核对；COM↔板贴标
- [ ] J58 自环预检（pin1↔pin5 短接，串口助手回显——R13）
- [ ] 若用台式电源替代适配器：12V/限流 2A 起、极性再三确认
- [ ] 拍照规范：IMG_日期_板号_项目（如 20261020_A_SW12.jpg）统一入 build/reviews/zc706_bringup/photos/

## 时间线（R2 修订；R11 已除名，8a 前置）

| 日期 | 内容 |
|---|---|
| 10-19（今天） | Phase 0 ✅ + **Phase 1–4 + 8a**（全部纯软件：wrapper/XDC/TCL/xvlog/ENROLL RTL+TB+CI） |
| 10-20~21 | Phase 5–6（自检→比特流→烧写→拨码；**含 8a 后的首个比特流**） |
| 10-21~22 | Phase 7（双 COM 联调 + 闭环验收 + 重放实证） |
| 10-22~25 | Phase 8（两板 enrollment 分钟级 + 阈值复核 + 交叉验证；留足缓冲） |
| 10-25~27 | Phase 9 收官 → W5 冻结（报告/视频） |
| 11-03 | 全量彩排 |
