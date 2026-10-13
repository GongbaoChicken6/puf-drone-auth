# 待办核对清单 · 复核标的 v2 · auto-review 2026-10

> **v1 → v2 修订记录**: v1 经 5 个独立代理(A 仓库事实 / B 文档合规 / C 一致性 / D 板卡事实 / E 排期风险)核验 + 共识综合:
> 25 断言 = 22 CONFIRMED / 3 PARTIAL(C01,C10,C24) / 0 REFUTED; 门禁 P0=0,P1=0,P2=4,P3=11 → FAIL, 本 v2 按共识 fix_list(F1~F16)修订, 修订处标【v2|Fn】。
> 仓库: D:\puf-drone-auth(只读)。权威文档: docs/HANDOFF_SUMMARY.md。
> 背景: PUF 无人机认证(ZC702,截止 2026-11-04 18:00)。A1(Speck64/96 统一 R2)已完成(CI 12 TB 全绿)。
> 2026-10-10 完成 wrapper 与上板脚本; w3_top.xdc 底稿已改写为 wrapper 端口名但仍全部注释、UART 引脚未选定。【v2|F11】
> 板卡 DS13 不亮(电源故障,另一会话处理中)。今日 2026-10-12,距死线约 23 天。

## A 组 · 仓库状态与文件事实
- C01【v2|F16 备注】: git HEAD=ffd6f2b, master, 73 提交, tag w3-complete; 无未提交的已跟踪文件变更(本审查产物目录 build/reviews/todo-recheck/ 为 untracked,系审查自身输入,非仓库缺陷)。
- C02: HANDOFF 开头有「会话交接记录(2026-10-10)」节;其 §一 HEAD a771f91 为写入时点,后追加 ffd6f2b 交接入库提交,非矛盾。
- C03: 教程 DS 位号错共 5 行: L58/L360/L388/L389/L390;LED 引脚 P17/P18/W10/V7 已正确。
- C04: w3_top.xdc 注释中 2 处 DS9~DS12(L25/L29);全部约束仍为注释状态。
- C05: board/zc702/README.md L8 写 "Two USB ports with different roles...",行尾有 "+ IOSTANDARD" 碎片;未按 UG850 三口(J17/U23/J1)描述。
- C06: 外部副本 D:\文件\ssssssss\FPGA\保姆教程_W1_从零到一号验证点.md 与仓库教程 SHA256 一致(1678CEF0...22FAC, 33691 字节)。
- C07: terminal_fsm.v PUF 响应仍是种子直通占位(L14/L305-308);DEVICE_KEY=NSA 公开向量 96'h13121110_0b0a0908_03020100(L92)。
- C08: tests/ 只有 test_a1_phase4.py;无 test_interop_rtl_model.py(一次性证据在 build/reviews/a1full/interop_run.json)。
- C09: ci_regression.ps1 全内联(12 TB + Python 段),无超时作业化;wrapper 与 clk_wiz 不在编译清单(设计如此)。
- C10【v2|F1】: src/python/server/ 无 enroll.py;main.py 已有 --port 串口模式与 SerialTransport 一问一答收发(main.py:183-232/812-823,C2 为桩随机数),无持续接收循环(L204 注释自证),未联调。
- C11: skill/ 仅 README.md;report/ 仅骨架+figures/.gitkeep+llm_log/w1_session.md;data/w1_readings/ 空。
- C12【v2|F5】: sim/tb/ 无 tb_uart_rx.v(uart_rx 无独立 TB);tb_gap_regression.v 含 GE1/GE2 灰区用例,GH 为 RESULT=4 重放拒绝(REPLAY)用例(tb 头注 L11 对 GH 的 inhibit 描述与实现 L265-277 不符,系上游注释混乱)。
- C13: 旧克隆(HEAD 5a3ec3c,920 文件,16,858,478 字节)存在;D:\fpga_work 仍在;build/vivado/ 空(.gitignore:82 有规则);主仓 0 BOM;UG850 PDF 在位。

## B 组 · 权威文档一致性与看板状态
- C14【v2|F6】: HANDOFF §三(L31-41): P17=DS15/P18=DS16/W10=DS17/V7=DS18;J17(U36,Mini-B)=UART CP2103GM、U23(Micro-B)=PL JTAG、J1(U9,Mini-B)=PS USB(零枚举);DS12=PS_MIO8_LED0、DS23=PS_LED1;DS14=12V、DS13=PWRGOOD。「UG850 LED 表无 DS9~DS11」出处为 §四:51(外部复核待办第 1 条),非 §三。
- C15【v2|F7】: 看板过时(按文件分列): architecture.html:314/316/330 三项齐(时钟/复位/拨码);project_flow.html:193-194 仅引脚/时钟;project_status.html:173 与 mindmap.html:140 为「引脚/时钟/复位」概括式——均未反映 10-10 已解决的 wrapper 适配;四份页脚 60 commits/147 files vs 实测 73/159;architecture.html 无 DS13/PWRGOOD 排查内容,「未上电验证」措辞过时。
- C16: W4/W5/W6 全部未开始;G5 四件套与判据在 design.md:262-265/278-281;11-03 晚提交、11-04 18:00 硬死线;ML 实验 0 文件(实验 A/B 与 ~120 CRP、结论口径=design.md:385-402)。
- C17: 遗留外部复核 3 项(DS9~DS11 含义/USB 丝印实测/JTAG 线型);教程现保守写「以实物丝印为准」。

## C 组 · 一致性/过度声明
- C18【v2|F10】: 纯 PC 清单与 HANDOFF 一致,无杜撰(尤其 §四 遗留问题节;B5 见 §五:223,tb_speck 毛刺见 §二:112,RemoteException 见 §二:105;文档存在两个「§四」:L46 交接节与 L140 主体节)。
- C19: 「HTML 已刷新至 A1 完成态」(1a4d65e,10-08)与「看板过时(未反映 10-10 适配)」并存不矛盾。
- C20: 板级验证=0/系统联调=0 仍准确(未烧板);但 ZC702 已尝试上电(DS14 亮/DS13 不亮),architecture.html「从未上电验证」笼统措辞过时(:301/:303 带限定语的仍准确)。

## D 组 · 板卡事实精确定位
- C21: 教程 L58/L360/L388/L389/L390、XDC L25/L29、board README L8 行号与引文逐字核实。
- C22: board_facts.json 系历史审查证据(MD5 快照),其「DS 对应待核实」为当时口径,后被 UG850 确认 DS15~DS18;不应回改。

## E 组 · 排期/交付/风险
- C23: design.md 风险表 8 项(L417-424)与依赖图(L428-440)转述一致。
- C24: mindmap W4 附加项与 W5-W6 清单大部分已纳入附录;v1 附录确有遗漏(AI 扩展闭环、W5-W6 七细项),v2 附录已补。
- C25: 「约 27 天」基于 10-08 看板;今日 10-12,实余约 23 天。

## 附录 · 主会话梳理的完整待办清单 v2

### 一、纯 PC 可立即做
B5 PUF 真实接入; P1-1 真密钥; P1-5 终端跨断电重放(三选一); 44-bit 熵混合; P2-1 故障注入加固;
预认证池 DoS 三子项: per-tid 限速 / 暂存-释放式 draw / 池补充 SOP【v2|F9】;
setkey getpass / c2reset 审计 / DeviceKeyStore 文件锁 / DPAPI 可选; 互操作 harness 固化 tests/; CI 超时作业化;
SimulatedHSM 决策 + save_secret 对齐; enroll.py + 注册语义配对; on_confirm 接线; tb_speck 输入毛刺; 日志 RemoteException;
B6 ML 实验 A/B + 评估工具适配; D13 报告初稿; D14 Skill 打包(≥2 可运行脚本)

### 二、需板卡(ZC702)——按前置顺序
0.【v2|F2】板卡电源故障排查(另一会话处理中,当前一切上板工作的前置): 重插 J60 → 断电重启 → 拔 FMC/PMOD/SD 清负载 → 仍不亮判硬件故障报告老师; 可用 Mini-B 线插 J17 验证 CP2103(主机供电不依赖板内电源)
1. 出厂 BIST(SW16=00010, Tera Term 115200-8-N-1)
2.【v2|F8】上板构建前置: 在 Vivado 工程内生成 clk_wiz_0 IP(200MHz 差分→100MHz+locked;不在仓库、不参与仿真/CI) + XDC 取消注释(LED/时钟/复位/按键/拨码引脚已核,UART 电台脚待选型 FMC/PMOD)
3. 验证点① VIO 读指纹比值(10 次极差<100); 验证点② 心跳+按键; 验证点③ PC 串口环路(前置: 持续接收循环待写——SerialTransport 一问一答已有【v2|F1】; FMC/PMOD 未选; 断电插拔)
4. W4 板上: 温度实验(ΔT≤30°C/70°C 硬停)与可靠性 vs 温度曲线【v2|F14】; PUF 核心假设验证; 多终端并发(实例 0~3); AI 扩展最小闭环(BNN/PQN overlay 或任务帧,教师要求)【v2|F3】; 电台半双工适配 + 无线联调参数(air rate 64k/ECC/NETID)【v2|F14】

### 三、需采购
433MHz SiK 电台一对 + USB-TTL×2; 第 2 块板(降级: 单板+软仿冒者/预录视频)

### 四、文档/仓库卫生
四份 HTML 看板刷新; DS 位号修正(教程 5 行 + XDC 2 行; **修正范围不含 build/reviews/tutorial/ 五份历史 JSON——repo_facts/walkthrough/board_facts/fix_verify/new_angle 均为入库审查证据不回改**【v2|F12】);
board README 三口修正(**以当前 L8 文字为定位基准**,HANDOFF §四 旧引文已过时;按 UG850 J17/U23/J1 改写并删行尾 "+ IOSTANDARD")【v2|F13】;
外部副本同步(保姆教程_W1_...md 与仓库 SHA256 一致,改其一须同步); 旧克隆删除(待用户确认); fpga_work/build-vivado 迁移定夺; 外部复核 3 项

### 五、W5-W6 交付细项【v2|F4 新增】
功能冻结令; 全量指标实测(ROC/EER+时延+资源+NIST); 纯 PC 软件基线对比; 视频 v1+终版; 复现包(从零跑通文档); 决赛彩排+答辩 QA 演练; 个人 Verilog 功课(决赛基础编程考核); G5 门禁四件套(互斥演示/CRP 全流程/ROC-EER/报告+视频); 11-03 晚提交

### 六、已知限制(非必做)
C2 回绕 256; 灰区 Level 3 完整路径待核实(GE1/GE2 灰区与 GH 重放用例在 tb_gap_regression)【v2|F5】; uart_rx 无独立 TB; Vivado 许可 11-23 到期前存档比特流;
【v2|F15】CRP 池余量<20% 触发重注册为运行期条件预案(design.md:420),非当前待办

## 共识盲区(未闭环,列此提示)
1. 教程验收数值口径(0.75Hz 心跳/1.34s/10 秒约 15 次翻转)与 RTL 心跳分频参数的交叉验算未做——复审代理补验。
2. 教程外部副本唯一性未全面枚举(仅核验已知一份)。
3. DS13 排查「另一会话」的进展时效未跟踪。
4. git 远端备份状态未核验(旧克隆删除/迁移定夺前有单点丢失风险)。
