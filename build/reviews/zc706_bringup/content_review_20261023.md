# Auto-Review Report — Mode 2 内容审查（ZC706 极性翻案修复成果）

**日期:** 2026-10-23 11:16–19:50 (Asia/Shanghai)
**审查类型:** Content Review（Mode 2，五代理 + 共识综合 + 修正循环 + 复审）
**执行者:** auto-review skill（Lead 编排，独立上下文 subagent：A 缺陷 / B spec 合规 / C 静默失效 / D 类型位宽 / E 测试覆盖 + 共识代理 + 复审代理）

---

## 摘要

| 指标 | 值 |
|------|-----|
| 审查对象 | P1–P5+P7 全部成果（未提交工作树 vs HEAD=d908eae：12 修改文件 + 未跟踪 P4/P7 产物） |
| 审查轮次 | 五代理并行（2 批）→ 共识综合 → 修正循环 1 轮 → 复审 1 轮 |
| 初审发现 | P0=0 / P1=0 / **P2=5** / P3=6 → 门禁 **FAIL** |
| 修正后复审 | 11/11 ✅ Fixed（全部本轮新证据）→ **P0=P1=P2=P3=0 → PASS** |
| 高可疑项(独立多源) | 0（6 条多代理命中经证据比对均为同源命中） |
| 最终结论 | ✅ **PASS**（修正循环后） |

---

## 初审发现与处置总表

| # | 级别 | 发现 | 处置 | 复审 |
|---|------|------|------|------|
| 1 | P2 | 三 TB T0 复位值直锁在 220k 拍，晚于消抖自愈点(100k)——对 M9 复发空转（A/C/E 三方同源命中） | 复位释放+10 拍 T0-early/T1-early 直锁 + seedgate 补 btn_prev + 220k 检查文案改口径 | ✅ |
| 2 | P2 | 松开沿负向锁缺失——XOR 双沿退化静默过全 CI，板上每次松开 SW7 多起一次认证（极性重写丢失 HEAD 对称锁） | 三 TB 补 1→0 驱动 + 150k/120k 窗计数不增断言 | ✅ |
| 3 | P2 | CI 不编译 wrapper——根因修复三要素零 CI 覆盖（"CI 全绿、板上复发"网眼） | ci_regression.ps1 新增 wrapper 3-element lock 阶段（正则锁三要素，回退即 exit 1）；合成回退文本实测咬住 | ✅ |
| 4 | P2 | keyloop T13 黄金值 0x92 依赖半拍竞态窗 + 机制注释归因错误（实为 key_valid+1 拍推进，非会话超时） | negedge 采样监视器冻结 c2_snap + T13 改读快照 + 注释按 RTL 实况更正（terminal_fsm:889-892/:700-702/:615-616 复核无误） | ✅ |
| 5 | P2 | 消抖无下界锁——消抖坏成"立即接受"三 TB 全绿，板上抖动穿透 | tb_w3_top/keyloop 加 guard<99_000 断言；seedgate 加 press_cycle/cyc/early_a-c 单块监视器 | ✅ |
| 6 | P3 | dbg_top v1 灯语图例与 v2 赋值矛盾（P6 板验依赖） | v1 图例删除+废弃说明 | ✅ |
| 7 | P3 | w3_top_dbg SEED_GATE_EN 参数注释未同步生产版（P4 漏网） | 逐字同步 | ✅ |
| 8 | P3 | seedgate DUT-A 参数注释"板级 bring-up 配置"与翻案声明矛盾 | 改"机制锁旁路臂（板级已恢复=1）" | ✅ |
| 9 | P3 | hw_facts banner 行号引用系插入前旧编号 | 改 L50/L66/L72 并注旧编号 | ✅ |
| 10 | P3 | T13 ===8'hA0 死分支（!==8'h92 前置截获） | 随 #4 重构前移复活 | ✅ |
| 11 | P3 | keyloop 看门狗无现场上下文 + 注释加式顺序不符 | 补六要素打印 + 按实际执行序改写 | ✅ |

**修正循环中额外根治的实施 bug**：CI 脚本插入块首版含中文，撞上 ps1 无 BOM 被 PowerShell 5.1 按 ANSI 解析的编码陷阱（GBK 配对吞掉引号 → parse error）——改纯 ASCII 并留 NOTE 注明该约束。此为修复引入后当轮发现当轮修复，复审以 cp936 视角 ParseInput 实测 0 错误。

## 独立验证记录

- **B 代理 4 项独立复跑**（非采信声明）：CI 顺序复跑 17/17、VERIFY_WRAPPER_PASS、check_style blob-hash 字节级对比（工作树 47E/5W == HEAD 基线）、timing.rpt WNS=0.406 + bit 产物 11:14:19。
- **修正后全量 CI**：exit 0 —— wrapper 3-element lock [PASS] + **=== 17/17 PASS ===** + ENROLL_NEG + Python 全绿（2026-10-23 19:3x）。
- **复审回归扫描**：三 TB 时序预算独立复算（189.0ms<250 / 139.0ms<160 / 154.0ms<250）全部吻合；新声明无编译顺序隐患；seedgate 监视器与既有 always 变量集不相交无竞态；松开段对 T3b/T13 无干扰；bringuo_fix banner 零行号引用无同类漂移。
- **docs 盲区抽查**（共识盲区项）：14 处 grep 命中逐条核对，全部为勘误 banner 旧文引用/删除线/计划锚表——零现行事实性错误极性陈述。

## 生产链路结论（五代理一致）

RTL 根因修复本体（wrapper 极性/rst_n/SEED_GATE_EN、XDC、build Tcl）、诊断副本、文档勘误、证据链：**零 P0-P2 发现**；范围蔓延为零（ZC702 遗产/协议栈/PUF/端口表/auth_start_pulse 全部零改动）。5×P2 全部集中在回归防护网，已全部修复并复审确认。

## 遗留

- P6 烧写+板上验收：等用户门禁（板上电/USB-JTAG/烧写授权）——bitstream 未受本轮影响（零 RTL 变更），build\board_zc706\w3_top_zc706.bit 仍有效
- P8 三笔提交（rtl/test/docs）：待 P6 后执行；提交前按计划 8.1 三查

**最终门禁：P0=0，P1=0，P2=0，P3=0 → ✅ PASS**
