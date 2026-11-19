# auto-review 报告 · 单 HC-12 共享信道改造（方案 B′）· 2026-11-19 19:45

审查方式：**降级多视角串行**（本会话仅有 lead，无 spawn_teammate/subagent 原语；Team 任务板可见但无派遣通道）——
以【缺陷审查 / 规格合规 / 静默失败 / 测试缺口 / 回归门禁】五视角串行过查，再综合定级。

审查范围（本轮改动）：

- src/rtl/w3_protocol/terminal_fsm.v（点名校验 S_POLL_CHK、3s 授权窗口、注册门控、会话态策略）
- web/bridge/enroll_real.py（每轮点名开窗）
- web/bridge/web_bridge.py（AUTH_POLL nonce 防 0，两处）
- scripts/demo_one_click.ps1（单口共享信道分支）
- sim/tb/*（TB 兼容参数 + 新增 tb_poll_gate）
- build/ps1/run_xsim_w3.ps1（仿真门禁补依赖）

## 发现与处置：P0=0 / P1=3（全修）/ P2=2（全修）/ P3=2（记录）

| 级别 | 发现 | 证据 | 处置 |
|---|---|---|---|
| P1 | S_POLL_CHK 的 nonce 末字节读取时序错误：idx==7 拍读到的仍是 payload[6]，poll_n3 取错字节 → nonce≠0 判定可能永远为假（点名无法唤醒） | 代码走查：fp_rd_addr 寄存一拍后数据才有效（terminal_fsm.v 既有注释亦如此规定） | 改为读满 9 拍：idx 1..8 收 payload[0..7]，idx==9 判定；tb_poll_gate T2 实证唤醒成立 |
| P1 | 4 个老 TB（tb_terminal_fsm / tb_gap_regression / tb_key_derive / tb_puf_path）直灌 CHALLENGE，被新窗口门控挡死 → 仿真门禁全红 | [WATCHDOG] TIMEOUT @ TE1 | 新增参数 POLL_GATE_EN（默认 1）；老 TB 显式传 0 保持历史语义；门控本身由新增 tb_poll_gate 覆盖 |
| P1 | 仿真门禁长期漏编依赖：ro_array_sim / speck64_96 / challenge_decode 未在 run_xsim_w3.ps1 文件表里 → tb_terminal_fsm 从未真正跑过（靠 xsim.dir/work 陈旧库侥幸 elaborate） | xelab: Module ro_array_sim not found | runner 补三个文件；7 套 TB 现全部真实编译并 PASS |
| P2 | POLL_WIN_CYC 声明在模块体内，Vivado 不允许实例化覆写（localparam cannot be overwritten）→ 无法做窗口过期测试 | clean-room xelab 报错 | 移入模块参数端口表，TB 覆写 400 拍做 T4 过期测试 |
| P2 | 两处 AUTH_POLL 的 nonce 若恰为 0（time_ns & 0xFFFFFFFF == 0，概率 1/2^32）会被板端当作仅开窗从而唤醒失败 | 代码走查 | 两处均加 or 1 |
| P3 | tb_poll_gate 用层次化 dut.state 观测（可接受于 TB，但不产生独立协议断言） | — | 记录；若后续需要，改为输出端口观测 |
| P3 | 单口桥在 /api/poll 的 resolve_listener 依赖单监听器直通路径，未加显式单口断言日志 | 代码走查 | 记录；演示前由 demo_one_click.ps1 的归类日志覆盖 |

## 修复后验证（新证据，非上一轮结论）

| 门禁 | 结果 |
|---|---|
| verify_wrapper.ps1（xvlog + xelab 全 RTL） | **VERIFY_WRAPPER_PASS**（15 端口全匹配） |
| run_xsim_w3.ps1（7 套 TB） | **CRC16 / MAVLINK / FRAME_PARSER / BYTE_FIFO / UART_TX / TERMINAL_FSM / POLL_GATE 全 PASS** |
| 新增门控 TB 断言 | T1 点名他机→保持 IDLE；T2 点名本机+nonce≠0→唤醒(state=12)；T3 nonce==0→不开认证但窗口内 CHALLENGE 被接受(state=14)；T4 窗口过期→CHALLENGE 被拒 |
| pytest tests/ -q | **220 passed / 1 skipped / 3 subtests** |
| demo_one_click.ps1 语法 | PARSE_CLEAN（PS5.1 parser） |

## 未执行（降级）

- spawn_teammate 多代理并行审查（环境不支持）→ 以串行五视角替代
- playwright 浏览器验证：本轮无前端改动（前端零改动是方案 B′ 的设计目标之一）
- 安全专项（security-best-practices / security-threat-model）：本轮为通信协议/固件改动，无 Web 入口新增；按技能要求需用户显式请求才触发，此处未执行

## 新发现的风险（待上板验证项）

1. **模板失效**：RTL 变化 → 环振布局变化 → v4c/seed2c 上板后必须重录 tid1/tid2 模板（脚本会告警）。
2. **窗口时序**：3s 窗口从点名开始；enroll 每轮刷新（约 0.5~1s/轮）足够，但若板端 PUF 测量慢于窗口，注册背靠背轮可能落在窗口外 → 已由每轮点名覆盖；上板验证需连续 3 轮以上不报超时。
3. **单口下 /api/poll 的限流**：_do_poll 与真板实轮共享每分钟配额，连点会限流（既有语义，记录）。

（完）