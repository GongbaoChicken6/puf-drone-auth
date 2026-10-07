# A1 阶段 5 上下文（审查对象）

## 增量（相对提交 5f0642a，工作区未提交）
| 文件 | 变更 |
|---|---|
| scripts/test_r2_nonlinearity.py | 新建：线性金丝雀。C0 负对照（仿射 ~C2 必须 |corr|~1 被抓）+ C1 位平衡（4σ）+ C2 一阶相关（5σ, 4096 次）+ C3 二阶奇偶（6σ, ~129k 次），Bonferroni 校正；N=256/密钥，固定种子，双密钥（W3 公开向量 + 固定随机） |
| scripts/ci_regression.ps1 | Python 段接线金丝雀 + gen_speck_vectors --check 向量新鲜度；删除两处 \$LASTEXITCODE = 1 预置（作用域阴影 bug，见下） |
| sim/tb/tb_challenge_decode.v | 终止标记 TB_PASS→TB_CHALLENGE_DECODE_PASS（TB_FAIL→..._FAIL），注释说明 CI 约定 |

## 阶段 5 期间发现并修复的两个预先存在缺陷（重要背景）
1. **tb_challenge_decode 标记不合规**：其他 10 个 TB 均打印 TB_<模块名>_PASS，唯它打印 TB_PASS:，永不匹配 CI 正则 TB_.*_PASS → CI 脚本从未可能 11/11；HANDOFF 阶段 3 的"11/11 TB 全 PASS"声明实际来自单独跑 TB（w3-complete 时代 ci_regression.ps1 尚不存在，git 考古确认）。功能本身一直正常（独立重跑通过）。
2. **CI Python 段预置 $LASTEXITCODE 导致假失败**（第二轮全量运行实测：11/11 TB 后 speck 自测门禁打印 FAILED，证据 build/reviews/a1p5/ci_second_run_python_gate_fail.log；删除两处预置后同一调用方式全绿，证据 ci_final_run.log——脚本级 A/B 成立）。机制声明修正（p5_spec 审查证伪了最初叙述）：裸 powershell -File 复刻加回预置不复现失败，"脚本作用域阴影"在无管道上下文不成立；失败仅在预置 × 本项目 CI 的实际调用上下文（外层管道捕获）组合下出现，精确机制未定。处置结论与环境无关地成立：预置零防御价值（Get-Command 守卫覆盖命令缺失，WindowsApps stub 9009 是新鲜退出码），删除后三通道 fail-closed 经独立实验复验。

## 全量回归证据（build/reviews/a1p5/ci_full_run.log）
- 11/11 TB PASS（含 gap_regression 6 安全测试与 level3 黄金帧链）
- Python 段：speck 自测 + 44/44 单测 + 金丝雀 PASS（实测 order1 max 0.2344 < 0.3125，order2 max 0.3125 < 0.3750，负对照 1.0）+ 向量 --check 新鲜度 1175 组 up-to-date
- CI-EXIT=0
- 首轮失败日志：ci_first_run_10of11.log（修复前，供审查员复现对照）

## 规格（阶段 5 范围）
- docs/HANDOFF_SUMMARY.md §二 阶段 5（全量 11 TB 回归 / Python 单测 speck.py+hsm.py 新路径 / 线性金丝雀 scripts/test_r2_nonlinearity.py——验证 R2 不可被线性拟合）
- docs/plans/A1_speck_plan_v3_final.md L44（CI 加：tb_speck + speck64_96.v + Python 测试段 + --check 新鲜度 + 线性金丝雀）
- 真相源：src/python/common/speck.py、scripts/gen_speck_vectors.py
