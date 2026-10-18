# Security 指标

| 指标 | 值 | 分级 | 来源 |
|---|---|---|---|
| 有效熵 | ~44 bit | **STATIC** | docs/project_design.md(16 环信息论上限) |
| LR 建模攻击上限(α=0.30) | 91.27%(贴 Bayes 90.72%) | **STATIC** | data/ml_attack/exp_a_results.json(seed=42) |
| 排序重构(flip=0.02@120CRP) | 精确率 100% → CRP 轮换阈 ≥120 | **STATIC** | data/ml_attack/exp_b_results.json |
| C2 重放拒止 | 服务器窗 + 终端侧双路 | **LIVE** | S3=REPLAY 门禁(PhaseA记录)+ tb GK 换电重放拒止 |
