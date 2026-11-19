# Auto-Review 报告：access_gate_design_20261116（plan模式）

> 对象：docs/process/plans/access_gate_design_20261116.md（演示步骤②方案）
> 规格：用户五步演示需求（步骤②）+ 仓库现状约束
> 环境：无spawn_teammate（list_agents仅lead，两次核实）→ 内联降级审查
> 方法：对抗性自查 + 把方案标注"待确认"的板端行为用 RTL/协议源码当场定案 + R2逐标记复验

## 判定

| 轮次 | P0 | P1 | P2 | P3 | 门禁 |
|---|---|---|---|---|---|
| R1 | 0 | 1 | 4 | 2 | FAIL（P1+P2>0）→ 进入修正循环 |
| R2（v2修订后复验） | 0 | 0 | 0 | 0 | **PASS**（10/10标记复验通过 + placeholder扫描clean） |

## R1 发现清单（8项，全部已在v2修复）

### P1-1（Critical）：/api/poll 双口路由缺陷被方案固化
- 证据：原方案CLI节写"保留 serial_listener 属性指向第一个（_do_poll 旧路径兼容）"；
  而 _do_poll 实际用 app.serial_listener 单引用写串口（web_bridge.py:828-838）
- 影响：双口模式下对板B的 poll（含录入向导"验证认证"按钮 enroll-wizard.ts:55）会打到板A端口，静默失败
- 修复：--tid-port 静态映射 + gate entries 查表路由；Phase1新增任务4（_do_poll按tid路由）；单口行为不变
- R2复验：v2含 "--tid-port" 与 "_do_poll 改为按 tid 路由" ✓

### P2-1：access.selected 事件时机自相矛盾
- 原方案时序里 selected 在五帧完成后发，但前端选中即应收弹窗
- 修复：拆为 access.selected（选中瞬间）/ access.finished（完成出队，带state）；SSE计数22→25

### P2-2：唤醒重试间隔1.5s无证据支撑（会打在板子等待窗内）
- RTL定案：POLL 仅 S_IDLE 消费（terminal_fsm.v:392）；S_WAIT_CHALL 只收 0x0091（:479-492）；
  板上等待窗=2s（:21），超时→S_BLOCKED→立即回 IDLE（:930-932）
- 修复：改"2.2s边界对齐"策略（Δ=2.2s-(now-last_request_ts)，Δ>0先等再发），最坏~4.5s，前端按钮转圈承载

### P2-3：dismiss 选中中的 tid 行为未定义 → 修复：409
### P2-4：同tid双板（SW12拨错）队列键冲突 → 修复：同tid不同port拒绝入队+server.log哨兵
### P2-5：验证步骤缺确切命令+预期输出 → 修复：各Phase补pytest/tsc/pnpm/playwright命令与预期
### P3-1：缺AccessGate接口签名 → 修复：补签名+decide()伪代码
### P3-2：F表混入非证据条目 → 修复：并入F9

## 审查中升级为"已确认"的方案前提（原标注联调时复核）

| 项 | 结论 | 证据 |
|---|---|---|
| 板端等待超时行为 | 2s→S_BLOCKED(result=3)→立即回S_IDLE，等待不伤状态可反复唤醒 | terminal_fsm.v:21/489-492/930-932 |
| 秒选时POLL是否丢 | 丢（S_WAIT_CHALL无视POLL）→时序对策必须存在 | terminal_fsm.v:392/479-492 |
| C2重放误判风险 | 不存在：重放窗只在on_access_request消费，闸门在其之前拦截（已把该顺序写成防退化约束） | main.py:169-170/476-486、web_bridge.py:2180 |

## 复验证据（R2）
- 10/10修复标记在v2文档中逐一命中（P1路由/事件拆分/2.2s对齐/dismiss409/同tid防线/tsc命令/接口签名/F10-F12定案/审查记录表）
- placeholder扫描（TBD/TODO/待定/implement later）：clean
- F10行原文含 :930-932（首次MISS为检索标记连写格式，非内容缺失）

## 结论
方案v2达到计划审查门禁（P0=P1=P2=0，P3清零），可进入实施。
按排期：Phase1+2（后端半天）→ Phase3（前端半天）→ Phase4真板联调。
降级说明：本轮无独立上下文子代理，交叉验证由"源码定案+标记复验"替代；实施完成后
（content模式）建议补一轮含运行验证的完整审查。
