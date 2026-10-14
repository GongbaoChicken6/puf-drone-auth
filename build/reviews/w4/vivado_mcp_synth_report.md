# W4 Vivado MCP 综合实测报告（2026-10-14）

## 综合环境
- **工具**: Vivado 2026.1 (win64) via MCP (vivado-mcp-server 2026.9.1)
- **器件**: xc7z020clg484-1 (ZC702)
- **顶层**: w3_top（含 W4-P2 B5a PUF 管线 + W4-P4 S2 密钥派生状态）
- **耗时**: 综合 55.5s + read_verilog 9.2s

## 资源利用率（综合后）

| 资源 | 已用 | 可用 | 利用率 | 备注 |
|---|---|---|---|---|
| **Slice LUTs** | **4011** | 53200 | **7.54%** | 含 PUF 管线全量 |
| LUT as Logic | 3991 | 53200 | 7.50% | |
| LUT as Memory | 20 | 17400 | 0.11% | 分布式 RAM |
| **Slice Registers** | **5967** | 106400 | **5.61%** | |
| F7 Muxes | 730 | 26600 | 2.74% | |
| F8 Muxes | 264 | 13300 | 1.98% | |
| BRAM | 0 | 140 | 0% | 未使用 |
| DSP | 0 | 220 | 0% | 未使用 |
| Bonded IOB | 17 | 200 | 8.5% | |

## 时序检查

| 检查项 | 数量 | 说明 |
|---|---|---|
| no_clock 寄存器 | 5991 | **预期**（综合时无 XDC 约束，sys_clk 未约束） |
| unconstrained 内部端点 | 14503 | 同上 |
| **组合环** | **16** | **预期**（16 个 RO 环振，w2_waiver.xdc 豁免） |
| latch_loops | 0 | 无锁存器环 |

## 关键结论

1. **设计适配确认**: 4011 LUT / 5967 FF（<8%/<6%）——资源余量极大
2. **W4 B5a PUF 管线综合成功**: challenge_decode + ro_array + 64 对比较 + Speck×2 KDF 全部综合通过
3. **W4-P4 S2 新态综合通过**: S_KEY_MEASURE/S_KEY_DERIVE 无综合错误
4. **组合环 16 个 = 16 个 RO 环振**: 与 w2_waiver.xdc 豁免清单一致（上板需挂载）
5. **与旧估算对比**: W3-only 约 700 LUT → 含 PUF 管线实际 4011 LUT（5.7x，因 challenge_decode 512bit 配对表 + 64 对比较器 + ro_array 接口）

## 对 W4 计划的影响

- **资源余量**: 足够添加 ro_entropy (~50 LUT) 和第二 ro_array 实例 (~200 LUT)
- **无需 B5b XOR-4 降级**: 7.54% LUT → XOR-4 约 30% 仍在预算内
- **时序无红灯**: 综合级无 critical warning（需 XDC 约束后才能看 WNS）
- **上板信心**: 设计在 Artix-7 级别资源下轻松适配

## 证据文件
- timing.rpt: 时序检查报告（无约束状态）
- util.rpt: 资源利用率报告
