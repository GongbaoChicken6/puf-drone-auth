# Phase 1–4 + 8a 执行证据（2026-10-19，迁移计划首个执行日）

> 计划：docs/process/plans/zc706_migration_plan.md（R3）
> 门禁全部通过后提交。逐项对应计划验证清单。

## Phase 8a · RTL 注册支持（P0 修复）

| 验证 | 结果 | 关键输出 |
|---|---|---|
| xvlog/xelab（改后语法） | ✅ exit 0/0 | — |
| 全量 CI | ✅ **16/16 TB PASS + Python 全过，exit 0** | 含改后的 tb_terminal_fsm |
| tb_terminal_fsm 默认编译（ENROLL_IDLE_ACCEPT=1） | ✅ TB_TERMINAL_FSM_PASS | T1/T2/T3 PASS + **[TE1] S_IDLE accepted CHALLENGE -> R1 (no button)** + **[TE1] S_WAIT_RESULT accepted next CHALLENGE -> R1** + **[TE1 PASS] enroll flow + idle-timeout self-clear** |
| tb_terminal_fsm 负向变体（xvlog -d ENROLL_NEG，param=0） | ✅ TB_TERMINAL_FSM_PASS | T1/T2/T3 PASS + **[TEN PASS] S_IDLE ignored CHALLENGE (param=0)** |
| 其余 15 TB（param=0 默认语义黄金不变） | ✅ 全 PASS | tb_w3_top/tb_level3/tb_gap/tb_w3top_keyloop 等全绿 |

改动：terminal_fsm.v（+参数 ENROLL_IDLE_ACCEPT=0 默认；S_IDLE/S_WAIT_RESULT 两处受控 0x0091 分支，
0x0093/0x0095 判定保持在前；S_IDLE 分支带 1 拍采样窗口注记）、w3_top.v（+参数 ENROLL_EN=0 透传）、
tb_terminal_fsm.v（TE1 正向 + TEN 负向 ifdef 变体；CI 清单零改动）。

## Phase 4 · wrapper 离板语法门禁

| 验证 | 结果 | 关键输出 |
|---|---|---|
| xvlog（15 RTL + wrapper + %TEMP% clk_wiz_0 stub，**不带** PUF_MODEL_SIM） | ✅ exit 0 | — |
| xelab w3_top_zc706 -s w3_zc706_chk（真 ro_array 板级网表） | ✅ exit 0 | `Compiling module work.w3_top(ENROLL_EN=1)` —— 参数贯通实证；快照生成 |
| build/ps1/verify_wrapper.ps1 | ✅ 入库 | 后续换板/改 wrapper 复用门禁 |

## Phase 1–3 产物

- src/rtl/w3_protocol/w3_top_zc706.v（新建，rtl-guardrails 风格；PMOD UART / 4bit DIP / ENROLL_EN=1）
- src/rtl/w3_protocol/w3_top_zc706.xdc（新建；DIFF_SSTL15 时钟 + PMOD AJ21/AB21 + 亮灯结果码映射）
- build/tcl/build_w3_board.tcl（zc702→zc706 全替换，grep 零残留）
- wrapper 残留检查：grep -nE "zc702|D18|C19|LVDS_25|GPIO_SW_N|W6|W7|6'h00" 零命中

## 备注

- rtl-guardrails 的 check_style.py 脚本文件本机未随技能安装（正文规则已遵守：具名连接/一端口一行/
  参数格式/中文注释/无尾逗号），排版未跑机器规整——如后续补装脚本可一键 --fix。
- 下一步（需板卡）：Phase 5 比特流+烧写（含 8a 后首个比特流）→ Phase 6 拨码 → Phase 7 双 COM → Phase 8 注册。
