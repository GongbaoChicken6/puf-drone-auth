# web-over 前端交付 · 验收检查报告

**日期:** 2026-10-15 ｜ **检查者:** 前端探索会话（对 D:\puf-drone-auth\web-over\web） ｜ **对象 HEAD:** fb29fd2（W4-P5 后）
**方法:** 静态契约比对 + 本机实证（typecheck / --once 八场景 / HTTP 冒烟 / SHA256 / 沙箱隔离运行）

---

## 结论

**前端本体可用、质量高；桥接层（web_bridge.py）对你当前 HEAD 不兼容，需一次小规模适配（约 5 个触点，全部集中在代演终端状态层）后即可整体启用。**

- 页面/契约/构建产物：typecheck 通过、事件总线与 v1.1 §8.5 逐条一致、dist 干净、报告副本与仓库版 SHA256 相同。
- 桥接对当前 server：8/8 自检场景 FAIL，单点根因＝W4-P3 重构（SimulatedTerminal→ROPairingPUF，commit 7837317）移除了 .secret 属性。
- HTTP 层与静态页对当前 server 仍正常（/api/status 200、/console.html 200、golden-frames 现场解析、SSE 正常）。

## 实证记录

| 检查项 | 结果 |
| --- | --- |
| npm run typecheck（本机 Node 24/npm 11.9） | ✅ EXIT=0 |
| 报告副本 SHA256 | ✅ 与 puf-drone-auth/web/前端探索报告.md 逐字节一致（020C1E8C…B1B） |
| bus.ts puf:* 映射 | ✅ 11 类与 v1.1 §8.5 完全一致（frame.tx/rx 合并、stage.ready/taken 握手在） |
| types.ts 契约镜像 | ✅ tau_pass/tau_reject/scaled_*/n_responses/hd_per_response/evilbase 全在 |
| dist 构建产物 | ✅ 三页+assets 齐全；无 _probe* 残留；favicon 内联 data: URI |
| --once s1…s7+golden（对当前 HEAD，沙箱 data-dir） | ❌ 8/8 FAIL：AttributeError: 'SimulatedTerminal' object has no attribute 'secret' |
| HTTP 冒烟（8643 端口沙箱实例） | ✅ /api/status 200（三源组装+link.proxy）、/console.html 200、/api/golden-frames 解析 protocol_contract §4、SSE 事件流正常 |
| 契约常量漂移 | ✅ 无：N_CHALLENGES=4、TAU_PASS=6/TAU_REJECT=16 未变 |
| merge-into-repo.ps1 dry-run | ⚠️ 本检查环境受限未能执行（exit 1 无输出，疑似 ConstrainedLanguage）；建议在普通终端跑一次。冲突预期＝0：唯一同名文件（报告）SHA 一致；仓库侧 web/reviews/*.md 为你独有，不受影响 |
| 仓库 data/ 污染 | ✅ 无（全部运行经 --data-dir 沙箱落在 web-over/web/.dev-data/check-*） |

## 根因与修复清单（给队友，精确到行号）

W4-P3 起 SimulatedTerminal 包装 ROPairingPUF（与 RTL testbench 同一黄金模型），器件身份从 32 字节 HMAC secret 变为 **16 环频率向量 freqs**（构造函数已支持 SimulatedTerminal(tid, freqs=[…])，main.py:122-127；只读属性 terminal.freqs）。桥接仍按旧属性读写：

1. web_bridge.py L790-792（bootstrap 再水化）：terminal(tid).secret = … → 改为以记录的 freqs 重建 SimulatedTerminal 并注入 transport。
2. L889（状态保存）："secret_hex": term.secret.hex() → "freqs": term.freqs（auth_count 保留；state schema 建议升 v2）。
3. L1031-1034（device_sig）：.secret → .freqs。
4. L190（secret_sig）：哈希对象改为 freqs 向量；tools/sample_hd.py 的同源实现必须同步改（README 明言两侧签名不一致会静默弃样本）。
5. --reset-demo 99 失败同源，随上述修复一并恢复。

**建议项（非断裂，对齐新语义）：** 代演终端的器件密钥宜走 provisionkey 语义（transport.terminal(tid).derived_key → store.set_key，cmd_provisionkey main.py:721-747 已有先例），使演示对齐 W4-P4 interop 口径；_ensure_device_key 随机铸钥仍是回退路径，不修也能跑。另注意 INTEG-F1 后灰区加测种子入 staging pool、PASS 才提交——修复后 S4 的池水位数值口径与旧版略有差异，属预期。

## 你这边演进对其的影响面（207b82a..HEAD 触及 server 的 10 个提交）

dd36c5e serial 接收循环与 on_confirm 接线 ｜ 7837317 SimulatedTerminal→ROPairingPUF（**本次断裂源**） ｜ ed07c45/be67b24/b65b3a8 P3/P4 审查修复与加固 ｜ 4d3880b TB 注入/洪泛/运维 ｜ 8073cc6 staging-release 池语义 ｜ a4d8ff8 DeviceKeyStore 外部变更检测 ｜ 15ec480 interop K provisioning＋契约 S9 KDF ｜ a5a6cd9 灰区加测入 staging pool

## 后续建议

1. 队友按上表 5 点适配桥接（预计半天内），修复验收＝--once 八场景退出码全 0（其 README §6 已内置该门禁，断言到具体结果码）。
2. 适配后你在普通终端跑一次 merge dry-run 确认，再 -Apply 合并；合并后按 README §2 验证链路。
3. 今后 server 侧再动 SimulatedTerminal/ROPairingPUF 公共接口时，--once 套件是最快的兼容性哨兵（对结果码断言，接错线会 FAIL 而非静默通过）。
