# M1-M4 方案 v2 · 第 2 轮复审（ar-spec-r1，2026-11-02，HEAD 6ed80a7）

方式：重新通读 v2 全文 131 行逐项复验（非按清单判定）+ 三条新设计点实证（阶序一致度探针 review/ar_spec_r1_kendall_probe.{py,log}）。

## Lead 追问三点裁决
- (a) order 元数据向后兼容：**v2 未定义，有真实陷阱**（P2，见 findings）——templates.json 的 device dict 是 seed→resp 映射，order 键会污染 auth 比对路径；版本包装 schema 的 load() 又只取 devices 段。建议沿 .stability.json sidecar 先例建 templates.orders.json，旧模板现算不回写。
- (b) 阈值 0.75 在克隆+近平局噪声下的一致度：**克隆侧安全（0.99+），独立侧不安全**——实测相邻近平局换位 agreement=119/120=0.9917（k 个相邻换位=(120-k)/120，3 个仍 0.975）；但独立随机全序对 mean=0.5015、σ=0.0932（方案误用 √(0.25/120)=0.046——Kendall 对间因传递性正相关，理论 σ=√(2(2n+5)/(9n(n-1)))/2≈0.0926 与实测吻合）、max=0.8000、P(>0.75)=9/2000=0.45%/对比 ⇒ 0.75 仅 2.7σ，族假阳随库规模线性放大。建议 0.85~0.90（经验 0/2000、克隆≥0.975 仍稳判）+ 边界用例。
- (c) predict_response↔RTL 等价性背书：**rootcause v3 的前向复算 HD=0（真板 100 CRP、官方解帧）就是锚**，v2:22 已引用为机理证据；建议把前向断言显式写进步 3/单测（reconstruct→predict 全 100 CRP HD=0），防位打包回归（P3，见 findings）。

## 逐项已修判定

| # | 第 1 轮问题 | 判定 | v2 证据 |
|---|---|---|---|
| 1 | P0：M3 改阶序签名（puf_order.py + Kendall + 0.75 单侧 + 门 + skip+WARN；G1-G6 阶序化） | 已修✓（阈值校准另见新 P1） | v2:27-39 puf_order.py 骨架（reconstruct_order/order_agreement/predict_response，usable=MIN_CRPS100+覆盖120+矛盾率≤0.02）；:43-52 AGREE_REJECT=0.75、a>0.75 判相关（方向正确：高一致度=相关=拒绝）；:48 skip+WARN fail-open with alarm；:72-80 G1-G6 全部阶序场景且附 pytest 命令 |
| 2 | P0 连带：M1 uniqueness 改 order_agreement 矩阵+预测辅口径；共有 seed 公式废除；同板口径显式放弃 | 已修✓ | v2:93 按共有 seed 的公式废除（恒空集）；:94 口径A order_agreement 矩阵；:95 口径B 跨阶序预测 mismatch（100 新随机种子、作分布报告不作判决）；:96 显式放弃同板口径并给理由（无逐环读出通道，留 future work） |
| 3 | P1：动机段改写（无 tid=2、0.4%=auth 轮 HD 1/256 误记） | 已修✓ | v2:19 『v1 方案按共有 seed 算 mismatch 设计——第 1 轮审查证伪：crp_pool.py reserve() 逐终端铸全新 CSPRNG 种子（:164），实测现行库 10 对 tid 组合共有 seed=0，守卫必然空转；mismatch≈0.4% 系将 auth 轮 HD 1/256=0.39% 误记（库里从未存在 tid=2）』；§0 P-2 同步改口径（:12） |
| 4 | P2：步分解/G 用例命令/CI 清单步/工时重排（烧板第 1 序） | 已修✓（M2/M4 命令残留见新 P3） | v2:83 M3 十一步（2-5 分钟粒度）；:73-80 每用例附 python -m pytest … -k … 命令+哨兵行；:70/:125 ci_regression.ps1 python 固定清单逐文件加行（原 18→19+ 表述作废并说明原因）；:112-122 烧板提为序 1、M3 90-120min、M1 120min |
| 5 | P3：D1 全库快照/M2 口径声明/M4 替代式/P-1 待确证/18 表述 | 已修✓（全部五项） | v2:60 Copy-Item 全库快照→templates_snapshot_FULL_20261102.json 再清理（并注明演示数据可再生、快照为审计留底）；:102 M2 模型口径声明（不含硬件近平局噪声、不外推硅上雪崩、与 ml_attack 并排）；:107 seed3 构建不含 PBlock 段（替代式）；:11 P-1 消除（待板端 P1 确证）；:125 原 18→19+ 表述作废 |

## 新发现 Findings（JSON）

```json
[
  {
    "severity": "P1",
    "file": "docs/process/plans/integrate_reference_20261102.md",
    "line": 24,
    "category": "阈值校准基于错误独立性假设（新发现）",
    "description": "v2 称独立全序 agreement σ≈√(0.25/120)≈0.046、0.75≈5.5σ、假阳率可忽略——把 120 个对指示变量当作独立。实测（review/ar_spec_r1_kendall_probe.{py,log}，2000 随机全序对）：mean=0.5015、σ=0.0932（2 倍于方案值；与 Kendall 理论 σ_agreement=√(2(2n+5)/(9n(n-1)))/2≈0.0926 吻合——传递性使对间正相关）、max=0.8000、P(agreement>0.75)=9/2000=0.45%/对比。库含 K 个模板时族假阳≈K×0.45%（D1 清理后 K=1 亦为 0.45%，比『可忽略』高两个数量级；论文多板场景线性放大）。真实演示模板对也印证宽散布（7vs9=0.60）。克隆侧：相邻近平局换位 agreement=119/120=0.9917，k 个相邻换位=(120-k)/120（3 个仍 0.975）——0.85~0.90 阈值可同时满足两侧（独立经验 max 0.80、克隆≥0.975）。修正：AGREE_REJECT 提到 0.85~0.90（理论 3.8~4.3σ，经验 0/2000），并补边界用例（G7：构造 agreement≈0.80 的独立序不得拒绝）。",
    "evidence": "**独立布局 ⇒ 独立全序 ⇒ agreement 期望 0.5**（σ≈√(0.25/120)≈0.046，0.75 阈值≈5.5σ，假阳率可忽略） ‖ AGREE_REJECT = 0.75   # 克隆≈1.0 vs 独立≈0.5±0.046；>0.75 判相关 ‖ 实测: mean=0.5015 stdev=0.0932 max=0.8000 P(>0.75)=9/2000",
    "function_context": "M3 §机理与审查实证 / §守卫逻辑常量",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P2",
    "file": "docs/process/plans/integrate_reference_20261102.md",
    "line": 55,
    "category": "order 元数据落盘 schema 未定义·现有 load/save 与 auth 路径有破坏陷阱（Lead 追问点 a）",
    "description": "『order 签名作为模板元数据随 enroll 落盘（templates.json 同文件 order 字段）』未定义确切 schema：(1) 若 order 作为 device dict 内键写入，将污染 seed→resp 映射——template_db.load() 直接 dict(pairs)（:207-209），auth 路径 hamming_distances/expected 会把 order 键当种子键处理（template_db.py:354-362），轻则报错重则错判；(2) 若用版本包装 schema 的顶层段，load() 只取 raw['devices']（:205-206），order 段在读取时被静默丢弃；(3) 旧模板无 order 的回写语义未定义（cached_or_reconstruct 现算后是否写回：写回=读路径改库，不写回=每次 enroll 重算）。建议：沿 .stability.json sidecar 先例建 templates.orders.json（零 schema 风险、auth 路径零接触），或显式扩展 _TEMPLATE_SCHEMA 并同步改 load/save+旧格式迁移；旧模板现算不回写（或守卫通过后随本次 enroll 的 save() 一并落盘）。",
    "evidence": "order 签名作为模板元数据随 enroll 落盘（templates.json 同文件 order 字段），比对免重算 ‖ template_db.py:207-209: self.templates = {str(tid): dict(pairs) for tid, pairs in raw.items()} ‖ :205-206: if ... raw.get('schema') == _TEMPLATE_SCHEMA: raw = raw.get('devices', {})",
    "function_context": "M3 §守卫逻辑·order 持久化 / template_db.load-save 往返",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P3",
    "file": "docs/process/plans/integrate_reference_20261102.md",
    "line": 33,
    "category": "矛盾率门与真实克隆+近平局噪声的边界（fail-open 借道）",
    "description": "usable 要求 contradiction_rate<=0.02（120 对中 ≤2 对矛盾）。多数票后的真板模板实测 0 矛盾（tid=1），但若某克隆模板近平局对在 3 次测量中按 1:2 分裂且跨 seed 重复出现 >2 对矛盾 → usable=False → skip+WARN fail-open，克隆借道入库。v2 已明示这是 fail-open with alarm 不静默的取舍（:54），但骨架只 print 单行——建议 WARN 行含 tid+矛盾率、REPL 汇总打印 skipped 计数，并补边界用例（克隆但矛盾率 3% → 预期 GUARD_SKIP 且告警可见）。",
    "evidence": "usable = n_crps >= MIN_CRPS(100) and pairs_covered >= 120 and contradiction_rate <= 0.02 ‖ 无高侧拒绝…重建失败→skip+WARN，**fail-open with alarm，不静默**",
    "function_context": "M3 §puf_order.py 骨架 / §守卫逻辑",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P3",
    "file": "docs/process/plans/integrate_reference_20261102.md",
    "line": 75,
    "category": "pytest 选择器与 CI 直跑方式不匹配",
    "description": "G1-G6 命令用 python -m pytest … -k G1_independent，而 ci_regression.ps1 的 python 清单以 python tests\\test_x.py 脚本直跑（:324 起，无 pytest 依赖）。步 10 清单加行时两者必须统一：测试文件须支持 __main__/unittest 直跑（如 unittest.main() + 用例名内嵌 G1..G6），或 CI 行改用 pytest 调用——方案未指明，实施时易踩。",
    "evidence": "`python -m pytest tests/test_template_guard.py -k G1_independent -q` ‖ ci_regression.ps1:324: python tests\\test_a1_phase4.py（脚本直跑） ‖ 步10: ci_regression.ps1 清单加行",
    "function_context": "M3 §验收用例 / §步分解步 10",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P3",
    "file": "docs/process/plans/integrate_reference_20261102.md",
    "line": 103,
    "category": "门禁#3 残留：M2/M4 缺确切命令行",
    "description": "M3/M1 已给命令与哨兵；M2 仍无工具完整调用行（如 python tools/puf_sac.py --freqs … --nbase 256 --out … 与预期末行 SAC_OK）、M4 无 vivado batch 试点命令与预期输出。局部残留，不阻塞。",
    "evidence": "步分解：1. 写 tools/puf_sac.py｜2. 固定 seed 金数单测｜3. 全量跑+落盘 JSON｜4. CI 清单加行（无命令行与预期输出）",
    "function_context": "M2 §步分解 / M4 §试点",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P3",
    "file": "docs/process/plans/integrate_reference_20261102.md",
    "line": 83,
    "category": "predict_response↔RTL 等价性锚建议显式化为 CI 断言（Lead 追问点 c）",
    "description": "v2 已引用『复算 HD=0』作机理证据（:22），但步 3 的哨兵 ORDER_RECON_OK 只断言『反演=共识全序』（后向）。前向等价（predict_response 的位打包 R1[63-8j-p] 与 terminal_fsm 逐位一致）由 rootcause v3 在真板 100 CRP 上以官方解帧背书（HD=0）——建议把该断言显式写进步 3/单测（tid=1 快照 reconstruct→predict 全部 100 CRP HD=0），防位打包回归，并在方案中点名 v3 为等价性锚（目前只在机理段隐含引用）。",
    "evidence": "3. tid=1 快照上手测反演=共识全序（哨兵 ORDER_RECON_OK） ‖ :22: （tid=1 真板 100 CRP：120/120 对覆盖、方向矛盾 0、复算 HD=0）",
    "function_context": "M3 §步分解步 3 / §机理与审查实证",
    "sources": [
      "ar-spec-r1"
    ]
  }
]
```

## 门禁终判

**PASS_WITH_NOTES**。第 1 轮全部整改项经本轮重读 v2 实文逐项确认已修（1×P0、1×P0 连带、1×P1、P2 组、P3 组全数落实），阶序守卫方向/挂载点/用例矩阵/步分解/工时重排均成立。放行条件（实施中必须落实，均为小改）：① AGREE_REJECT 0.75→0.85~0.90（一行常量+一个边界用例，依据本轮实测；0.75 的『假阳率可忽略』表述作废）；② order 持久化改 sidecar（templates.orders.json）或显式扩展 schema 并同步 load/save——禁止把 order 键写进 device dict；③ 步 3 哨兵补前向 HD=0 断言；④ CI 加行时统一 pytest/直跑调用方式；⑤ M2/M4 补确切命令行（可在实施时补，不阻塞开工）。
