# A1 阶段 5 审查证据与日志谱系

| 文件 | 生成时机 | 对应工件状态 | 说明 |
|---|---|---|---|
| ci_12tb_final_run.log | **定稿运行（权威证据）** | 最终版金丝雀（C0 三重负对照+C4 精确线性）+ 最终版 CI 脚本（12 TB + 哨兵守卫 + Vivado 检查 + --check 可审计）+ 修复后的 gen_speck_vectors --check（纯计算比对） | 12/12 TB + Python 五件套全绿，CI-EXIT=0 |
| ci_final_run.log / ci_full_run.log | 中间状态 | 旧版金丝雀（无 C4）/ 11 TB | 历史调试过程，非最终证据（ci_gate P2 指出的漂移源，保留仅为谱系完整） |
| ci_first_run_10of11.log | 首轮 | tb_challenge_decode 标记修复前 | 10/11，TB 门禁正则不匹配的实证 |
| ci_second_run_python_gate_fail.log | 第二轮 | TB 修复后、预置删除前 | 11/11 后 "PYTHON SPECK SELF-TEST FAILED"——预置 × 调用上下文假失败的 A/B 证据（机制未定，见 P5_CONTEXT 修正） |

审查发现：canary_stats.json / p5_spec.json / ci_gate.json；上下文：P5_CONTEXT.md（机制叙述已经 p5_spec 证伪后修正）。
