# Auto-Review Report — 前端桥接与功能完整性（合并入库后终审）

**日期:** 2026-10-18 ｜ **类型:** Content Review（两视角 + 编排器运行时验证） ｜ **对象:** D:\puf-drone-auth\web\（合并入库版）

## 摘要

| 指标 | 初审 | 修复后 |
|------|------|--------|
| bridge-reviewer | ❌ FAIL（P1×1 + P2×2 + P3×9） | — |
| frontend-completeness-reviewer | ✅ PASS（P3×4） | — |
| 运行时验证（八场景 + mock 认证 + 页面探针） | — | ✅ 全绿 |
| round-1 修复 | — | P1/P2 全修；py_compile=0；八场景 8/8 exit 0；mock 页面零错误 |

**最终结论：✅ PASS**（P1+P2=0；两视角合计 P3×13 均已登记为遗留，不阻断）。

## 统一发现表

| # | 级别 | 来源 | 位置 | 问题 | 状态 |
|---|------|------|------|------|------|
| P1-1 | P1 | bridge | web_bridge.py:1257,1261 | MockApp._replay_worker 传 3 参(run_id,tid,mode)而 _script_auth 仅收 1 → TypeError 杀死 worker 线程，--mock 认证按钮零事件 | **Fixed**（签名补齐 tid+mode） |
| P2-1 | P2 | bridge | web_bridge.py:648 / main.py:156-159 | S4 gray flip_prob=0.13 经 respond() **永久突变共享器件** _puf.flip_prob；后续 S1 期望 HD≈8.3>TAU_PASS 意外灰区/REJECT | **Fixed**（_auth_round 拆分 wrapper + finally 恢复） |
| P2-2 | P2 | bridge | web_bridge.py:520-524 | submit_sync 超时仅放弃等待——Job 仍在队列必然执行，副作用（setkey/c2reset/pool reset）照常落盘，调用方误读为「失败已回滚」 | **Fixed**（文档化 + 错误消息标注「job still queued; side effects will apply」） |
| P3×9 | P3 | bridge | 多处 | 见下方遗留清单 | Pending |
| FC-P3×4 | P3 | frontend | 多处 | 指标卡 LUT 旧口径未并注、mock.ts 死导出、链路浮层缺 role、事件账本 8000 条封顶 | Pending |

## 运行时验证证据

| 验证项 | 结果 |
|--------|------|
| py_compile | ✅ 0 |
| 八场景 --once（修复后） | ✅ s1=0 s2=0 s3=0 s4=0 s5=0 s6=0 s7=0 golden=0（verdict 逐场景正确；golden R2 逐字命中） |
| --mock POST /api/auth + 页面 S1 点击 | ✅ mock 页面 11 行日志含 run ID、stat=idle（场景完成）、零页面错误 |
| 前端完备性审查 | ✅ 三页齐全（§5）；五区+S1-S7+CONFIRM+hex 对齐（§6.2/§6.3）；V6=MODEL/V7=REAL-STATIC/V5=MOCK（§7）；§8 端点+12 型事件逐一对齐；上轮四项按钮修复无回退；可达性 tabindex/aria 就位 |

## 遗留清单（P3，不阻断——W5 冻结周只修缺陷时择优处理）

bridge-reviewer: 注释漂移(verdict_for 预热)、evilbase REJECT 路径/SESSION 残留、队列满 poison 投递可静默失败、persist_terminal 未知 tid 垃圾、B2 未复用 decide()、v1 迁移不清理 c2_history、enroll provisionkey 静默覆盖 setkey、viz 读端点无快照隔离、C2_GOLDEN_HEX 死常量。
frontend-completeness: 指标卡 LUT 旧口径未并注新 4443、mock.ts ?mock=1 死导出、链路/数据源浮层缺 role=dialog、事件账本 8000 条封顶截旧。

## 调度与降级记录
两子代理（前台逐个——并行前台在本环境不可用）。运行时验证由编排器直接执行（--once 套件 + mock 桥接 + Playwright 页面探针）。无降级。

## 手动验证步骤
1. 仓库根: python web/bridge/web_bridge.py --loopback --open
2. console 页点 S1 → 五帧全绿+PASS；点 S2 → REJECT+差异高亮
3. viz 页确认 V6=琥珀 MODEL / V7=紫 REAL-STATIC / V5=灰 MOCK
4. --mock 模式: python web/bridge/web_bridge.py --mock --open → console 点 S1 有事件流
