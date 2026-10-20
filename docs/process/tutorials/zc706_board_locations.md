# ZC706 板卡「标号 → 实物位置」速查（官方图集本地版）

> 依据：AMD UG954 v1.8《ZC706 Evaluation Board User Guide》
> 本地官方 PDF：D:\文件\ssssssss\FPGA\ug954-zc706-eval-board-v1.8.pdf（8.9MB，页面页码与官方一致）
> 配图：assets/zc706/ 目录（从官方 PDF 以 300dpi 提取，可直接放大/打印）

---

## 一、五种方法（推荐按顺序用）

| # | 方法 | 怎么做 | 适用 |
|---|---|---|---|
| 1 | 官方 Figure 1-3 + Table 1-1（最快最权威） | 打开 UG954 PDF 第 12 页：整板俯视图带 1–38 编号，配合 Table 1-1（P.12–14）查编号对应的器件。打印这页或手机看 | 任意器件 |
| 2 | 本目录切好的 6 张图 | 用 assets/zc706/ 里的全板图 + 4 张区域放大图，按区域找编号 | 日常联调常用件 |
| 3 | 板子丝印 | 每个器件旁都有白色丝印标号（DS3、SW12、J22、J58 等）；手机开手电+变焦拍 | 精确到单颗 |
| 4 | 方位定锚 | 先认大件（FMC 两个大连接器、电源口、风扇、SD 槽、HDMI/SFP/USB 面板），再按相对位置找小件 | 新板快速熟悉 |
| 5 | 拍照问 | 把器件附近拍清楚发我，我按 Figure 1-3/Table 1-1 对照指认 | 拿不准时 |

### 方位对照（重要，防看反）

- 官方图的方向：FMC HPC(30) / LPC(31) 在上缘；J22(38) 电源口 + SW1(27) 在右缘；左侧面板是 SFP/HDMI/RJ45/USB 那一片（14/18/15/17/6）；PCIe 金手指(13)在下缘偏左；中央是 SoC(1)+风扇。
- 编号约定（图例原文）：圆形 = 板正面的器件，方形 = 板背面的器件。
- 编号标的是器件群体，具体单颗（哪颗 LED、哪颗按键）请看板上白色丝印。

---

## 二、常找的 20 项速查

| 对象 | 板上丝印 | 图编号 | 位置（按官方图方向） | 备注 |
|---|---|---|---|---|
| 12V 电源输入 | J22 | 38 | 右缘上部（白色 6 针座） | 插套件 12V 适配器 |
| 电源滑动开关 | SW1 | 27 | J22 左侧（粉色拨柄） | 拨 ON 供电 |
| JTAG 选择拨码 | SW4 | 34 | 中央偏左，logo 旁、FMC HPC 下方 | 01=Digilent（板载 USB） |
| USB-JTAG 口 | U30（面板 JTAG 口） | 6 | 左侧面板区，SFP(14) 下方 | Micro-B，烧录用 |
| 启动模式拨码 | SW11 | 29 | 中央（风扇上方、SW4 右侧） | 全下=00000=JTAG |
| 用户拨码（终端 ID） | SW12 | 24 | 中央偏右（SW11 右侧） | ON=1；ID1=0001 |
| 用户按键排 | SW7 / SW13 / SW8 / SW9 | 23 | 板下缘中部一排 4 颗 | SW7=认证键；SW13=复位 |
| PROG_B 按键 | SW10 | 28 | SW12 下方 | 按了清配置，别按 |
| 用户 LED | DS8–DS10、DS35 | 22 | 板右上角 GPIO LEDS 丝印处 | 结果码/心跳 |
| DONE / INIT 灯 | DS3 / DS2 | 22 附近 | 右上角同区 | 烧写状态灯 |
| PMOD 排针 | J57 / J58 | 26 | 右中部（SW12 右侧、板缘 2×6） | UART 用 J58 |
| FMC HPC 连接器 | J37 | 30 | 上缘（大的那个） | 本项目不用 |
| FMC LPC 连接器 | J5 | 31 | 上缘（靠右） | 本项目不用 |
| USB-UART 桥 | J21（Mini-B） | 17 | 左侧面板、SD 槽下方 | 只连 PS，PL 用不了 |
| USB OTG | J2（Micro-B） | 19 | 右缘中部 | 与项目无关 |
| SD 卡槽 | J30 | 5 | 图右上（FMC 下方） | — |
| 电源管理芯片 | U48（UCD90120A） | 32 | 右中部 | 各路电源时序 |
| XADC 排针 | J63 | 33 | 图右上（SD 槽左侧） | 模拟输入 |
| QSPI Flash | U58 / U59 | 4 | 图左上 | 固化启动用 |
| SoC + 风扇 | U1 | 1 | 板中央 | 主芯片 |

---

## 三、Table 1-1 全表（图编号 1–38）

| 编号 | 器件 | 丝印/说明 |
|---|---|---|
| 1 | Zynq-7000 XC7Z045 SoC（带风扇散热器） | U1，XC7Z045T-2FFG900C |
| 2 | DDR3 SODIMM 内存（PL） | 插槽 J1（背面） |
| 3 | DDR3 组件内存（PS）1GB | 4×256M，U2–U5 |
| 4 | Quad-SPI Flash | U58–U59（128Mb） |
| 5 | SD 卡接口 | J30 |
| 6 | USB-JTAG 接口 | U30，Micro-B，Digilent 模块 |
| 7 | 系统时钟 200MHz LVDS | U64（SiT9102） |
| 8 | 可编程用户时钟（I2C） | U37（背面，默认 156.25MHz） |
| 9 | 用户 SMA 时钟 | J67/J68 |
| 10 | GTX SMA 时钟 | J36/J31 |
| 11 | 抖动衰减时钟 | U60（背面） |
| 12 | GTX 收发器 | 集成在 U1 |
| 13 | PCIe 端点 | P4 卡缘 4-lane |
| 14 | SFP/SFP+ 模块连接器 | P2 |
| 15 | 以太网 PHY（RGMII） | U51 + RJ45 P3 |
| 16 | GTX 差分 SMA TX/RX | J35/J34、J32/J33 |
| 17 | USB-UART 桥 | U52 + J21（Mini-B）→ 只连 PS |
| 18 | HDMI 输出 | U53 + P1 |
| 19 | USB 2.0 ULPI | U12 + J2（Micro-B） |
| 20 | I2C 总线 MUX | U65（背面） |
| 21 | 以太网 PHY 状态灯 | DS28–DS30 |
| 22 | 用户 LED | DS8–DS10、DS35 |
| 23 | 用户按键 | SW7、SW9、SW8（左/中/右）+ SW13（CPU 复位） |
| 24 | GPIO 拨码 SW12 | 4 位，ON=1 |
| 25 | ARM PJTAG 排针 | J64 |
| 26 | 用户 PMOD 排针 | J57、J58 |
| 27 | 电源滑动开关 | SW1 |
| 28 | PROG_B 按键 | SW10 |
| 29 | SoC MIO 配置拨码 | SW11（5 位） |
| 30 | FMC HPC 连接器 | J37 |
| 31 | FMC LPC 连接器 | J5 |
| 32 | 电源管理 | UCD90120A 等（正/背面） |
| 33 | XADC 连接器 | J63 |
| 34 | JTAG 选择拨码 | SW4（2 位） |
| 35 | JTAG flying lead 排针 | J62 |
| 36 | PMBus 连接器 | J4（2×5） |
| 37 | JTAG 14-pin 排线座 | J3 |
| 38 | 12V 电源输入 | J22（2×6） |

---

## 四、开关默认值（Table A-1，P.88）

| 开关 | 功能 | 出厂默认 | 选择 |
|---|---|---|---|
| SW1 | 总电源滑动开关 | OFF | 交付时 OFF |
| SW4 | JTAG 选择（2 位） | 10 | = J3 排针（USB 烧录需改 01） |
| SW11 | PS 启动模式（5 位） | 全下 = 00000 | = JTAG |
| SW12 | 用户拨码（4 位） | 全 OFF | = 0（4.7k 下拉） |

---

## 五、常用跳线（Table A-2 摘录；跳线位置见 assets/zc706/figA-1_jumpers.jpg）

| 跳线 | 功能 | 默认 | 含义 |
|---|---|---|---|
| J18 | FMC_VADJ_ON_B（VADJ 使能） | 1-2 安装 | FMC/PL 的 VADJ=2.5V 上电使能（保持默认） |
| J66 | PL_PWR_ON（PL 电源使能） | OPEN（空） | PL 电源上电使能（保持为空） |
| J6 / J65 | Bank0 CFGBVS / INIT_DONE 测试头 | OPEN | CFGBVS=1（3.3V 配置） |
| J19 | PCIe lane 宽度 | 3-4 | 4-lane PCIe |
| J70–J74 | MIO 选择 | 1-2 | QSPI 启动相关 |

---

## 六、配图清单（assets/zc706/）

| 图片 | 内容 | 适合找 |
|---|---|---|
| fig1-3_board.jpg | 官方整板俯视图（带 1–38 编号） | 全板任何东西 |
| regionA_fmc_power.jpg | 图右上：FMC 30/31、SD 5、XADC 33、LED 22、SW1 27、J22 38、PJTAG 25 | 电源/烧写/状态灯 |
| regionB_center.jpg | 图中央：SoC 1、DDR3 2/3、QSPI 4、SW4 34、SW11 29、SW12 24、SW10 28、按键 23、PMOD 26、SMA 9/10/16 | 联调最常用 |
| regionC_pmod_btn.jpg | 图右下：SW11 29、SW12 24、SW10 28、按键 23、PMOD 26、电源管理 32、J2 19 | PMOD/UART 接线、按键 |
| regionD_left.jpg | 图左侧面板：PMBus 36、SFP 14、J62 35、J3 37、U30 6、J21 17、RJ45 15、HDMI 18、PCIe 13 | JTAG/UART/网口 |
| figA-1_jumpers.jpg | 跳线位置图（Figure A-1，编号 1–34） | J18/J66 等跳线 |

> 图片均从官方 PDF 提取；若与实物丝印有出入，以实物丝印为准并记录差异。

---

## 七、电源指示灯在哪（DS22 / DS24）

位置：板子**右上角**，紧贴 **J22（12V 输入白色 6 针座）与 SW1（粉色电源拨柄）** 的那一排小灯群。丝印能读到 **GPIO LEDS / INIT / DONE / PWRGOOD / VTT / 3.3V** 等字样（放大图见 `assets/zc706/power_leds_zoom.jpg`）。

| 灯 | 功能 | 在哪 | 什么时候亮 |
|---|---|---|---|
| **DS22** | 12V 输入指示（VCC12_P） | J22/SW1 旁 | SW1 拨 ON 后**立即亮** |
| **DS24** | CTRL1_PWRGOOD（电源控制器总好信号） | 同排，丝印 **PWRGOOD** 旁 | 电源时序完成后亮（比 DS22 **稍晚**） |

同排/同区还有各路电源指示：DS11=VCCINT(1.0V)、DS13=VCC1V5_PL(1.5V)、DS15=VADJ、DS16=VCC3V3(3.3V)、DS20/21=DDR VTT、DS23=FMC PG 等（Table 1-27）。

上电自检顺序：SW1 ON → **DS22 亮** → 稍后 **DS24/PWRGOOD 亮** → 各轨道灯亮 → INIT(DS2) 红转绿 → 烧写后 DONE(DS3) 绿。

> 找不到时：手机放大拍那一排，**PWRGOOD / GPIO LEDS / INIT / DONE** 是板上最大的丝印字样，顺着它们就能认出整组状态灯。



