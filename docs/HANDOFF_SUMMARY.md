# PUF 无人机认证项目 · 交接摘要

## 会话交接记录（2026-10-10）

> 本节由「A1 整体复审 → 看板刷新 → 保姆教程五轮审查 → 板卡调试」会话写入。
> 板卡硬件调试继续在原对话进行；软件侧工作在新对话继续，以下为交接内容。

### 一、仓库当前状态

- HEAD：`a771f91`（工作区干净，无未提交变更）
- A1 六阶段 + 十轮审查全部完成（详见 §二～§五及 build/reviews/）
- 最近提交链（本会话新增 9 个）：
  - `fc27345` 教程去除冗余暂存步骤
  - `9ff5299` 教程三轮审查修复 + 新增 ZC702 板级 wrapper
  - `312f5de` 审查产物入库
  - `895b4fb` HANDOFF 登记板卡适配状态
  - `d17b038` 复验轮 9 项修复（build_w3_board.tcl、XDC 重写、IP reset 对齐等）
  - `3071840` 复验产物入库
  - `e26c9cc` 板卡事实修正（LED 引脚 P1）+ 新角度走查修复
  - `e62953a` 板卡事实审查产物入库
  - `a771f91` 最终审查产物（字节校验）

### 二、保姆教程最终状态（五轮审查后）

- 文件：`docs/tutorials/w1_tutorial.md`（= 用户的 `D:\文件\ssssssss\FPGA\保姆教程_W1_从零到一号验证点.md`，两份字节一致）
- 审查产物：`build/reviews/tutorial/`（repo_facts / walkthrough / board_facts / fix_verify / new_angle 五份 JSON）
- 验证：CI 12/12 TB + 44 单测 + 金丝雀 + 契约同步 = CI-EXIT 0；wrapper xvlog+xelab 通过；clk_wiz IP 配置 Vivado 实测 IP_CHECK_OK；全仓 0 BOM

### 三、板卡调试会话的硬件结论（UG850 官方依据）

- **三个 USB 口**：
  - **J17**（U36，**Mini-B**）= USB-UART 桥 CP2103GM，**由电脑 USB 5V 供电**（板子关机也能枚举出 COM 口）
  - **U23**（**Micro-B**，集成在 Digilent 模块上）= PL JTAG（Vivado Hardware Manager 用）
  - **J1**（U9，**Mini-B**）= PS USB 2.0 ULPI（OTG；无 PS 程序时**零枚举**，容易误插）
- **LED 定义**（UG850 Table）：
  - DS14 = `VCC12_P_IN`（12V 电源开）
  - DS13 = `PWRCTL_PWRGOOD`（板载各路电源正常）
  - **用户 LED**：P17=**DS15**、P18=**DS16**、W10=**DS17**、V7=**DS18**（即 w3_top_zc702 的 led_busy/heartbeat/result[1:0] 对应 DS15/16/17/18）
  - DS12 = PS_MIO8_LED0、DS23 = PS_LED1（PS 侧，勿混用）
- **电源**：J60 = 6 针 mini-fit（Molex 39-30-1060）；套件适配器 LTE65ES-S2.1（12V/5A/60W，Pin1=+V、Pin3=GND）；**严禁 ATX 6 针**（引脚不同会烧板，UG850 CAUTION 原文）
- **当前故障**：DS14 亮（12V 到位）但 **DS13 不亮（PWRGOOD 未建立）**→ 板内电源未起来 → JTAG/USB 全部无法工作
- 已排除：适配器规格/引脚（已核对为套件原装）、USB 线材（手机对照测试枚举成功）、驱动（Digilent/FTDI/CP210x 均已安装且在驱动库中）
- 下一步（板卡会话继续）：重新插紧 J60 → 断电重启 → 拔 FMC/PMOD/SD 清空负载 → 若 DS13 仍不亮则判硬件故障报告老师；同时可用 Mini-B 线插 J17 验证 CP2103（主机供电，不依赖板内电源）
- UG850 PDF 位置：`D:\文件\ssssssss\FPGA\ug850-zc702-eval-bd.pdf`（pdftotext 已提取到 %TEMP%\ug850.txt）

### 四、遗留待办（新对话需要知道的）

1. **教程 LED 位号未改完**：验收节仍写"数 DS10"，应改为 **DS16**（P18=心跳）；板卡表行"DS9~DS12"应改为 **DS15~DS18**。引脚 P17/P18/W10/V7 已正确，只是位号文字未同步。
2. **board/zc702/README.md** 仍写"Two micro-USB ports: only use the JTAG port"，应按 UG850 修正为 J17(Mini-B UART)/U23(Micro-B JTAG)/J1(Mini-B PS USB)。
3. **旧克隆待清理**：`D:\文件\ssssssss\FPGA\puf-drone-auth\`（16MB/920 文件、HEAD 5a3ec3c 旧提交、含 1 个 BOM 文件与过时教程副本）——用户尚未确认是否删除。
4. **外部复核待做**（智谱配额 10-10 21:57 重置后）：DS9~DS11 的含义（LED 表中未见）、板上 USB 口丝印实测、JTAG 口线型确认。
5. W4 backlog 不变：P1-5 终端重放修复、44-bit 熵混合、P1-1 真密钥、CI 超时作业化、SimulatedHSM 决策、互操作 harness 固化、注册语义配对（详见 §五 W4 备忘）。

生成时间：2026-10-08（**A1 全部六个阶段完成**；上版为阶段 3 后/阶段 4 后两版）
项目路径：D:\puf-drone-auth
Git：57 commits（截至 A1 收官提交 a678274）· 144 files · tag w3-complete（阶段 4/5/6 三笔提交 + 各阶段审查证据入库）

## 一、项目概况

**竞赛**：2026 全国大学生嵌入式芯片与系统设计竞赛（FPGA 创新赛道，AMD 初级组）
**截止**：11-04 18:00（距现在约 28 天）
**平台**：ZC702 (XC7Z020-1CLG484)
**项目**：XOR-CRO-PUF 硬件指纹无人机认证系统（HF-IDA 双向认证协议）
**教师要求**：回归 PUF 本体、协议不加密、论文多实现少的 FPGA 实现、扩展无人机 AI 应用、突出特色

## 二、当前进度（A1 任务）

### A1 = 统一 R2 算法（用 Speck64/96 替换不安全的 ~C2）

**已完成：**
- ✅ 阶段 1：密码核基础
  - src/python/common/speck.py（~180 行，双实现+NSA KAT）
  - src/rtl/common/speck64_96.v（133 行，4 态 FSM，53 周期）
  - sim/tb/tb_speck.v（8 用例全过）
  - NSA 官方测试向量验证通过（字节序修复后）

- ✅ 阶段 2：向量基础设施
  - scripts/gen_speck_vectors.py（5 类向量，--check 模式）
  - sim/testvectors/speck_random.mem（1175 组，6 类含 NSA KAT；阶段 6 起由 tb_speck T4 全量回放消费）
  - CI 已接入（A1 后现状：ci_regression.ps1 = 12 TB + Python 五件套 + 契约同步门禁）

- ✅ 阶段 3：FPGA 集成
  - terminal_fsm.v：新增 S_CALC_R2 状态（4'd12），Speck 实例化
  - C2 字节重排（NSA 约定）：c2[0..3]→y→pt[63:32], c2[4..7]→x→pt[31:0]
  - R2 解包：ct[39:32..]→r2[0..7]
  - 256 周期看门狗 + fp_rx_inhibit 扩展
  - DEVICE_KEY 参数：96'h13121110_0b0a0908_03020100（W3 测试值）
  - tb_terminal_fsm.v + tb_level3_protocol.v 黄金值更新
  - tb_gap_regression.v（6 安全测试：伪造R2/重放/灰区）
  - 11/11 TB 全 PASS

- ✅ 阶段 4：PC 集成（2026-10-08，经 5 轮 auto-review 共识 PASS：P0/P1/P2=0）
    - hsm.py：SpeckHSM 类（R2 = Speck64/96(K_term, C2)，per-terminal 12B 密钥；保留 SimulatedHSM）
    - protocol.py：_finish_pass 传 terminal_id；C2 防重放窗口（P1-2 修复，持久化跨重启）+ RESULT_REPLAY=4；迟到/冲突 C2 在评分前验证；HSM 故障转 RESULT_ERROR 帧
    - main.py：DeviceKeyStore（JSON 0600 原子写 + 失败回滚 + RLock）修复密钥不持久化；REPL setkey/c2reset；loopback C2 计数器对齐 RTL 语义
    - tests/test_a1_phase4.py：44 个单测（黄金向量/重启防重放 E2E/灰区路径/回滚）；CI 接入 Python 段（fail-closed 门禁）
    - 审查证据：build/reviews/a1p4/（CONSENSUS.md 终审报告 + FIXLIST.md 四轮修复轨迹 + 7 份审查 JSON）
    - 黄金对齐：REPL setkey W3 密钥后首次认证 R2 = 7b45b0545e59aa94（与 tb_terminal_fsm 逐位一致）

- ✅ 阶段 5：集成测试（2026-10-08，经 3 视角交叉审查 + 共识终审 PASS：P0/P1/P2=0，11 项 FIXED-VERIFIED）
    - 全量回归 **12/12 TB**（含新接入的 tb_w3_top 顶层链路 TB）+ Python 五件套（speck 自测 + 44 单测 + 金丝雀 + 1175 向量新鲜度 + 哨兵守卫），CI-EXIT=0
    - 线性金丝雀 scripts/test_r2_nonlinearity.py：C0 三重负对照（仿射/宽扇入 GF(2)/xor-tree 全被抓）+ C1 平衡 + C2 一阶 + C3 二阶 + **C4 精确 GF(2) 线性判定**（高斯消元，完全线性映射零漏检）——Speck 双密钥 exact-linear 0/64
    - 审查中修复的预先存在缺陷：①tb_challenge_decode 终止标记不符合 CI 约定（"11/11 全 PASS"声明从未在 CI 脚本上成立过）②gen_speck_vectors --check 恒真且静默重写销毁 stale 证据（P0，重构为纯计算比对）③CI 预置 $LASTEXITCODE 假失败（A/B 实证删除，机制未定已诚实记录）④python shim 假通过链（-CommandType Application + 哨兵探针）
    - 证据：build/reviews/a1p5/（CONSENSUS.md 终审 + 3 份审查 JSON + 4 份 CI 日志谱系 README）
    - deferred：CI 超时作业化（W4 首项）、日志 RemoteException 包装行（证据语义无损）

**未完成：**
    
- ✅ 阶段 6：文档 + 提交（2026-10-08，经 3 视角交叉审查：契约位级/文档诚实性/收官完整性）
    - protocol_contract.md：新增 §4.1 R2 生成算法定义（算法参数/三方字节序/C2 语义/黄金向量/金丝雀）+ §4 增 RESULT_A1_GOLDEN 黄金帧；check_contract_sync 扩展至 7 帧并接入 CI
    - project_design.md：hsm 接口/终端 R2 验证语义（HD→Speck 精确比对）修正 + "A1 后安全态势"诚实声明块（5 条可/不可声明）
    - **tb_speck 补齐 T4 全量向量回放**（$fgets 消费单源 .mem，1175 组全匹配——修复"向量无 RTL 消费者"P2）+ T9 时延上界（实测 53 周期）；输入毛刺用例登记为计划偏差（集成中输入恒稳，W4 可补）
    - 旧计划文档加 SUPERSEDED 版本链标注；main.py save() docstring 平台限定；伪代码示意标注
    - 证据：build/reviews/a1p6/（3 份审查 JSON）

## 三、关键技术决策（已定稿）

### Speck64/96 参数
- 字长 32 bit / 块 64 bit（=8B=R2）/ 密钥 96 bit（=12B=PUF 稳定位）/ 26 轮
- ARX 结构（无 S 盒），NSA 2013 规范
- 最好攻击只到 19/26 轮（73%），安全余量 27%

### 字节序（NSA 官方约定，已冻结）
- plaintext bytes[0:4] → y → plaintext_in[63:32]
- plaintext bytes[4:8] → x → plaintext_in[31:0]
- ciphertext 先序列化 y 再 x
- key bytes[0:4]→k0→key_in[31:0], [4:8]→l0→[63:32], [8:12]→l1→[95:64]
- 全部小端（little-endian）

### DEVICE_KEY
- 当前：96'h13121110_0b0a0908_03020100 = NSA 公开测试向量（安全=零，仅 W3 演示）
- W4 计划：从 PUF 稳定位运行时提取（16 环信息论上限 ~44 bit 根熵）

### CRC 计算域
- MAVLink v2：header[1:10]（9 字节，含 MSGID 第 3 字节）+ payload + CRC_EXTRA
- CRC_EXTRA for RESULT(0x0093) = 0x5D
- 首次认证 R2 = Speck(K, C2=a1..a8) = 7b45b0545e59aa94
- RESULT 帧 CRC = ff 1d（seq=0x50 时）

## 四、三代理审查遗留问题

### 安全类（Agent C 发现）
| ID | 问题 | 严重度 | 归属 |
|---|---|---|---|
| P1-1 | DEVICE_KEY 是公开向量 | P1 | W4 修复 |
| P1-2 | 重放窗口=现在（断电+C2回绕+服务器无检查） | P1 | ✅ 阶段 4 已修（服务器侧窗口检查+持久化；C2 回绕为 W4 已知限制，断电恢复走 c2reset） |
| P1-3 | hsm.py 仍用 HMAC | P1 | ✅ 阶段 4 已修（SpeckHSM 为默认后端，黄金向量与 RTL 一致） |
| P1-4 | PUF 占位（种子直通） | P1 | W4 修复 |
| P2-1 | 跳过 S_CALC_R2 的故障注入→安全绕过 | P2 | W4 加固 |
| P1-5 | **终端侧 RESULT 帧跨断电重放**（2026-10-08 威胁建模实证）：RTL 验证无新鲜度源——C2 上电确定性复位 A0+j → 每次上电首次 (C2,R2) 恒为 a1..a8/7b45b0545e59aa94；nonce 恒 0xDEADBEEF；SEQ 不校验。被动窃听者录帧 + 终端换电池重启后注入即冒充基站（实测通过 RTL 忠实模型复现）；**W4 换真 PUF 密钥后依然成立**（重放帧无需密钥）。服务器侧重放窗只防上行方向，与此路径无关 | P1 | W4 修复（三选一：C2 种子非易失保存/上电随机化；nonce 随机化并在 RESULT 回显校验；RESULT 绑定会话随机数）。证据：build/reviews/a1p4/security_threat.json |

### 安全复审新增 W4 待办（2026-10-08 威胁建模，P3 级）

- **预认证池耗尽 DoS**：伪造随机 C2 的 ACCESS_REQUEST 即可过重放窗消耗 CRP 池（实测 26 请求耗尽 100 种子池；R2 不泄露——PUF 轮仍门控，纯可用性）。W4：per-tid 限速 / 暂存-释放式 draw / 池补充 SOP
- **W4 密钥熵不足**：16 环 ~44 bit 根熵 + 链路明文 (C2,R2) 对 = 离线穷举 oracle（GPU 小时级恢复 K 后永久冒充基站）。W4：K = PUF_out XOR station_random 或 HKDF 混合基站侧高熵秘密；或提升根熵 ≥80 bit
- **明文对称密钥保管**：device_keys.json 明文持有全部密钥；Windows/NTFS 下 os.chmod 0600 仅只读位、无 ACL 保护（main.py docstring "owner-only" 表述在部署平台失实）；对称密钥=能读任一侧即可冒充另一侧。阶段 6 文档诚实化（可选 DPAPI）
- **c2reset/setkey 无确认无审计**：每次真终端换电池必然触发 c2reset 清空整个重放窗（与 P1-5 同源，W4 修复后例行性消失）；运维命令应加确认提示与追加式操作日志

### A1 整体复审新增备注（2026-10-08 全六阶段交叉审查，全部 P3 级）

- **SimulatedHSM 已休眠**：A1 后无任何生产调用方与测试覆盖（规格要求保留供 legacy enroll），W4 决策点：删除或补 3-4 行最小单测防 bit-rot
- **on_confirm 无运行时调用方**：HF-IDA 最后一步（基站确知终端已验证 R2）的 PC 侧消费在串口接收环路落地时必须接线（W3 上板清单第 5 条的自然延伸）
- **互操作 harness 固化建议**：整体复审的跨阶段实演（RTL 语义终端模型↔真实服务器栈，18/18 断言：黄金 R2/重放拒止/跨重启持久/灰区/CONFIRM 闭环）价值高，建议 W4 固化为 tests/test_interop_rtl_model.py（本次为一次性证据，见 build/reviews/a1full/interop_run.json）
- **串口联调前置：注册语义配对**：当前 loopback 终端响应=HMAC、RTL W3 占位=种子直通——未来串口环路联调时，enroll 必须用与终端一致的响应语义（或对真实终端注册），否则 PUF 评分必 REJECT、易误判为协议缺陷
- 本轮已顺手修复：tb_level3 两处 ~C2 过时注释、tb_gap 新增 GH 用例（码 4 + 正确 R2_7 → REJECT，锁定阶段 4 语义）、check_contract_sync 输出措辞诚实化（TB 数组为人工镜像，工具不读）
- **setkey 明文输入通道**（安全编码扫描）：密钥以 REPL 参数明文输入，留存于终端回显/录屏/脚本日志。W4 接真实密钥前改 getpass 隐藏回显或从 0600 文件/环境变量导入
- **DeviceKeyStore 跨进程 last-writer-wins**（安全编码扫描，实验实证）：两服务器实例共享同一密钥文件时，陈旧实例的 save 会静默抹除另一实例的新密钥（单实例 REPL 假设下可接受）。W4：文件锁或 mtime 失配检测
- **SimulatedHSM.save_secret 遗留 API**（安全编码扫描）：明文 write_text、无 0600/原子写，低于 DeviceKeyStore 新基线；全仓无调用方。W4 前删除或对齐基线

### 覆盖类（Agent B 发现——已修复）
- ✅ 伪造 R2 测试 → tb_gap_regression GF
- ✅ 二次认证测试 → tb_gap_regression GD1/GD2  
- ✅ 灰区测试 → tb_gap_regression GE1/GE2

### 集成类（Agent A 发现——已修复）
- ✅ speck.py 文档字符串字节序写反 → 已修
- ✅ terminal_fsm 死代码 ~C2 → 已删

## 五、项目全景

### 文件结构
- src/rtl/ — 15 个 Verilog 模块（~2400 行）
  - common/：crc16, mavlink_frame, frame_parser, byte_fifo, uart_tx/rx, speck64_96
  - w1_ratio/：ro_ring, ro_div, ro_ratio_top
  - w2_array/：ro_array, challenge_decode, w2_top
  - w3_protocol/：terminal_fsm, w3_top, w3_top.xdc
- src/python/ — 11 个 Python 文件（~2600 行）
  - common/：speck.py
  - server/：protocol, crp_pool, template_db, threshold, hsm, main
  - evaluation/：hamming_analysis, compare_devices, quantizer
- sim/tb/ — 11 套 TB（~2100 行）
- sim/testvectors/ — speck_random.mem（1175 组）
- scripts/ — ci_regression, setup_external, gen_speck_vectors
- build/tcl/ — synth_w3.tcl, build_w3.tcl
- docs/ — protocol_contract, project_design, architecture.html, plans/

### 六周排期
- ✅ W1 信号验证（ro_ring + Artix-7 综合）
- ✅ W2 阵列 + B 线 Python 全套
- ✅ W3 协议栈 + 顶层 + 比特流（A1 已完成）
- ⬜ W4 实验周（ML 攻击 + 温度 + PUF 接入——纯 Python 部分可提前）
- ⬜ W5 冻结周（报告 + Skill + 视频）
- ⬜ W6 交付周（11-03 提交）

### 上板前必做清单（保姆教程三轮审查后的状态，2026-10-10）
1. **填入 ZC702 真实引脚**（查 UG850 + 主 XDC）——⬜ 待做：`w3_top.xdc` 仍全部注释；
   LED 四行原本只有 PACKAGE_PIN、缺 IOSTANDARD（不补会被 DRC NSTD-1 拦）；`auth_btn` 原本没有对应行，已补注释占位（无引脚则 2.5 测 3 跳过）
2. **时钟适配**——✅ 方案已落地：新增板级 wrapper `src/rtl/w3_protocol/w3_top_zc702.v`（clk_p/clk_n 差分 → `clk_wiz_0` → 100MHz；xelab 已验通过，见下）
   **w3_top 端口一行不改**（改端口会破坏 `tb_w3_top`，且 Clk Wizard IP 无仿真源）→ 12/12 CI 不受影响
   上板时须在 Vivado 工程内生成 `clk_wiz_0`（200MHz 差分 → 100MHz + locked），wrapper 不参与仿真/CI
3. **复位源**——✅ wrapper 已组合：`rst_n = sys_rst_btn_n & mmcm_locked`（按键低有效 + MMCM 未锁持续复位，两者不冲突）
4. **购买 433MHz 电台一对**——⬜ 待做
5. **PC 串口通信循环**——⬜ 待做（前置：选定 FMC/PMOD 的 UART 引脚；**插 FMC 前必须断电**，官方禁止带电插拔）
6. **拨码开关不够 8 位**——✅ 已在 wrapper 内解决：`term_id_dip[1:0]`（W6/W7）+ 内部 `{6'h00, term_id_dip}` tie 高位，无需手工改代码

> 支撑改动：`build_w3.tcl` 原先**完全不加载** `w3_top.xdc`（引脚约束在批处理流里静默失效）——已补 `add_files -fileset constrs_1`。
> 教程：`docs/tutorials/w1_tutorial.md` 经三轮独立审查（仓库事实 / ZC702 硬件 / 端到端走查）修正 20+ 处，
> 证据 `build/reviews/tutorial/{repo_facts,walkthrough,fix_verify,new_angle}.json`；新增 wrapper 以 xvlog+xelab 实证可编译可 elaborate（clk_wiz 用临时 stub）。

### 纯电脑端可做的 21 项任务
详见对话中的盘点，优先级最高的剩余项：
- ~~A1 阶段 4-6~~（已全部完成，见 §二）
- B5 PUF 真实接入（W4 核心创新）
- B6 ML 攻击实验（W4 交付物，20 分）
- D14 Skill 打包（15 分）
- D13 报告初稿（15 分）

## 六、工作方式约定

- 所有 RTL 遵循 rtl-guardrails（Verilog-2001，无 output reg，同步复位，声明时初始化）
- 每个阶段完成后用 auto-review 派遣多代理审查
- 审查发现按 P0→P1→P2→P3 修复，修复后跑全量回归
- CI：scripts/ci_regression.ps1 = 12 TB + Python 段（哨兵探针 + 五道检查：speck 自测 / 44 单测 / 金丝雀 / 向量新鲜度 / 契约同步）
- 提交信息详细描述改动内容和原因

## 七、下一步（新会话直接从这里开始）

**A1 已全部完成**（六阶段 + 五轮多代理审查，证据 build/reviews/a1p4~a1p6/）。选择下一任务：

1. **B5 PUF 真实接入**（W4 核心创新，最高优先）：替换种子直通占位 → challenge_decode + ro_array 真实测量；同时处理 W4 安全项（P1-1 真密钥 / P1-4 PUF / P1-5 终端重放三选一 / 44-bit 熵混合 / CI 超时作业化）
2. **B6 ML 攻击实验**（W4 交付物，20 分）：实验 A 合成 arbiter 基线 + 实验 B 排序重构攻击（设计见 project_design.md §W4）
3. D14 Skill 打包（15 分）/ D13 报告初稿（15 分）

上板前必做清单仍见 §五（真实引脚/时钟适配/复位源/电台/串口循环）。
