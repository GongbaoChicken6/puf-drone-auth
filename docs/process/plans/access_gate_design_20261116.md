# 方案：接入弹窗 + 手动选择 + 等待队列（演示步骤②）v2

> 2026-11-16 制定，同日 auto-review R1 修订（发现清单见文末"审查记录"）。
> 目标：两板按 SW7 主动发起认证后，web 弹窗列出两台待接入机器，
> 人工选择一台走五帧验证，另一台留在等待队列（稍后可再选中验证）。
> 本方案是五步演示剧本中唯一需要开发的部分；①③④⑤已具备。

## Phase 0 勘察结论（代码级证据，已逐条核实；★=R1新增RTL/协议定案）

| # | 事实 | 证据位置 |
|---|---|---|
| F1 | 板端 SW7=auth_btn（AK25，带消抖）按下发 ACCESS_REQUEST；AUTH_POLL(0x0097) 等效遥控 SW7 | src/rtl/w3_protocol/w3_top_zc706.v:36、terminal_fsm.v:109-112 |
| F2 | 桥端 RealSerialListener 单串口监听；收到 0x0090 立即持锁内联跑完五帧（无人工介入点） | web_bridge.py:2051(单port)/2132-2142(自动_auth) |
| F3 | main() 仅启动一个监听器：--serial-port 单值；app.serial_listener 单引用 | web_bridge.py:2345-2349 |
| F4 | AUTH_POLL 下发模式现成：_do_poll（串口锁+先写后发+3s 等 last_access_request_ts 跳变+忙拒） | web_bridge.py:818-856 |
| F5 | 全局互斥已存在：app.serial_bus_lock + app.auth_in_progress（跨端口共享） | web_bridge.py:2134-2142 |
| F6 | SSE 契约有编译期穷尽锁：EventType/EVENT_TYPES/PayloadMap 四处同步 + 计数注释，新增须双侧同步 | web/src/core/types.ts:14-47 |
| F7 | 前端模态框可抄模式：EnrollWizard（role=dialog、ew-* class、分步、api 调用） | web/src/components/enroll-wizard.ts:10-60 |
| F8 | REST 路由表集中一处，加端点模式简单 | web_bridge.py:1711-1742 |
| F9 | 真板=tid1/tid2（模板与 pool_1/pool_2 注入逻辑）；板上 tid 由 SW12 拨码设定 | web_bridge.py:2066-2087 |
| F10★ | 板上等待窗=2s（TIMEOUT_CYCLES=50M@100M，板上200M=2s）；超时→S_BLOCKED(result=3)→**立即回 S_IDLE**（阻断即冷却，无自锁）→等待不伤状态，可反复唤醒 | terminal_fsm.v:21、:489-492、:930-932 |
| F11★ | AUTH_POLL **仅在 S_IDLE 被消费**（S_IDLE 分支 auth_start‖poll_start）；S_WAIT_CHALL 内 POLL 被无视（只收 0x0091）→"选中快于2s窗口"时首帧 POLL 必丢，必须有时序对策（见唤醒策略） | terminal_fsm.v:392、:479-492 |
| F12★ | 站端 C2 重放窗只在 on_access_request 里消费；闸门在 on_access_request **之前**拦截入队 → 入队不污染重放窗；唤醒后板子发新 C2（计数器每轮认证自增）必新鲜 → **重放误判风险不存在**（前提：闸门调用点在 proto.on_access_request 之前，实现时锁死这个顺序） | src/python/server/main.py:169-170/476-486、web_bridge.py:2180(调用点) |
| F13 | demo_start.ps1 现只接受单串口参数（auto 探测一只 CH340/CP210/FTDI） | scripts/demo_start.ps1:11-12/91-100 |
| F14 | 桥测试模式：test_poll_bridge.py（AUTH_POLL 桥测，假串口）、test_channel_ids.py（importlib 载入 web_bridge） | tests/ |

### 允许使用的现成 API（照抄，不得发明）
- self.protocol.pack(self.P.MSG_AUTH_POLL, terminal_id=tid, nonce=n) — web_bridge.py:834
- app.serial_bus_lock / app.auth_in_progress — :837/:2136
- self.hub.publish(etype, payload) — SSEHub
- app.submit_poll(tid) — RealApp:1231（选择动作的发板逻辑从此抽取）
- api.fetch 封装 — web/src/core/api.ts（enroll-wizard 同款）

## 设计总览

### 时序（目标体验）
1. 板A按SW7 → ACCESS_REQUEST(C2=n) 到 COM6 监听器 → **闸门拦截**（on_access_request 之前）：入队+发 SSE access.requested（不跑认证）
2. 板B按SW7 → 同上（COM11）→ 徽标+弹窗列出两台
3. 用户点"验证 板A" → POST /api/access/select {terminal_id:1}
   → 桥：按唤醒策略对齐时序 → 发 AUTH_POLL → 板A回新 ACCESS_REQUEST(C2=n+1)
   → 闸门见"已选中tid"放行 → 原 _auth 五帧全链（verdict/confirm/session.update 照旧）
   → 弹窗即时收起（依据 REST {ok:true} + access.selected 事件）
4. 板B仍在队列（其 FSM 已自动回 IDLE，F10）；轮到它时重复步骤3
5. 演示④场景：对板B选择验证但用"无模板/跨身份"编排得到 REJECT（本方案只管队列机制，拒绝编排属剧本层）

### 为什么闸门同时是并发安全的必需品（不止演示效果）
单口监听时 auto-auth 无冲突；**双口**后两板可能同时按 SW7，若都直跑 _auth 会共享
proto/templates 状态交叉污染。因此双口模式下未选中的 ACCESS_REQUEST 一律入队——
闸门 = 演示特性 + 串行化保护，一举两得。

### 唤醒策略（R1修订：2.2s 边界对齐，替代原"1.5s盲重试"）
依 F10/F11：POLL 只在 S_IDLE 生效；板子按 SW7 后有 2s 等待窗，窗内 POLL 必丢。
- select(tid) 计算 Δ = 2.2s - (now - entry.last_request_ts)
  - Δ ≤ 0（板子早已回 IDLE）：立即发 POLL
  - Δ > 0（用户秒选）：先 sleep Δ 再发（REST 同步等待，最坏 ~2.2s，前端按钮转圈即可）
- POLL 后 3s 内 last_access_request_ts 未跳变（板 BLOCKED 长滞或链路断——理论上
  S_BLOCKED 即回 IDLE 不该发生，防御性保留）→ 再补一次 POLL（+2.2s 对齐后）→
  仍无响应 → 回滚 selected_tid，409 附原因（"板端无响应：检查链路/按SW13后重试"）
- 整个 select 期间持有 app.serial_bus_lock 与 auth_in_progress 纪律照抄 _do_poll

### 闸门状态机（桥端，新增类 AccessGate）
接口与核心伪代码（实现照此签名，不得偏移）：

    class AccessGate:
        entries: dict[int, dict]     # tid -> {port, label, first_seen_ts, last_request_ts, repeats}
        selected_tid: int | None
        enabled: bool
        def decide(self, tid, port) -> str:      # "run" | "park"
            # enabled=False → "run"（旧行为）
            # enroll_session_active 或 auth_in_progress → "park"
            # tid == selected_tid → "run"
            # else → "park"
        def park(self, tid, port): ...            # 新entry或repeats+=1+刷新last_request_ts
        def can_select(self, tid) -> str | None   # None=可选, 否则409原因串
        def can_dismiss(self, tid) -> str | None  # tid==selected_tid → "verification in progress"
        def finish(self, tid, final_state): ...   # _auth尾部调用：清selected+出队

- 决策点在 RealSerialListener._loop 0x0090 分支（:2132-2142），**先 gate.decide 再
  on_access_request**（F12 顺序锁死）；放行时走原 _auth，parked 时 publish access.requested
- 出队时机：_auth 尾部（:2313 session.update 后）回调 gate.finish(tid) → publish
  access.finished {terminal_id, state}
- 防线：park 时若同 tid 已在不同 port 有 entry → 拒绝入队第二条 +
  server.log error（"SW12 拨码疑似重复：tid=N 同时出现在 COM6/COM11"）——
  演示配置错误的显式哨兵，而非静默覆盖
- dismiss：POST /api/access/dismiss {terminal_id}；对 selected_tid 返回 409

### SSE 契约新增（types.ts 四处同步 + 计数 22→25）
- access.requested {terminal_id, port, label, first_seen_ts, repeats}
- access.selected {terminal_id, ts}                    —— 选中+唤醒成功瞬间（弹窗收起依据）
- access.finished  {terminal_id, state}                —— 五帧结束出队（state: SESSION|BLOCKED）
- access.dismissed {terminal_id}
（R1修订：原方案把"选中"事件放在完成时刻发，语义混淆；拆分为 selected/finished 两事件）

### REST 契约新增（do_POST 路由表，web_bridge.py:1742 前）
- POST /api/access/select {terminal_id} → 200 {ok,terminal_id} / 404 {reason:"not queued"} /
  409 {reason}（并发选中/auth进行中/唤醒失败）
- POST /api/access/dismiss {terminal_id} → 200 {ok} / 409（选中验证中）
- GET /api/access/queue（挂 do_GET）→ {entries:[...], selected}（页面刷新恢复）

### CLI 变更（R1修订：补 tid→port 路由，修 /api/poll 双口缺陷）
- --serial-port 接受逗号分隔多口：COM6,COM11（单口写法兼容）
- --access-gate 开关（默认关）；**多口时强制开**（main 里断言：并发安全必需）
- --access-label "1=板A,2=板B" 可选（默认"终端#tid"）
- --tid-port "1=COM6,2=COM11" 可选静态映射；**多口模式下 /api/poll 与 select 唤醒
  必须按 tid 路由到正确监听器**（查表顺序：gate entries 的 port → --tid-port 静态表；
  都没有且监听器>1 → 明确报错"无法定位 tid=N 的串口"）。单口时保持 app.serial_listener
  旧语义直通（_do_poll:828 的原路径）。—— R1发现：原方案"serial_listener 指向第一个"
  会让板B的 /api/poll（含录入向导的"验证认证"按钮）打到板A口

## Phase 1 后端：闸门 + 双串口 + poll 路由（web_bridge.py + 新测试）

任务（照抄锚点，不发明）：
1. AccessGate 类（上述签名，纯逻辑不碰串口——便于单测）
2. RealSerialListener._loop 0x0090 分支改走 gate.decide()（改动≈20行，_auth 本体零改动；
   决策点在 on_access_request 之前——F12）
3. RealApp.submit_access_select / submit_access_dismiss（含 2.2s 对齐唤醒策略；
   发板逻辑从 _do_poll:818-856 抽取共用函数 _send_poll_to(tid)）
4. _do_poll 改为按 tid 路由（--tid-port + gate entries 查表；单口行为不变）
5. main() 多口启动 + 多口强制 gate 断言 + --tid-port 解析（:2345-2349 处）
6. _auth 尾部（:2313 后）挂 gate.finish 钩子

验证（确切命令+预期）：
- python -m pytest tests/test_access_gate.py -q → 新增≥12例全 passed
  （入队/重复按压刷新/选中放行/选中忙拒/409三分支/唤醒2.2s对齐逻辑用假时钟测/
  唤醒失败回滚/tid-port路由/同tid双port防线/dismiss选中409/未开gate旧行为回归）
- python -m pytest tests/test_poll_bridge.py tests/test_channel_ids.py tests/test_confirm_race.py -q
  → 全部 passed（基线不回退）
反模式：不得绕过 serial_bus_lock 直写 ln.ser；不得"先发事件后写串口"（_do_poll:839 纪律）；
不得改动 _auth 帧节奏（2200-2205 的 0.2s 约束是板上超窗教训）；
gate.decide 不得调到 on_access_request 之后（F12 重放窗前提）

## Phase 2 REST + SSE 端点（承接 Phase 1）

1. do_POST 两路由 + do_GET /api/access/queue（模式抄 :1716-1742）
2. hub.publish 四事件（具名事件，桥侧无需注册表——前端才锁）
3. 验证：python -m pytest tests/test_access_gate.py -q → passed（路由层用例并入同一文件）

## Phase 3 前端：弹窗 + 队列徽标（全部抄 EnrollWizard 模式）

1. types.ts：EventType/EVENT_TYPES/PayloadMap 四处 + 计数注释 22→25（漏一处 tsc 报错）
2. components/access-popup.ts（新建，~150行）：模态列出 entries（tid/标签/端口/等待时长/
   重复按压数），每条"开始验证"→ POST /api/access/select（按钮转圈承载最坏~4.5s等待）；
   409 展示 reason；access.selected 到达或 REST ok 即收起
3. topbar 徽标：队列长度>0 显示"待接入 N"，点击重开弹窗；刷新后先 GET /api/access/queue 恢复
4. store.ts 挂四个事件处理；main-console.ts mount
5. console.css 增 ~40 行（类名 ap-* 前缀，风格随 ew-*）
6. 验证（确切命令+预期）：
   - cd web && npx tsc --noEmit → 0 error（穷尽锁生效）
   - cd web && pnpm build → dist 重建无报错
   - playwright 截图三态（空/两台待选/一台等待+验证中）存 build/reports/，文件存在且>0B
反模式：弹窗里不得直接跑认证逻辑（只发 select，五帧展示复用现有事件流）；
不得用 onmessage（SSE 是具名事件，types.ts:26-28 注释明示）

## Phase 4 启动脚本 + 联调（板子回来后）

1. demo_start.ps1：多口参数（-SerialPorts COM6,COM11）+ --access-gate + --tid-port + 标签
2. 联调清单（真板，逐条证据落盘）：
   - SW12 确认板A=tid1、板B=tid2（F9；拨错时依赖同tid防线哨兵）
   - 冷启动预热（首帧 0xFE 已知坑，先各 poll 一次）
   - 双板同按 SW7 → 弹窗两台 → 选A（含"秒选"场景：按下后<1s即选，验证2.2s对齐）
   → A 全链 PASS → 队列只剩B → 选B（接④拒绝剧本编排）
   - 验证 /api/poll 在双口下对板B可用（录入向导"验证认证"按钮回归）
   - 链路断场景（拔板B串口）→ select 409 文案正确
   - 全程录屏 + 截图存 build/reports/

## Phase 5 终验
- 后端：python -m pytest tests/ -q → 基线 193 passed + 新增全过（总数下限=193+12）
- 前端：tsc 零错误 + dist 重建 + 三态截图
- 端到端：真板双机全流程一遍（步骤②串进五步剧本彩排）

## 工作量与排期
- Phase 1+2（后端+测试）：半天
- Phase 3（前端+重建+截图）：半天
- Phase 4（联调）：板子恢复后 2 小时内
- 今日(11-16)可完成 1-3 的虚拟验证部分，不依赖板子

## 决策记录（默认已定，可推翻）
1. 弹窗形态：顶部徽标+点击展开（不遮挡五帧动画）
2. 未选中机器不自动出队（等演示者处置；手动 dismiss）
3. access.dismissed 独立事件（审计回放完整）
4. R1新增：唤醒用"2.2s边界对齐"而非固定延迟重试（RTL证据 F10/F11）

## 审查记录（auto-review plan模式，R1，2026-11-16）
环境无spawn_teammate → 内联降级：对抗性自查 + 把方案中"待确认"项用 RTL/协议源码定案。
R1发现与处置（门禁 P0=0 P1=1 P2=4 P3=2 → FAIL → 全部修复后本文档即v2）：
| # | 级别 | 发现 | 处置 |
|---|---|---|---|
| 1 | P1 | 原方案保留 serial_listener 单引用指向第一个监听器 → 双口下 /api/poll（录入向导"验证认证"按钮）对板B打到板A口 | 已修：--tid-port 静态映射 + gate entries 查表路由，Phase1任务4 |
| 2 | P2 | access.selected 计划在五帧完成时才发，与"选中即收弹窗"的前端时序矛盾 | 已修：拆分 selected（选中瞬间）/finished（完成出队）两事件 |
| 3 | P2 | 唤醒重试间隔1.5s无依据：板子2s窗内POLL必丢，1.5s重试可能仍落在窗内 | 已修：2.2s边界对齐策略（F10/F11证据），并给最坏时延~4.5s |
| 4 | P2 | dismiss 选中中的 tid 行为未定义 | 已修：409 |
| 5 | P2 | 同tid双板（SW12拨错）队列键冲突互相覆盖 | 已修：同tid不同port拒绝入队+server.log哨兵 |
| 6 | P2 | 验证步骤缺"确切命令+预期输出" | 已修：各Phase补 pytest/tsc/pnpm/playwright 命令与预期 |
| 7 | P3 | 缺 AccessGate 接口签名/伪代码 | 已修：补签名+decide伪代码 |
| 8 | P3 | F表混入非证据条目（SW12标签说明） | 已修：并入F9 |
同时把三项"联调时复核"升级为已确认（F10/F11/F12，file:line 见表），其中 F12
（重放窗安全）是原方案未论证的隐含前提，现已锁死调用顺序为防退化约束。
