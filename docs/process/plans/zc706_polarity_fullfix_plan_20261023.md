# ZC706 按键极性翻案 · 全量修复执行计划（2026-10-23）

> **依据**：`HANDOFF_zc706_bringup_20261023.md` §三任务清单 + 三路全量盘点（RTL/构建、文档、CI 管线，2026-10-23 10:00–10:20 三子代理报告，Lead 已复核关键分歧点）。
> **基准事实**：SW13(PL_CPU_RESET, A8) 与 SW7(GPIO_SW_LEFT, AK25) 板上实测 **空闲=0 / 按下=1**（2026-10-22 23:27 health 灯语实证）。全项目原假设（空闲=1/按下=0、SW13 低有效）作废。
> **真根因**：wrapper `.reset(~sys_rst_btn_n)` 空闲时恒 1 → MMCM 上电锁死复位，历史 bitstream 设计从未运行。
> **执行约定**：各阶段自洽、可独立执行；文中行号是 HEAD=d908eae 工作树快照，**执行时一律用锚文本定位（edit 工具字面匹配），不盲信行号**。
> 仓库 `D:\puf-drone-auth`，工作区 `D:\文件\ssssssss\FPGA`，Vivado 2026.1。

---

## Phase 0 事实基线（盘点已完成，本计划依据）

### 0.1 权威命令与判据（全部从仓库根 D:\puf-drone-auth 执行）

| 动作 | 命令 | 成功判据（精确串） | 失败判据 | 实测时长 |
|---|---|---|---|---|
| wrapper 门禁 | `powershell -File build\ps1\verify_wrapper.ps1` | `VERIFY_WRAPPER_PASS` | `VERIFY_WRAPPER_FAIL (...)` | 秒级 |
| CI 回归 | `powershell -File scripts\ci_regression.ps1` | 逐项 `[PASS] <tb>` + `=== 17/17 PASS, 0 FAIL ===` + exit 0 | `COMPILE FAILED` / `ELAB FAILED: <tb>` / `[FAIL] <tb>` / `PYTHON xxx FAILED` | 12-TB 时代全量 13.1min；17-TB 无存档，预算 ~15min |
| 板级构建 | `& 'D:\vivado\2026.1\Vivado\bin\vivado.bat' -mode batch -source build\tcl\build_w3_board.tcl -tclargs xc7z045ffg900-2 build\board_zc706 src` | 中途 `LUTLP-1 waiver nets: 32 (expect 32 = ro_array 16 + ro_entropy 16)` + 末行 `BITSTREAM_SUCCESS WNS=<n>`（n≥0）；产物 `build\board_zc706\w3_top_zc706.bit` | `ERROR: srcdir...` exit 2 / `LUTLP-1 waiver matched ZERO nets` exit 5 / `TIMING_FAILED WNS=<n>` exit 4 | 热跑 4.4–4.8min；冷跑 28min |
| health 构建（备用） | `vivado -mode batch -source build\dbg\build_health.tcl`（无参数，必须仓库根起跑） | `HEALTH_BUILD_SUCCESS`；产物 `build\board_zc706_health\health_top.bit` | — | 2.7–3.7min |
| 烧写 | vivado batch 跑 Tcl（模板 `D:\文件\ssssssss\FPGA\_tmp\prog_health.tcl`） | `HEALTH_PROGRAM_OK` 同型自定义串 | connect/open_hw_target 报错 | 秒级 |

⚠ 第 3 个 tclargs 必须是 `src`（不是仓库根）。⚠ 烧写前置：hw_server localhost:3121 在线、`get_hw_devices` 选 **xc7z045_1**（不是 arm_dap）。

### 0.2 关键结构事实（盘点实证）

- **CI 不编译 wrapper**：ci_regression.ps1 RTL 清单（:106-116）无 w3_top_zc706.v；wrapper 唯一门禁=verify_wrapper.ps1（只 xelab 不仿真，**极性错误结构性抓不到**）。修复后端口名不变，门禁仍通过。
- **极性波及 TB 恰好 3 个**：tb_w3_top.v / tb_w3top_keyloop.v / tb_w3_top_seedgate.v（仅它们例化 w3_top、驱动 auth_btn）；tb_terminal_fsm / tb_puf_path / tb_level3_protocol 直接驱动 auth_start 脉冲，**不受影响**；全仓库 TB 无 dut.btn_state 引用（极性锁全锚 dut.auth_start_pulse）。
- **RTL↔TB 强耦合**：RTL 回退 btn_state=1'b0 时，旧 TB（空闲建模=1）会自己制造 0→1 幽灵沿，T0 静默窗必炸——**改漏任何一边 CI 必红（这是保护，不是麻烦）**。
- **auth_btn 极性依赖面**：仅 w3_top.v 与 build/dbg/w3_top_dbg.v 的消抖+边沿两处；其余模块零依赖。
- **health_top.v 已是修正版**（L18 直连高有效 + "板上实测"注释；mtime 23:29 为 build/dbg 最新）——wrapper 修复的正确参照物。
- **XDC 电气层无错**：A8/AK25 的 set_property 引脚/电平正确，全仓库无任何 PULL 约束；health 实测证明板路自偏置空闲=0。
- **诊断副本污染且误用可达**：build_ila.tcl / build_dbg2.tcl 以 dbg_top_zc706 为 top，照抄重跑会把错误极性再烘焙进新 bitstream。
- **上位机代码零波及**：scripts/ 与 src/python 全量 grep 无按键提示文本。

### 0.3 已裁决决策点（执行时不再讨论）

| # | 决策 | 裁决 | 理由 |
|---|---|---|---|
| D1 | 触发语义 | **保持上升沿触发表达式不动**，物理含义变为"按下瞬间触发"；所有文档"按一下并松开"改为"按下即触发" | HANDOFF §三.1 明示表达式不动；改边沿属无收益变更 |
| D2 | 端口名 `sys_rst_btn_n` | **不改名**，在端口注释标注命名陷阱（_n 后缀承载高有效信号；改名波及 XDC get_ports/health/烧写脚本） | 最小 diff 原则，避免涟漪 |
| D3 | XDC 是否加 PULLDOWN | **不加** | health 实测无 PULL 约束时空闲=0，板路自偏置已实证 |
| D4 | ZC702 遗产（w3_top_zc702.v、w3_top.xdc、w1_tutorial、保姆教程、两份 handoff_summary） | **一律不动**，在本计划风险表登记方法论风险 | ZC702 板已退役，其极性从未板测；ZC706 翻案不构成反证但同属"图纸推断未实测" |
| D5 | build/dbg 诊断副本 | **修复而非删除**（与出货 RTL 同步改），防止未来诊断构建误用错误版本 | build_ila/build_dbg2 重跑可达 |
| D6 | 提交拆分 | 按用户惯例 **rtl / test / docs 三笔**；test 提交信息注明"rtl 单独 checkout 时 CI 红（极性配对变更）" | HANDOFF §三.4；bisect 代价已知悉 |
| D7 | rtl-guardrails `check_style.py --fix` | **不用 --fix**（会整文件重排污染 diff）；用 check-only 确认未引入新违规；如需全文件规整另立独立提交 | 本次是外科手术式 5 行+注释修改 |

### 0.4 明确不做（反模式总纲）

- 不改协议栈任何文件（terminal_fsm/mavlink/uart/speck/…零改动，HANDOFF:34 实证健康）
- 不改 PUF 子系统（ro_array/ro_entropy 零改动）
- 不改 w3_top 端口表、不 rename 任何信号
- 不原地改写历史证据文档（hw_facts/bringuo_fix/synthesis_round1——只加勘误 banner）
- 不动 ZC702 遗产（D4）
- 烧写前必须先向用户打招呼（用户偏好，2026-10-22 授权已过期）
- "health 灯语固件写入 runbook 作为 bring-up 第一步"（HANDOFF §三.5 可选项）本计划不做，登记为后续顺手项

---

## Phase 1 RTL / XDC / 构建脚本终修（→ commit 1: fix/rtl）

> **锚文本执行注意**：表中锚含"…"的均为截断展示，edit 时必须展开为实际整行做字面匹配；跨行注释块（如 w3_top.v:151-154 心跳注释，正文实际在 152/153 行折行）先按行区间读出整段再整段替换，禁止单行字面匹配跨行内容。

### 1.1 src/rtl/w3_protocol/w3_top_zc706.v

| 锚（现行文本） | 改为 |
|---|---|
| :56 `.reset     ( ~sys_rst_btn_n ),   // IP 复位高有效 <- 按键低有效取反` | `.reset     ( sys_rst_btn_n   ),   // IP 复位高有效 <- 按键高有效直连（板上按下=1）` |
| :62-63 `// 按键低有效 AND MMCM 已锁定…双保险` + `wire rst_n = sys_rst_btn_n & mmcm_locked;` | 注释改"按键高有效：按下=复位；MMCM 未锁定持续复位（双保险）" + `wire rst_n = ~sys_rst_btn_n & mmcm_locked;` |
| :70 `.SEED_GATE_EN ( 0        )` | `.SEED_GATE_EN ( 1        )` |
| :70-75 三要素旁路注释整块 | 重写：旁路依据（熵卡死屏蔽按键）已被 2026-10-23 翻案作废——设计从未出复位，E_IDLE 是复位假象；恢复 P1-5 门控，豁免条目见 build/reviews/zc706_bringup/HANDOFF_20261023_根因翻案.md |
| :35 端口注释 `// SW13 PL_CPU_RESET（低有效，A8）` | `// SW13 PL_CPU_RESET（A8）板上实测：空闲0/按下1（高有效，2026-10-22 23:27 health 实证；端口名沿用 _n 是历史命名，勿按名推极性）` |
| :36 端口注释 `// SW7 GPIO_SW_LEFT（空闲1/按下0，UG954 Table 1-29…）` | `// SW7 GPIO_SW_LEFT（AK25）板上实测：空闲0/按下1（2026-10-22 23:27 health 实证，推翻 UG954 图纸解读）` |

### 1.2 src/rtl/w3_protocol/w3_top.v（回退 auto-review M9 误修）

| 锚 | 改为 |
|---|---|
| :100-101 `reg btn_state = 1'b1;` / `reg btn_prev = 1'b1;` | 声明初值回 `1'b0` |
| :106-107 复位分支 `btn_state <= 1'b1; btn_prev <= 1'b1;` | 回 `1'b0` |
| :93-99 M9 注释块（"初值=1 板级空闲电平…幽灵认证…"） | 重写：初值=0=板级空闲电平（板上实测空闲0/按下1）；auto-review M9 曾按 UG954 图纸极性改成 1'b1，方向反了——真极性下复位值 0 与空闲一致，无幽灵沿；"幽灵沿/熵卡死屏蔽按键"双根因已翻案（证据同上） |
| :38-43 SEED_GATE_EN 参数注释（"bring-up 修复…环振未起振屏蔽按键"） | 重写：参数=熵门控开关（P1-5）；板级曾因误判旁路（=0），2026-10-23 起恢复默认 1；TB 双向锁定其语义 |
| :136-141 auth_start_pulse 上方 C-F2 注释中 `SEED_GATE_EN=0（板级 bring-up）时旁路熵门控：防 seed 卡死把按键屏蔽` 句 | 删除旁路理由句，保留 C-F2 窗口压制原理句 |
| :151-154 心跳注释中 `SEED_GATE_EN=0 旁路后死熵与活熵的板上现象靠此区分` | 改为：门控恢复后快闪（seed_fault=1）同时意味着认证被 fail-closed 压制——板上快闪=熵子系统需修 |

⚠ :140-141 `auth_start_pulse` 表达式**一个字符都不动**（D1）。

### 1.3 src/rtl/w3_protocol/w3_top_zc706.xdc（仅注释两行）

- :20 `# === RESET：SW13 PL_CPU_RESET（A8，bank34，LVCMOS15！低有效）===` → `…（A8，bank34，LVCMOS15！板上实测高有效：空闲0/按下1）===`
- :23 `# === AUTH 按钮：SW7 GPIO_SW_LEFT（AK25，bank11，空闲1/按下0）===` → `…（AK25，bank11，板上实测：空闲0/按下1）===`
- :21/:24 set_property 行**不动**（电气正确；不加 PULLDOWN，D3）

### 1.4 build/tcl/build_w3_board.tcl

- :48 注释 `…reset（wrapper 里接 ~sys_rst_btn_n）` → `…reset（wrapper 里直连 sys_rst_btn_n，板上高有效）`

### 1.5 验证（Phase 1 出口条件）

1. `powershell -File build\ps1\verify_wrapper.ps1` → `VERIFY_WRAPPER_PASS`
2. `python "D:\文件\ssssssss\FPGA\.dsh\skills\rtl-guardrails\scripts\check_style.py" src/rtl/w3_protocol/w3_top_zc706.v src/rtl/w3_protocol/w3_top.v`（**无 --fix**；路径已实测存在）——不得引入新 ERROR
3. grep 复核 `src/rtl` 与 `build/tcl`：`空闲1/按下0`、`按键低有效`、`SEED_GATE_EN ( 0` 零命中（豁免注释里的"已作废"引述除外）
4. `git diff -w` 逐块人工过目：只有预期 5 处代码值 + 注释变化，无夹带

---

## Phase 2 TB 极性回退（→ commit 2: test）

三个 TB 与 RTL 同拍改（0.2 耦合警告）。新极性建模统一为：**空闲=0，按下=1，0→1 上升沿（按下沿）触发**。

### 2.1 sim/tb/tb_w3_top.v

- :16 `reg auth_btn = 1'b1;` → `1'b0`，注释改"板级空闲电平（板上实测空闲0/按下1）"
- T0 静默窗（btn 保持 0，220k 拍）断言改为：`pulse_cnt === 0` **且** `dut.btn_state === 1'b0`（复位值=空闲电平不变量锁）+ `dut.btn_prev === 1'b0`
- T1 流程：`auth_btn = 1'b1`（按下）→ guard 轮询（≤300k 拍）等 `pulse_cnt >= 1`（消抖 ~100k 拍出 pulse）→ 记快照 p0 → 再保持 ≥220k 拍断言 `pulse_cnt == p0`（**首个 pulse 后计数不再增长**）→（可保持亦可拉低，回环等待不受影响）→ 原 1M 拍回环/BLOCKED 断言不动
- M3 计数器与 PASS 串 `TB_W3_TOP_PASS` 不动；看门狗核算：10+220k+300k+220k+1M ≈ 1.74M 拍=174ms < 250ms，**沿用 250ms**
- 所有"按下(1→0)/松开(0→1)/松开沿极性锁"注释按新极性重写

### 2.2 sim/tb/tb_w3top_keyloop.v

- :12 init 回 `1'b0` + 注释更新；T0 同 2.1（加 btn_state 锁）
- 触发段：按下 `auth_btn=1'b1` → guard 等 `fsm_key_valid`（600k 上限保留）→ T7-2/3/4、T13 断言全部不动（黄金值/熵种子链路与极性无关）
- **按住稳定锁**：首个 pulse 后 ≥150k 拍计数不增长（替代旧"按住期零触发"）
- ⚠ **看门狗重算（已落定 #160_000_000）**：新最坏线 = 复位 10 + 静默 220k + 按下→首 pulse guard ≤300k + 稳定窗 150k + fsm_key_valid guard ≤600k ≈ 1.28M 拍 = 128ms > 现 120ms → 看门狗统一改 **#160_000_000**（各 guard 是上限、实际提前退出，160ms 留 ~25% 余量；不再二选一）

### 2.3 sim/tb/tb_w3_top_seedgate.v

- :22 三个 btn init 回 `1'b0` + 注释；:5-15 头注释重写（旁路"板级修复主张"已作废；本 TB 价值=SEED_GATE_EN 参数机制双向回归锁，板上已恢复=1）
- T1 静默窗（220k）三 DUT 零触发断言保留（可加 dut_a.btn_state 锁）
- **T2/T3 时序对调**：T2=三 DUT 同时按下（0→1）→ guard ≤400k 等 `pulse_a>=1 && pulse_c>=1`（消抖 ~100k 拍出 pulse）→ T3（旁路+熵未完成放行）/T8（旁路+零熵被拒仍放行）判定原文保留
- T5：按下后再等 150k 拍断言 `pulse_b==0 && busy_b==0 && dut_b.u_fsm.state==0`（门控 fail-closed，判定原文保留）
- **按住稳定锁**：A/C 首 pulse 后 ≥150k 拍计数不增长；B 全程零
- T3b（A→BLOCKED，guard 500k）不动；T6/T9/T9b（零熵 seed_fault/心跳编码）不动
- 看门狗核算：10+220k+400k+150k+150k+500k ≈ 1.42M 拍=142ms < 250ms，沿用

### 2.4 验证（Phase 2 出口条件）

1. 单独快跑三 TB（可选，用 ci_regression 同款 xvlog/xelab/xsim 命令）确认 PASS 串
2. grep：三 TB 中 `1'b1;   // 板级空闲`、`松开` 触发叙述零残留

---

## Phase 3 门禁 + CI 全量回归（Phase 1+2 合并出口）

1. `powershell -File build\ps1\verify_wrapper.ps1` → `VERIFY_WRAPPER_PASS`
2. `powershell -File scripts\ci_regression.ps1` → **`=== 17/17 PASS, 0 FAIL ===`**（预算 15min；若 3 个极性 TB 红，按 0.2 耦合清单排查是驱动值/断言/看门狗哪处漏改）
3. 记录日志末尾摘要供证据文档引用

---

## Phase 4 诊断副本与辅助文件修复（工作树，不入 commit——build/dbg 未跟踪）

### 4.1 build/dbg/dbg_top_zc706.v（与 1.1 同型）

- :65 `.reset(~sys_rst_btn_n)` → 直连；:72 `rst_n` → `~sys_rst_btn_n & mmcm_locked`；:79 `.SEED_GATE_EN(0)` → `(1)`；:35/36/71 注释同步（参照 health_top.v:18 的写法）

### 4.2 build/dbg/w3_top_dbg.v（与 1.2 同型）

- :108-109/:114-115 btn 初值+复位值回 `1'b0`；:101-107/:148 注释按翻案重写

### 4.3 build/dbg/health_top.v

- 代码不动（已是正确版）；:5 端口注释补一句命名陷阱说明（同 1.1 :35）

### 4.4 工作区 _tmp 一次性脚本（低优先，防误导）

- `_tmp\build_dbg_vio.tcl:48` 注释同 1.4 改法；`_tmp\prog_fix.tcl:11` puts 串标注"该 bit 描述的修复已翻案，仅存档"

### 4.5 验证

- grep `build/dbg/*.v`：`~sys_rst_btn_n`、`SEED_GATE_EN ( 0`、`空闲1/按下0` 零命中（health_top 的历史注释除外）
- （可选）重跑 build_health.tcl 确认诊断链路仍 `HEALTH_BUILD_SUCCESS`——仅当后续还要用灯语诊断时

---

## Phase 5 板级构建

- 命令见 0.1（tclargs 第 3 参=**src**）
- 判据：`LUTLP-1 waiver nets: 32` + `BITSTREAM_SUCCESS WNS=<n>`（n≥0；参考基线 WNS 2.023/1.821）
- 核对产物 `build\board_zc706\w3_top_zc706.bit` mtime 为本次

---

## Phase 6 烧写 + 板上验收（⚠ 用户参与，烧写前打招呼）

### 6.1 烧写

1. 前置检查：hw_server localhost:3121 可连（可先跑 `_tmp\query_hw.tcl` 探测；昨夜 GUI Vivado PID 14752 今日未必还在，不通则请用户开 Vivado HW Manager 或授权起 hw_server）
2. 新建 `_tmp\prog_w3.tcl`（复制 prog_health.tcl 模板）：`PROGRAM.FILE {D:/puf-drone-auth/build/board_zc706/w3_top_zc706.bit}`，device 取 `xc7z045_1`（**不是 arm_dap**），成功串改 `W3_PROGRAM_OK`
3. **烧写前向用户确认**（D 约定）

### 6.2 板上验收脚本（请用户操作，两个分支都要有预期）

| 操作 | 预期（熵正常分支：DS35 慢闪 0.75Hz） | 预期（熵故障分支：DS35 ~3Hz 快闪=seed_fault=1） |
|---|---|---|
| 空闲 | DS35 0.75Hz 慢闪 | DS35 ~3Hz 快闪 |
| 按住 SW7 约 1s 松开 | DS9 亮 ~2s → DS8+DS10 同亮（BLOCKED=无站应答的正常结果） | **SW7 无反应（fail-closed 门控压制，属预期）** → 转"环振诊断跟踪任务" |
| 按下 SW13 | 全灭（复位中）；松开心跳重闪、结果灯灭 | 同左 |

- 慢闪=熵子系统首次真检验通过，P1-5 完整闭环，旁路彻底了结
- 快闪=环振真死 → 后续走 VIO/ILA 16 环计数采证（HANDOFF §三.5，不在本计划内）
- 结果记录进 Phase 7 证据文档

---

## Phase 7 文档全面勘误 + 证据链（→ commit 3: docs）

### 7.1 docs/process/plans/zc706_migration_plan.md

| 锚 | 动作 |
|---|---|
| :26-27 事实卡极性行 | 勘误：SW13 高有效（板上实测）、SW7 空闲0/按下1；标注"2026-10-22 23:27 板上实测推翻 UG954 图纸解读" |
| :53 步骤模板"低有效"句 | 同步勘误 |
| :57 auth_btn 极性确认段 | 重写：按下瞬间触发（上升沿=按下沿）；标注原"松开后启动"结论来源=错误极性 |
| :58 "其余一律不动：…rst_n = sys_rst_btn_n & mmcm_locked…" | 加勘误注：该"不动"指令正是错误 wrapper 的来源，已修正 |
| :80/:82 XDC 模板注释 | 同 1.3 |
| :178 Phase 6"按一下并松开" | 改"按下即触发" |
| :201 Phase 7 豁免引用/:225 Phase 8 豁免 banner/:233 步骤 6 挂起 | 全部改"豁免已撤销（依据作废）"，恢复原验收步骤 |
| :293-306 豁免条目整节 | 标题加"【已撤销 2026-10-23：依据作废】"，正文保留作历史，末尾补翻案引用；:306 决策记录勘误（"双根因"叙述作废） |

### 7.2 docs/process/tutorials/zc706_board_runbook.md

- :112 SW7 行："按下即触发认证（板上实测按下=1，上升沿=按下沿）"；:113 SW13 行："高有效，按下=复位"
- :122 DS35 行：改"快闪=熵零熵被拒，**门控恢复后认证同时被压制**（fail-closed）"
- :146/:151 busy 时序叙述："按下后亮"；:252 的"按下去再松开"措辞改"按下"（:253 是空行，文本在 :252）
- :277 bring-up 豁免门槛条、:307-310 Stage 6 例外 banner：撤销/改写为"门控已恢复（2026-10-23），Stage 6 恢复执行"
- 顺带修 :114/:367 mojibake（\u 转义乱码，与极性无关的既存瑕疵）

### 7.3 docs/process/tutorials/zc706_tutorial.md

- :37（速查表 SW13 行）、:38（SW7"按一下再松开"）、:117（器件表 SW13 低有效）、:253（操作清单）、:327（故障表"上升沿=松开沿"机制叙述）按新极性勘误

### 7.4 证据链（build/reviews/zc706_bringup/）

- **HANDOFF_20261023_根因翻案.md 扩写成完整翻案证据文档**：health 灯语观察表（空闲四灯全灭/按 SW13→L亮+0闪/按 SW7→C亮/极性修正版 0闪+L亮）+ 时间线（20:13→23:35 全程）+ 作废清单五条 + CI/构建/板上验收结果（Phase 3/5/6 回填）
- **hw_facts_ug954.md 加勘误 banner**（顶部）：仅"按键空闲=1/按下=0"结论被板上实测推翻（L45/L61/L67）；DIP ON=1、LED 高有效两条结论未翻案仍有效——banner 要圈定范围
- **bringuo_fix_20261022.md 加勘误 banner**：双根因（幽灵沿/熵卡死）与"0 灯亮=时钟冻结"均已翻案，以翻案证据文档为准；原文保留
- （工作区 _tmp/synthesis_round1.md、findings_round1.json 为 scratch，头部加一行"建立在错误极性上，结论已被翻案"即可，不入库）

### 7.5 验证（Phase 7 出口条件）

- grep docs/（排除 reviews 存档与 ZC702 遗产）：`空闲1/按下0`、`低有效`（SW13/SW7 语境）、`按一下并松开`、`SEED_GATE_EN=0 旁路期` 零命中
- 三份存档 banner 到位；翻案证据文档含观察表+时间线+回填结果

---

## Phase 8 提交与终验

### 8.1 提交前三查

1. `git status`：**不得夹带** `clockInfo.txt`、`.vivado-ai/`、`build/board_zc706_*/`、`build/dbg/`（未跟踪产物）；`build/vivado_mcp/.vivado-ai/*.tcl` 三文件的工作树删除**先恢复**（`git checkout -- build/vivado_mcp`）——属 MCP 会话残留，与本次无关，保持树聚焦（是否清理另问用户）
2. `git diff -w` 复核三笔各自范围
3. CI 在完整工作树已绿（Phase 3）

### 8.2 三笔提交

1. `fix(rtl): button polarity overturn -- clk_wiz reset direct-active, rst_n invert, SEED_GATE_EN=1 restored (board-proven 2026-10-22)`（含 xdc 注释 + build tcl 注释）
2. `test: TB polarity revert to board-true idle=0/press=1, press-edge trigger (pairs with previous rtl commit)`（注明 rtl 单独 checkout CI 红）
3. `docs: polarity errata across migration plan/runbook/tutorial + overturn evidence + waiver revoked`（含本计划文件入库）

### 8.3 终验清单（全过才算完）

- [ ] CI 17/17（日志摘要留存）
- [ ] BITSTREAM_SUCCESS WNS≥0，bit mtime=本次
- [ ] 板上验收两分支之一有结论并回填证据文档
- [ ] grep 终检：src/、sim/、build/tcl/、build/dbg/、docs/（除存档 banner 与 ZC702 遗产）无错误极性陈述残留
- [ ] `git log --oneline -3` 三笔齐全，`git status` 无意外夹带
- [ ] 翻案证据文档完整（观察表+时间线+CI/构建/验收回填）

---

## 风险登记表（"潜在问题"总账）

| # | 风险 | 缓解 |
|---|---|---|
| R1 | 诊断副本重跑烘焙错误极性 | Phase 4 同步修复（D5） |
| R2 | RTL/TB 半改导致 CI 红 | 0.2 耦合清单 + Phase 3 一次性合并验证；红灯即查漏改处 |
| R3 | 环振真死（DS35 快闪）+ 门控恢复 → SW7 无反应 | 6.2 验收脚本两分支预案；快闪≠失败，转环振诊断跟踪任务 |
| R4 | hw_server 今日未起 | 6.1 前置探测 + 请用户开 HW Manager |
| R5 | ZC702 遗产同型"图纸推断未板测" | D4 不动 + 本表登记；ZC702 若回归必须先板测极性 |
| R6 | keyloop 看门狗 120ms 可能不够新时序 | 2.2 明确重算并调 160ms |
| R7 | check_style --fix 整文件重排 | D7 check-only |
| R8 | 工作树杂散（clockInfo.txt/.vivado-ai/已删 tcl） | 8.1 三查；不夹带、先恢复 |
| R9 | 行号漂移 | 全部锚文本定位 |
| R10 | ILA debug hub not detected 未解 | 明确出范围（HANDOFF §三.5），PUF 深度诊断再攻 |
| R11 | README 仍写 ZC702（非极性问题） | 出范围登记，顺手项可问用户 |
| R12 | verify_wrapper 抓不到极性（只编不仿） | 已知结构局限；真正的极性锁=三 TB 回归（Phase 2） |
