# W4-P5 ML 攻击实验 · 执行方案 v2（三代理审查闭环后）

> 编制 2026-10-15 v1 → 同日 v2 修订（TECH 3xP1 + 5xP2 + SPEC 2xP2 + 7xP3 全部纳入）
> 依据：project_design.md L379-410（冻结文案）+ W4_design.md §7 + HANDOFF B6（20 分）
> 工具链：sklearn 1.8.0 / matplotlib 3.11.1 / numpy 2.2.6 / scipy 1.16.3（版本写入 JSON）
> 与 AMD/Vivado 无关（纯 Python，MCP 不适用）

---

## 0. 冻结规格（逐字，报告唯一引用源）

### 0.1 两组实验定义（project_design.md L379-396 逐字）

> **关键认知**：我们的设计是 **RO 配对比较 PUF**（非 arbiter PUF），设备秘密本质是 16 个环频的总排序（有效熵 ≈ log2(16!) ≈ 44 bit）。有效 CRP 空间 = C(16,2)=120 种配对比较，而非 2^64。

**实验 A**（文献复现，证明方法论）：合成 arbiter PUF（加性延迟，64 级）+ LR 攻击；预期 >95% 准确率（Rührmair et al. 2010 共识）；结论："文献基线在我们的评估框架中复现成功"

**实验 B**（诚实评估）：攻击者积累 CRP → 恢复 16 环频率排序；方法：响应反推比胜关系 → 拓扑排序；预期 ~120 条带噪 CRP 即可高概率重构；结论："CRP 空间坍缩至 ~2×10^6 种配对构型，排序重构攻击在 ~120 次观测内可恢复完整排序——这是我们设计的已知边界，在报告中如实讨论"

> ⚠️ **F2 已知矛盾（报告处理口径）**：冻结结论中 "~2×10^6" 与同文档 "~2^44"（16!≈2.09×10^13）差 10^7 量级，疑似 10^13→10^6 笔误。处置：报告引用保持 verbatim + 脚注说明，提请 W6 冻结前裁决。

### 0.2 安全声明口径（project_design.md L398-402，逐字四项）

- ✅ 可声明："抗逻辑回归建模攻击"（对 XOR 合并后的响应）
- ❌ 不可声明："抗机器学习攻击"（排序重构对 RO 结构有效）
- ✅ 可声明："已量化安全边界：有效熵 ≈44 bit，排序重构需 ~120 CRP"
- ✅ 可声明（未来工作）："增加环数至 64+ 可将有效熵提升至 ~296 bit"

---

## 1. 实验 A：合成 Arbiter PUF + LR 基线

### 1.1 数学模型（TECH T4 已验证正确）

64 级加性延迟；特征 phi_i(c) = 前缀积 cumprod(±1)（Rührmair 后缀积的镜像，均匀挑战下同分布）；响应 = sign(w·phi + eps)。**train/test 共享同一设备 w**（仅挑战不同）。

### 1.2 噪声：相对量纲（T1 修复，v1 绝对 sigma 无效）

signal_std = std(Phi@w) 生成时实测；eps ~ N(0, alpha * signal_std)。训练集与测试集同噪声。

| alpha（相对噪声） | 预期准确率（TECH 实测贴 Bayes 上限） |
|---|---|
| 0.00 | >99%（1k 即 97%，100k 到 99.9%） |
| 0.05 | ~98.6%（Bayes 98.4%） |
| 0.15 | ~93-95% |
| 0.30 | ~90%（Bayes 90.7%） |

> **冻结底线 >95%**（sigma=0 时判 PASS）；**自设目标 >=99%**（实测 95-99% 时按冻结底线 PASS 并诚实记录）——SPEC F4。

### 1.3 扫描

| 参数 | 值 |
|---|---|
| 训练集 | 1k, 5k, 10k, 50k, 100k |
| 测试集 | 10k（同设备不同挑战，同噪声） |
| 相对噪声 alpha | 0.00, 0.05, 0.15, 0.30 |
| 分类器 | LogisticRegression（默认超参，TECH 验证 100k 无收敛警告 0.2s） |

### 1.4 输出

data/ml_attack/exp_a_results.json：含 repro_command / versions{sklearn,numpy,scipy,matplotlib} / seed / train_sizes / noise_rel / signal_std / accuracy / conclusion_A 逐字 / frozen_floor=0.95 / self_target=0.99 / note（相对噪声+同设备+同噪声说明）

data/ml_attack/exp_a_accuracy.png：x=训练集对数轴，4 条 alpha 线 + Bayes 上限虚线

---

## 2. 实验 B：RO 排序重构攻击

### 2.1 攻击链（TECH 确认推理正确，T2 修正聚合）

1. **配对提取**：decode_pair_table(seed) 公开 → 每种子 64 对有向 (A,B) 索引 + 响应位
2. **无序对聚合（T2 修复）**：key = (min(A,B), max(A,B))；方向归一：原始 (A,B) 且 bit=1 → B 胜；原始 (B,A) 且 bit=1 → A 胜。v1 有序键分裂票（~32+32）
3. **多数表决**：每无序对取胜者方向（偶数票按环索引小者 tie-break）
4. **拓扑排序**：见 2.3 环处理

### 2.2 设备生成（T5 修复：频率碰撞）

ROPairingPUF randint(3100,9600) 采样——birthday 碰撞率 1.75%（TECH 实测 35/2000）。碰撞设备排序真值未定义。**修复**：拒绝采样至 16 频率互异。JSON 记录 rejection_count。

### 2.3 环处理（T6 修复：写死算法）

1. 主算法：找环 → 删环内票强度最弱边（|c0-c1| 最小）→ 重复至 DAG → Kahn 拓扑排序
2. 退化方案：Copeland 出度排名（竞赛图 DAG 当且仅当出度 0..15 互异）
3. 偶数票平票：环索引小者胜（确定性）

> TECH 实测：N>=50 时最少 19 票/对（P误=3e-6），无环。环只在 N<=20 出现。票数 min/med/max=19/48/419（非均匀，报告写 ">=19 票/对" 而非 "~64"——T9）。

### 2.4 扫描矩阵（T3 修复：加低 N 点）

| 维度 | 值 |
|---|---|
| CRP 数 N | **3, 5, 8, 12, 20, 30**, 50, 75, 100, **120**, 150, 200, 300, 400 |
| flip_prob | 0.00, 0.02, 0.05, 0.10 |
| 每配置重复 | 20 次独立试验 |

> TECH 实测：flip=0.10 时 N=12 到 exact 0%, N=20 到 40%, N=30 到 90%, N>=50 到 100%。v1 的 50-400 全平无信息。冻结结论 "~120 内恢复" a fortiori 成立。

### 2.5 评估指标

| 指标 | 定义 | 注意 |
|---|---|---|
| Kendall tau | 恢复排序 vs 真实秩相关 | 用每环在两排序中的**位置向量**算 scipy.stats.kendalltau（直接传排列会错——T10）；频率互异无 tie，tau_a=tau_b |
| 精确匹配率 | 排序完全一致 | 20 trial 比例 |
| 对准确率 | 120 对表决方向正确 | 中间诊断 |
| 环消除次数 | 去环删边数 | 低 N 时非零 |

### 2.6 性能（T7 修正）

前缀复用：每 trial 生成 N_max=400 CRP 一次，各 N 取前缀（respond 各次独立，统计合法）。实测 640 重构 ~14s（naive 48s）。

### 2.7 输出

data/ml_attack/exp_b_results.json：含 repro_command / versions / seed / N_sweep / flip_levels / tau_mean/std / exact_match_rate / pair_acc / cycles_count / rejection_count / conclusion_B 逐字 + F2 脚注 + iid 假设局限 note

data/ml_attack/exp_b_reconstruction.png：x=N，y=exact%，4 条 flip 线 + tau 副轴

---

## 3. 模块结构（~400 行）

```
src/python/evaluation/ml_attack.py
+-- gen_arbiter_crps(n, alpha, rng)             # A：相对噪声+同设备 w
+-- run_exp_a(out, seed)                        # A：扫描+LR+Bayes 上限+图
+-- extract_unordered_observations(crps)        # B：(min,max) 键聚合（T2）
+-- majority_vote_unordered(obs)                # B：方向归一多数表决
+-- topo_sort_with_cycle_break(votes)           # B：最弱边删+Kahn（T6）
+-- kendall_tau_positions(rec, truth)           # B：位置向量 tau（T10）
+-- gen_distinct_freq_puf(rng)                  # B：拒绝采样互异频率（T5）
+-- run_exp_b(out, seed)                        # B：前缀复用扫描+图
+-- main()                                      # CLI: --exp A|B|all --out --seed
```

实现注意（T8/T10）：
- matplotlib.use('Agg') 在 pyplot import 之前
- json.dumps 前全部 int()/float() 强转（np.int64/np.bool_ 会 TypeError）
- 全部英文标签（中文乱码）
- iid per-bit 翻转是对攻击者最有利假设（真实环抖动跨对相关会更快劣化表决）——JSON 加 note

## 4. 单测（tests/test_ml_attack.py，8 项）

| 测试 | 断言 |
|---|---|
| test_arbiter_noiseless_lr | sigma=0 + 1k 训练 → >=95% |
| test_arbiter_relative_noise_scales | alpha=0.3 准确率 < alpha=0.05 |
| test_majority_vote_unordered | 无噪 + 两种朝向混合 → 正确方向 |
| test_topo_sort_known_tournament | 已知 DAG → 已知排序 |
| test_cycle_break_removes_cycles | 人造环 → 删边后成 DAG |
| test_kendall_tau_bounds | 恒等=1, 逆=-1, 随机约 0 |
| test_exp_b_noiseless_sufficient_crps | flip=0 + N=20 → exact=1.0 |
| test_exp_a_smoke | 100 样本冒烟 exit 0 |

## 5. 执行步骤（~4h）

| # | 内容 | 估时 |
|---|---|---|
| S1 | ml_attack.py 骨架 + CLI + 实验 A（相对噪声+Bayes） | 60min |
| S2 | 实验 B 核心（无序聚合+表决+去环+tau） | 60min |
| S3 | 实验 B 扫描（前缀复用）+ 图 | 40min |
| S4 | 单测 8 项 | 40min |
| S5 | CI 接入 + 全量 CI + 提交 | 20min |

## 6. 验收（M3 判据）

- [ ] --exp A exit 0 且 sigma=0 >=95%（冻结底线）
- [ ] --exp B exit 0 且 flip=0.02@120CRP exact >=80%（预期 ~100%）
- [ ] --exp all exit 0（三形态均验收——SPEC F3）
- [ ] 2 PNG + 2 JSON 生成；JSON 含 repro_command/versions/冻结文案四项/F2 脚注
- [ ] 单测 8/8 通过，入 CI
- [ ] 全量 CI 全绿

## 7. 风险（已按 TECH 实测修订）

| 风险 | 状态 |
|---|---|
| 噪声无效 | 已修（相对量纲 alpha） |
| 扫描全平 | 已修（加低 N 点 3-30） |
| 频率碰撞 | 已修（拒绝采样互异） |
| numpy JSON | 已列（int()/float() 强转） |
| 冻结文案 2x10^6 矛盾 | 保持 verbatim + 脚注 + 提请 W6 裁决 |
| matplotlib 后端 | 显式 Agg |