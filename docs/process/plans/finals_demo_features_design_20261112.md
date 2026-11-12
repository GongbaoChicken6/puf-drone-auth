# 决赛演示新功能 · 完整实现设计（finals_demo_features_design）

> 日期 2026-11-12 ｜ 工作区 D:\puf-drone-auth（HEAD=eda6dec，无未提交跟踪改动）
> 需求来源：D:\文件\ssssssss\FPGA\FEATURES_finals_demo_20261112.md（N1-N11 规格）+ HANDOFF_finals_demo_20261112.md
> 本文档 = 实现级设计：架构全景、逐功能改动设计（文件:行 + 接口 + 帧格式）、批次R 执行序列、验证矩阵、回退方案。

---

## 0. 口径对齐（HANDOFF ↔ FEATURES ↔ 本设计）

| 项 | HANDOFF（11-12 15:40） | FEATURES/本设计 | 说明 |
|---|---|---|---|
| LED 增强 | 方案A内一句话 | 细化为 N1（板载闪烁模式）+ N7（PMOD 外接大灯/蜂鸣器） | 同一轮 RTL 重建 |
| 演示优化范围 | 方案A三件套 | 方案A + N2-N5/N8/N10/N11（8问+后续需求新增） | 排期 11-13→11-19 |
| 演示场景 | 心跳→认证→假冒→重放→本尊 | 不变，追加"基站主动巡检(AUTH_POLL)"与"伪基站攻击+告警"两个环节 | 解说词更新 |
| 仓库 | 不动 RTL | terminal_fsm/mavlink_frame/w3_top_zc706 三文件定点改动 + 新文件 | 走 CI 全门禁 |

**仓库现状核实（2026-11-12 16:46）**：HEAD eda6dec，src/rtl、web、build/tcl 均与设计读取一致，无重命名/搬迁。仅存在历史未跟踪调试散件（_*.py/_*.png，不影响）。

---

## 1. 项目架构全景（实现设计的事实基础）

### 1.1 RTL 层次与数据流

```
w3_top_zc706 (板级 wrapper, src/rtl/w3_protocol/w3_top_zc706.v)
 ├─ clk_wiz_0        200MHz差分(H9/G9, DIFF_SSTL15) → 100MHz + locked
 ├─ rst_n = ~SW13(高有效!) & mmcm_locked
 └─ w3_top (ENROLL_EN=1, SEED_GATE_EN=1, ENABLE_KEY_DERIVE=0→DEVICE_KEY常量)
     ├─ terminal_fsm (src/rtl/w3_protocol/terminal_fsm.v, 16态, L90-105)
     │   ├─ speck64_96 u_speck      R2=Speck(K,C2)；KDF 时分复用（sp_key mux L250）
     │   ├─ challenge_decode u_cd   种子→512bit 配对表
     │   ├─ ro_array u_ro_array     认证测量（16环，w2_waiver 豁免 LUTLP-1）
     │   ├─ ro_array u_ro_entropy_array + ro_entropy  上电熵→C2初值（P1-5）
     │   ├─ mavlink_frame u_mf      帧构造（start/pay_phase/frame_done 握手，§6.1）
     │   ├─ byte_fifo(64B)→uart_tx  （FIFO 强制，禁直连）
     │   └─ uart_rx→frame_parser    （fp_frame_ok 单拍→rx_ok_latch 粘滞）
     └─ LED: auth_busy→DS9(G2) auth_result[1:0]→DS10/DS8(W21/Y21) heartbeat→DS35(A17)
```

**terminal_fsm 关键接口/语义（改动设计依据）**：
- 端口（L36-84）：`auth_start`（单拍，w3_top 由 SW7 消抖+熵门控产生）；RX 侧 `fp_msg_id/fp_frame_ok/fp_rd_*/fp_rx_inhibit`；TX 侧 `mf_*`。
- `rx_ok_latch` 粘滞锁存（L316-324）：仅等待态保持；**S_IDLE/S_SESSION 收帧时只有 1 拍可见窗口**——既有 ENROLL_IDLE_ACCEPT 分支（L395-408 注释）就是按此惯用法写的，AUTH_POLL 沿用同一 idiom。
- `fp_rx_inhibit`（L305-308）不含 S_IDLE/S_SESSION/S_WAIT_* → 空闲期帧可正常接收。
- `result_r`：0进行中/1PASS/2REJECT/3BLOCKED；保持到下一轮 auth_start（L384-385/L675）或 rst；**S_BLOCKED 一拍自清回 S_IDLE（L906-908），锁的是显示码不是状态**。
- R2 失配精确分支：L648-651（`fp_rd_data != r2_expected[...]` → S_BLOCKED + 2'd3 + 清 key_valid_r）。这是 N3 唯一改动点。
- S_TX_CONFIRM 组帧预填（L452-455）与完成后跳转（L418-426 case：`S_TX_CONFIRM: state <= S_SESSION`）——N3/N4 都要动这处分流。
- 站端挑战受控接受：仅 S_IDLE（L395-408）与 S_WAIT_RESULT（背靠背注册轮）；进入注册轮即清 `calc_done_flag`（L406，防重放绕过 P2-1 守卫）→ 站端主动挑战**结构上无法**完成 R2 双向验证。

### 1.2 站端（Python）

```
web/bridge/web_bridge.py（103KB 单文件）
 ├─ BridgeHandler.do_GET/do_POST 路由表（L1543-1594）：
 │   GET  /api/status /api/golden-frames /api/events(SSE) /api/viz/*
 │   POST /api/auth{tid,mode} /api/enroll{tid,n} /api/c2reset /api/setkey /api/demo/reset
 ├─ RealApp.submit_* → Orchestrator(Job) 异步 → SSE hub.publish 事件
 ├─ RealSerialListener（L1895）：单串口；_loop 只 dispatch 0x0090（L1959），
 │   其余帧 parse 后丢弃；_auth 串行完成五帧（R1→RESULT 有 0.2s 节奏 sleep L1989）
 │   CONFIRM 等待 17B 仅 rv==0（L2030-2043，confirm.done 硬编码 status:0 ← N3 修）
 └─ 注入：templates.json(tid1/2)+pool_1/2 → 真板模式

src/python/server/
 ├─ protocol.py  帧字节级唯一真相源（§3 消息表/_CRC_EXTRA/pack/parse/黄金）
 ├─ enroll.py    enroll_device(protocol,transport,tid,n,measurements,on_progress)
 │               ← 传输无关 + UI 进度回调（N5 直接复用）
 ├─ hsm.py       SpeckHSM/设备密钥（12B）管理
 ├─ crp_pool.py / template_db.py / threshold.py(TAU 6/16) / puf_order.py
 └─ evaluation/puf_model.py  derive_device_key（KDF 与 RTL L232-238 冻结一致）
```

### 1.3 前端（web/src，Vite+TS，dist 预构建离线）

- `core/api.ts`：REST 封装 + SSE 客户端（断线退避→1s 轮询降级）。
- `components/terminal-card.ts`：**已有按钮** 认证(normal)/仿冒(spoof)/重放(replay)/注册/清C2窗/演示密钥——全部走仿真路径（/api/auth 对真板 tid 被守卫拦为 run.error）。
- 其余：topbar（S3 场景钮）、frame-timeline、hex-viewer、audit-log、hd-gauge、stage3d/particles、left/right-panel。
- 事件流：桥 hub.publish → SSE → `core/bus.ts` dispatchPuf → 组件。

### 1.4 构建/CI/QSPI 链

- 双板构建：build/tcl/build_w3_board.tcl（生产）与 build_w3_board_seed2.tcl（环振 PBlock→X1Y0 + USERID 0x5EED0002）；WNS<0 exit 4 / WHS<0 exit 10 / LUTLP-1 豁免 32 nets 响亮校验。
- CI（scripts/ci_regression.ps1）：①wrapper 三元素锁（w3_top_zc706.v：SW13直连clk_wiz/rst_n取反/SEED_GATE_EN=1）②board-tcl 锁+filelist 一致性+**MANIFEST/prereg SHA 钉死**③编译/精化/仿真 18 TB（`TB_.*_PASS` 正向哨兵）④ENROLL_NEG 变体⑤Python 全套（speck 自检/单元/serial/puf_model/interop/dos_flood/ml_attack/threat_poc/R2 canary）。
- TB 四规约（sim/tb/README）：watchdog 双向收尾/正向证据计数器/变异验证/孪生 BFM 激励。
- QSPI：write_cfgmem spix4 128 → MCS → JTAG 烧 QSPI → SW11=00000→00110。**当前 build/ 下无任何 MCS**。
- 桥单进程单串口；两板共享一条串口信道（HC-12 同信道广播）。板A=C001、板B=C006。

---

## 2. 逐功能实现设计

### N1 · demo_led 闪烁模式模块（批次R）

**新文件** `src/rtl/w3_protocol/demo_led.v`（TB 哨兵 `TB_DEMO_LED_PASS`；看门狗预算 > 最坏闪序总时长，含 BLOCKED 常亮路径——sim/tb 四规约；变异项：破坏 REJECT 翻转分支喂入必须 FAIL，使规约三引用自洽）：

```verilog
module demo_led #(parameter FREQ_HZ = 100_000_000) (
    input  wire       clk, rst_n,
    input  wire [1:0] result_in,      // 0进行中 1PASS 2REJECT 3BLOCKED（来自 terminal_fsm.auth_result）
    input  wire       busy_in,        // 透传 busy
    output wire [1:0] led_result,     // → DS8/DS10
    output wire       led_busy,
    output wire [3:0] ext_led,        // → PMOD 外接 绿/绿/红/琥珀（N7）
    output wire       ext_buzzer      // → PMOD 蜂鸣器（N7）
);
```

行为表（FLASH_HALF=FREQ_HZ/8=12.5M 拍≈125ms）：

| result_in | led_result 行为 | ext_led | ext_buzzer |
|---|---|---|---|
| 0（进行中） | 00 | 全灭 | 短哔×1（busy_in 0→1 上升沿触发） |
| 1 PASS | result 持续拍计数：绿闪 3 次（亮125ms灭125ms）后绿灯常亮 | 绿×2 同步闪后常亮 | 上扬两短哔 |
| 2 REJECT | led_result 在 2'd2↔2'd0 间 2Hz 切换（红亮灭闪，非红绿交替） | 红+琥珀交替 | 长哔 600ms |
| 3 BLOCKED | 双亮保持（现语义不变） | 红+琥珀常亮 | 长-长两声 |

设计要点：①纯函数于 result_in + 自由计数器，无 FSM；②result 变化沿复位计数器（新一轮重新闪）；③busy 直通。**不例化进 w3_top（不动 18 TB 语义），只例化进 w3_top_zc706**：wrapper 里 `auth_result` 断开直连，经 demo_led 再出引脚。

**wrapper 改动**（w3_top_zc706.v）：加 demo_led 例化 + 新端口 ext_led[3:0]/ext_buzzer。⚠ CI wrapper 三元素锁只断言三处既有语句，加例化不触碰——但仍须跑 CI 确认。
**XDC 改动**（w3_top_zc706.xdc）：ext_led/ext_buzzer 引脚 = PMOD J58 未占用脚（UART 占 J58.1=AJ21/J58.5=AB21）。候选：PMOD1_1/3/4/5/6/7——**执行时以 UG954 v1.8 J58 表 + part0_pins.xml 双源定脚，LVCMOS25**（与 UART 同 bank，经 TXS0108E 到 3.3V 侧）。
**build tcl**：两个构建脚本 add_files 各加一行 `$SRC/rtl/w3_protocol/demo_led.v`（filelist 一致性锁要求双脚本同步加）。

### N3 · CONFIRM_FAIL 上行告警（批次R）

**terminal_fsm.v 两处定点改动**：

1. R2 失配分支（L648-651）：
```verilog
// 改前: state<=S_BLOCKED; result_r<=2'd3; calc_done_flag<=1'b0; key_valid_r<=1'b0;
// 改后: 先上报后阻断
tx_buf[0]   <= terminal_id;          // CONFIRM 载荷 <IB>: tid(4B)+status(1B)
tx_buf[1..3]<= 0;  tx_buf[4] <= 8'h01;   // status = CONFIRM_FAIL
tx_len      <= 6'd5;
result_r    <= 2'd3;
state       <= S_TX_CONFIRM;         // 发完在 done 分流进 S_BLOCKED
calc_done_flag<=1'b0; key_valid_r<=1'b0;
```
2. 发送完成分流（L418-426）：`S_TX_CONFIRM: state <= (result_r == 2'd3) ? S_BLOCKED : S_SESSION;`
   （时序安全：result_r 在进入 S_TX_CONFIRM 前一拍已 NBA 为 3；发帧耗时 >> 1 拍。）

**mavlink_frame 零改动**（0x0094 已在表内）；**protocol.py 零改动**（CONFIRM_FAIL=1 语义已有，on_confirm L589-602 已处理）。

**web_bridge.py 两处**：

答辩口径（诚实边界）：CONFIRM_FAIL 本身无 MAC——攻击者可在真 PASS 后注入伪造 CONFIRM(1) 制造假警报（不能劫持会话）；Tier2 ALARM(0x0096) 的 MAC 关闭该缺口。
1. `_auth` CONFIRM 等待段（L2030-2043）：用 `self.proto.parse(cf)` 返回字典的 `status` 字段（payload[4]；`<IB` 布局 = tid(4B)+status(1B)，protocol.py L433。**勿按载荷[0] 读**——那是 tid LSB，tid=1 时会把每次真 PASS 误判 FAIL 触发假告警）——
   - status==0 → 现行为（confirm.done verified_r2:True）；
   - status==1 → publish `confirm.rejected` + **矛盾关联告警** `base.spoof.suspected` {`own_verdict`:rv, `terminal_says`:"FAIL", `evidence`:"R2 mismatch at terminal"} + server.log error；
2. 修 bug：现 L2041-2042 硬编码 status:0。

**TB（tb_terminal_fsm.v 增用例 + 变异）**：
- T-CF1（正向）：驱动完整认证到 S_VERIFY_R2，注入 R2 失配 RESULT 帧 → 断言 TX 字节流出现合法 0x0094 帧且载荷 status=1（正向哨兵 `TX_CONFIRM_FAIL_SEEN`）→ 之后 result_r==3；
- T-CF2（不变式）：正常 PASS 路径 CONFIRM status=0 行为不变（黄金回放）；
- 变异验证：pre-fix RTL（L648 直接 S_BLOCKED）喂 T-CF1 必须 FAIL（规约三）。

### N4 · AUTH_POLL(0x0097) 基站主动认证（批次R）

**帧格式**（契约 §3 新增第 7 条）：
```
MSG_AUTH_POLL = 0x0097 (server→terminal)
载荷 8B "<II": terminal_id(4B LE) + nonce(4B)   ← 板端忽略载荷内容，仅识别 MSGID
CRC_EXTRA = 0x60（0x5A..0x5F 已占满）
```

**terminal_fsm.v**（新 localparam + 两处 OR，全仿 idle-accept 惯用法）：
```verilog
localparam [23:0] ID_POLL = 24'h0097;
wire poll_start = rx_ok_latch && fp_msg_id == ID_POLL;
// S_IDLE (L384): if (auth_start || poll_start) begin ... 原分支体不变
// S_SESSION (L674): if (auth_start || poll_start) begin ... 原分支体不变
```
（1 拍采样窗口语义与 L395-399 注释同理；S_IDLE/S_SESSION 不在 inhibit 列表，帧可入。）

**mavlink_frame.v（TX 侧，auto-review R2 P2 修复）**：①L92-98 查表加 `ID_POLL: crc_extra = 8'h60;` + localparam；②**L105-107 `id_legal` 加 `|| (msg_id == ID_POLL)`**——TX 构造器在 S_IDLE 以 `cmd_ok = id_legal && len_ok` 拒绝 start（frame_err，L187-200），漏扩则 0x0097 帧造不出来：tb_mavlink_frame 0x0097 用例、T-FP1 的帧源、N11 ALARM 发送全部失效（与 RX 侧 frame_parser 同类缺口的 TX 镜像）。
**frame_parser.v（RX 侧，auto-review R1 P1 修复——漏改则 poll 帧被解析器拒收）**：①localparam 加 `ID_POLL = 24'h0097`；②L107-117 CRC_EXTRA 查表加 `ID_POLL: crc_extra = 8'h60;`（default=0x00 会使 CRC 校验必败→frame_err）；③L119-121 `id_legal` 加 `|| (msgid_r == ID_POLL)`（否则 S_CHECK 直接拒帧，rx_ok_latch 永不置位）。⚠ 该缺口**无既有门禁可拦**：check_contract_sync.py 只比对 protocol.py↔契约文档，tb_terminal_fsm 直驱 fp_* 绕过真解析器——靠下述 T-FP1/T-L31 补门禁。
**protocol.py**：MSG_AUTH_POLL=0x0097 / _CRC_EXTRA / _MSG_NAMES / pack/parse 载荷校验。
**契约文档**：§3 表加行 + §7 变更记录 + `tools/check_contract_sync.py` 重跑全绿（黄金向量生成一只合法 poll 帧）。
**web_bridge.py**：
- do_POST 加 `/api/poll`：`{"run_id": app.submit_poll(tid)}` → Job(kind=poll) → `ser.write(protocol.pack(MSG_AUTH_POLL, tid=tid, nonce=os.urandom(4)))` + `frame.tx` 事件 + **`poll.sent` 事件 {tid, nonce}**（N6 的 EVENT_TYPES 订阅此名，巡检钮/向导靠它显示在途状态——事件名以 poll.sent 为准）；
- 结果等待复用现有机制：板子回 ACCESS_REQUEST → RealSerialListener._auth 照常全链（判决/verdict/confirm 全自动）；
- 3s 内无 0x0090 入站 → Job 失败 → publish `run.error` {"hint":"无响应：终端阻断态请按 SW13，或检查信道/供电"}。
**前端**：terminal-card 新增 `巡检` 按钮（绿 ghost；现有六按钮之外的第七个）〔R2 备案:对所有终端卡渲染而非仅 real-terminal——loopback/demo 点击由桥端诚实回 run.error,不假成功;TerminalState 无 source 字段,加门控需扩 store 契约,收益不抵〕→ `api.poll(tid)`；types.ts/api.ts 加对应类型与 EVENT_TYPES。

**TB（tb_terminal_fsm 增用例）**：
- T-AP1：S_IDLE 收合法 0x0097 帧 → 断言 TX_ACCESS 发出（C2 递增）；
- T-AP2：S_SESSION 收 0x0097 → 同上；
- T-AP3：S_WAIT_CHALL 中段收 0x0097 → 必须被忽略（不破坏在飞轮次）；
- T-AP4（变异关键）：pre-fix RTL（无 poll 分支）喂 T-AP1 必须 FAIL。
- tb_mavlink_frame：0x0097 帧 CRC_EXTRA 正确性（黄金向量比对）。
- T-FP1：tb_frame_parser 增 0x0097 接受用例——用 tb_mavlink_frame 生成的合法 poll 帧喂**真解析器**，断言 frame_ok + msgid 正确（端到端锁住 RX 查表/id_legal 两道门）。
- T-L31：tb_level3_protocol（已互连真 terminal_fsm+mavlink_frame+frame_parser）增 poll 端到端用例：发 poll 帧 → 全链路出现 TX_ACCESS。

### N2 · 信道 IDS（站端批，零协议改动）

**web_bridge.py `_loop`（L1951-1963）**：parse 成功且 `mid in (0x0091, 0x0093, 0x0095)`（三个 MSGID 均只可能由站端发出——入站方向即异常）→ publish `channel.intrusion` {`msg_id`,`name`,`hex`,`len`,`note`}（payload 级 ts 由 SSE 信封层统一提供，键名以实现为准）+ 同款 try/except 线程保护；噪声半边：1s 滑窗内 ≥3 次 resync → 限速 publish `channel.noise` {`events`,`window_s`,`dropped_bytes`,`note`}（同窗只发一次）。〔auto-review c1 轮已实现，9 测试锁定〕
**前端**：红色横幅（订阅 channel.intrusion，5s 自动衰减，body 悬浮位——有意偏离 topbar 槽位以不动 console.html 网格，备案）；审计行经 server.log(error) 通道落账（类型筛选按 server.log——备案简化）。`enroll_session_active` 锚点已在 RealApp.__init__ 显式初始化（N5 跨批次契约防漂移）。**注意**：与 N5 注册互斥——enroll_real 期间站端自己发 0x0091 属预期，IDS 在 enroll 会话窗口内静默（否则自触发）。

### N5 · 真板指纹录入（站端批）

**桥侧新端点与执行器**：
```
POST /api/enroll_real {terminal_id, n=100, measurements=3} → run_id
  前置: tid ∈ real_serial_tids；串口空闲（互斥锁 serial_bus_lock 已于 R2 轮新建并锚定 RealApp.__init__——_auth 全程持锁、_do_poll 写口持锁、N5 enroll runner 届时同锁；另 auth_in_progress 忙标志供 poll 快速忙拒）
  实现形态(auto-review R1 P3 修复)：薄 SerialTransport 适配器 ——
    transport.respond(tid, seeds, frame=chal) = ser.write(chal) + 从 enroll_rx_queue 等 0x0092(超时3s)
    然后**直接调用 enroll_device(protocol, transport, tid, n, measurements, on_progress)**
    （单一实现防漂移：批量循环/回滚/majority_bytes 全复用 enroll.py L42-98；on_progress→publish enroll.progress 直连；仅当适配器不可行才允许手写循环并注明原因）
  写入: <data-dir>/templates/templates.json (沙箱)  + publish enroll.done {n_pairs, stability}
POST /api/enroll_real/export {terminal_id}  ← 显式二次确认(前端弹窗)
  备份 data/templates/templates.json → templates.json.bak-<ts> 后合并写入仓库模板库
```
**串口协调**：RealSerialListener._loop 增旁路——`app.enroll_session_active` 为真时，0x0092/0x0091 帧推入 `app.enroll_rx_queue` 而非丢弃；enroll runner 从队列取（复用既有 parse）。0x0090 仍走 _auth（互斥锁保证不会并发）。
**前端**：新组件 `components/enroll-wizard.ts`（modal）：tid 预填、挑战数/测量次数、SSE 进度条、每批 HD 稳定性列表、完成后自动调 /api/poll 验证（"录入→巡检→认证"一条龙）。terminal-card 的"注册"按钮对真板 tid 改为打开 wizard。
**坑位**（设计已吸收）：末轮后板停 S_WAIT_RESULT 2s 超时锁 2'd3 显示码 → wizard 完成后自动 poll（走完整轮刷新显示）+ 提示文案；板B 先 setkey 再 enroll（铁律6，wizard 内置顺序检查并提示）。

### N6 · 前端数据流展示升级（站端批）

- ~~`core/frame-decode.ts`（新）~~〔R2 备案:实现时发现等价能力已由 format.ts payloadFields(字段字节分段)+hex-viewer fieldNotes(中文名+🔒+密文着色)联合承担,不再新建模块;FEATURES 的"挑战/响应配对连线"子项裁剪(字段注记已并排呈现,连线增益低);飞行动画实测 900ms/→←基站 文字/独立 body 悬浮组件(非 timeline 内嵌),信息等价备案〕
- hex-viewer.ts：渲染 frame-decode 结果（分段着色 + 中文字段名 + R2/密文字段锁形样式）；
- frame-timeline.ts：新增 `flight` 动画层——帧事件到达时从终端卡片→基站卡片（或反向）飞行 800ms，携带 `len B ↑/↓` 徽标；
- types.ts：EVENT_TYPES 增 `channel.intrusion / channel.noise / confirm.rejected / base.spoof.suspected / enroll.progress / enroll.done / poll.sent`。
- 构建纪律：`npm run build` → dist 自包含 → console.html 截图验证（铁律4）。

### N7 · 外接大信号灯 + 蜂鸣器（硬件，并入批次R 的 demo_led 输出）

- 器件：10mm LED 绿×2/红×1/琥珀×1 + 有源蜂鸣器（3.3V），330Ω 限流；接 J58 对应信号脚+GND（3.3V 侧，经 TXS0108E）。
- **执行时定脚**：UG954 v1.8 J58 引脚表 × part0_pins.xml 双源核对（本地 ug954_text.txt/高清图可查），避开 AJ21/AB21。
- 流程铁律：**断电插拔**；先 JTAG 验证灯语再 QSPI。

### N8 · 伪基站演示编排（脚本批）

`tools/attack/fake_base.py`（新，pyserial）：
```
用法: python tools/attack/fake_base.py COM9 --tid 1 --mode inject
  监听字节流 → 解析出 RESPONSE_R1(0x0092) → ≤50ms 内注入伪 RESULT(0x0093)
  (protocol.pack 合法 CRC + result=0 + 乱填 r2 —— 竞速: 真站 R1→RESULT 有 0.2s sleep+计算)
  --mode replay --file <旧RESULT.hex>   # 重放变体
  --mode noise                          # 纯噪声 DoS 变体
日志: data/d1_evidence/finals_demo/attack/<ts>.log（帧 hex + 时间戳, 证据落盘）
```
演示剧本（解说词新增"镜头 4.5 伪基站攻击"，约 40s）：SW13→SW7 → 攻击端注入 → 板A R2 失配 → CONFIRM_FAIL 上行 → BLOCKED 双亮 → 屏幕三重证据（channel.intrusion 红警 + confirm.rejected + base.spoof.suspected 矛盾关联）。

### N9 · 一键启动 demo_start.ps1（auto-review c1 轮加固版，UTF-8 BOM）

```ps1
1. Stop 残留 web_bridge/python(桥特征命令行匹配;逐个报成败,杀后验证端口已释放,失败弹窗)
2. 枚举 COM: WMI(CH340/CP210/FTDI) × [SerialPort]::GetPortNames() 双源互核 → 候选落盘沙箱 com_probe.log;多候选时中止并要求 -SerialPort 显式指定(决赛双串口日)
3. New-Item 沙箱 %TEMP%puf_demo_<ts> (铁律5)
4. Start python web/bridge/web_bridge.py --repo-root . --data-dir <沙箱> --serial-port <COM> --port 8642 --open
5. 失败自检: 15s 内 /api/status 不通 → 弹窗报错 + 日志路径
```

### N10 · 厂商集成指南 docs/integration_guide.md（P2）

大纲：终端侧接口表（UART 115200/auth_btn/term_id[7:0]/LED + 参数 FREQ_HZ·BAUD·TIMEOUT_S + 资源 2% LUT + WNS）｜站端 Python API（protocol/enroll/hsm/pool/threshold 对外函数）｜注册准入流程（setkey→enroll 100 CRP→巡检）｜迁移步骤（wrapper/XDC/时钟/重注册/阈值重标定）｜诚实边界（常量 K→PUF 派生 KDF 已仿真待 ECC、熵 44bit、DoS 不设防）。

### N11 · ALARM 0x0096 带 MAC（Tier2，仅缓冲日）

帧：`MSG_ALARM=0x0096, 载荷 {alarm_code(1B), tid(4B), mac(8B)=Speck(K, C2‖code)}`，CRC_EXTRA=0x61。
RTL：S_BLOCKED 入口前新增 S_TX_ALARM（复用 u_speck 空闲窗口算 MAC→tx_buf→mavlink_frame）；**mavlink_frame 侧同步：查表 +0x0096/0x61 + id_legal 加 ID_ALARM（TX 侧 id_legal 漏扩则 ALARM 帧构造被拒，N11 功能性断裂）**；站端验 MAC 后 publish `alarm.authenticated`。答辩口径优先，工程仅在 11-18 缓冲日富余时做。若做：tb_terminal_fsm 增 ALARM 用例 + 变异（pre-fix 不发 ALARM 帧）。

---

## 3. 批次R 执行序列（RTL 单轮重建，11-14）

**文件改动矩阵**：

| 文件 | 改动 | 功能 |
|---|---|---|
| src/rtl/w3_protocol/demo_led.v | 新增 | N1/N7 |
| src/rtl/w3_protocol/terminal_fsm.v | L648-651 改写 + L424 分流 + ID_POLL/OR 两处 | N3/N4 |
| src/rtl/common/mavlink_frame.v | 查表 +ID_POLL/0x60 + **id_legal(L105-107) 扩展**（N11 再+0x0096/0x61 与 id_legal 加 ID_ALARM） | N4/N11 |
| src/rtl/w3_protocol/w3_top_zc706.v | demo_led 例化 + ext_led/ext_buzzer 端口 | N1/N7 |
| src/rtl/w3_protocol/w3_top_zc706.xdc | 新引脚约束（执行时按 UG954 定） | N7 |
| build/tcl/build_w3_board{,_seed2}.tcl | add_files 各 +demo_led.v（filelist 锁） | N1 |
| sim/tb/tb_demo_led.v | 新增（四规约） | N1 |
| sim/tb/tb_terminal_fsm.v | +T-CF1/2、T-AP1..4 用例 | N3/N4 |
| sim/tb/tb_mavlink_frame.v | +0x0097 帧用例 | N4 |
| src/python/server/protocol.py | +MSG_AUTH_POLL/_CRC_EXTRA/载荷 | N4 |
| docs/protocol_contract.md | §3/§7 增补 + 黄金向量 | N4 |
| src/rtl/common/frame_parser.v | localparam + CRC_EXTRA 表(8'h60) + id_legal 扩展 | N4 |
| sim/tb/tb_frame_parser.v | +T-FP1（0x0097 接受，真解析器） | N4 |
| sim/tb/tb_level3_protocol.v | +T-L31（poll 端到端） | N4 |
| tools/check_contract_sync.py | build_frames() +POLL 生成器（否则反向 ORPHAN 检查 @L171-173 响亮失败——失败即停门禁，无静默漂移路径） | N4 |
| scripts/ci_regression.ps1 | $tbs +tb_demo_led.v、$tbNames +tb_demo_led、**$rtl +src\rtl\w3_protocol\demo_led.v**（编译清单=$rtl+$tbs @L235，漏加则 TB 不可编译；或参照 ro_array_sim.v 挂 $tbs 的辅件惯用法）；tb_frame_parser/tb_level3 新用例随各自 TB 文件自动入册 | N1/N4 |

**执行序列**（每步有门禁，失败即停）：
```
0.  （11-13 Day1 已先行）用现有 bit 走通 QSPI 固化全流程练手——批次R 第 13 步二次固化沿用同一流程
1.  git checkout -b finals-demo
2.  RTL/TB/protocol.py/契约 全部改动落盘
3.  tools/check_contract_sync.py → 全绿（黄金向量双侧一致）
4.  单 TB 快跑: tb_terminal_fsm(含新用例) / tb_mavlink_frame(0x0097 构帧) / tb_frame_parser(T-FP1) / tb_level3_protocol(T-L31) / tb_demo_led → TB_*_PASS
5.  变异验证: pre-fix terminal_fsm 喂 T-CF1/T-AP1 → 必须 FAIL（证据落盘 data/d1_evidence/finals_demo/mutation/）
6.  scripts/ci_regression.ps1 → 19/19 PASS（18+tb_demo_led）+ ENROLL_NEG + python 全套
7.  vivado build_w3_board.tcl       → BITSTREAM_SUCCESS WNS≥0（板A）
8.  vivado build_w3_board_seed2.tcl → BITSTREAM_SUCCESS WNS/WHS≥0 + SEED2 tally（板B）
9.  sha256 更新: build/board_zc706_seed2/MANIFEST.txt + prereg 文件（CI BOARD_LOCK 钉死项）
10. 重跑 ci_regression.ps1（确认 SHA 锁过）→ 19/19
11. program_zc706.tcl JTAG 烧板A → 灯语验证（PASS闪3常亮/REJECT亮灭闪/BLOCKED双亮 + AUTH_POLL 实测 + 伪 RESULT 实测 CONFIRM_FAIL + **决策点#2 定案实验：REJECT 后不按 SW13 直接巡检/SW7，验证 L906-908 一拍自清**）
12. 同板B（SN 210251A04F2C）→ 同验收单
13. write_cfgmem ×2 → 烧 QSPI ×2 → SW11=00110 → 断电重启全流程复验
14. 证据归档 data/d1_evidence/finals_demo/（日志/照片/视频 + 正向哨兵行）
15. git commit + push（决赛专用分支，master 不动）
```

**回退方案**：任何一步失败 → JTAG + 旧 bit（两板原 bit 均保留未删）即时恢复演示能力；QSPI 烧坏场景 → SW11 拨回 00000 回 JTAG 模式。

## 4. 站端批执行序列（11-15）

N2(_loop 分支+横幅) → N5(串口注册 runner+wizard) → N6(frame-decode+飞行动画) → N9(demo_start.ps1)。每项：--data-dir 沙箱跑 → 注入测试 → `npm run build` → console 截图（idle/S1/intrusion/enroll-wizard/poll 五景）→ 落盘。

## 5. 验证矩阵（摘要）

| 功能 | 虚拟验证 | 板上验收 | 证据 |
|---|---|---|---|
| N1 | tb_demo_led 四态时序哨兵 | 灯语录像 | d1_evidence/finals_demo/led/ |
| N3 | T-CF1/2+变异 | 伪 RESULT 注入→CONFIRM_FAIL→双亮 | .../confirm_fail/ |
| N4 | T-AP1..4 + T-FP1 + T-L31 + 变异 | web巡检钮→完整五帧→PASS；SESSION态唤醒 | .../auth_poll/ |
| N2/N5/N6/N9 | 沙箱+截图 | 真板录入→巡检一条龙 | .../webui/ |
| N7 | 由 tb_demo_led 覆盖（ext_led/ext_buzzer 为 demo_led 输出端口） | 断电接线→JTAG 灯语→QSPI | .../led/ |
| N8 | — | 攻击剧本全链（三重证据同屏） | .../attack/ |
| N10 | —（文档交付物） | 内容评审对照 spec 大纲 | docs/ |
| N11 | tb_terminal_fsm ALARM 用例+变异（L260，仅缓冲日） | 仅缓冲日，验 MAC 告警 | .../alarm/ |

## 6. 风险与对策

| 风险 | 对策 |
|---|---|
| CI SHA 锁/MANIFEST 漏更 | 序列第 9-10 步强制重跑 CI；建议脚本化 rebuild_and_pin.ps1 |
| 契约六处同步漏一处（protocol.py / mavlink_frame(TX 查表+id_legal) / frame_parser(RX 查表+id_legal) / 契约文档 / 黄金向量+TB / CI 清单） | check_contract_sync 只覆盖 protocol.py↔契约文档（黄金向量再生），**RTL 两侧查表与 CI 清单不在其射程**；缺口由 T-FP1/T-L31 + tb_mavlink_frame 0x0097 用例门禁兜住（均在序列第 4 步先行执行） |
| rx_ok_latch 1拍窗口在 S_SESSION 的采样差异 | T-AP2 专测；若仿真现差异，把 S_SESSION 加入锁存保持列表（一行）并回归全 TB |
| 半双工碰撞毁告警帧 | N8 剧本含重试；答辩口径主动讲 |
| N7 带电插拔 | 铁律3：全程断电操作，双人复核 |
| 排期挤压 | 降级序：N11 → N6 飞行动画（保留字段解码）→ N10 |
```
（完）
