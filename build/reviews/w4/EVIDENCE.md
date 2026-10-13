# W4-P0 验收证据 · CI 超时作业化 + RemoteException 清理（2026-10-13）

## T1 超时作业化（HANDOFF deferred「W4 首项」）

**机制**：ci_regression.ps1 的每个原生工具调用经 `Invoke-TimedNative`（Start-Job + Wait-Job -Timeout）执行；超时路径尝试按作业 PID 树击杀（**审查 C-P3 修正：PS 5.1 标准 Job 的 ChildJobs[0].ProcessId 实际为空，精准击杀目前为 no-op，孤儿 xsim 依赖 Stop-Job 兜底**——已知残余风险，日志中有 WARN 提示），判 `[TIMEOUT][FAIL]` 并继续后续 TB。

**注入实验**（scripts/ci_timeout_experiment.ps1，挂死 TB = forever 振荡 + 永假 wait）：
- 日志：build/reviews/w4/ci_timeout_experiment.log
- 结果：`[TIMEOUT] xsim tb_ci_hang_tmp exceeded 20 s -- job killed` → `[FAIL] tb_ci_hang_tmp` → `[PASS] tb_crc16 (3.0s)` → `1/2 PASS, 1 FAIL` → **exit 1**
- 覆盖判据：①挂死 TB 被超时判定不挂死 CI ②后续 TB 正常续跑 ③退出码诚实
- 临时 TB 自动删除，未入 sim/tb

**生产全量验证**（build/reviews/w4/ci_full_prod_run.log）：12/12 PASS（含每 TB 计时）+ 44+19 单测 + 金丝雀 + 向量 + 契约同步，exit 0。

## T2 RemoteException 清理

Python 五段输出捕获改 `cmd /c "... 2>&1"`（stderr 在 cmd 层合并为纯文本，PS 5.1 不再生成 ErrorRecord）。验证：ci_full_prod_run.log 全文 `RemoteException` 出现次数 = **0**（旧版每次运行均有数处）。

## 过程中实证修复的陷阱（供后续会话避坑）

1. PS 行续符是反引号非反斜杠（解析器不报错、运行时参数错乱）
2. Start-Job 作业体丢失父作用域 → 必须显式传参（含工作目录）
3. powershell.exe -File 不拆分数组参数（逗号相连也不行）→ 纯字符串 + 脚本内 split
4. Stop-Job 无 -Force 参数（PS 5.1）
5. 事件驱动仿真器会瞬间跳过单个大延迟 → 真实挂死须用 forever 事件流

## 变更清单

- scripts/ci_regression.ps1（超时作业化 + WorkDir + cmd/c 捕获 + 测试用覆盖参数 + 每 TB 计时）
- scripts/ci_timeout_experiment.ps1（新增，可复用实验）
- build/reviews/w4/{ci_timeout_experiment.log, ci_full_prod_run.log, EVIDENCE.md}

## 审查轮（agent-W4P0，2026-10-13）与修复

发现 1×P1 + 2×P2 + 3×P3，全部修复并复验：

| 级别 | 问题 | 修复 |
|---|---|---|
| P1 | 工具未启动时 [int]$null→0 假绿（compile/elab 门） | Code/结果为 null → Code=-1 + 作业态诊断行；探针实证：不存在工具 → Code=-1（修复前 0）；cmd exit 3 → Code=3（PROBE PASS） |
| P2 | 覆盖参数静默替换可冒充全量绿 | OVERRIDE ACTIVE 横幅 + 实际清单回显 + 汇总行 [SUBSET/OVERRIDE] 标记 |
| P2 | 进程树击杀 PID 复用误伤 + CIM 静默漏杀 | 击杀前按 ProcessId+CreationDate 复核（复用即跳过）；CIM 空查询/杀空清单告警 |
| P3 | 超时丢弃挂死 TB 部分输出 | 击杀前非阻塞 Receive-Job 保留末 10 行 |
| P3 | sim PASS 不校验退出码 | 判据加退出码等于 0 |
| P3 | 实验脚本双反斜杠路径 | 改单反斜杠 |

复验（build/reviews/w4/ 两份日志）：注入实验含横幅/子集标记，超时→FAIL→续跑→exit 1；生产全量 CI_EXIT=0（12/12 + 44+19 + 金丝雀 + 向量 + 契约），RemoteException=0。
