# Auto-Review 报告 · N2+N9 内容审查（Mode 2）

**日期:** 2026-11-12 ｜ **审查类型:** Content Review（5 视角并行 + 共识综合） ｜ **对象:** finals-demo 分支 `eda6dec..0797b02`（N2 信道 IDS + N9 一键启动）

## 摘要

| 指标 | 值 |
|------|-----|
| 审查视角 | 缺陷(defect) / spec合规 / 静默失效 / 类型设计 / 测试覆盖（5 独立 fresh 队友） |
| 原始发现 | 35 项（P1×1 / P2×7 / P3×27，重叠多） |
| 去重后 | P0=0，P1=0，**P2×9**（含 P1 仲裁降级 1 项），P3×18 |
| 修复 | P2×9 全修 + P3 修 12 项 + 备案 6 项（有意设计/零实害） |
| 复审证据（本轮新跑） | pytest 全套 **129 passed + 3 subtests**；vite build EXIT=0（含新增编译期穷尽断言）；demo_start loopback **SCRIPT_EXIT=0** + BOM=EF BB BF + 中文输出正常 |
| 最终结论 | ✅ **PASS_WITH_NOTES**（仅备案项） |

## 调度与降级记录

| 项 | 状态 |
|----|------|
| 5 审查队友（ar-defect/spec/silent/type/test-c1，fresh） | ✅ 全部完成，输出统一 JSON |
| 共识综合独立队友 | ⬇️ **降级**：Team 成员上限 8 已满（3 计划审查队友为持久成员），共识由编排器内联执行（去重/同源判定/仲裁），发现 JSON 逐字保留于本对话记录 |
| playwright 运行验证 | ✅（首轮 N2 验收时已做：DOM 证明 + 截图目检） |

## 去重后 P2 清单（9 项，全部已修 @ a1f2d98）

| # | 发现 | 来源（去重） | 修复 |
|---|------|--------------|------|
| 1 | channel.noise 噪声半边未实现（设计承诺，N8 依赖） | spec+test | 1s 滑窗 ≥3 次 resync → 限速发布 + CHANNEL NOISE error 行 + 洪泛测试 |
| 2 | demo_start 无 BOM → PS5.1 中文乱码 | spec | UTF-8 BOM（字节级验证） |
| 3 | 自检固定端口 vs 桥自愈顺延 → 假失败 | defect+spec+silent | 探测 Port..Port+5 + Content-Type json 身份校验 + 顺延提示 |
| 4 | 杀桥三条吞错路径无后验 | silent | 逐个 try/catch 报告 + 端口释放后验 + 失败弹窗 |
| 5 | 提前退出指向 stdout 而 traceback 在 stderr | silent | 失败消息含 stderr 路径 + tail stderr 尾部 |
| 6 | 0x0093/0x0095 变体零测试（0x0093 恰是决赛注入帧；test 侧 P1 仲裁为 P2：实现本身经 3 视角核实正确，缺的是回归锁） | test+defect+silent | 三变体参数化用例 |
| 7 | enroll 窗口恢复未测（N5 若把 flag 提出循环→注册后 IDS 永久哑火且测试照绿） | test | 双帧中窗翻 flag 用例 |
| 8 | 噪声 resync 与 IDS 共存未测 | test | garbage+帧用例 |
| 9 | parse 失败两边界未测（坏 CRC 不告警 + 流不吞） | test | 坏 CRC+好帧用例 |

## P3 处置摘要

**已修（12）**：TS 四处同步锁进编译期（satisfies 交叉约束 + 双穷尽断言）；ChannelNoise 类型全套；"12 个 type"过期注释 ×2；横幅 5s 对齐设计；IDS 分支线程保护；RealApp.enroll_session_active 锚点；COM 双源探测+候选落盘；多候选中止（决赛双串口保护）；失败弹窗+完整路径；参数 ValidatePattern/Range；payload 契约断言（hex/note/level）；FakeSerial 协作退出。
**备案（6，有意设计/零实害）**：body 悬浮 vs topbar 槽位；审计行 type=server.log（不能单独筛 channel.intrusion）；payload 无 ts（信封层兜底）；IdsBanner 无 dispose（页面单例）；0x0095 超设计明示元组（方向已核实，良性）；import 隔离前瞻（N5 注意互异模块名）。

## 手动验证步骤（演示机 pre-flight）

```powershell
# 1. 语法门禁(编辑过脚本后)
powershell -Command "[System.Management.Automation.Language.Parser]::ParseFile('D:\puf-drone-auth\scripts\demo_start.ps1',[ref]$null,[ref]$errs)|Out-Null; if($errs.Count){'SYNTAX FAIL'}else{'SYNTAX OK'}"
# 2. loopback 冒烟(无串口)
powershell -ExecutionPolicy Bypass -File D:\puf-drone-auth\scripts\demo_start.ps1 -SerialPort none -NoBrowser -Port 8642   # 期望 exit 0 + 绿框 URL
# 3. IDS 单测
cd D:\puf-drone-auth; python -m pytest tests/test_channel_ids.py -q   # 期望 9 passed
```

## 结论

N2/N9 实现经五视角审查后达到门禁标准（P0=P1=P2=0，复审证据齐全）。审查净收益：抓出 1 个真功能缺口（channel.noise）、5 个演示日高风险场景（PS5.1 乱码/端口假失败/杀桥吞错/stderr 指错/双串口误绑）+ 5 个回归锁测试。分支 finals-demo @ a1f2d98 可继续 A 层后续项（N6/N10/N3/N4 站端）。

---

# 附:A 层整体复审（R2，2026-11-12 晚）

**范围:** eda6dec..69aa851 全分支(含 R1 未审的 N6/N3/N4/N10 与修复提交) ｜ **执行者:** 复用 R1 的 5 名审查队友(ar-*-c1,send_message 唤醒——Team 上限 8 的既定降级路径,既有上下文反增复验价值) ｜ **共识:** 编排器内联(同 R1 降级)

## R2 轮次结果

| 视角 | 复验 R1 发现 | 新发现 | Verdict |
|------|--------------|--------|---------|
| 缺陷 | 4/4 已修(超要求) | **P1×1** + P3×4 | FAIL |
| 测试 | 8 修/2 合理回应 | P2×2 + P3×2 | FAIL |
| 静默失效 | 10/10 已修 | P2×1 + P3×6 | FAIL |
| 类型 | 5 修/1 复发/1 维持 | P3×4 | PASS_WITH_NOTES |
| spec | 10/10 已修或备案 | P3×7 | PASS_WITH_NOTES |

## 关键发现与处置(修复提交 b8461af,15 文件 +362/−76)

- **P1 `_do_poll` 挂错类**:分发是 `getattr(Orchestrator,"_do_poll")`,handler 却定义在 RealApp → 巡检桥层 100% 落空。R1 声称的"loopback 负路径已验证"实为看到 run.error 未核文案(教训已记)。**修复:迁至 Orchestrator(先写后发+锁+忙拒),SSE 端到端实测返回设计文案 `poll requires real-serial mode...`**
- **P2 串口写竞态**:`_do_poll`(编排线程)与 `_auth`(监听线程)并发写同一 ser → 帧交错且症状全指向错误方向(resync/超时/误导按 SW13)。**修复:`serial_bus_lock`(RealApp 锚定,`_auth` 全程持锁+poll 写口持锁) + `auth_in_progress` 忙拒**
- **P2 证据序**:poll 先发事件后写串口,违反本文件"先写成功再发事件"纪律 → **改先写后发**
- **P2 桥级测试零覆盖** → `test_poll_bridge.py` 6 用例(分发 P1 回归锁/写-发顺序断言/忙拒/loopback 拒/超时 SW13 提示/confirm.rejected 全链舞步——**DanceSerial 应答式串口**,顺带修掉测试夹具的黄金 C2 重放窗陷阱:不可预跑 on_access_request)
- **P3×20 修复/备案**:confirm-wait except 落日志+意外帧日志、MockApp run_id 同源、横幅判别联合(去伪造字段)+头注释、PUF_EVENT satisfies Record、own_verdict 字面量联合、api.ts 计数祛数字、**confirm.rejected/poll.sent 审计行消费(N8 三重证据补全)**、flight finished.finally(cancel 不泄漏)、FakeSerial 默认协作退出、demo_start 回退不自动绑非 USB 口、设计文档 R2 备案×4(frame-decode 不建/配对连线裁剪/900ms/巡检全卡渲染)、**n6_flight 截图重拍(徽章文字可辨读自证)**

## R2 后门禁(全部本轮新证据)

pytest **141 passed**(+6 桥级) ｜ vite build EXIT=0 ｜ 契约 sync 全绿 ｜ /api/poll SSE 实测诚实文案 ｜ 飞行截图目检可辨 ｜ **P0=P1=P2=0 → PASS_WITH_NOTES**(余 P3 备案项:IdsBanner/FrameFlight 无 dispose[页面单例]、N6 配对连线裁剪、巡检按钮全卡渲染)

## 过程教训(已存记忆)

1. **验证要核文案不只看状态**:run.error 出现 ≠ 错误路径正确——P1 就是这么漏过首轮自验的
2. **验证前先杀旧进程**:8642 被修复前的旧桥蹲位,新桥被挤走,验证打到旧代码得出误导结论
3. **测试夹具的隐藏状态**:协议重放窗会咬预跑调用;应答式 Fake(DanceSerial)比预录字节流更鲁棒
