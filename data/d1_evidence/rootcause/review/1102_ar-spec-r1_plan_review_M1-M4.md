# M1-M4 集成方案 · 第1轮计划审查（ar-spec-r1，2026-11-02）

对象：docs/process/plans/integrate_reference_20261102.md ｜ 方式：只读审查+独立实证（模板库统计、阶序反推复算、CI/B-LOCK/MANIFEST/prereg v2 核验）

## F1 裁决：成立（P0），且比 Lead 所述更重

1. 代码层：reserve() 逐终端 CSPRNG 铸种、碰撞仅查本池（crp_pool.py:145-171）；enroll.py:66 一切注册路径（含同 tid 重录）都取全新种子 ⇒ 任何两个分别注册的终端共有 seed≈C(100,2)/2^64≈0。
2. 数据层：现行 templates.json 全部 10 对 tid 组合共有 seed=0（实测）；且不存在 tid=2——动机所述『tid=1/tid=2 模板 mismatch≈0.4%』既无数据也无机制可产生，0.4% 与 1101 在线第二轮 HD 1/256=0.39% 巧合，疑误引。
3. 方案层：G6 把空转路径合法化（无共有 seed→成功+skipped），P-2 威胁（同布局板新 tid 注册）必走此路径 ⇒ 守卫在生产中恒不触发；G1/G2 只能靠测试内伪造共有种子构造 ⇒ 『测试绿、生产不设防』。M1 跨模板 uniqueness 同病。
4. 候选修复（阶序签名）可行性：实证成立——tid=1 真板 100 CRP 反推：唯一对覆盖 120/120、矛盾 0、严格全序（独立复现共识全序）；独立序间预测 mismatch 0.40~0.67，同布局克隆≈0~2%，低侧分离巨大；同时天然修复 M1 uniqueness。风险与必备约束：小模板（20-24 CRP）重建不可靠（矛盾 83 处、假反相关 0.668）⇒ 最小样本/覆盖/矛盾率门；独立序可低至 0.402 且 prereg v2 MC p5≈0.34 ⇒ 双侧 [0.40,0.60] 有假阳，建议单边 <0.30 或直接比 120 对 Kendall 一致度；>0.60 应视为重建失败复核而非拒绝；演示 tid 须先清理（D1 已列）。

## Findings（JSON）

```json
[
  {
    "severity": "P0",
    "file": "docs/process/plans/integrate_reference_20261102.md",
    "line": 23,
    "category": "设计缺陷·守卫在真实场景空转（Lead F1 复核成立并加强）",
    "description": "M3 守卫核心规则『只对两模板共有的 seed 取平均』在一切生产注册路径上恒为空集：crp_pool.py reserve()（:145-171）为每个终端用 secrets.SystemRandom().randbytes(8) 独立铸种，碰撞检查（:166）只对本终端集合；enroll.py:66 一切注册（含同 tid 重录）都经 reserve() 取全新种子。实证：当前 data/templates/templates.json 全部 5 个 tid 两两共有 seed=0（10 对全零）。且验收用例 G6『无共有 seed → 成功 + skipped 计数』恰好把空转路径固化为合法行为——P-2 威胁场景（同布局第二块板以新 tid 注册）必然走 G6 路径静默入库，守卫形同虚设。G1/G2 用例只能在测试里人工伪造共有种子才能构造——测试绿、生产不设防。M1 跨模板 uniqueness『HD(R_i,R_j)/共有位数…按共有 seed 归一』（:63）同理恒不可算。",
    "evidence": "`mismatch(R_new, R_i) = HD(R_new, R_i) / n_bits`（只对两模板共有的 seed 取平均；无共有 seed 时跳过该模板并计数） ‖ crp_pool.py:164: seed = self._rng.randbytes(SEED_BYTES)；:166: if key in self._available or key in self._used: continue ‖ 实测: 1vs7/1vs9/1vs55/1vs99/7vs9/7vs55/7vs99/9vs55/9vs99/55vs99 共有 seed 均为 0",
    "function_context": "M3 §设计·规则 + §验收 G6；M1 §uniqueness 公式",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P1",
    "file": "docs/process/plans/integrate_reference_20261102.md",
    "line": 18,
    "category": "动机前提不可复现·数字疑为误引",
    "description": "事故回放称『两块同 bitstream 板先后 enroll 成 tid=1/tid=2，两模板 mismatch≈0.4%』：(a) 当前模板库不存在 tid=2（实测 TIDS=1/7/9/55/99，provenance 亦确认 7/9/55/99 为 web 桥演示残留）；(b) 即使存在 tid=2，共有 seed=0 使『mismatch』按方案自身机制不可计算；(c) 0.4% 与 1101 服务器审计的三轮在线 HD=4/1/3 中第二轮 1/256=0.39% 数值巧合，疑为板内 auth 轮 HD 被误记为跨模板 mismatch。动机数字无任何可溯日志/脚本。需给出出处或改写为可复现表述，否则 G2『复刻昨夜事故』无真实锚点。",
    "evidence": "11-01 夜：两块同 bitstream 板先后 enroll 成 tid=1/tid=2，两模板 mismatch≈0.4%，无任何告警 ‖ 实测 TIDS: ['1','7','9','55','99'] ‖ 审计报告:15: 三轮 serve 分别得 4/1/3（1/256=0.39%） ‖ provenance:6: 7/9/55/99 为 web 桥演示残留",
    "function_context": "M3 §动机（事故回放）",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P2",
    "file": "docs/process/plans/integrate_reference_20261102.md",
    "line": 22,
    "category": "候选修复可行性已实证·但双侧阈值与样本门未定义（F1 修复设计要求）",
    "description": "阶序签名方案可行（本审查实证）：tid=1 真板模板 100 CRP → 唯一对覆盖 120/120、方向矛盾 0、严格全序（独立复现共识报告全序 [4,11,15,13,2,10,1,3,9,7,14,6,5,12,8,0]）；跨模板阶序预测 mismatch 于独立序落 0.40~0.67、同布局克隆将落在 ≈0~2%（仅 {7,9} 型近平局翻转，参照在线 HD 4/1/3/256），低侧分离度巨大。但方案必须补三条设计约束：(a) 小模板重建不可靠——tid=55（24 CRP）方向矛盾 83 处、tid=99（20 CRP）阶序预测 0.668 触发假『反相关』——守卫须设最小 CRP/覆盖/矛盾率门（不足则 skip+计数，语义同 G6 豁免）；(b) 双侧 [0.40,0.60] 阈值在校准上有假阳风险——独立序对可到 0.402（order[7]→tid=9，32000 位实测）且 prereg v2 自家 MC 显示轮 HD p5≈87/256≈0.34，建议低侧改单边（如 <0.30 拒绝）或直接比阶序（120 对 Kendall 一致度：同布局≈1 vs 独立≈0.5，与位数无关）；(c) 高侧 >0.60 应视为重建失败/复核信号而非注册拒绝。",
    "evidence": "规则（对齐参考工程 intra_uniqueness 的 [0.40,0.60] 区间） ‖ 实测: tid=1 unique_pairs=120/120 contradictions=0 strict_order=True；order[7] predicts tid=9: mismatch=0.4022；tid=55 contradictions=83；tid=99 预测 0.6680 ‖ prereg v2:19: min=34，p5=87，中位 129，p95=168（<64 概率 0.2%）",
    "function_context": "M3 §设计·规则（若采纳阶序签名修复）",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P2",
    "file": "docs/process/plans/integrate_reference_20261102.md",
    "line": 87,
    "category": "门禁#4 不满足·无 2-5 分钟步分解",
    "description": "实施顺序表只到里程碑级（40/60/40/30/20/90 分钟档），全篇无一处 2-5 分钟粒度的原子步骤分解（如『guard 常量定义→enroll() 插入点→单测文件骨架→…』），不满足 Mode 1 门禁第 4 条。对依赖 auto-review 执行文化的方案，缺步骤分解会直接放大 F1 类设计缺陷在执行中被固化的风险。",
    "evidence": "| 1 | M3 守卫（含 D1 清演示模板） | 40min | 无 |（§5 全表均为 20~90min 档，无更细分解）",
    "function_context": "§5 实施顺序",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P2",
    "file": "docs/process/plans/integrate_reference_20261102.md",
    "line": 42,
    "category": "门禁#3 部分不满足·缺确切测试命令",
    "description": "验收表给了期望（含哨兵名 GUARD_OK/METRICS_OK/SAC_OK）但全篇无一条确切执行命令：无 pytest 调用行、无 tools/puf_metrics.py 的完整命令行示例、M4 无 vivado batch 命令与试点预期输出。另『CI 挂 tests/ 后 18→19+ 套全绿』单位混用：18 是 xsim TB 数（$tbNames 共 18 项+ENROLL_NEG），python 测试是 ci_regression.ps1:324-355 的固定逐文件调用清单——新增测试文件必须改脚本，此步仅在 §5 条目 4 隐含覆盖、未进 M3 改动文件表。",
    "evidence": "| G1 独立模板 | 与既有 mismatch≈50% | 注册成功 + [GUARD] OK 行 |（无对应命令行） ‖ 哨兵行：`GUARD_OK` / 用例名；CI 挂 tests/ 后 18→19+ 套全绿 ‖ ci_regression.ps1:324: python tests\\test_a1_phase4.py（固定清单逐个调用）",
    "function_context": "M3 §验收 / §6 总口径",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P2",
    "file": "docs/process/plans/integrate_reference_20261102.md",
    "line": 91,
    "category": "工时不现实（F1 返工后）",
    "description": "M3 按 40min 估（含 6 用例+既有对齐）是按共享种子简单实现的口径；改为阶序签名后需：反推/投票模块+覆盖与矛盾门+阈值校准（或 Kendall 口径）+G1-G6 全部重写为阶序场景——实际 90~120min。M1 的 uniqueness 机制同理需返工（跨阶序预测或同种子查询实验设计）。死线 11-03 且今日 D2 论文日、烧板主线随时插入，按原表排程会挤压论文时间或导致赶工简化（恰是 F1 被埋进去的路径）。",
    "evidence": "| 1 | M3 守卫（含 D1 清演示模板） | 40min | 无 | ‖ | 2 | M1 指标 v1（含真数据产出） | 60min | 无 |",
    "function_context": "§5 实施顺序条目 1-2",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P3",
    "file": "docs/process/plans/integrate_reference_20261102.md",
    "line": 31,
    "category": "D1 快照声称与删除范围不符",
    "description": "『rootcause/ 已有快照』仅覆盖 tid=1（templates_snapshot_tid1_20261101.json，SHA 02CEF985…）；被删除的 7/9/55/99 无快照，且 templates.json 本身未跟踪（git ?? 状态）——删除即永久丢失这 4 份演示模板。它们是 web 桥可再生的演示数据，丢失风险低，但方案应改为『快照全库后清理』或注明可再生，避免以 tid=1 快照为全部删除背书。",
    "evidence": "清除运行库中演示残留 tid=7/9/55/99（rootcause/ 已有快照，两次事故源头） ‖ provenance:5-6: SHA256: 02CEF985…；7/9/55/99 为 web 桥演示残留（快照文件仅 tid=1） ‖ git status: ?? data/templates/templates.json",
    "function_context": "M3 §设计·决策点 D1",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P3",
    "file": "docs/process/plans/integrate_reference_20261102.md",
    "line": 74,
    "category": "M2 口径局限未显式声明（论文措辞风险）",
    "description": "SAC 在黄金模型（固定 fixture 频率、确定性）上测得，度量的是挑战解码器/LFSR+Fisher-Yates 的配对扩散（固定配对会得 0%，重洗牌≈50%），不含硬件近平局对噪声——不能外推为硅上雪崩性质；且 SAC≈50% 与『已可建模』（ml_attack 11/11）不矛盾，论文须并排陈述防审稿人反问。方案已写『偏离=发现』，但应补一行明确的 model-level 证据声明+硬件 caveat。nBase=256×64 翻转纯软件可行，设计本身无问题。",
    "evidence": "预登记预期：全局 ≈ 50%（挑战经 LFSR+Fisher-Yates 洗牌，扩散性应良好） ‖ 对照文档:32: SAC 雪崩 … 有标准脚本 | 无 → 应补：黄金模型上跑，纯软件",
    "function_context": "M2 §tools/puf_sac.py 设计",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P3",
    "file": "docs/process/plans/integrate_reference_20261102.md",
    "line": 83,
    "category": "M4『替代/叠加 PBlock』语义未定 + B-LOCK 衔接",
    "description": "逐环 LOC 若与 PBlock『叠加』，LOC 站点必须全部落在 X1Y0 内否则直接冲突报错——应明确 seed3 为替代式（去掉 PBlock）或 LOC 全部取自 X1Y0。B-LOCK 现锁 seed2 tcl 不变量与双构建 filelist 一致（ci_regression.ps1:194-214），新增 build_w3_board_seed3.tcl 不受影响，但若按方法论纵深入论文，建议顺带把 seed3 纳入 B-LOCK 模式（可选）。试点单环先行的风险控制设计合理。",
    "evidence": "build_w3_board_seed3.tcl = seed2 加固版流程 + source 该片段（替代/叠加 PBlock） ‖ ci_regression.ps1:194: pat = 'set pick \"X1Y0\"'（seed2 region pinned）",
    "function_context": "M4 §构建",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P3",
    "file": "docs/process/plans/integrate_reference_20261102.md",
    "line": 10,
    "category": "§0 P-1『消除』措辞超前于证据",
    "description": "P-1 标注防线性质=消除（构建层），但按 prereg v2 口径 seed2 修复在板端 P1 落地前仍是『预期』（MC 带 <64 概率 0.2%、失败分支含 seed3 重建）；『消除』应降为『待板端确证』。同表 P-2/P-3 措辞无此问题。",
    "evidence": "| P-1 | 跨板唯一性失效（同 bit ⇒ 同指纹，11-01 实证） | seed2 已建；M4 提供逐环级细粒度差异化（seed3 备选+策略纵深） | **消除**（构建层） |",
    "function_context": "§0 问题→措施映射",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P3",
    "file": "docs/process/plans/integrate_reference_20261102.md",
    "line": 63,
    "category": "对照清单可选项未声明取舍",
    "description": "对照文档 §4 条目 1 的『（可选）同板 16 环两两口径』在 M1 中未出现且未声明放弃——覆盖面建议显式写『不做，理由』（同板多实例口径与当前单实例架构不匹配），其余 §4 条目 1-4 与『明确不抄』清单均已覆盖（M1/M2/M3/M4 一一对应）。",
    "evidence": "uniqueness 等烧板 REJECT 后补跨板数 + （可选）同板 16 环两两口径（对照文档:40）‖ 方案 M1 仅有跨模板口径",
    "function_context": "M1 §tools/puf_metrics.py 设计",
    "sources": [
      "ar-spec-r1"
    ]
  }
]
```

## 独立复验通过项
| 方案声称 | 复验 |
|---|---|
| M3 挂载点 template_db.py:238 为唯一咽喉 | ✓ enroll() 恰在 :238；src 内唯一调用者 enroll.py:90 |
| M1 v1.1 前提『enroll 已收 measurements，加持久化』 | ✓ enroll.py:90 传 measurements=data；template_db 仅用于掩码计算后丢弃（:273-278），save() 不落原始测量 |
| M1 金数 tid=1 uniformity=0.487±0.001 | ✓ 实测 0.4873 |
| reliability v1 前提（tid=1 64/64 稳定） | ✓ provenance:3 + stability 掩码 |
| M4『既有门禁全保留…USERID』 | ✓ 加固版 seed2 tcl:123 USERID=0x5EED0002，B-LOCK 锁定（ci_regression.ps1:194-198）；seed3 用 0x5EED0003 一致 |
| M4 触发与 prereg v2 衔接 | ✓ prereg v2:35 失败分支已含『逐环 LOC 重建 seed3』 |
| 对照文档 §4 覆盖 | ✓ 条目1→M1、2→M2、3→M3、4→M4；条目5 明示 future work；『明确不抄』均未违反（缺可选同板口径声明，见 P3） |
| 零 placeholder | 基本满足（D1 为带默认值的显式决策点，可接受） |

## 结论段

**门禁判定：FAIL（第 1 轮）**——M3 的核心机制在真实注册场景恒空转（P0，Lead F1 成立并加强），连带 M1 跨模板 uniqueness 公式不可算；动机数字不可溯（P1）；叠加门禁#3/#4 格式缺口与工时失真（P2×3）。方案骨架（M2/M4 设计、实施顺序、prereg v2/B-LOCK 衔接、防线分层思想）健全，修复方向明确。

**修正优先级**：
1. 【P0】M3 改阶序签名比对（或等效种子无关机制）：enroll 时反演 win-count 全序入库为模板元数据；比对用 Kendall 一致度或跨阶序预测 mismatch；设最小 CRP（≥100）/对覆盖（120/120）/矛盾率门，不足则 skip+计数；阈值重校准（建议单边 <0.30 拒绝 + >0.60 转人工复核）；G1-G6 全部改为阶序场景（克隆→拒、独立→过、小模板→skip、force→过）。
2. 【P0 连带】M1 uniqueness 改同机制（跨阶序预测），或显式设计『同种子集跨板查询』实验路径；公式行同步改写。
3. 【P1】动机段给出 0.4% 出处或改写（当前库无 tid=2；与 1101 轮 HD 1/256 区分清楚）。
4. 【P2】补 2-5 分钟步分解 + 每步确切命令与预期输出行（含 ci_regression.ps1 的 python 清单改动步）。
5. 【P2】工时重排：M3 → 90-120min，M1 → +60min；D2 论文日优先保烧板主线与论文，M4 维持『烧板后可选』。
6. 【P3】D1 改为全库快照后清理；M2 补 model-level 声明与硬件 caveat；M4 明确替代式 PBlock；§0 P-1 改『待板端确证』；M1 声明放弃同板口径及理由；『18→19+』改为准确表述。
