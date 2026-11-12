# Auto-Review 报告 · 决赛演示新功能实现设计（计划审查）

**日期:** 2026-11-12 ｜ **审查类型:** Plan Review（Mode 1，3 轮迭代） ｜ **执行者:** auto-review skill（Agent Teams 独立审查队友 ar-plan-r1/r2/r3，均 fresh 上下文）

## 摘要

| 指标 | 值 |
|------|-----|
| 审查轮次 | 3（上限 3） |
| 被审文档 | docs/process/plans/finals_demo_features_design_20261112.md（+FEATURES 规格联动 2 处） |
| P0 阻断 | 0 |
| P1 Critical | 1（R1，已修） |
| P2 Important | 4（R1×3 + R2×1，全修） |
| P3 Minor | 14（全处理：13 修复 + 1 评审判定无需动作） |
| 最终结论 | ✅ **PASS_WITH_NOTES**（P0=P1=P2=0） |

## 调度与降级记录
- 派遣工具：spawn_teammate ×3（ar-plan-r1/r2/r3，context=fresh，逐轮新队友保持上下文隔离）✅
- 审查载体：agents/plan-reviewer.md 模板 + 仓库事实交叉核验（审查队友自带 repo 读权限，18+ 处 file:line 引用逐条比对）
- 安全专项（Mode 4）：计划审查阶段不适用；安全相关项（AUTH_POLL 攻击面/CONFIRM_FAIL 无 MAC/沙箱/断电插拔）已由 checklist §7 覆盖 ✅
- 无降级执行。

## 审查轮次历史

| 轮次 | P0 | P1 | P2 | P3 | 结论 | 本轮修复 |
|------|----|----|----|----|------|---------|
| R1 | 0 | 1 | 3 | 8 | FAIL | 15 处计划编辑 + FEATURES 同步 1 处 |
| R2 | 0 | 0 | 1 | 4 | FAIL | 11 处计划编辑 + FEATURES 同步 1 处 |
| R3 | 0 | 0 | 0 | 2 | **PASS_WITH_NOTES** | 2 处（P3-1 矩阵行 + P3-2 §5 补行） |

## 关键发现（价值排序）

1. **[R1·P1] frame_parser.v RX 侧缺口**：frame_parser 有自己的 CRC_EXTRA 表（default=0x00）与 id_legal 白名单，AUTH_POLL 0x0097 帧会被解析器拒收（frame_err），根本到不了 terminal_fsm。且**无任何既有门禁能拦**：check_contract_sync 只比对 protocol.py↔契约；tb_terminal_fsm 直驱 fp_* 绕过真解析器。→ 修复：N4 加 frame_parser 三处改动 + T-FP1（真解析器接受用例）+ T-L31（level3 端到端）新门禁。
2. **[R2·P2] mavlink_frame.v TX 侧 id_legal 镜像缺口**：TX 构造器同样以 cmd_ok=id_legal&&len_ok 拒 start，漏扩则 0x0097/0x0096 帧造不出来（tb_mavlink_frame 用例、T-FP1 帧源、N11 ALARM 全失效）。→ 修复：N4/N11/矩阵/FEATURES 四处补 TX id_legal。
3. **[R1·P2] CONFIRM status 偏移**：载荷 <IB 布局下 status 在 payload[4]，原文"载荷[0]"会让 tid=1 的每次真 PASS 触发假伪基站告警。→ 修复：用 parse() 返回的 status 字段 + 显式警告。
4. **[R1·P2] CI 编译清单**：tb_demo_led 入 TbList 但 demo_led.v 不在 $rtl（编译=$rtl+$tbs@L235）→ TB 不可编译。→ 修复：矩阵行补 $rtl += demo_led.v。
5. 其余：poll.sent 事件名对齐 / serial_bus_lock 标注新建 / N5 改薄适配器复用 enroll_device / N1 灯语与蜂鸣沿消歧 / N11 TB 行 / Day1 练手步骤 / 决策点#2 上板实验 / N3 诚实边界口径 / tb_demo_led 哨兵与变异 / check_contract_sync 射程表述 / 引用名 4 处（on_confirm/_MSG_NAMES/第七按钮/25MHz 标签）。

## 遗留与判定
- R3 终审：占位符扫描 0 命中；N4/N11/矩阵/TB 清单/风险表/FEATURES 六表面全对齐；铁律映射、回退路径（JTAG 旧 bit + SW11 回拨）、批次结构、CI 数学（18→19 TB）全部复核通过。
- 遗留 1 项（R3-P3-2 原文"无需动作"，本轮已顺手补 §5 行消歧）；无未处理发现。

## 结论
**计划已批准执行（PASS_WITH_NOTES）。** 建议按 §3 批次R 15 步序列于 11-14 开工；N11 严守 11-18 缓冲日门禁（降级序首位）。
