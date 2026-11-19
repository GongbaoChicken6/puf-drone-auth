# 单 HC-12 共享信道 + 帧级区分双板 —— 背景调查与方案设计

> 日期：2026-11-19 · 状态：**设计稿（未实施）** · 需求方：老师
> 一句话：物理层把三只 HC-12 统一到同一信道/波特率、PC 只留一只；逻辑层靠 **tid 字段** 区分 A/B。
> 背景调查结论：**上行天然可分（0x0090/0x0094 带 tid），下行不可分（0x0091/0x0093 不带 tid）→ 必须改协议/固件，否则共享信道会串扰。**

---

## 1. 现状与目标

| 项 | 现状 | 目标 |
|---|---|---|
| HC-12 数量 | 3 只（PC 1 + 板A 1 + 板B 1） | 3 只（PC 1 + 板A 1 + 板B 1），物理不变 |
| 信道 | 板A=C001，板B=C006，PC 侧随板 | **统一 C001**（或任选一致值） |
| 波特率 | 115200 | **统一 115200** |
| FU 档位 | FU3 | **统一 FU3**（档位含义/空速以 HC-12 手册为准，三只读回必须一致） |
| PC 串口 | COM6(板A) + COM11(板B) 双口 | **单口**（一只 HC-12 收全部帧） |
| 桥启动 | `--serial-multi COM6,COM11 --tid-port 1=COM6,2=COM11` | `--serial-port COMx --access-gate` |
| A/B 区分 | 端口归属（物理隔离） | **帧内 tid**（ACCESS_REQUEST 的 terminal_id 字段） |
| 前端 | 两个终端各一套动画 | 不变（事件仍按 tid 分发，前端零改动） |

## 2. 背景调查：帧级事实（代码实测）

`src/python/server/protocol.py` 的 payload 定义：

| 帧 | ID | payload 布局 | **带 tid?** |
|---|---|---|---|
| ACCESS_REQUEST | 0x0090 | `<II8s` = terminal_id(4B) + nonce(4B) + C2(8B)，16B | **✅ 带** |
| CHALLENGE | 0x0091 | 4×8B seeds，32B | **❌ 不带** |
| RESPONSE_R1 | 0x0092 | 3~4×8B，24/32B | ❌ 不带 |
| RESULT | 0x0093 | `<BB8s` = result(1B) + hd(1B) + r2(8B)，10B | **❌ 不带** |
| CONFIRM | 0x0094 | `<IB` = status(4B) + terminal_id(1B)，5B | **✅ 带** |
| EXTRA_CHALLENGE | 0x0095 | 3×8B，24B | **❌ 不带** |
| AUTH_POLL | 0x0097 | `<II` = terminal_id(4B) + nonce(4B)，8B | **✅ 带** |

板端（RTL）实测：

- `terminal_fsm.v:122` `wire poll_start = rx_ok_latch && (fp_msg_id == ID_POLL);` —— **只看帧类型，不比对 tid**
- `terminal_fsm.v:392/698` `if (auth_start || poll_start)` → **任何 AUTH_POLL 都会唤醒任何一块板**
- `w3_top.v:206` `.ENROLL_IDLE_ACCEPT(ENROLL_EN)`，`w3_top_zc706.v:89` `.ENROLL_EN(1)` → **IDLE 态恒可接受 0x0091 进入注册**（`S_IDLE` 分支 403 行）
- `S_WAIT_CHALL`(479 行) 接受 0x0091 时同样**不比对 tid**

站端（Python）实测：

- `web_bridge.py:1263 resolve_listener()`：单监听器时**直接直通** → 单口 + 多 tid **无需改路由** ✅
- 闸门 `access_gate` 已按 tid 排队/选中/唤醒，`_poll_wake_once` 的应答判据是 **per-tid** ✅
- `c2_history(tid)` 按终端隔离，共享信道不会串 C2 重放窗 ✅
- 信道 IDS（伪基站检测）在单口下照常工作，且**两板都能听到攻击帧**（演示更真实）✅

## 3. 冲突分析（共享信道后会出现什么）

| 编号 | 冲突 | 触发场景 | 级别 | 说明 |
|---|---|---|---|---|
| **C1** | AUTH_POLL 广播唤醒 | 选中板B 验证时发 `AUTH_POLL(tid=2)` → **板A 也被唤醒** → 两台同时发 0x0090 → 空口碰撞 | **P1** | 每次“选中验证”都会发生，高频 |
| **C2** | CHALLENGE/EXTRA 无 tid，且 IDLE 板恒可接受注册挑战 | 站端给板A 发 0x0091 → **IDLE 的板B 也进注册**并回 R1 → 两条 R1 同时发射，桥收到乱帧/两组 R1 | **P0** | 阻断级：共享信道下认证无法稳定完成；enroll 同样污染 |
| **C3** | 两板同时按 SW8 | 两条 0x0090(28B) 同刻发射，HC-12 半双工必撞 | P2 | 概率性；闸门 park + 2s 超时回 IDLE 可重按恢复 |
| **C4** | RESULT 无 tid | 误收对方 RESULT：板A 在 S_WAIT_RESULT 期间听到发给板B 的 RESULT → 用错误 R2 判定 | P2 | 实际窗口窄（仅一板在 S_WAIT_RESULT），但配合 C1 放大 |
| **C5** | HC-12 参数不一致 | 空速/信道不同 → 完全收不到 | P0(配置层) | 一次配置、掉电保存，属实施项而非设计项 |

> **结论：C2 是 P0，纯操作手段（错峰按键、分时上电）无法根治 → 必须改协议/固件。**

## 4. 方案设计

### 4.1 物理层：三只模块统一参数（无代码风险）

1. 三只 HC-12（PC 侧、板A 侧、板B 侧）全部刷成：**`FU3` + `B115200` + `C001`**
2. 配置方式：沿用 `tools/hc12/hc12_config_c001.py`（SET 上电前接地 → 9600 进 AT → 写参 → 115200 复验 → `AT+RX` 读回断言）
3. 验收判据：每只模块 `AT+RX` 读回同时含 `OK+FU3`、`OK+B115200`、`OK+RC001`；三只逐一贴日志入证据
4. 注意：**写参数必须在原会话波特率回读**（历史坑：SET 接地期间写入的新波特率不生效）；改参数后断电重启才生效

### 4.2 协议层：给下行帧加 tid 定向（核心改动）

**原则：只在必须处加字段，能少改就少改。**

| 帧 | 改动 | payload | 理由 |
|---|---|---|---|
| CHALLENGE 0x0091 | **加 target_tid(4B) 置 payload 首部** | 32B → 36B（帧 44B → 48B） | 堵死 C2：板端先验 tid==本机，不等就直接丢弃；正常板才进注册/等挑战 |
| EXTRA_CHALLENGE 0x0095 | 同上 | 24B → 28B | 灰区二次挑战同一路径 |
| RESULT 0x0093 | **加 target_tid(4B)** | 10B → 14B | 堵死 C4，顺带为将来多板并行留余量 |
| ACCESS_REQUEST / CONFIRM / AUTH_POLL | **不变** | — | 已带 tid |

板端落地（`terminal_fsm.v`，3 处小改）：

1. `poll_start = rx_ok_latch && (fp_msg_id == ID_POLL) && (rp_payload_u32 == terminal_id)` —— 逐字节读 payload 前 4B 比较（既有 `fp_rd_addr` 读机制已可复用）
2. `S_IDLE` 的 ENROLL 接受条件（403 行）追加 `&& (payload[0..3]==terminal_id)`
3. `S_WAIT_CHALL` 接受 0x0091（479 行）同样追加 tid 校验；`S_WAIT_RESULT` 接受 0x0093/0x0095 追加 tid 校验

站端落地（`protocol.py` + 调用点）：

1. `_build_payload`：CHALLENGE/EXTRA 前置 `struct.pack('<I', tid)`；RESULT 前置 tid
2. `_parse`/`unpack`：解析出 `target_tid` 并作为 `fields['terminal_id']` 返回；`on_access_request`/`on_response` 路径对不上直接忽略（防御性）
3. 调用点补 tid 实参（`sessions`/`enroll`/`_auth_round`）
4. **黄金帧/回归**：golden 帧常量、`tests/` 期望字节、仿真 TB 同步更新（一次性同步改，避免半套）

兼容性口径：**帧格式 v2**，与 v1 不互通 → 双板 bit 与站端必须同批更新；`docs/` 记录版本号，答辩稿写“协议 v2：下行帧携带目标终端号”。

### 4.3 站端仲裁：闸门保持串行（不改逻辑，只改启动参数）

- 桥启动：`python -u web/bridge/web_bridge.py --repo-root . --data-dir .demo_state --port 8642 --serial-port COMx --access-gate --access-label "1=板A,2=板B"`
- 选中验证时的唤醒：`AUTH_POLL(tid=选中tid)` → 加 tid 过滤后**只醒目标板**（C1 解除）
- 前端：`access.requested`/`access.selected` 事件照旧按 tid 分发 → **两个弹窗/两套动画零改动**
- 一键脚本 v3.1：检测到“单候选串口”时自动走单口分支（去掉 `--serial-multi/--tid-port`）

### 4.4 碰撞缓解（C3，可选增强）

- 操作层：演示话术固定为“先按板A，等 1 秒再按板B”，闸门天然串行
- 固件层（可选）：`S_TX_ACCESS` 前插 **0~30ms 伪随机退避**（用现有 PUF 噪声或 LFSR），两板同刻按键时有 ~60% 概率错开；代价是单板响应慢 30ms（无感）
- **不建议**做 CSMA/CD：HC-12 无载波检测引脚，实现成本高于收益

## 5. 改动清单（按文件）

| 文件 | 改动 | 风险 |
|---|---|---|
| `src/python/server/protocol.py` | CHALLENGE/EXTRA/RESULT 加 tid；解析字段 | 中（黄金帧全改） |
| `src/rtl/w3_protocol/terminal_fsm.v` | poll/CHALLENGE/RESULT tid 校验（3 处） | 中（需仿真+上板） |
| `tests/test_protocol*.py` + golden 帧 | 期望值更新 | 低（机械） |
| `web/bridge/web_bridge.py` | 无功能改动（可选：单口启动自检日志） | 低 |
| `scripts/demo_one_click.ps1` | 单口分支 + banner 口径 | 低 |
| `tools/hc12/hc12_config_unified.py`（新增） | 三只模块统一配置 + 读回断言 | 低 |
| `docs/` | 协议 v2 说明 + 本方案 | — |

## 6. 分阶段实施与验收

| 阶段 | 内容 | 验收判据 | 预计 |
|---|---|---|---|
| P0 | 三只 HC-12 统一 C001/115200/FU3 | 三份 `AT+RX` 读回断言全 PASS | 15 min |
| P1 | 协议 v2（下行加 tid）+ golden 帧全量更新 | `pytest` 全绿（220+ 用例） | 2~3 h |
| P2 | 板端 tid 过滤 + 重建 v4c/seed2c bit | `verify_wrapper` PASS + 仿真 TB PASS + 上板五帧 PASS | 2 h + 建流 15 min |
| P3 | 单口桥 + 前端双动画联调 | 两板各按 SW8 → 两条待接入 → 分别选中验证 → 各自 PASS；无串扰日志 | 1 h |
| P4 | 登记证据（日志/截图/录屏） + 论文口径更新 | 证据入 `data/d1_evidence/finals_demo/` | 30 min |

**回退预案**：新 bit 与旧协议不互通 → 保留现双口配置（C001+C006 两只 PC 模块）随时可切回；两套 bit 同时留档（v4b/seed2b = 双口版；v4c/seed2c = 单口版）。

## 7. 风险登记

| # | 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|---|
| R1 | 协议改动引入回归（黄金帧/仿真/测试） | 中 | 高 | 一次性同步改 + 全量 pytest + 仿真 TB；不在演示当天动 |
| R2 | 板端 tid 比较实现错误（payload 读取时序） | 中 | 高 | 复用既有 `fp_rd_addr` 读机制；先仿真后上板 |
| R3 | 两板同按碰撞导致弹窗只出其一 | 低 | 中 | 闸门 + 2s 超时重按；答辩话术“先A后B” |
| R4 | HC-12 空速档位与手册不一致（批次差异） | 低 | 高 | 三只全部 `AT+RX` 读回比对，不一致先统一 |
| R5 | 单口下 enroll 阶段（改动前）互相污染 | 高 | 高 | **P2 完成前不要做单口 enroll**；先做 P1+P2 再统一切单口 |

## 8. 需要拍板的问题

1. **信道取值**：统一 C001（沿用板A 现值）还是另选（如 C021 避开教室干扰）？
2. **协议 v2 是否可接受**（下行帧 +4B）：若不可，替代方案是“注册模式改为站端 AUTH_POLL 后限时开启”的 RTL 方案，改动更小但语义更绕
3. 是否保留**双口模式**作为备份（建议保留，切换只需换 bit + 改启动参数）
4. 演示流程是否需要“两板同时按”的镜头（若有，需把 4.4 的退避做进 P2）

---

### 附：关键代码位置（供实施时定位）

- `src/rtl/w3_protocol/terminal_fsm.v:122` poll_start 定义
- `terminal_fsm.v:403` S_IDLE 注册接受 · `:479` S_WAIT_CHALL · `:603` S_WAIT_RESULT
- `w3_top.v:206` ENROLL_EN→ENROLL_IDLE_ACCEPT 映射 · `w3_top_zc706.v:89` 板级 ENROLL_EN=1
- `src/python/server/protocol.py:242` pack · `:307` _build_payload（改这里）
- `web/bridge/web_bridge.py:1263` resolve_listener（单口直通）· `:2059` --serial-multi 参数
- `tools/hc12/hc12_config_c001.py` 统一配置基线（改信道号即可复用）

---

## 9. 方案修订（2026-11-19 18:30）：改为【点名窗口 B′】——**取代 §4.2 的协议 v2**

### 9.1 推翻原方案的原因（硬约束）

`src/rtl/common/frame_parser.v` 实测：`MAX_PAYLOAD = 32`、`payload_rd_addr [4:0]`（0~31 字节）。
CHALLENGE 载荷**已经占满 32B**（4×8B seeds）→ 原方案的"CHALLENGE + 4B tid"**物理上装不下**，
除非同时把帧解析缓冲加宽到 36B+（连带 `fp_rd_addr` 位宽、全部地址比较、黄金帧、仿真），
改动面与回归风险都远超收益。**故改用不加字段的点名窗口方案。**

### 9.2 方案 B′ 原理

```
站端                     共享信道(C001)                板A(tid=1)        板B(tid=2)
  │  AUTH_POLL(tid=1, nonce≠0) ──▶ 广播 ──▶  校验tid=1命中 → 唤醒+开窗3s
  │                                    └─▶  校验tid=2≠本机 → 无视(不醒/不开窗)
  │  ◀──────────────── ACCESS_REQUEST(tid=1) ←── 板A 发 0x0090（帧内自带 tid）
  │  CHALLENGE(无tid) ────────────▶ 广播 ──▶  板A在等挑战 → 接受
  │                                    └─▶  板B无窗口 → 丢弃 ✔
  │  ◀──────────────── RESPONSE_R1(无tid) ←── 板A 回 R1
  │  RESULT(无tid) ───────────────▶ 广播 ──▶  板A在等RESULT → 处理
  │                                    └─▶  板B IDLE 不解析 0x0093 ✔
```

- **A/B 区分靠上行帧**：`ACCESS_REQUEST(0x0090)` 载荷含 `terminal_id(4B)`、`CONFIRM(0x0094)` 也含——
  正是老师说的"用认证帧的组成不同来区分"，**协议零改动**。
- **下行定向靠点名**：板端只有**被点名**（tid 匹配）才开 3s 授权窗口，窗口内才接受 CHALLENGE / 注册挑战；
  没被点名的板自动丢弃 → 彻底解决 §3 的 C1/C2/C4。
- **nonce 载荷复用**：`nonce==0` = 只开窗、不起认证（enroll 用）；`nonce≠0` = 点名即唤醒（等效按 SW8）。

### 9.3 实际改动（已完成，2026-11-19 18:3x）

| 文件 | 改动 | 状态 |
|---|---|---|
| `src/rtl/w3_protocol/terminal_fsm.v` | 状态位宽 4→5 + 新增 `S_POLL_CHK` 微状态（顺序读 8B 载荷校验 tid/nonce）；`S_IDLE` 注册接受加 `poll_win` 门控；`S_WAIT_RESULT` 背靠背注册轮同样门控；`S_SESSION` 去掉 poll 打断；3s 窗口倒计时 | ✅ `VERIFY_WRAPPER_PASS` |
| `web/bridge/enroll_real.py` | 每轮 CHALLENGE 前发 `AUTH_POLL(tid, nonce=0)` 刷新授权窗口 | ✅ |
| `web/bridge/web_bridge.py` | 两处 AUTH_POLL 的 nonce 加 `or 1`（防止 time_ns 恰为 0 被当成"仅开窗"） | ✅ |
| 协议/黄金帧 | **零改动**（本方案不加任何帧字段） | ✅ `pytest 220 passed` |
| `sim/tb/tb_poll_gate.v`（新增） | 门控专项 TB：点名他机不醒 / 点名本机唤醒 / nonce=0 仅开窗 / 窗口过期拒绝 | ✅ TB_POLL_GATE_PASS |
| `sim/tb/*`（4 个老 TB） | 加 POLL_GATE_EN(0) 保持历史语义（门控由新 TB 覆盖） | ✅ 全 PASS |
| `build/ps1/run_xsim_w3.ps1` | 补 ro_array_sim/speck64_96/challenge_decode（此前漏编，tb_terminal_fsm 从未真跑） | ✅ 7 套全 PASS |
| 新 bit | build/board_zc706_arm_v4c（板A）、build/board_zc706_seed2c（板B） | 🔄 最终 RTL 构建中 |

### 9.4 连带影响（重要）

1. **RTL 变了 → 环振物理布局可能再变 → 两板模板必须重录**（铁律：换 bit 必重录）。
2. SD 自举镜像需重新打包（`BOOT_SD_FINAL_V4C_FC.bin` / `BOOT_SD_BOARDB_SEED2C.bin`）。
3. 一键脚本 v3 需加"单口分支"（`--serial-port`）与"C001 统一"自检。
4. 双口版 bit（v4b/seed2b）保留作回退。

### 9.5 上板步骤（需人工）

1. **三只 HC-12 统一 C001/115200/FU3**：SET 脚上电前接地 → 9600 进 AT → `AT+FU3`/`AT+B115200`/`AT+C001` → 115200 复验 → `AT+RX` 读回断言（沿用 `tools/hc12/hc12_config_c001.py`，三只都跑一遍）
2. 烧 v4c → 板A、seed2c → 板B（JTAG 8 秒）
3. 单口桥：`--serial-port COMx --access-gate`
4. 重录 tid1(100对) / tid2(30对)
5. 验收：板A 按 SW8 → 前端**只出板A 一条**待接入；板B 全程无反应（反之亦然）→ 选板A 验证 PASS
6. 复验：拔掉板A 电源，板B 按 SW8 → 只出板B 一条 → PASS

