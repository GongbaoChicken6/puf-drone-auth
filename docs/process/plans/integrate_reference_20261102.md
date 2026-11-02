# 参考工程（PUF_ARTY_S7）借鉴集成实施方案 · M1-M4

日期：2026-11-02（D2）｜依据：docs/PUF_ARTY_S7_reference_comparison_20261102.md｜死线：11-03 保守
原则：先虚拟后上板（全部四项先在模型/单测层验证）；证据落盘；断言正向；不碰生产 bit 与已验证 seed2。

## 0. 问题 → 措施映射（"确保问题消除"的三层防线）

| 编号 | 问题（现状） | 措施 | 防线性质 |
|---|---|---|---|
| P-1 | 跨板唯一性失效（同 bit ⇒ 同指纹，11-01 实证） | seed2 已建；M4 提供逐环级细粒度差异化（seed3 备选+策略纵深） | **消除**（构建层） |
| P-2 | 相似/相同指纹设备可静默注册（昨夜双板双模板无告警入库） | M3 enrollment 相关性守卫 | **防御**（服务层兜底：即使再来一次同布局板，第二次注册直接被拒） |
| P-3 | 评测不成体系（无 uniformity/uniqueness/reliability/SAC 标准口径） | M1 三件套 + M2 SAC | **验证**（仪表：证明 P-1 已修复、给论文标准数字） |
| P-4 | 布局差异化仅区域级（PBlock），无策略实验能力 | M4 逐环 LOC 生成器 | 消除+纵深 |

## 1. M3 · enrollment 相关性守卫（最高优先，~40 分钟）

### 动机（事故回放）
11-01 夜：两块同 bitstream 板先后 enroll 成 tid=1/tid=2，两模板 mismatch≈0.4%，无任何告警——若守卫在场，第二次注册当场被拒：`ENROLL_REJECTED: new template correlates with tid=1 (mismatch=0.4% < 40%)`。

### 设计
- 挂载点：`TemplateDB.enroll()`（template_db.py:238，serial/loopback/web 桥全部注册路径的唯一咽喉）。
- 规则（对齐参考工程 intra_uniqueness 的 [0.40,0.60] 区间）：
  `mismatch(R_new, R_i) = HD(R_new, R_i) / n_bits`（只对两模板共有的 seed 取平均；无共有 seed 时跳过该模板并计数）
  - min_i mismatch < CORR_LO(0.40) → 拒绝（CorrelatedTemplateError，含与谁、多少）
  - mismatch > CORR_HI(0.60) → 拒绝（反相关异常，同参考工程双侧判据）
  - 阈值为模块常量 + enroll() 形参可覆盖。
- 豁免通道：
  - `enroll(..., allow_correlated=True)`：显式逃生口（REPL `enroll <tid> <n> force`，供故意重录同一设备/实验场景）；
  - 测试/演示：现有单测里"同一模型多 tid"场景改传 allow_correlated=True 或断言新错误类型（新增正向用例覆盖）。
- REPL/日志输出：注册成功时打印与各既有模板的 mismatch 清单（一行/模板，`[GUARD] tid=1 mismatch=0.503 OK`），被拒时打印 `[GUARD] ENROLL_REJECTED ...`——证据落盘文化。
- 决策点 D1（需你确认，默认执行）：清除运行库中演示残留 tid=7/9/55/99（rootcause/ 已有快照，两次事故源头），使守卫只面对真实终端；web 桥隔离目录（web/.dev-data）不受影响。

### 改动文件
| 文件 | 改动 |
|---|---|
| src/python/server/template_db.py | enroll() 加 guard + CorrelatedTemplateError + 阈值常量 |
| src/python/server/main.py | REPL enroll 命令支持 force 形参 + [GUARD] 输出 |
| src/python/server/serial_server.py | 注册端点透传异常为 RESULT_ERROR（不炸 serve 循环，沿用 B-P2 文化） |
| tests/test_template_guard.py（新） | 见验收表 |
| 既有受影响单测 | 逐个对齐（预计≤3 处） |

### 验收（正向哨兵，全部进 CI）
| 用例 | 输入 | 期望 |
|---|---|---|
| G1 独立模板 | 与既有 mismatch≈50% | 注册成功 + [GUARD] OK 行 |
| G2 复刻昨夜事故 | 与既有 mismatch≈0.4% | CorrelatedTemplateError，模板库无写入 |
| G3 反相关 | mismatch≈100% | 拒绝 |
| G4 force 逃生 | G2 + allow_correlated=True | 成功 + 告警行 |
| G5 首个终端 | 库空 | 直接成功（空集合不误杀） |
| G6 无共有 seed | 完全不同挑战集 | 成功 + skipped 计数 |
哨兵行：`GUARD_OK` / 用例名；CI 挂 tests/ 后 18→19+ 套全绿。

### 风险与回退
- 误杀真实设备：独立布局 mismatch 预期 0.5，带宽 0.40-0.60 极宽；万不得已 force 参数 5 秒解锁；
- 回退：guard 常量置 None 即禁用（一行），不动其他逻辑。

## 2. M1 · 标准三件套指标工具（~60 分钟）

### tools/puf_metrics.py 设计
- 输入：`--templates data/templates/templates.json --tids 1[,2,...] [--stability data/templates/templates.stability.json] [--out data/d1_evidence/puf_metrics_<date>.json]`
- 输出（JSON+Markdown 表，论文直接贴）：
  - **uniformity**（每 tid）：`mean(popcount(R))/ (n·64)`，期望 50%（tid=1 实测预期 48.7%，与既有画像交叉验证）
  - **uniqueness（跨模板对）**：`HD(R_i,R_j)/共有位数` 的均值/分布（参考工程裸 mismatch + 学界标准双口径并列输出）；共挑战缺失时按共有 seed 归一
  - **reliability v1（掩码代理）**：从 templates.stability.json 的 stable-bit 掩码算 `stable_bits/64`（tid=1 已知 100%）；**v1.1（小改）**：enroll 路径把原始 measurements dict 落入 stability 文件（enroll.py:90 → template_db.enroll 已收 measurements，加持久化），此后 reliability 升级为标准口径 `1 - 翻转位率`（参考工程 11 次测量口径，我们 3 次，论文注明）
- 单测（tests/test_puf_metrics.py）：构造全 0/全 1/已知 HD 的合成模板，断言指标精确值（golden 数字表）；真数据 smoke：tid=1 uniformity=0.487（±0.001）。
- 产出计划：今天用 tid=1+演示对照出表；烧板后补 tid=2（seed2 板）与跨板 uniqueness=期望≈50%——论文评测章三件套齐活。
- 哨兵：`METRICS_OK`。

## 3. M2 · SAC 雪崩测试工具（~40 分钟）

### tools/puf_sac.py 设计
- 用黄金 CRP 链：`decode_pair_table(seed) + ROPairingPUF(freqs)`（rootcause v3 已复用的同一模型，RTL↔模型等价有 tb_puf_path 黄金锚背书）。
- 流程：nBase=256 随机种子为基；对每个基种子逐位翻转（64 位 × 1 位翻转）→ 统计每位、全局响应翻转率；输出 per-bit SAC + 全局均值 + 最差/最好位。
- 预登记预期：全局 ≈ 50%（挑战经 LFSR+Fisher-Yates 洗牌，扩散性应良好）；若某位显著偏离（<40%），这是**发现不是失败**：写论文"挑战编码扩散性"小节 + future work（多种子混合）。
- 单测：固定 freqs+seed 的 golden 断言 + 全 0/全 1 边界；CI 挂载；哨兵 `SAC_OK`。

## 4. M4 · 逐环 LOC 布局策略生成器（seed3，烧板后可选 ~90 分钟）

### tools/gen_ring_layout.py
- 策略（对齐参考工程 placementType 思想，XDC/tcl 化）：`--strategy rand --seed N`（每环独立随机 SLICE/BEL，参考工程 RAND 同款）/ `stride`（等距栅格）/ `cluster`（双簇对角）。
- 粒度：**环间分散、环内紧凑**——每环 5 个 LUT 钉在同一 SLICE 列相邻行（保环内一致），32 环彼此散开（制造排序差异）。
- 输出：`build/tcl/ring_loc_seed<N>.tcl` 片段（**综合后应用**，沿用 w2_waiver 教训：XDC 综合前 nets/cells 不存在会静默空匹配；片段内含逐环 get_cells 过滤 + set_property LOC/BEL + 32 环唯一性断言）。
- 构建：`build_w3_board_seed3.tcl` = seed2 加固版流程 + source 该片段（替代/叠加 PBlock）+ 既有门禁全保留（32 环断言/WHS/落位报告/USERID=0x5EED0003）。
- 触发时机：(a) seed2 板实验落失败分支（预登记已写）；(b) 论文"布局策略"纵深（区域级 PBlock vs 逐环 LOC 两级方法论）。
- 风险：Vivado 2026 对 LUT LOC/BEL 语法兼容（试点：先只钉 1 环构建验证语法与时序，再全量）；时序收敛（环内紧凑+环间分散应无碍，DRC 门禁兜底）。

## 5. 实施顺序（今天 D2）

| 序 | 项 | 耗时 | 依赖 |
|---|---|---|---|
| 1 | M3 守卫（含 D1 清演示模板） | 40min | 无 |
| 2 | M1 指标 v1（含真数据产出） | 60min | 无 |
| 3 | M2 SAC | 40min | 无 |
| 4 | CI 挂载 + 全量回归（pytest+xsim） | 30min | 1-3 |
| 5 | **烧板主线（seed2 实验，随时插入，最高优先）** | 30min | 硬件在手 |
| 6 | M1 v1.1（measurements 落盘） | 20min | 2 |
| 7 | M4 生成器 + seed3（仅当 5 失败或晚上有余力） | 90min | 5 结果 |

## 6. 验收与回归总口径
- 每项都有正向哨兵行 + pytest 套件；全部合入后跑 scripts/ci_regression.ps1 全绿（含 B-LOCK）；
- 证据：tools 输出 JSON 落 data/d1_evidence/；守卫的 [GUARD] 行天然进 REPL 日志；
- 不碰：生产 bit、已验证 seed2 bit、prereg v2 锚点、RTL 源（本方案零 RTL 改动，纯软件+构建脚本）。

## 7. 遗留衔接
- 烧板后：M1 补跨板 uniqueness → 论文；M3 在真实 enroll 流程中验证 [GUARD] 输出；
- GitHub push 待 VPN（9f57f8b 与后续提交一起推）。
