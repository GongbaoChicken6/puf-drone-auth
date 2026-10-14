# W4 实验周 · 计划书 v2.0

> 状态：**执行中**（P0-P3 完成 + P4 部分完成，M1 达成）｜更新 2026-10-13 晚
> 编制 v1.0 2026-10-13 → v1.1 同日 3 代理计划审查闭环 → v2.0 执行中进度更新
> 代码基线：HEAD be67b24（88 commits / 183 files，CI 13 TB + 83 单测 + threat_poc 全绿）
> 时间窗：10-13 → 10-24（W5 冻结 10-25 起；11-03 晚提交；11-04 18:00 硬死线）
> v2.0 更新：P0-P3 全✅ + P4 T3/T4/T6✅；M1 提前 4 天达成；审查发现 11 项 P0/P1 全闭环；剩余 P4 子项 + P5-P7 排期压缩

---

## 0. 输入快照与兼容基线（v2.0 更新）

| 项 | 现状（10-13 晚） | 变化 vs v1.1 |
|---|---|---|
| CI | **13 TB** + speck 自测 + **83 单测**(44+19+14+6) + 金丝雀 + 1175 向量 + 契约同步(S4+S8) + PUF fixture --check + **threat_poc**(3 用例) | +1 TB(tb_puf_path) +20 单测 +2 门禁 |
| RTL | **B5a PUF 真实管线已上线**：S_PUF_DECODE→S_PUF_MEASURE(热稳定 7 窗)→S_PUF_PACK；种子直通桩退役 | 从"W3 桩"到"真实测量" |
| PC 侧 | SimulatedTerminal→ROPairingPUF + serial_server(serve 命令) + interop harness | loopback 走真实 RO 语义 |
| 安全 | P2-1 calc_done_flag + DoS 令牌桶 + threat_poc(replay/brute/inject) | M2 核心已达成 |
| 板卡 | DS13 电源故障排查中（另一会话） | 不变 |
| 并行会话 | 板卡 + 前端共用仓库 | R5 协议执行中 |

## 1. 已完成阶段（勿重做）

| 阶段 | 提交 | 审查 | 交付 |
|---|---|---|---|
| **W4-P0** CI 健康化 | 32030e5 | 1 缺陷代理→1P1+2P2+3P3→全修 | 超时作业化 + RemoteException=0 |
| **W4-P1** PUF 黄金模型 | 7cf52ce | （并入 P2 综合审查） | puf_model + 契约 S8 + 三方对拍 |
| **W4-P2** RTL B5a | 23ed28a→baa9a00→6644196 | **4 代理(A/B/C/D)**→1P0+2P1→全修(130c9ec/ae58d8a) | S_PUF 三态 + tb_puf_path 字节锁 + CI 12→13 |
| **W4-P3** PC 全链 | 7837317 | **3 代理(A/B/C)**→0P0/P1/P2→3P2→全修(ed07c45) | ROPairingPUF 薄壳 + interop 6 用例 |
| **W4-P4 部分** | be67b24 + 审查修复 | **2 代理(A/B)**→1P1+4P2→全修 | threat_poc(3 用例绿) + DoS 限速(死锁已修) + P2-1(每会话重置) |

### 审查发现闭环统计（全部阶段）

| 阶段 | 代理数 | P0 | P1 | P2 | 已修 | 延后 |
|---|---|---|---|---|---|---|
| P0 | 1 | 0 | 1 | 2 | 全修 | — |
| P1+P2 | 4 | 1(clk) | 2(watchdog+false-coverage) | 6 | 全修 | wire_helpers 重构 |
| P3 | 3 | 0 | 0 | 3 | 全修 | — |
| P4 | 2(进行中) | — | — | — | — | — |

## 2. 剩余阶段

### W4-P4 安全包·剩余子项（预估 1 天 + 0.5 审查）
| 任务 | 状态 | 说明 |
|---|---|---|
| **T1 P1-1 真密钥派生** | 🔶 **部分** | **RTL 已实现并仿真验证**（S1-S4: derive_device_key + S_KEY_MEASURE/S_KEY_DERIVE + w3_top 回环 + tb_key_derive/tb_w3top_keyloop）；**板上未可用**——站端缺 K 下发通道（0x0096 KEY_SEED 未做）+ K_boot 单次测量噪声可靠性未解 → `w3_top.ENABLE_KEY_DERIVE` **默认 0（fail-safe）**。**不得声明板上 P1-1 达成** |
| T2 P1-5 C2 随机化 | 🔶 **RTL 已实现（仿真验证）** | `ro_entropy.v`（105 行）+ w3_top 第二 ro_array 例化 + seed_load 脉冲链路；tb_ro_entropy(T10/T11/T12) + tb_w3top_keyloop T13 顶层集成断言。**诚实边界**：仿真下 fixture 确定性 → 确定性 boot_seed（黄金 0x34F1996F07D25792）；**真实熵只在板上成立**（有效熵 ~16-32bit/次上电 + 服务端 128 窗兜底）。终端侧 S_VERIFY_R2 拒止的**换电重启 PoC 证据待 GK 用例** |
| T3 P2-1 TB 用例 | ✅ | tb_gap GI 用例（force calc_done_flag=0 → BLOCKED） |
| T4 DoS 洪泛测试+文档 | 🔶 部分 | 令牌桶死锁已修 + test_dos_flood.py 入 CI；**暂存-释放语义 + 池补充 SOP 文档仍缺**（限速只削峰不防池耗尽） |
| T5 运维加固 | 🔶 部分 | setkey 环境变量导入 + 审计日志已做；**DeviceKeyStore mtime 检测 + SimulatedHSM 决策未做** |
| T6 威胁 PoC | ✅ | threat_poc.py 3/3 入 CI |

### W4-P4 T1/S3-S4 审查闭环（2026-10-14，3 代理 A/B/C）
| 代理 | P0 | P1 | P2 | 处置 |
|---|---|---|---|---|
| A 缺陷 | 1（w3_top 回环断线） | 0 | 4 | P0 已修（311fec4）+ 新增 tb_w3top_keyloop |
| B 安全/合规 | 1（同上，独立复现） | 1（K 下发通道缺失） | 2 | P1 采纳 fail-safe 默认 0 + 文档诚实标注 |
| C 静默失败 | 0 | 1（TODO 步骤号 + T2 未闭环） | 6 | TODO 修正 + T1/T2 状态诚实化 |

**关键教训（W5 复用）**：声明"完成"前必须验证**顶层集成**（w3_top 级 TB），单元/子模块 TB 全绿不能替代——本次 P0 正是子模块 TB 自接回环掩盖的。

### W4-P5 ML 攻击实验（1.5 天，纯 PC）
实验 A 合成 arbiter+LR（sklearn 已装）／实验 B 排序重构（puf_model 数据）；产出 data/ml_attack/*.json + 图。

### W4-P6 板上实验（待板卡，口径冻结见设计书 §8）
上板五步 + 温度/唯一性/多终端/无线/AI。

### W4-P7 W5 前置（利用松弛穿插）
D13 报告骨架 + D14 Skill ≥2 脚本。

## 3. 里程碑更新

| 里程碑 | 原定 | 实际 | 状态 |
|---|---|---|---|
| M1 仿真级 PUF 全链 | 10-17 | **10-13** | ✅ **提前 4 天** |
| M2 安全包闭环 | 10-20 | ~10-15 | 🔶 threat_poc 已绿，T1/T2/T5 待做 |
| M3 ML 数据就绪 | 10-22 | ~10-17 | ⬜ |
| M4 板上+冻结 | 10-24 | ~10-20 | ⬜ |

G4 门禁更新：CI 全绿（**TB≥13 + 单测≥83** + threat_poc exit 0 + fixture --check）✅ 达标。

## 4. 风险与降级（v2.0 更新）

| # | 风险 | 概率 | 更新 |
|---|---|---|---|
| R1 | 板卡不复活 | 中 | 不变；板上项口径已冻结 |
| R2 | 真环不可仿真 | ~~确定~~ | ✅ 已解决（ro_array_sim stub） |
| R3 | 单路 97% 达不到 | 中 | ring_en 占空比差异已文档化（W2 常开 vs W4 认证期开振）→ P6 判据 |
| R4 | 时间溢出 | **低** | **进度提前 4 天**；P4 剩余可压缩 |
| R5 | 并行会话冲突 | 低 | 执行中无事件 |
| R6 | ro_entropy 熵不足 | 中 | T2 未实现；降级=simulation-only + 报告标注 |
| R7(新) | w3_top PUF 互连零 TB 覆盖 | 已知 | clk bug 借此存活（已修）；防回归=板上冒烟（P6 首步） |

## 5. 审查经验教训汇总（供后续阶段避坑）

| 教训 | 来源 | 影响 |
|---|---|---|
| Verilog 隐式 net（未声明标识符→恒 z） | P2 clk bug | 上板必败但 CI 全绿——w3_top 级 TB 缺口 |
| timeout_cnt 跨态连续计数 | P2 watchdog | WAIT 时间侵蚀 PUF 预算→分段清零 |
| tx_byte_count 跨轮泄漏 | P2 T3/T4 | 看门狗假覆盖→每轮 auth 前清零+状态断言 |
| PS 行续符=反引号非反斜杠 | P0 | 5 处修复 |
| Start-Job 丢失父作用域 | P0 | 显式传参 |
| -File 不拆逗号数组 | P0 | 纯字符串+split |
| ro_array_sim $readmemh cwd 依赖 | P2 相对路径 | CI 需 cwd=repo 根 |
| flip_prob 运行时改写绕过校验 | P3 | 已加范围检查 |