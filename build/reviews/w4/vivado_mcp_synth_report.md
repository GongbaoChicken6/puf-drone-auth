# W4 Vivado MCP 综合实测报告（HEAD 版，覆盖 W4-P4 S1-S4）

> 生成 2026-10-14 21:26（Vivado 2026.1 via MCP）｜**取代** vivado_mcp_synth_report.md 的 S2 快照内容
> 闭审查发现：A-P2-2 / B-P3-2 / C6（旧证据早于 S3/S4；且综合的 undriven-net 检查本可暴露 P0）

## 覆盖范围
| 项 | 值 |
|---|---|
| 提交 | **e3ea9c5**（含 S1-S4 + P0 修复 311fec4 + B/C 审查修复） |
| 顶层 | w3_top |
| 器件 | xc7z020clg484-1 (ZC702) |
| 综合耗时 | 56.9s，**error_count = 0** |

## 资源利用率（HEAD，综合后）

| 资源 | HEAD | S2 快照 | Δ | 可用 | 利用率 |
|---|---|---|---|---|---|
| **Slice LUTs** | **4190** | 4011 | +179 | 53200 | **7.88%** |
| LUT as Logic | 4170 | 3991 | +179 | 53200 | 7.84% |
| **Slice Registers** | **6133** | 5967 | +166 | 106400 | **5.76%** |
| F7 Muxes | 730 | 730 | 0 | 26600 | 2.74% |
| F8 Muxes | 264 | 264 | 0 | 13300 | 1.98% |
| Unique Control Sets | 256 | 253 | +3 | 13300 | 1.92% |
| BRAM / DSP | 0 / 0 | 0 / 0 | 0 | 140 / 220 | 0% |

**增量归因**：+179 LUT / +166 FF = W4-P4 T1 密钥派生逻辑（S_KEY_MEASURE 子态机 + S_KEY_DERIVE 双 Speck 时序 + kdf_key12 拼接 + key_valid 生命周期 + 密文 x 兜底）。资源余量充足（<8% LUT）。

## 关键验证：P0 修复的综合级证据

**未连接端口告警：key_valid / key_reg 零命中** ✅

修复前（审查代理 B 实测，HEAD=fc150a6）：

    WARNING: [VRFC 10-3645] port 'key_valid' remains unconnected for this instance [w3_top.v:158]

修复后（HEAD=e3ea9c5）：综合日志无该告警；xvlog 层 unconnected 计数 = 0。

> 这正是 B 代理指出的要点——综合的 undriven-net 检查本可暴露 P0，故本次重跑综合同时作为该缺陷的独立闭环证据。

## 其余综合告警（全部良性，既有项）

| 告警 | 位置 | 判定 |
|---|---|---|
| port 'busy' of module 'frame_parser' is unconnected | w3_top.v:336 | 良性：frame_parser.busy 未使用 |
| Port ra_busy in module terminal_fsm is either unconnected or has no load | terminal_fsm | 良性：FSM 以 ra_done 为完成信号 |
| Port fp_frame_err in module terminal_fsm is ... no load | terminal_fsm | 良性：帧错误由 fp_frame_ok 路径覆盖 |
| Found unconnected internal register 'puf_seed_asym_reg' trimmed 64->56 bits | terminal_fsm.v:487 | **良性**：左移装配仅低 56bit 参与读取；逐字节追踪确认 8 字节装配 = 大端序 b0..b7，与 R1 黄金值一致 |

## 证据文件
- build/vivado_mcp/util_head.rpt（HEAD 资源，Date 2026-10-14 21:26:30）
- build/vivado_mcp/timing_head.rpt（HEAD 时序检查）
- build/vivado_mcp/.vivado-ai/vivado_81067483_517a2ddc.log（综合全日志）

## 待办（W4-P6 上板前）
- 带 XDC 约束的综合（当前无约束 → timing 报告无 WNS 意义）
- report_drc 完整检查（本次仅确认 TOP_PORTS=17）