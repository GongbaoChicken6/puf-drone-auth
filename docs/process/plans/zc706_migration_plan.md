# ZC706 板卡迁移执行计划（w3_top · 双 ZC706 终端编队）

> 生成：2026-10-19（make-plan 会话）· 依据：docs/HANDOFF_SUMMARY.md「板卡迁移交接记录」+
> build/reviews/handoff_check/FINAL_SUMMARY.md + 本会话全部实证复核。
> 截止：**2026-11-04 18:00**（约 16 天）。W5 冻结周（报告/视频）最迟 10-27 启动 → 硬件 bring-up 窗口只剩 **~8 天**。

## 0. 基线状态（本计划启动前必须全真，已核验 ✅）

| 项 | 状态 | 证据 |
|---|---|---|
| 工作区干净 | ✅ 2026-10-19 | HEAD=`c7ab101`；3 笔提交：e00e7a8(gitignore)/d4b0317(web PhaseC)/c7ab101(msg.txt)。cred*.ps1 等凭据脚本已 gitignore（仍在磁盘，未入库） |
| CI 全绿基线 | ✅ 2026-10-19 | `scripts/ci_regression.ps1` → **16/16 TB PASS**（含 tb_puf_path/tb_key_derive/tb_w3top_keyloop/tb_ro_entropy）+ Python 门禁全过，exit 0 |
| 参考模板 | ✅ | src/rtl/w3_protocol/w3_top_zc702.v（57 行，结构完整）+ w3_top.xdc（全注释底稿）+ build/tcl/build_w3_board.tcl |
| W4 状态 | ✅ 已收官 | 提交 d8d44c5：P0–P5 全部完成（PUF 已集成进 w3_top、T1/T2 密钥派生与上电熵已实现、P1-5 断电重放已修）。**Step 8 只是板上 enrollment，不是从零接入** |
| ZC706 板卡文件 | ✅ | D:\vivado\2026.1\data\xhub\boards\XilinxBoardStore\boards\Xilinx\zc706\1.5\part0_pins.xml（D:\vivado\2026.1\Vivado\data\... 同内容副本） |

**执行约定**：每个 Phase 结束单独一笔提交（信息模板见各 Phase 尾部）；CI 必须保持 16/16 绿（wrapper/TCL 改动不在 CI 清单内，改坏 CI 即事故）；证据 JSON 入 build/reviews/zc706_bringup/。

## 0.5 已冻结事实卡（引脚 × Bank × 电平，全部本机实证）

数据源：part0_pins.xml（板卡官方）+ xc7z045_ffg900.pkg（IBIS 封装，bank 号权威）。

| 信号 | wrapper 端口 | 引脚 | Bank | IOSTANDARD | 板文件组件名 |
|---|---|---|---|---|---|
| 差分时钟 200MHz | clk_p / clk_n | **H9 / G9** | **34 = VCC1V5_PL 1.5V 固定轨** | **DIFF_SSTL15**（AMD 官方 zc706/1.5/new.ucf 对同引脚的原生标准） | sys_diff_clock（SiT9102 200MHz 差分） |
| 复位按键(低有效) | sys_rst_btn_n | **A8** | 34 | **LVCMOS15** | reset（CPU_RESET；A8=IO_L3P_T0_DQS_PUDC_B_34，PUDC_B 复用脚，作普通输入无需特殊处理） |
| 认证按键 | auth_btn | **AK25** | 11 (VADJ) | LVCMOS25 | SW7 GPIO_SW_LEFT（空闲1/按下0；备选 SW8=R27、SW9=K15(b35,LVCMOS15!)） |
| DIP SW12 pin1 | term_id_dip[0] | **AB17** | 10 (VADJ) | LVCMOS25 | GPIO_DIP_SW0；**ON=1/OFF=0**（板上 4.7k 下拉，出厂全 OFF） |
| DIP bit1 | term_id_dip[1] | **AC16** | 10 | LVCMOS25 | _tri_i_1 |
| DIP bit2 | term_id_dip[2] | **AC17** | 10 | LVCMOS25 | _tri_i_2 |
| DIP bit3 | term_id_dip[3] | **AJ13** | 10 | LVCMOS25 | _tri_i_3 |
| UART 发(→USB-TTL RX) | radio_txd | **AE12** | 10 | LVCMOS25 | fmc_lpc_la02_p |
| UART 收(←USB-TTL TX) | radio_rxd | **AF12** | 10 | LVCMOS25 | fmc_lpc_la02_n |
| LED 认证中 | led_busy | **Y21** | 11 (VADJ) | LVCMOS25 | **DS8** GPIO_LED_LEFT（高电平亮） |
| LED 心跳 | led_heartbeat | **A17** | 35 = 1.5V 固定 | **LVCMOS15!** | **DS35** GPIO_LED_0（独立位，常闪不干扰结果读数） |
| LED 结果0 | led_result[0] | **G2** | 33 = 1.5V 固定 | **LVCMOS15!** | **DS9** GPIO_LED_CENTER |
| LED 结果1 | led_result[1] | **W21** | 11 (VADJ) | LVCMOS25 | **DS10** GPIO_LED_RIGHT（DS8/9/10 三连排 = busy + 2bit 结果码） |

- LED 映射决策（UG954 Table 1-28 实证）：busy=Y21(**DS8**)、result[0]=G2(**DS9**)、result[1]=W21(**DS10**)——LEFT/CENTER/RIGHT 三连排正好显示 busy+结果码（01=通过 10=拒绝 11=阻断）；heartbeat=A17(**DS35**) 独立位。全部高电平点亮（NMOS 图腾，图 1-26）。**不要**照搬 ZC702 的 P17/P18/W10/V7。
- ⚠ **共 4 颗 LVCMOS15**（G2/A17/K15/A8）：任何一颗写成 25 都会 DRC 卡死。**电源轨（UG954 Table 1-3）：bank9-13=VADJ_FPGA 出厂 2.5V（J18 默认装，UCD90120A 硬件时序器上电自动拉起，纯 PL 设计无需 PS 启动）；bank33/34/35=VCC1V5_PL 1.5V 固定**。bank34 的 A8 与 H9/G9 同 bank ⇒ 时钟用 DIFF_SSTL15，ZC702 的 LVDS_25 禁抄（R1 已关闭）。注：UG954 Table 1-28 把 4 颗 LED 全标 LVCMOS25 与其正文 bank 描述自相矛盾，以板卡文件+封装 bank 数据为准（G2/A17=LVCMOS15）。
- term_id 数据通路（已核 w3_top.v:44,190）：`term_id_sw[7:0]` 原样喂 `terminal_id`，**RTL 无取反**；SW12 ON=1/OFF=0 ⇒ 直接按二进制拨（ID1=0001、ID2=0010），无需 PULLUP。
- clk_wiz_0 配置零改动依据：ZC706 sys_diff_clock 与 ZC702 同为 200MHz 差分（board.xml 两板描述一致），仅换引脚。

⏳A 已回填 ✅（2026-10-19，UG954 v1.8 官方全文核查，证据存档 build/reviews/zc706_bringup/hw_facts_ug954.md；UG954 全文缓存 D:\文件\ssssssss\FPGA\ug954_text.txt 可 grep）。⏳B 已回填 ✅（直接实证 main.py/serial_server.py/enroll.py/crp_pool_sop.md/measure_w1.tcl/ci_regression.ps1/w4 综合报告）。**本文档已无待定项。**

---

## Phase 1 · 创建 w3_top_zc706.v（纯软件，无板即可做）

**做什么**：整文件 COPY w3_top_zc702.v → w3_top_zc706.v，然后只做以下 4 处改动：
1. 模块名 `w3_top_zc702` → `w3_top_zc706`（含头注释标题）。
2. 端口 `input wire [1:0] term_id_dip` → `input wire [3:0] term_id_dip`（ZC706 有 4 位拨码）。
3. 例化连线 `.term_id_sw({6'h00, term_id_dip})` → `.term_id_sw({4'h00, term_id_dip})`。
4. **auth_btn 极性决策**：UG954 实证按键空闲=1/按下=0，而 w3_top.v:121 为**上升沿触发**（`btn_state & ~btn_prev`）⇒ 现语义=「按下并**松开**后启动」。可选在 wrapper 给 w3_top 传 `~auth_btn` 改为「按下即启动」（wrapper 不在 CI，零风险）。**默认：直通**（与 ZC702 模板一致），教程叙述写「按一下并松开」。
5. 头注释重写：贴 0.5 节引脚表 + 「4 颗 LVCMOS15」「时钟 bank34=1.5V 固定轨用 DIFF_SSTL15」+ SW12 ON=1。

**其余一律不动**：clk_wiz_0 实例（200MHz 差分→100MHz+locked）、`rst_n = sys_rst_btn_n & mmcm_locked` 组合、参数 BAUD/TIMEOUT_S。w3_top.v 端口**一个字符都不改**（改了会破坏 tb_w3_top → 16/16 CI）。

**文档参考**：w3_top_zc702.v:1-57（模板）；HANDOFF_SUMMARY.md「迁移步骤」Step 1。
**验证清单**：`grep -n "zc702" src/rtl/w3_protocol/w3_top_zc706.v` 零命中；Phase 4 的 xvlog/xelab 通过（wrapper 不在 CI 清单，**CI 不会替你抓语法错**——completeness.json 已警告）。
**反模式**：❌ 顺手"优化"w3_top；❌ 把 wrapper 加进 ci_regression.ps1 的 $rtl（会引入 clk_wiz 依赖搞挂 CI）；❌ 端口名改动。
**提交**：`feat(board): add w3_top_zc706 wrapper (dual ZC706, 4-bit DIP, bank-aware pins)`

## Phase 2 · 创建 w3_top_zc706.xdc

**做什么**：以 w3_top.xdc 注释结构为骨架，按 0.5 节表重填。下方即**最终目标内容，可整块照抄**（全部事实已核验，无待定项）：

```tcl
# w3_top_zc706.xdc -- ZC706 (xc7z045ffg900-2) 引脚/时钟约束
# 顶层 = w3_top_zc706（wrapper 端口名）。禁止照抄 ZC702 任何引脚。

# === CLOCK（bank34=VCC1V5_PL 1.5V 固定轨；ZC702 的 LVDS_25 在此 bank 非法）===
set_property -dict {PACKAGE_PIN H9 IOSTANDARD DIFF_SSTL15} [get_ports clk_p]  ;# 与 AMD 官方 zc706/1.5/new.ucf 对 H9/G9 的原生约束一致
set_property -dict {PACKAGE_PIN G9 IOSTANDARD DIFF_SSTL15} [get_ports clk_n]
create_clock -period 5.000 -name sys_clk_p [get_ports clk_p]

# === 异步 I/O false_path（防伪时序违例，照抄 ZC702 语义）===
set_false_path -from [get_ports sys_rst_btn_n]
set_false_path -from [get_ports auth_btn]
set_false_path -from [get_ports {term_id_dip[*]}]
set_false_path -to [get_ports led_*]

# === RESET（bank34，LVCMOS15！CPU_RESET 按键低有效）===
set_property -dict {PACKAGE_PIN A8 IOSTANDARD LVCMOS15} [get_ports sys_rst_btn_n]

# === AUTH 按钮（AK25=SW7 GPIO_SW_LEFT，bank11 LVCMOS25，空闲1/按下0；不接则教程测3跳过）===
set_property -dict {PACKAGE_PIN AK25 IOSTANDARD LVCMOS25} [get_ports auth_btn]

# === UART（FMC LPC LA02_P/N，bank10 LVCMOS25；ZC702 的 L21/L22 禁用）===
set_property -dict {PACKAGE_PIN AE12 IOSTANDARD LVCMOS25} [get_ports radio_txd]
set_property -dict {PACKAGE_PIN AF12 IOSTANDARD LVCMOS25} [get_ports radio_rxd]

# === LED（见 0.5 映射决策）===
set_property -dict {PACKAGE_PIN Y21 IOSTANDARD LVCMOS25} [get_ports led_busy]         ;# DS8
set_property -dict {PACKAGE_PIN A17 IOSTANDARD LVCMOS15} [get_ports led_heartbeat]     ;# DS35（心跳，独立位）
set_property -dict {PACKAGE_PIN G2  IOSTANDARD LVCMOS15} [get_ports {led_result[0]}]   ;# DS9
set_property -dict {PACKAGE_PIN W21 IOSTANDARD LVCMOS25} [get_ports {led_result[1]}]   ;# DS10

# === DIP SW12（ON=1/OFF=0，板上 4.7k 下拉无需 PULLUP；ID1=0001、ID2=0010）===
set_property -dict {PACKAGE_PIN AB17 IOSTANDARD LVCMOS25} [get_ports {term_id_dip[0]}]
set_property -dict {PACKAGE_PIN AC16 IOSTANDARD LVCMOS25} [get_ports {term_id_dip[1]}]
set_property -dict {PACKAGE_PIN AC17 IOSTANDARD LVCMOS25} [get_ports {term_id_dip[2]}]
set_property -dict {PACKAGE_PIN AJ13 IOSTANDARD LVCMOS25} [get_ports {term_id_dip[3]}]
```

**注意**：w2_waiver.xdc（环振 LUTLP-1 豁免）由 build_w3_board.tcl 单独 add_files，**不并入本文件**；迁移中任何时刻都不得丢失该豁免，否则 write_bitstream 被 DRC 阻断（migration_assess 已确认原样有效）。
**验证清单**：逐行 diff part0_pins.xml（0.5 节表即逐字来源）；Phase 5 综合日志 grep 无 `NSTD-1`/`UCIO-1`。
**反模式**：❌ 引用 ZC702 引脚号；❌ 删/忘 w2_waiver.xdc；❌ 给 clk 用 LVDS_25；❌ 把 G2/A17/K15/A8 写成 LVCMOS25。
**提交**：`feat(board): zc706 pin constraints (bank-aware, LVCMOS15x4, FMC-LPC UART)`

## Phase 3 · 更新 build_w3_board.tcl

**做什么**：4 处字符串替换，语义零改动：
1. `$SRC/rtl/w3_protocol/w3_top_zc702.v` → `w3_top_zc706.v`
2. `add_files -fileset constrs_1 $SRC/rtl/w3_protocol/w3_top.xdc` → `w3_top_zc706.xdc`
3. `set_property top w3_top_zc702` 与 `synth_design -top w3_top_zc702` → `w3_top_zc706`
4. `write_bitstream ... w3_top_zc702.bit` → `w3_top_zc706.bit`；头注释 ZC702→ZC706。

**保持不动**：part 仍由 tclargs 传入；15 文件 add_files 清单（含 ro_entropy.v——W4 P1-5 依赖）；w2_waiver.xdc 行；clk_wiz IP 配置块（200MHz 差分→100MHz+locked+reset 全不变）。
**验证清单**：`grep -n zc702 build/tcl/build_w3_board.tcl` 仅剩注释性历史说明或零命中；Phase 5 实跑即终验。
**反模式**：❌ 删 ro_entropy.v / w2_waiver 行；❌ 改 clk_wiz 参数；❌ 换成 Board flow（保持 part 直传）。
**提交**：`build(tcl): retarget build_w3_board.tcl to xc7z045ffg900-2 / w3_top_zc706`

## Phase 4 · 离板验证 xvlog + xelab（wrapper 唯一语法门禁）

**做什么**（命令已对照 ci_regression.ps1:163 与脚本头注释核验）：

1. 写 %TEMP%\clk_wiz_0_stub.v（**不得放进 src/**，防与真 IP 冲突）：
```verilog
module clk_wiz_0 (input wire clk_in1_p, input wire clk_in1_n, input wire reset,
                  output wire clk_out1, output wire locked);
  assign clk_out1 = clk_in1_p;
  assign locked   = ~reset;
endmodule
```
2. 编译（**不带** `-d PUF_MODEL_SIM`——要 elaboration 走真 ro_array 板级网表；环振组合环只允许 WARNING）：
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
3. （交付项，completeness.json 建议）新增 build/ps1/verify_wrapper.ps1 把上述流程脚本化入库（ZC706 之后任何换板可复用），CI 不接入。

**验证清单**：xvlog exit 0；xelab exit 0 且快照生成、无 `ERROR`。
**反模式**：❌ 用 -d PUF_MODEL_SIM 验板级网表（验到的是替身）；❌ 把 stub 提交进 src/rtl；❌ 跳过本步直接开 Vivado（慢反馈浪费小时级）。
**提交**：`build(ps1): add verify_wrapper.ps1 (xvlog+xelab gate for board wrappers)`

## Phase 5 · 比特流 + 双板烧写（需板卡在手）

**做什么**：
1. 生成（脚本用法=tclargs <part> <outdir> <srcdir>，srcdir=仓库根）：`cd D:\puf-drone-auth && vivado -mode batch -source build\tcl\build_w3_board.tcl -tclargs xc7z045ffg900-2 build\board_zc706 .` → 期待 `BITSTREAM_SUCCESS`；检查 utilization/timing（基线：W4 实测 ZC702 综合 4190 LUT / 7.88% / 6133 FF / 0 error，56.9s；ZC706 资源绝对量应基本持平，利用率降到 ~2% 属正常）。
2. 记录 DRC：若有 LUTLP-1/NSTD-1/UCIO-1 → 回 Phase 2/3 修，不许手 waiver 之外的豁免。
3. 烧写：**COPY build/tcl/measure_w1.tcl 的 hw_manager 骨架**（去掉 VIO 轮询段，保留其防御写法：get_hw_targets 空判 exit 3、get_hw_devices 取设备、PROGRAM.FILE、program_hw_devices、refresh_hw_device）另存 build/tcl/program_zc706.tcl，骨架：
```tcl
open_hw_manager
connect_hw_server -url localhost:3121
set ts [get_hw_targets -quiet]
if {[llength $ts] == 0} { puts "ERROR: 未找到 JTAG 目标（检查电源/USB/驱动）"; exit 3 }
open_hw_target
set dev [lindex [get_hw_devices] 0]
set_property PROGRAM.FILE $BIT $dev
program_hw_devices $dev
refresh_hw_device $dev
close_hw_target
disconnect_hw_server
```
线缆：Standard-A↔Micro-B 插面板「JTAG」口（板载 Digilent U30，iMPACT 识别 JTAG-SMT2，Vivado 自带驱动）。两块板可同接一台 PC（同一 hw_server 枚举两个 target，Vivado 逐个打开编程；求稳也可逐块上电烧）。
4. 烧写前板级自检（UG954 实证）：J22=6pin Mini-Fit 12V 输入（套件含 12V/5A 适配器 PN 6003-300-000；**严禁 ATX 6 针**——引脚不同烧板失保）；SW1 滑到 On，DS22 亮=12V 到位；电源好=DS24(PWRGOOD)+DS15(VADJ)；**SW4 拨 01**（出厂 10=J3 排针，USB JTAG 不通的头号原因）；SW11 保持出厂 00000（JTAG 模式）；J18 保持默认安装（VADJ 使能）、J66 保持 OPEN、SW10(PROG_B) 勿误按；DONE=DS3、INIT=DS2（红=配置中）。

**验证清单**：BITSTREAM_SUCCESS；timing met（WNS≥0）；板 A/B 各自 DONE 灯亮 + **心跳 LED（A17=DS35）~0.75Hz 闪** = 全链路（时钟/复位/约束）OK。不闪排障顺序：DS15(VADJ)→DS24→DS3(DONE)→J18/SW4/SW11→SW10 误按。UG954 全文已缓存 D:\文件\ssssssss\FPGA\ug954_text.txt 可随时 grep。
**反模式**：❌ 两板同插 JTAG 盲烧；❌ VADJ 未确认前插 FMC 外设；❌ 动 w2_waiver 之外的 DRC 豁免。
**提交**：`build(tcl): program_zc706.tcl + bringup evidence (bitstream reports)`

## Phase 6 · 拨码设终端 ID + 按键/LED 行为验证

**做什么**：SW12 拨码（ON=1）：板 A=**0001**（pin1 ON→ID1）、板 B=**0010**（pin2 ON→ID2）。功能自证法（比万用表强）：接串口后发起一次认证，PC 侧日志读 ACCESS_REQUEST 帧的 terminal_id 字段 = 期望值即通过。auth_btn=AK25(SW7)：**按一下并松开**触发认证（见 Phase 1 极性决策），led_busy(DS8) 亮→DS9/DS10 给 01=通过。每板拍照留证（竞赛材料）。
**验证清单**：terminal_id 回读 = 1/2；两板行为一致；心跳正常。
**反模式**：❌ 两板同 ID（CRP 池/模板按 tid 索引会串）。
**提交**：`docs(evidence): zc706 dip/led bringup records`

## Phase 7 · 双 COM 串口联调（PC = 基站）

**硬件**：2×USB-TTL（优先 FTDI/CH340，VIH≤2.0V；CP2102 VIH=2.31V 边缘）。接线（每板）：AE12(txd)→适配器 RX；AF12(rxd)←适配器 TX；GND↔GND 共地；适配器 VCC 不接。
⚠ **R3 电平（VADJ=2.5V 已证实）**：适配器 3.3V TX 直怼 bank10 超 abs-max → **每板 rxd 线必装分压 1kΩ/2.2kΩ（3.3→2.27V）**；txd 方向 2.5V 高电平对 CH340/FT232（VIH=2.0V）足够，CP2102（VIH=2.31V）边缘避开。
⚠ **R11 物理引出**：LA02 在 FMC LPC 连接器 **J5**（160pin Samtec SEAF，部分贴装）的 H7/H8 针位——需 2×FMC LPC 转接板；**转接卡若引出 JTAG 引脚必须带 TDI-TDO 旁路**（否则 FMC 卡串入 JTAG 链导致无法编程，UG954 p.35）。USB-UART J21=CP2103→PS MIO，PL 用不了、驱动也不用装。
**软件**（命令已核验 main.py:1-24/890-920）：
```
pip install pyserial
:: 终端1（板A，COM3）
python -m src.python.server.main --port COM3 --baud 115200
:: 终端2（板B，COM4）——双终端=双 REPL 实例（serve 是单口阻塞循环，serial_server.py:253）
python -m src.python.server.main --port COM4 --baud 115200
```
REPL 内：`status` 看池/模板/会话 → `setkey 1 131211100b0a090803020100`（W3 公开密钥，24 hex；板B 同理 tid=2）→ `serve` 进入终端发起接收循环（Ctrl-C 回 REPL）。
⚠ **R9 双实例共库**：两实例共享 data/templates/templates.json + data/crp_datasets/pools + device_keys.json，跨进程 last-writer-wins 是 A1 复审已知限制——**enrollment 阶段严禁双实例并发**（串行：实例1 enroll 板A → 退出 → 换口 enroll 板B）；并发 serve 只读+定期 C2 flush，若见 external-change 报错立即改串行演示。
CI 契约门禁复跑：`python tools\check_contract_sync.py`（协议侧改动时才需要）。
**验收（保姆教程验证点等价）**：任一板上电后链路 C0→C2→R2；**首次认证 R2 黄金值 = 7b45b0545e59aa94**（W3 公开密钥、ENABLE_KEY_DERIVE=0 语义）逐位一致；RESULT 帧 CRC 正确；两板同时在线各自完成一轮互认（CONFIRM_OK，serial_server 已接线）。
**反模式**：❌ 波特率非 115200；❌ 不共地；❌ 用 enroll 前不核对响应语义（见 Phase 8）。
**提交**：`feat(server): dual-COM bring-up notes + evidence`

## Phase 8 · PUF 板上注册（W4 收官，最大单项 8~12h/板）

**做什么**（流程已核验 crp_pool_sop.md 全文 + enroll.py:1-53 + main.py cmd_enroll:587；顺序勿颠倒）：
1. 板 A：REPL `enroll 1 100`（默认 100 CRP、每挑战 3 次测量取 majority；reserve→CHALLENGE/RESPONSE 逐批→模板入库，中断自动 release 回滚）。池语义（SOP §1-2）：CLI `--pool-size` 默认 500，每次认证消耗 4 CRP（灰区追加 3）；失败认证/停滞会话 30s 自动退回种子（staging-release）——池只在 PASS 时缩小。阈值复核：threshold.decide_scaled 灰区宽度复核 + 跨板区分度（hamming_analysis）过一遍。T2 上电熵在真芯片首次成立（ro_entropy 上电采样窗 ENTROPY_CYCLES）。
2. **注册语义配对**（enroll.py:5-9 原文警告）：enroll 必须用与终端一致的响应语义——串口模式 enroll 走 SerialTransport=真终端响应 ✅；**切勿**用 --loopback 语义的模板去认证真板（必恒 REJECT，且易误判为协议缺陷）。
3. 板 B 重复（换 COM 口 + `enroll 2 100`）。**两板 PUF 指纹必然不同 = 演示卖点**：交叉验证——板 A 的模板对板 B 必 REJECT（留证）。
4. （时间富余才做）T1 密钥派生使能：ENABLE_KEY_DERIVE=1 重综合 + 站端 derive_device_key 流程（W4_design §5v2；KEY_SEED 0x0096 通道未实现，勿宣称）。

**验证清单**：每板首认证 PASS（真 PUF 评分过阈值）；交叉 REJECT；断电重启后重放帧被拒（P1-5 修复的板级实证，GK 用例语义）；crp_pool/模板文件按 SOP 归档。
**反模式**：❌ **注册语义配错必 REJECT**（enroll 必须用与终端一致的 Speck 响应语义——HANDOFF 头号警告）；❌ 未复核阈值就宣称达标；❌ 模板/密钥文件（data/device_keys/ 已 gitignore）误提交。
**提交**：`feat(w4): on-board enrollment x2 + threshold recheck evidence`

## Phase 9 · E2E 收官 + 文档冻结（对接 W5）

**做什么**：双终端编队演示脚本走通（基站 PC 同时服务 ID1/ID2，全流程 ACCESS→CHALLENGE→R2→RESULT→CONFIRM）；CI 全绿复跑（16/16）；文档三处更新——HANDOFF_SUMMARY 状态节、w1_tutorial 板卡节（ZC702→ZC706 勘误：DS 位号/引脚表）、README/架构图板卡名；证据归档 build/reviews/zc706_bringup/（JSON+日志+照片清单）；竞赛材料（报告/视频脚本）进入 W5 冻结。
**验证清单**：CI exit 0；演示 3 次连跑无掉线；文档 grep 无 "ZC702" 残留（教程历史叙述除外，逐处人工判断）。
**提交**：`docs: zc706 migration complete -- handoff/tutorial/README freeze`

---

## 风险登记表

| # | 风险 | 影响 | 缓解 | 状态 |
|---|---|---|---|---|
| R1 | 时钟 IOSTANDARD 选错（bank34=1.5V 固定轨，LVDS_25 非法） | 综合 DRC 失败 | ✅ **DIFF_SSTL15**（AMD 官方 zc706/1.5/new.ucf 对 H9/G9 原生即用此标准）+ Phase 5 DRC 复核 | 已关闭 |
| R2 | VADJ 默认值/所属 bank 不明 | FMC/LED bank 电平错 | ✅ UG954 Table 1-3 注1：出厂 VADJ=2.5V 供 bank9-13；J18 默认装 + UCD90120A 硬件时序器上电自动拉起（**纯 PL 设计无需 PS 启动**）；bank33/34/35=VCC1V5_PL 1.5V 固定 | 已关闭 |
| R3 | USB-TTL 3.3V → bank10(2.5V) 超压 | 烧输入脚 | 每板 rxd 线 1k/2.2k 分压（→2.27V）必装；txd 方向 2.5V 对 CH340/FT232 足够 | 已缓解 |
| R4 | JTAG 口线型/驱动未知 | 无法烧写 | ✅ Digilent U30 面板 Micro-B「JTAG」口 + Vivado 自带驱动；**SW4=01**（出厂 10=J3）、SW11=00000 默认即 JTAG | 已关闭 |
| R5 | 433MHz 电台未购 | 无线演示缺失 | 双 USB-TTL 直连（已定）；报告注明射频替换 | 已接受 |
| R6 | DIP 极性/上拉未知 | 终端 ID 错 | ✅ SW12 ON=1/OFF=0（4.7k 下拉）；ID1=0001/ID2=0010；仍保留 terminal_id 回读自证（Phase 6） | 已关闭 |
| R7 | enrollment 时间（8~12h×2）挤压 W5 | 冻结周缩水 | 硬件窗口 8 天硬顶；Phase 1–4 今天做完 | 已排程 |
| R8 | 第二块 ZC706 也有硬件故障（ZC702 前科） | 单终端降级 | 上电自检首批做（Phase 5 步 4）；降级预案=单终端+loopback 演示 | 开放 |
| R9 | 双 REPL 实例共享 templates/pools/device_keys 跨进程覆盖（A1 复审已知限制） | 密钥/模板静默丢失 | enrollment 严格串行；serve 并发期盯 external-change 报错，必要时降级串行演示 | 已缓解 |
| R10 | measure_w1.tcl 硬连 3121 端口 + 单 target 假设 | 双板 JTAG 识别混淆 | 逐块上电烧写；两 target 时按序列号选 dev | 已缓解 |
| R11 | FMC LPC(J5) 物理引出未落实（160pin SEAF 连接器）+ FMC 卡串入 JTAG 链风险 | 接不了 USB-TTL / 烧不了板 | 采购/借用 2×FMC LPC 转接板；确认转接卡 JTAG 引脚旁路；现场清单核对（见下） | **开放（唯一硬采购项）** |

## 现场核对清单（拿到板子第一分钟，全部拍照）

- [ ] J22 电源口 + 套件 12V 适配器在位；上电 DS22/DS24/DS15 全亮；**ATX 6 针禁插 J22**
- [ ] **SW4 拨 01**（USB JTAG）；SW11 确认出厂 00000；J18 默认装、J66 OPEN、SW1 On
- [ ] 面板「JTAG」Micro-B 口 ×2 + Standard-A↔Micro-B 线 ×2
- [ ] SW12 拨码 ON 方向丝印确认（文档口径：ON=1）
- [ ] SW7(AK25 认证)/SW13(A8 复位)/SW10(PROG_B 勿误按) 位置
- [ ] DS8/DS9/DS10/DS35 + DS3(DONE)/DS2(INIT) 位号拍照
- [ ] FMC LPC=J5 转接板到位（H7=AE12 txd、H8=AF12 rxd 针位确认 + JTAG 旁路确认）
- [ ] 两板序列号登记（板 A=ID1、板 B=ID2 物理贴标签）

## 时间线（硬顶）

| 日期 | 内容 |
|---|---|
| 10-19（今天） | Phase 0 ✅ + Phase 1–4（纯软件，全部完成并提交） |
| 10-20~21 | Phase 5–6（板卡到手：自检→比特流→烧写→拨码） |
| 10-21~23 | Phase 7（双 COM 联调 + 黄金 R2 对齐） |
| 10-23~27 | Phase 8（两板 enrollment + 交叉验证；每天一块） |
| 10-27 起 | W5 冻结（报告/视频），Phase 9 收官 |
| 11-03 | 提交日前全量彩排 |
