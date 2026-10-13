# 待办核对清单 · 复核标的（claims）· auto-review 2026-10

> 本文件是主会话「未做事项核对梳理」的可核查断言清单,由 auto-review 独立子代理逐条取证复核。
> 仓库: D:\puf-drone-auth(只读)。权威文档: docs/HANDOFF_SUMMARY.md。
> 背景: PUF 无人机认证(ZC702,截止 2026-11-04 18:00)。A1 已完成(CI 12 TB 全绿)。2026-10-10 完成板级适配(wrapper/XDC/上板脚本)但看板未刷新。板卡 DS13 不亮(电源故障,另一会话处理)。

## A 组 · 仓库状态与文件事实 [代理A核验]
- C01: git HEAD=ffd6f2b, master, 工作区干净, 提交总数 73, tag w3-complete 存在。
- C02: docs/HANDOFF_SUMMARY.md 开头存在「会话交接记录(2026-10-10)」节;其 §一 写 HEAD a771f91 是写入时点状态,之后追加 ffd6f2b(交接记录入库提交),非矛盾。
- C03: 教程 docs/tutorials/w1_tutorial.md 中 DS 位号错共 5 行: L58(板卡表 DS9~DS12)、L360、L388(数 DS10)、L389、L390(led_busy(DS9));LED 引脚 P17/P18/W10/V7 本身已正确。
- C04: src/rtl/w3_protocol/w3_top.xdc 注释中 2 处 DS9~DS12: L25 与 L29;文件内全部约束仍为注释状态(未启用)。
- C05: board/zc702/README.md L8 写 "Two USB ports with different roles...",行尾有疑似误粘的 "+ IOSTANDARD" 碎片;未按 UG850 三口(J17/U23/J1)描述。
- C06: 外部副本 D:\文件\ssssssss\FPGA\保姆教程_W1_从零到一号验证点.md 与仓库教程 SHA256 一致。
- C07: terminal_fsm.v 中 PUF 响应仍是种子直通占位;DEVICE_KEY 参数为 NSA 公开向量 96'h13121110_0b0a0908_03020100。
- C08: tests/ 只有 test_a1_phase4.py;无 test_interop_rtl_model.py(一次性证据在 build/reviews/a1full/interop_run.json)。
- C09: scripts/ci_regression.ps1 全内联(12 TB + Python 段),无超时作业化;wrapper w3_top_zc702.v 与 clk_wiz 不在其编译清单(设计如此,非缺陷)。
- C10: src/python/server/ 无 enroll.py(design.md 注册流程设计的"新增文件"未创建);main.py 无真实串口收发循环(仅 --loopback)。
- C11: skill/ 只有 README.md;report/ 只有 README 骨架+figures/.gitkeep+llm_log/w1_session.md;data/w1_readings/ 空(.gitkeep)。
- C12: sim/tb/ 无 tb_uart_rx.v(uart_rx 无独立 TB);tb_gap_regression.v 含 GE/GH 灰区用例。
- C13: 旧克隆 D:\文件\ssssssss\FPGA\puf-drone-auth 存在(HEAD 5a3ec3c, 920 文件, 16,858,478 字节);D:\fpga_work 仍存在(含 w3_bitstream/w3_synth/speck_ooc/feas_w2 等);D:\puf-drone-auth\build\vivado\ 存在但为空(.gitignore:82 有规则);主仓 src/board/docs/build-tcl/build-ps1/sim/scripts 无 BOM;UG850 PDF 在 D:\文件\ssssssss\FPGA\ug850-zc702-eval-bd.pdf。

## B 组 · 权威文档一致性与看板状态 [代理B核验]
- C14: HANDOFF §三 UG850 权威事实: 用户 LED P17=DS15/P18=DS16/W10=DS17/V7=DS18;J17(U36,Mini-B)=USB-UART CP2103GM、U23(Micro-B)=PL JTAG、J1(U9,Mini-B)=PS USB(零枚举易误插);DS12=PS_MIO8_LED0、DS23=PS_LED1;UG850 LED 表无 DS9~DS11;DS14=12V 到位、DS13=PWRGOOD。
- C15: 看板过时: docs/ 下 project_status/project_flow/mindmap/architecture 四份 HTML 仍把时钟适配/复位源/拨码开关不足列为待办,实际已被 w3_top_zc702.v + clk_wiz_0 + build_w3_board.tcl + XDC wrapper 端口名解决(2026-10-10);HTML 页脚统计(60 commits/147 files)落后实际(73 commits);architecture.html 未反映 DS13 电源故障排查进展。
- C16: 排期: W4/W5/W6 全部未开始;W5 G5 门禁四件套(互斥演示/CRP 全流程/ROC-EER/报告+视频)与判据在 design.md;W6 11-03 晚提交、11-04 18:00 硬死线;ML 攻击实验 0 文件(实验 A 合成 arbiter+LR、实验 B 排序重构 ~120 CRP,结论口径已在 design.md 冻结)。
- C17: 遗留外部复核 3 项: DS9~DS11 含义、板上 USB 丝印实测、JTAG 线型确认(教程现保守写"以实物丝印为准")。

## C 组 · 一致性/过度声明 [代理C核验]
- C18: 主会话"纯 PC 可立即做"清单(B5/P1-1/P1-5/熵混合/P2-1/预认证池 DoS/setkey 与 c2reset 审计/DeviceKeyStore 文件锁/DPAPI/interop 固化/CI 作业化/SimulatedHSM 决策/enroll/on_confirm/tb_speck 毛刺/RemoteException 日志)与 HANDOFF §四 一致,无杜撰。
- C19: "四份 HTML 已刷新至 A1 完成态"(用户摘要语)与 C15"看板过时"并存——需明确: HTML 反映到 10-08 A1 完成态,未反映 10-10 板级适配与板卡调试,两者不矛盾但表述要区分。
- C20: "板级验证=0/系统联调=0"仍准确(未烧板);但 ZC702 已尝试上电(DS14 亮/DS13 不亮),architecture.html "从未上电验证"措辞已过时。

## D 组 · 板卡事实精确定位 [代理D核验]
- C21: 教程 L58/L360/L388/L389/L390 与 XDC L25/L29 及 board README 的行号、引文逐字准确。
- C22: build/reviews/tutorial/board_facts.json 是历史审查证据(其"DS9~DS12 对应仍需核实"系当时口径,后被 UG850 确认 DS15~DS18),不应回改该 JSON。

## E 组 · 排期/交付/风险 [代理E核验]
- C23: design.md 风险表 8 项与依赖图与主会话转述一致(Vivado 许可 11-23、板 2 降级方案、CRP 池<20% 重注册等)。
- C24: mindmap 的 W4 附加项(温度 ΔT≤30°C/70°C 硬停、无线联调 air rate 64k/ECC/NETID、多终端实例 0~3、AI 扩展最小闭环、可靠性曲线)与 W5-W6 清单(功能冻结令/全量指标/NIST/视频/Skill/复现包/决赛彩排/个人 Verilog 功课)均已纳入主会话梳理,或属遗漏(需指出)。
- C25: 看板"约 27 天剩余"基于 10-08;实际剩余天数需按今日日期重算(时效问题)。

## 附录 · 主会话梳理的完整待办清单(供遗漏/误标扫描对照)
一、纯 PC: B5 PUF 真实接入; P1-1 真密钥; P1-5 终端跨断电重放(三选一); 44-bit 熵混合; P2-1 故障注入加固; 预认证池 DoS 限速; setkey getpass/c2reset 审计/DeviceKeyStore 文件锁/DPAPI 可选; 互操作 harness 固化 tests/; CI 超时作业化; SimulatedHSM 决策+save_secret 对齐; enroll.py+注册语义配对; on_confirm 接线; tb_speck 输入毛刺; 日志 RemoteException; B6 ML 实验 A/B+评估工具适配; D13 报告初稿; D14 Skill 打包(≥2 可运行脚本)
二、需板卡: 出厂 BIST; 验证点① VIO 10 次极差<100; 验证点② 心跳+按键(前置:XDC 取消注释); 验证点③ PC 串口环路(前置:串口循环未写/FMC/PMOD 未选/断电插拔); 温度实验; PUF 核心假设验证; 多终端并发(实例 0~3); 电台半双工适配
三、需采购: 433MHz SiK 电台一对+USB-TTL×2; 第 2 块板(降级:单板+软仿冒者/预录视频)
四、文档/仓库卫生: 四份 HTML 看板刷新; DS 位号修正(教程 5 行+XDC 2 行)+board README 三口+外部副本同步; 旧克隆删除(待用户确认); fpga_work/build-vivado 迁移定夺; 外部复核 3 项
五、已知限制(非必做): C2 回绕 256; 灰区 Level 3 完整路径待核实; uart_rx 无独立 TB; Vivado 许可 11-23 到期前存档比特流
