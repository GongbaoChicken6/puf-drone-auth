# Auto-Review 报告：N6接入闸门实现（content模式，R1→R2）

> 对象：1382ba7（实现）→ ad20cae（R1修复），base=a804ed0，分支finals-demo
> 规格：docs/process/plans/access_gate_design_20261116.md（v2，plan审查已PASS）
> 环境：无spawn_teammate → 内联降级（对抗性逐块审查+修复后新证据复验）

## 判定

| 轮次 | P0 | P1 | P2 | P3 | 误报驳回 | 门禁 |
|---|---|---|---|---|---|---|
| R1（审查1382ba7） | 0 | 1 | 1 | 2 | 1 | FAIL → 修复循环 |
| R2（复验ad20cae） | 0 | 0 | 0 | 0 | — | ~~PASS~~（下轮被推翻） |
| R3（用户质询"再复核"，专项攻击R1修复本身） | 0 | **1** | 0 | 0 | — | FAIL → 修复 → **PASS** |

### R3 发现（F1 修复自身引入的 P1——R2 判定过早）
- **F5 · P1：跨板按压假成功 → 闸门死锁**
  推演链：F1 修复让任何板入队都刷新全局 last_access_request_ts；而
  _poll_wake_once 的成功判据抄自 _do_poll 仍是全局戳 → 选择板A唤醒期间
  板B被按SW7入队(全局戳跳) → 唤醒假成功 → 板A实际沉默 → 无 _auth →
  无 finish → selected_tid 悬挂 → 其余机器 select 409、本机 dismiss 409
  → **闸门死锁至重启桥**。双板演示两板连按，窗口易踩。
- 修复（本轮提交）：last_access_request_by_tid per-tid 信号表（_auth 与
  _park 双写）；_poll_wake_once 判据改 per-tid（全局戳仅作无表假app回退）；
  AccessGate.is_selected 锁内读取代 F3 防护的裸读。_do_poll 遗留契约与
  其测试不动（跨板误报降级为 P3 已知项：/api/poll 成功语义是建议性的）。
- **变异验证**（按TB规约）：同场景下旧全局判据=SUCCESS（复现死锁路径）、
  新 per-tid 判据=TIMEOUT，MUTATION_PROOF_PASS。
- 新增回归：test_other_tid_bump_does_not_fake_success（跨板楔死）+
  test_own_tid_bump_only_still_succeeds。
- R3 复验：py_compile 0；pytest 全量 **216 passed**（214+2）。

**教训入档**：R2 只验证了"R1 的修复是否落地"，没有攻击"修复是否引入新缺陷"
——修复改变了共享信号的语义（任何park都刷全局戳），所有消费该信号的路径都
必须重审。这正是 R1-F1 与 R3-F5 构成一对"修一漏一"的原因。

## R1 发现与处置（全部基于真实diff/代码取证）

### F1 · P1：闸门模式下 /api/poll 成功信号断裂（假超时）
- 证据链：_park()（旧L2611-2629）入队不刷新 app.last_access_request_ts；
  _do_poll/_poll_wake_once 的成功判据**只有**该时间戳（web_bridge.py:849-853/1288-1293）
- 后果：闸门开启时点"验证认证"（录入向导按钮）→ 板子回应 ACCESS_REQUEST → 被入队 →
  时间戳不动 → poll 报"no ACCESS_REQUEST within 3s"假超时，请求却躺在队列里
- 修复：_park 无条件刷新 last_access_request_ts（ad20cae，L2626 标记）；
  语义注记进方案Phase4（poll成功=入队，需再从弹窗选择）
- 回归锁：test_park_refreshes_poll_signal（并入既有park用例断言）

### F2 · P2：_poll_wake_once 零直接测试
- 证据：两个 select 用例均 stub 掉 _poll_wake_once，真路径（组帧/写口/事件次序/超时）无覆盖
- 修复：新增 TestPollWakeOnce 两例——成功路径用 _PROTO.parse 解帧断言 msg_id=0x0097+tid
  （首版用硬偏移断言是错的，1!=151 当场暴露，改为协议解帧）；3s静默超时路径
  （超时也必须已写过帧，先写后查不伪造）

### F3 · P3：对齐睡眠期间板被再按 → 唤醒POLL把已验证机器重新入队
- 场景：select 睡Δ(≤2.2s)期间该板被物理再按SW7 → 认证走完出队 → 我们的POLL到达 →
  板子重新ACCESS_REQUEST → decide发现selected已清 → 入队 → 弹窗莫名重弹
- 修复：睡眠后（及重试前）复查 gate.snapshot/selected_tid，已消费则按成功返回
  （ad20cae L1325 标记，两处）

### F4 · P3 → **误报驳回**
- 候选：刷新恢复时"验证中"行无标记
- 驳回证据：access-popup 构造器 this.selected = q.selected，render() 对
  selected行渲染"验证中…"（组件代码实读）——行为已存在，非缺陷

### 附带：测试自身缺陷（修复中暴露）
- 首版帧断言硬编码偏移 frame[3:6]（1!=151 失败）→ 改 _PROTO.parse 解帧。
  教训入档：断协议帧一律走 parse，勿猜字节偏移

## R2 复验证据（新HEAD=ad20cae）
- python -m pytest tests/ -q → **214 passed, 1 skipped**（基线193+21新，零回退）
- npx tsc --noEmit → 0 error
- 修复标记在HEAD实测命中：R1-F1 @ web_bridge.py:2626、R1-F3 @ :1325（ripgrep）
- git 状态：ad20cae 顶置，受审文件工作树干净

## spec 合规抽查（方案v2承诺 vs 实现）
decide先于on_access_request✓ | 2.2s对齐+防御重试+回滚✓ | tid路由(修P1)✓ |
多口强制闸门✓ | 同tid双口哨兵✓ | REST三端点✓ | SSE四事件+计数26✓ |
弹窗+徽标+刷新恢复✓ | mock桩✓ | 证据归档✓ | UI三态（vision+DOM）✓

## 安全内联清单（Mode 2 附带）
REST参数全部int()强转（ValueError→400既有兜底）✓ 无shell拼接/无路径拼接✓
仅绑127.0.0.1✓ 无新增密钥/日志敏感项✓

## 手动验证步骤（Phase 4 真板，板子回来后）
1. 双口启动：--serial-multi COM6,COM11 --access-gate --tid-port 1=COM6,2=COM11 --access-label 1=板A,2=板B
2. 双板同按SW7 → 弹窗两台 → 秒选板A（<1s）验证2.2s对齐 → PASS → 队列余板B
3. 录入向导"验证认证"（闸门模式）→ 应看到请求入队而非超时（F1修复的实板确认）
4. 拔板B串口后select → 409人话文案
5. 证据：录屏+截图落 build/reports/

## 结论
P0=P1=P2=0，P3清零（含误报驳回记录），**PASS**。
降级说明：本轮无独立子代理，交叉验证以"真实diff取证+修复后全量重跑+标记实测命中"替代。
