# Auto-Review Report — web/前端探索报告.md

**日期:** 2026-10-13 ｜ **审查类型:** Plan Review（设计文档多视角审查） ｜ **执行者:** auto-review skill（编排器 + 独立子代理）
**对象:** D:\puf-drone-auth\web\前端探索报告.md（v1.0 → 修复为 v1.1，446 行） ｜ **Spec:** docs/FRONTEND_HANDOFF.md + 会话确认的三项决策

---

## 摘要

| 指标 | 初审（去重后） | 修复后（round-2 复核） |
|------|------|------|
| 审查轮次 | 第 1 轮（3 视角并行） | 第 2 轮（修复清单核验+回归检查） |
| P0 阻断 | 0 | 0 |
| P1 Critical | 2 | 0 |
| P2 Important | 11 | 0 |
| P3 Minor | 9 | 0（未再报） |
| 高可疑项（独立多源命中） | 2（均经编排器直读代码升级为实证） | — |
| 最终结论 | ❌ FAIL | ✅ **PASS** |

**通过判定:** P0=0 and P1=0 and P2=0 -> PASS。round-2 结论：13/13 项修复全部落实（逐项附 v1.1 行号引文新证据），回归抽查未发现新 P1/P2/P3 问题。

---

## 调度的技能与降级记录

| 环节 | 执行方式 | 结果摘要 | 状态 |
|------|---------|---------|------|
| plan-reviewer（完备性） | 独立上下文 subagent | PASS_WITH_NOTES：P2×5、P3×4；spec 覆盖与 tokens 逐值核对全过 | ✅ 已执行 |
| feasibility-reviewer（可行性） | 独立上下文 subagent（实读 server/evaluation 代码） | FAIL：P1×1、P2×4、P3×4 | ✅ 已执行 |
| practicality-reviewer（实用性/数据纪律） | 独立上下文 subagent（实读代码+G5 判据） | FAIL：P1×1、P2×6、P3×8 | ✅ 已执行 |
| 共识综合 | 编排器执行（降级） | 空间去重＋证据源比对；关键项以编排器直读 threshold.py/protocol.py/crp_pool.py/main.py 二次实证 | ⬇️ 降级（见下） |
| round-2 复核 | 独立上下文 subagent（仅核验修复清单+回归） | PASS：13/13 ✅、零新问题 | ✅ 已执行 |
| playwright / security | — | 纯设计文档、无运行时与代码变更，不适用 | ➖ 未执行（不适用） |

**降级执行记录：** ① 三个审查子代理的并行前台派遣曾失败（子代理通道约束），改为逐个/后台派遣，结果均经消息送达收齐，无质量损失；② 共识综合未单独派遣子代理，由编排器在主上下文完成——因所有 P1/P2 级发现均经编排器直接读取仓库源码二次验证（threshold.py TAU 常量、cmd_auth 无 CONFIRM、crp_pool 状态文件优先级、TemplateDB sidecar、evaluation 仅消费 CSV、653/~14ms 实存位置），证据强度高于代理间交叉印证，置信度不受影响。

---

## 审查轮次历史

| 轮次 | P0 | P1 | P2 | P3 | 结论 | 本轮动作 |
|------|----|----|----|----|----|---------|
| 1（初审，3 视角去重） | 0 | 2 | 11 | 9 | FAIL | 全量修复于 v1.1（P1/P2 全部＋P3 全部顺手清零） |
| 2（修复核验） | 0 | 0 | 0 | 0 | **PASS** | 无需再修 |

---

## 统一发现表（初审去重后，P1/P2 全部 Fixed）

| # | 严重度 | 置信度 | 来源 | 位置 | 问题 | 状态 |
|---|--------|--------|------|------|------|------|
| 1 | P1 | 三源独立命中＋编排器实证 | §8.3/L265 等 | verdict.thresholds 命名（T_pass/T_gray）与 threshold.py（TAU_PASS=6/TAU_REJECT=16）不符，缺 n_responses 与 decide_scaled 缩放口径，HD 仪表将出现「PASS 但指针越线」 | Fixed（v1.1 §8.3/§6.2/附录A） |
| 2 | P1 | 两源独立命中＋编排器实证 | §6.1/§8.1/L127 | 五帧动画含 CONFIRM，但 cmd_auth 编排产不出 CONFIRM（且终端侧三帧从不 pack），S1 验收不可达 | Fixed（桥接代演：pack 三帧＋on_confirm；新增 confirm.done 事件） |
| 3 | P2 | 两源 | §7.1 V1/V2 | HD 分布数据管道不存在（evaluation 只消费 measurement CSV） | Fixed（采样脚本列为 D9 交付物） |
| 4 | P2 | 两源＋实证 | §7.1 V3/V4 | 「64bit×CRP 稳定性」「每 CRP 测量抖动」数据不落盘（TemplateDB 仅投票响应＋64 位掩码 sidecar） | Fixed（V3 改位矩阵+掩码条；V4 改桥接旁路捕获） |
| 5 | P2 | 两源＋实证 | §6.3 S5 | --demo-pool 与 CRPPool 语义冲突（registry 级参数；状态文件 committed 值优先；n=100>20 会直接抛异常） | Fixed（预写 pool_99.json＋n=16~20＋清状态说明） |
| 6 | P2 | 单源（feas） | §3 | file:// 直开断言不成立（ESM/CORS） | Fixed（删除，统一桥接 HTTP/--mock） |
| 7 | P2 | 两源 | §8.5/§11 | puf:* 事件映射不全（10+ 类 SSE 只映射 4 个）、握手次序未定，而 schema 已宣称冻结 | Fixed（11 类全量映射表＋ready→taken 600ms 握手） |
| 8 | P2 | 单源（prac） | §6.3 | G5①「双向拒绝」只覆盖服务器侧（S2），缺假基站/终端 BLOCKED 反向场景 | Fixed（新增 S7 evilbase＋common/speck.py 复算） |
| 9 | P2 | 单源（prac） | §12 | 缺「竞赛机 Python 运行时」风险（离线链硬依赖） | Fixed（风险行＋便携 Python 随 zip＋验收项） |
| 10 | P2 | 单源（prac） | §6.1/§12 | 缺分辨率/投影仪适配（1280×720 常见） | Fixed（分辨率基线＋断点方案＋验收项） |
| 11 | P2 | 两源＋实证 | §7.2/§9 | 指标卡溯源错位：653/~14ms 实存于 docs/project_flow.html，非 project_design.md（其延迟口径为 10ms+20ms） | Fixed（逐数拆分角标＋注明刷新日期） |
| 12 | P2 | 两源 | §6.2 | hex「黄金帧逐字节 diff」语义误导（实时随机帧 vs 固定回归向量必然全差异） | Fixed（改字段结构对齐；S2 差异用 hd_per_response；diff 仅回放模式） |
| 13 | P2 | 两源 | §6.2/§8.2 | R2 金色角标不可达（loopback 随机铸钥）且有硬造风险 | Fixed（POST /api/setkey＋「演示密钥→首证→金角标」节拍） |

P3（9 项，全部顺手修复）：/api/status 改三源组装口径；S4 补 flip_prob 0.13–0.15 与自动重试；SSE 补 HTTP/1.1＋Content-Length＋: ping 心跳＋seq 重同步；附录示例常量改真实值（msg_id 0x0091=145、CHALLENGE 44B）；元数据更新（server 9 文件、main.py 860 行，快照声明）；serial 风险行按 serial_server.py 现状改写（serve_forever 已存在，缺口=C2 桩+无硬件验证）；排期日历锚点＋≥2 天缓冲＋V4 降缓冲项；新增一键连播剧本与逐帧单步；验收清单同步扩充。

## 驳回记录（已知误报清单）

- plan-reviewer 称「LUT 490 位于 build/reports/utilization_w2_feas.txt」——编排器 grep build/reports/*.rpt 未找到 490/653；v1.1 采用可实证口径（653/~14ms → docs/project_flow.html L77/L181/L183 实存；下限标注为 A1 计划底稿估算），未采纳该文件路径。round-2 未重复上报。

## 附注：审查期间的重要发现

仓库正被并行会话推进：src/python/server/ 已由 7 文件演进为 9 文件（新增 enroll.py、serial_server.py），main.py 837→860 行。v1.1 已按「实读快照＋演进声明」口径更新，并提示实施前重对接口、冲突以 docs/HANDOFF_SUMMARY.md 为权威。

## 最终结论

**✅ PASS** —— v1.1（446 行）达到「零上下文工程师可开工」标准：初审 13 项 P1/P2 与 9 项 P3 全部修复并经独立复核确认；事件 schema（SSE 11+1 类 ↔ puf:* 全量映射）已真正冻结，可供 3D 队友按 mock.ts 并行开发。
