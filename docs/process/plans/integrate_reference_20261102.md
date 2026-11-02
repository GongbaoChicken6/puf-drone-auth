# 参考工程（PUF_ARTY_S7）借鉴集成实施方案 · M1-M4 · v2

日期：2026-11-02（D2）｜v2 修订：第1轮计划审查（ar-spec-r1，报告 data/d1_evidence/rootcause/review/1102_ar-spec-r1_plan_review_M1-M4.md）门禁 FAIL 后全量修正
依据：docs/PUF_ARTY_S7_reference_comparison_20261102.md｜死线 11-03 保守
原则：先虚拟后上板；证据落盘；断言正向；零 RTL 改动；不碰生产 bit / 已验证 seed2 / prereg v2 锚点。

## 0. 问题 → 措施映射（v2 措辞校准）

| 编号 | 问题（现状） | 措施 | 防线性质 |
|---|---|---|---|
| P-1 | 跨板唯一性失效（同 bit ⇒ 同布局 ⇒ 同指纹，11-01 实证；修复待板端确证） | seed2 已建（预登记待验证）；M4 逐环 LOC 为纵深/备选 | 消除（**待板端 P1 确证**） |
| P-2 | 相似指纹设备可静默注册（11-01 经 auth 观测到同模板双板均 PASS；守卫防的是该场景进入注册库） | M3 **阶序签名守卫**（v1 共有 seed 方案被审查证伪：crp_pool 逐终端 CSPRNG 铸种、实测 10 对 tid 共有 seed=0） | 防御（服务层） |
| P-3 | 评测不成体系 | M1 三件套 + M2 SAC | 验证 |
| P-4 | 布局差异化仅区域级 | M4 | 纵深 |

## 1. M3 · enrollment 阶序签名守卫（v2 重设计，90-120 分钟）

### 动机（v2 校正史实）
11-01 夜两块同 bitstream 板对同一 tid=1 模板 auth 均 PASS（HD=1/0），若当时执行 enroll 2 将把"同指纹"第二条模板静默入库。v1 方案按"共有 seed 算 mismatch"设计——第 1 轮审查证伪：crp_pool.py reserve() 逐终端铸全新 CSPRNG 种子（:164），实测现行库 10 对 tid 组合共有 seed=0，守卫必然空转；"mismatch≈0.4%"系将 auth 轮 HD 1/256=0.39% 误记（库里从未存在 tid=2）。v2 改用**种子无关的阶序签名**。

### 机理与审查实证
根因调查证明：指纹由 16 环频率全序唯一决定，全序可从任一模板反推（tid=1 真板 100 CRP：120/120 对覆盖、方向矛盾 0、复算 HD=0）。因此：
- **同布局克隆 ⇒ 同全序 ⇒ 120 对一致度 agreement≈1.0（实测预期，仅近平局对噪声±2%）**
- **独立布局 ⇒ 独立全序 ⇒ agreement 期望 0.5**（σ≈√(0.25/120)≈0.046，0.75 阈值≈5.5σ，假阳率可忽略）
- 判决用 **120 对 Kendall 一致度**（与 CRP 位数无关），不用跨阶序预测 mismatch 的双侧带（审查实证独立序可低至 0.402、prereg MC p5≈0.34，双侧 [0.40,0.60] 有假阳）。

### 新增模块 src/python/server/puf_order.py（骨架）
```python
def reconstruct_order(template: Mapping[str, str]) -> OrderResult:
    """胜场计票反演全序（rootcause v3 同法）。
    返回 OrderResult(order: list[int](快->慢), n_crps, pairs_covered,
    contradiction_rate, usable: bool)
    usable = n_crps >= MIN_CRPS(100) and pairs_covered >= 120 and contradiction_rate <= 0.02
    —— 审查实证小模板不可靠（tid=55 24CRP 矛盾 83 处）"""
def order_agreement(order_a, order_b) -> float:
    """120 无序对中同向比例（Kendall 一致度，1.0=同序，0.5=独立）"""
def predict_response(order, seed_int) -> int:
    """decode_pair_table(seed) + order -> 64bit（M1 uniqueness 复用）"""
```

### 守卫逻辑（挂 template_db.enroll() :238，持久化之前）
```python
AGREE_REJECT = 0.75   # 克隆≈1.0 vs 独立≈0.5±0.046；>0.75 判相关
new = reconstruct_order(pairs_as_template)
for tid, existing in real_templates.items():
    ex = cached_or_reconstruct(existing)
    if not new.usable or not ex.usable:
        skipped += 1; print(f"[GUARD] tid={tid} ORDER-SKIP (unreliable order)"); continue
    a = order_agreement(new.order, ex.order)
    print(f"[GUARD] tid={tid} agreement={a:.3f} {'REJECT' if a > AGREE_REJECT else 'OK'}")
    if a > AGREE_REJECT and not allow_correlated:
        raise CorrelatedTemplateError(tid, a)
```
- 无高侧拒绝（v1 的 mismatch>0.60 判据废除：一致度空间无此风险；重建失败→skip+WARN，**fail-open with alarm，不静默**）；
- order 签名作为模板元数据随 enroll 落盘（templates.json 同文件 "order" 字段），比对免重算；
- allow_correlated=True 逃生口（REPL `enroll <tid> <n> force`）；
- serial_server 注册路径异常→RESULT_ERROR 帧（实施时核实其 enroll 调用点，沿 B-P2 文化）。

### D1（清演示 tid，v2 改全库快照）
执行顺序：先 `Copy-Item data/templates/templates.json → data/d1_evidence/rootcause/templates_snapshot_FULL_20261102.json`（**全库**快照，v1 只快照过 tid=1），再从运行库移除 7/9/55/99（演示序两两不同、不干扰阶序比对，但清理后守卫只面对真实终端）。演示数据可再生（web 桥隔离目录），快照仅为审计留底。

### 改动文件（v2 补 CI 步）
| 文件 | 改动 |
|---|---|
| src/python/server/puf_order.py | 新模块（反演/一致度/预测） |
| src/python/server/template_db.py | enroll() 守卫 + order 元数据落盘 |
| src/python/server/main.py | REPL enroll force 形参 + [GUARD] 输出 |
| src/python/server/serial_server.py | CorrelatedTemplateError → RESULT_ERROR |
| tests/test_template_guard.py | 新（用例表 v2） |
| scripts/ci_regression.ps1 | **python 测试固定清单新增一行**（审查指出：清单逐文件硬编码，非自动发现） |

### 验收用例 v2（全部阶序场景；命令与预期）
| # | 构造 | 命令 | 预期输出（哨兵行） |
|---|---|---|---|
| G1 | 库含 tid=1；新模板=独立随机序 | `python -m pytest tests/test_template_guard.py -k G1_independent -q` | agreement≈0.5、注册成功、`GUARD_OK G1` |
| G2 | 新模板=tid=1 同序克隆（构造同序响应） | `... -k G2_clone` | CorrelatedTemplateError、库无写入、`GUARD_REJECT G2 tid=1` |
| G3 | 新模板仅 24 CRP（不可靠序） | `... -k G3_small` | skip+WARN、注册成功、`GUARD_SKIP G3` |
| G4 | G2 + force | `... -k G4_force` | 成功 + 告警行、`GUARD_FORCE G4` |
| G5 | 空库首个终端 | `... -k G5_first` | 直接成功（空集合不误杀） |
| G6 | 既有模板自身不可靠（矛盾率>2%） | `... -k G6_unreliable_existing` | skip+WARN（对侧不可靠不拒绝新模板）、`GUARD_SKIP G6` |

### 2-5 分钟步分解
1. 写 puf_order.py 反演函数（含自校验断言）｜2. 写 order_agreement｜3. tid=1 快照上手测反演=共识全序（哨兵 ORDER_RECON_OK）｜4. template_db.enroll 挂守卫｜5. order 元数据落盘｜6. main.py force+[GUARD]｜7. serial_server 映射（先核实调用点）｜8. D1 全库快照+清理｜9. 写 tests 六用例｜10. ci_regression.ps1 清单加行｜11. 跑全套+全量回归。

### 风险与回退
- 阶序不可靠模板→skip（不误杀）；阈值 0.75 保守可调（常量）；回退=常量置 None 禁用守卫，其余不动。
- 工时 90-120min（v1 的 40min 按 VOC 方案失真）；若 D2 时间被论文挤压，M3 最小可用版=反演+G2 克隆拒绝两个用例先行，其余补齐。

## 2. M1 · 三件套 v2（uniqueness 机制重设计，60+60 分钟）

- uniformity：不变（tid=1 金数 0.4873 已交叉验证）。
- reliability：v1 稳定掩码代理不变；v1.1 原始测量落盘不变（enroll.py:90 已传 measurements，template_db :273-278 算完掩码即丢弃——补持久化）。
- **uniqueness（跨模板）v2：按共有 seed 的公式废除（恒空集）**，改用阶序机制（复用 puf_order）：
  - 口径 A（主）：order_agreement 矩阵（克隆≈1 / 独立≈0.5）；
  - 口径 B（辅）：跨阶序预测 mismatch——用 predict_response(orderA, seed) vs predict_response(orderB, seed) 对 100 个新随机种子求均值（审查实证独立序 0.40~0.67，作为分布报告而非判决）；
  - **声明放弃**"同板 16 环两两口径"（对照文档标可选）：现协议每挑战只出 64 位响应、无逐环读出通道，板上无法取得环内独立实例数据——留待 future work（与 M4/环频直读同章节）。
- 命令与哨兵：`python tools/puf_metrics.py --templates data/templates/templates.json --out data/d1_evidence/puf_metrics_1102.json` → 末行 `METRICS_OK`；单测金数表（全 0/全 1/构造 HD）不变。

## 3. M2 · SAC（40 分钟，补口径声明）

- 设计不变（nBase=256、逐位翻转、per-bit+全局、CI 哨兵 `SAC_OK`）。
- **口径声明（论文措辞，v2 补）**：本指标在黄金模型（确定性 fixture 频率）上度量**挑战解码/配对扩散**（LFSR+Fisher-Yates），不含硬件近平局对噪声，不外推为硅上雪崩；SAC≈50% 与"可建模（ml_attack 11/11）"并排陈述、不矛盾。
- 步分解：1. 写 tools/puf_sac.py｜2. 固定 seed 金数单测｜3. 全量跑+落盘 JSON｜4. CI 清单加行。

## 4. M4 · 逐环 LOC 生成器（seed3，烧板后可选，90 分钟）

- v2 明确：**替代式**（seed3 构建**不含** PBlock 段，仅逐环 LOC）——审查指出 LOC 与 PBlock 叠加会因站点越区冲突报错。
- tools/gen_ring_layout.py：--strategy rand --seed N / stride / cluster；环内 5 LUT 同列相邻行、32 环彼此散开；输出 build/tcl/ring_loc_seedN.tcl（**综合后应用**、含 32 环唯一 LOC 断言、逐环 get_cells 过滤——w2_waiver 文化）；构建脚本 build_w3_board_seed3.tcl = seed2 加固版流程 − PBlock + source 片段，USERID=0x5EED0003，既有门禁全保留（WHS/32 环断言/落位报告）。
- 试点：先只生成 1 环的 LOC 构建验证语法+时序，再全量（30min+60min）。
- CI 衔接（可选）：seed3 tcl 建成后把 B-LOCK 的 filelist 一致性检查从双脚本泛化为 seed* 通配（5 分钟）。

## 5. 实施顺序 v2（工时重排）

| 序 | 项 | 工时 | 备注 |
|---|---|---|---|
| 1 | **烧板主线（seed2 实验，最高优先，随时插队）** | 30min | prereg v2 判据 |
| 2 | M3 阶序守卫（步 1-11） | 90-120min | 最小可用版可裁 |
| 3 | M1 v2（步：公式改阶序/工具/金数/真数据） | 120min | uniqueness 复用 puf_order |
| 4 | M2 SAC | 40min | |
| 5 | 全量回归（CI + B-LOCK） | 30min | |
| 6 | M1 v1.1 测量落盘 | 20min | |
| 7 | M4 seed3（仅当烧板失败分支或余力） | 90min | 替代式 |

## 6. 验收与回归总口径（v2 单位校准）
- 新增 pytest 文件 2 个（test_template_guard / test_puf_metrics+test_puf_sac 合并或分开），**ci_regression.ps1 的 python 固定清单逐文件加行**（原"18→19+"表述作废：18 是 xsim TB 数，python 清单是独立硬编码列表）；
- 哨兵：GUARD_OK/GUARD_REJECT/GUARD_SKIP、METRICS_OK、SAC_OK、ORDER_RECON_OK；
- 全绿标准：scripts/ci_regression.ps1 退出 0（含既有全部 xsim TB 与 python 清单）。

## 7. 遗留衔接
- 第 1 轮审查报告归档：review/1102_ar-spec-r1_plan_review_M1-M4.md；本 v2 逐条对账见其"修正优先级清单"；
- GitHub push 待 VPN（9f57f8b/374c6ec 及后续一并推）。
