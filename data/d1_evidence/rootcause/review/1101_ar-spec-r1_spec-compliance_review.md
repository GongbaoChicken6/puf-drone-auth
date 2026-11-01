# seed2 修复路径 spec 合规审查（ar-spec-r1）

- 审查范围：git 242d9bd..1760b72（c348baa → 062c776 → a94775f → 1760b72，184 文件 +8648 行）
- spec = data/d1_evidence/rootcause/1101_ROOTCAUSE_consensus.md + 修复路径声明（首选：按板差异化布局使环排序独立）
- 方式：只读审查 + 独立复验（SHA256、git 跟踪状态、Vivado 器件网格实测、构建日志核验）；仓库源码零改动，产物仅写入本目录
- 日期：2026-11-01 17:5x Asia/Shanghai；审查员代理：ar-spec-r1

## 一、findings（JSON）

```json
[
  {
    "severity": "P1",
    "file": "(git commit 1760b72 message)",
    "line": 1,
    "category": "claim-vs-fact / 证据链不可复现",
    "description": "提交信息声称生产 bit 已被 git 跟踪，实际从未跟踪：`git ls-files '*.bit'` 无 build/board_zc706/w3_top_zc706.bit；`git log --all -- build/board_zc706/w3_top_zc706.bit` 为空；.gitignore:85 整目录忽略 build/board_zc706/。后果：修复方案的核心对照主张『seed2 SHA256 与生产 bit 不同，确认布局真实差异』中，对照基线（生产 bit 24ED4EED…）仅存在于本机磁盘，任何 fresh clone 无法复现该对比；板上实验前的双 bit 哈希登记缺乏版本库背书。建议：将生产 bit 复制入 data/bitstreams/（符合 .gitignore:29-31 自述政策）或在提交信息/预登记中更正记录并登记其 SHA256。",
    "evidence": "artifact: layout-variant-B bitstream + placement/timing evidence (force-added past *.bit ignore; production bit already tracked) ‖ 实测: git ls-files '*.bit' → 仅 build/board_zc706_seed2/w3_top_zc706_seed2.bit、data/bitstreams/ro_ratio_top.bit、data/bitstreams/w1_waived.bit；git check-ignore → .gitignore:85:build/board_zc706/ build/board_zc706/w3_top_zc706.bit",
    "function_context": "1760b72 变体 bitstream 工件提交（审查范围 HEAD）",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P2",
    "file": "data/d1_evidence/rootcause/1101_ROOTCAUSE_consensus.md",
    "line": 32,
    "category": "引用源错误（spec 内部数据一致性）",
    "description": "共识修复路径把跨板 HD 预测值 ≈32/64 归因于『仿真 dieC 预测』，但 EXPERIMENT_LOG E7 表中 dieC（C=A±10%/环）实测 HD=224/256（=56/64），并非 ≈32/64。≈128/256（每响应 32/64）的真实来源是 rtl_r1_order_reconstruction_v3.py 的 G3 段（独立随机频率×50 抽样，均值≈128，理论期望 128），而 G3 的运行输出未落盘入库。spec 头条预测数字引用了错误的实验，正确来源又无归档输出——预登记 P1 的『独立排序理论中位 127』与 G3/理论一致，但证据链在共识报告这一环断裂。",
    "evidence": "跨板 HD 回到 ≈32/64（仿真 dieC 预测） ‖ EXPERIMENT_LOG.md:52: | C = A ±10%/环 | 2673..3251 | 4806..5845 | dd987b0d7cb6e6ca | 224 | ‖ v3:96: print(f\"   G3 独立随机频率×50 次抽样:          HD 中位={hds3[25]}/256，min={hds3[0]}，max={hds3[-1]}（均值≈128）\")",
    "function_context": "共识报告 §修复路径 第 1 条（首选方案预测依据）",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P2",
    "file": "data/d1_evidence/rootcause/seed2_board_preregistration.md",
    "line": 11,
    "category": "预登记数值不可溯 / 失败分支不完备",
    "description": "P1 判据中阈值部分可溯（≥64 即 REJECT、≤24 即 PASS 溯源到服务器审计报告第 16 行 threshold.py:87-91 的 TAU_PASS=6/TAU_REJECT=16×4 轮），但核心预测带 90~170/256 在三份调查报告及全部 rootcause 文件中无任何推导或蒙特卡洛出处（grep 90/170 仅命中预登记自身）。且 256 个比较位由 16 环全序决定、位间强相关（同一环对跨种子重复出现），二项 σ=8 不适用，带宽需要『两个独立随机全序→HD 分布』的 MC 支撑（G3 仅 50 次抽样且输出未归档）。失败分支另有三处缺口：(a) HD∈25~63 的协议灰区无分支；(b) HD>170（REJECT 但超出预测带）无分支；(c) P3（seed2 自模板 auth2）FAIL 无任何预案——布局迁移破坏自一致性时无处置路径。另第 18 行『P1 REJECT 但 HD<64 边缘』自相矛盾（REJECT 判定本身要求 HD≥64）。",
    "evidence": "| P1 | seed2 板对 tid=1 模板（生产排序）跑 auth 1 | **REJECT**，total HD 落在 90~170/256（独立排序理论中位 127；≥64 即 REJECT） | 唯一性成立=根因修复实锤 | ‖ - P1 REJECT 但 HD<64 边缘：排序部分相关 → 记录数据，追加 seed3 变体 ‖ 审计报告:16: 门限：TAU_PASS=6/TAU_REJECT=16（每 64bit 响应），4 响应轮 PASS≤24、REJECT≥64（threshold.py:87-91）",
    "function_context": "预登记 §预登记判据 P1 行 与 §失败分支预案",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P2",
    "file": "build/tcl/build_w3_board_seed2.tcl",
    "line": 89,
    "category": "证据声称夸大（单向落位证据）",
    "description": "注释称 ring_sites_seed2.rpt 是『与生产 bit 对比的直接证据』，但对比的另一半不存在：生产脚本 build_w3_board.tcl 从不输出落位报告（以 write_bitstream 结束），build/board_zc706/ 整目录被 git 忽略，生产 32 环的历史站点无处可查。已入库证据只能证明 seed2 侧落位。本审查独立复核了 seed2 侧的真实性：Vivado 实测 xc7z045 CLOCKREGION_X1Y0 = SLICE_X90Y0..X163Y49，rpt 全部落点（X125~141, Y35~48）确在其内；但『对比』二字在版本库层面不成立。附带：脚本未 write_checkpoint，无 routed DCP 存档，落位事后无法从设计工件重验。建议：补一次生产流构建（或打开旧工程）导出 ring_sites.rpt 入库，形成双侧证据。",
    "evidence": "# SEED2 落位证据：32 环的物理站点（与生产 bit 对比的直接证据） ‖ 生产脚本尾部: write_bitstream -force $OD/w3_top_zc706.bit（无任何落位输出） ‖ 本审查实测: CRBOUND X1Y0 : SLICE_X90Y0 .. SLICE_X163Y49；rpt:18: u_top/u_ro_array/gen_ro_ring[0].u_ro_ring/n1_inferred_i_1 SLICE_X127Y39",
    "function_context": "构建脚本 write_bitstream 前的落位证据导出段",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P2",
    "file": "data/d1_evidence/rootcause/rtl_r1_order_reconstruction_v3.py",
    "line": 24,
    "category": "根因取证输入未入库（可复现性缺口）",
    "description": "根因链最强的定量证据（6400 比较位反推唯一 16 环全序零矛盾、正向复算 HD=0、在线三轮 HD=4/1/3 全预测命中）以 data/templates/templates.json 为唯一输入，但该文件处于未跟踪状态（git status: ?? data/templates/templates.json），脚本还硬编码本机绝对路径 D:\\puf-drone-auth。三路调查中 RTL 路既无报告 md 也无运行输出日志（服务器路有审计 md、仿真路有 EXPERIMENT_LOG.md），结论只存在于共识报告转述——fresh clone 无法复核。建议：入库 templates.json（或其 tid=1 副本+SHA256）并补跑 v3 存输出日志。",
    "evidence": "d = json.load(open(r\"D:\\puf-drone-auth\\data\\templates\\templates.json\", encoding=\"utf-8\")) ‖ git status --short: ?? data/templates/templates.json",
    "function_context": "RTL 路调查 v3 脚本 §反推全序（模板取证输入）",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P2",
    "file": "data/d1_evidence/rootcause/seed2_board_preregistration.md",
    "line": 22,
    "category": "引用证据文件未入库",
    "description": "预登记把 rootcause/build_seed2.log 列为证据文件，但该文件被 .gitignore:8（*.log）忽略、未提交（本审查已在磁盘核验其内容：BITSTREAM_SUCCESS WNS=1.213 SEED2_REGION=X1Y0、三阶段 DRC 0 Errors、LUTLP-1 waiver nets: 32，与已入库 timing.rpt 的 WNS=1.213/WHS=0.055 一致）。证据在本机落盘但未进版本库，同目录的 1101_假冒实验 log 当初是 force-add 入库的，此处标准不一致。建议 force-add 或将关键门禁行摘录为 md。",
    "evidence": "- 构建：rootcause/build_seed2.log、board_zc706_seed2/ring_sites_seed2.rpt ‖ git check-ignore: .gitignore:8:*.log\tdata/d1_evidence/rootcause/build_seed2.log ‖ 磁盘核验: BITSTREAM_SUCCESS WNS=1.213 SEED2_REGION=X1Y0",
    "function_context": "预登记 §证据文件",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P3",
    "file": "data/d1_evidence/rootcause/1101_ROOTCAUSE_consensus.md",
    "line": 32,
    "category": "spec 与实现机制偏差（已披露）",
    "description": "共识首选路径表述为『每块板用不同 placement seed 重 Implementation』『换 seed 重烧一块板』，实际实现是 PBlock 强制重定位（无 seed 变更）。目标等价（按板差异化布局使排序独立），且预登记与 a94775f 提交信息均如实描述了 PBlock 机制，无隐瞒；但 spec 文本未更新，且 PBlock 与改 seed 的『排序独立性』置信机理不同（区域强制 vs 随机扰动），预登记失败分支已诚实覆盖『PBlock 不足以致变』。属文档漂移而非不忠实。",
    "evidence": "每块板用不同 placement seed 重 Implementation ⇒ 各板排序独立 ‖ build_w3_board_seed2.tcl:71-73: create_pblock pb_rings_seed2 / add_cells_to_pblock pb_rings_seed2 $ringcells / set pbrange \"CLOCKREGION_$pick:CLOCKREGION_$pick\"",
    "function_context": "共识报告 §修复路径 1 与 build_w3_board_seed2.tcl §SEED2 差异化",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P3",
    "file": "data/d1_evidence/rootcause/sim/EXPERIMENT_LOG.md",
    "line": 75,
    "category": "引用数值与原始记录不符",
    "description": "仿真路裁决句称『与两板实测 HD≤1~2 定量吻合』，原始记录中两板实测为 HD=1（04F2C）与 HD=0（0195C），全仓库无任何『2』的出处；共识报告第 4/18 行与 c348baa 提交信息均正确写 HD=0/1（≤1）。EXPERIMENT_LOG 的『≤1~2』是无出处的放宽表述。",
    "evidence": "HD=0~3 —— 与两板实测 HD≤1~2、轮内漂移 1~4 bit 定量吻合 ‖ 1101_假冒实验log:3-4: 04F2C: auth 1 -> verdict PASS, total HD = 1 / 0195C: auth 1 -> verdict PASS, total HD = 0",
    "function_context": "仿真注入实验记录 §裁决 H2 段",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P3",
    "file": "data/d1_evidence/rootcause/1101_ROOTCAUSE_consensus.md",
    "line": 41,
    "category": "产物清单计数失准",
    "description": "产物清单称仿真路为『四 fixture+蒙特卡洛』，实际目录有 9 个 freq_*.mem 注入向量、5 颗 E7 芯片（A/B/C/M/M2）、9 个 run_* 隔离运行目录加系统级注入矩阵。为缩小方向的失准（不夸大结果），但作为三路调查的产物索引不准确。",
    "evidence": "- rootcause/sim/EXPERIMENT_LOG.md（仿真注入四 fixture+蒙特卡洛） ‖ EXPERIMENT_LOG.md:16: | freq_*.mem ×9 | 注入频率向量（确定性公式见下） |",
    "function_context": "共识报告 §产物清单",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P3",
    "file": "build/tcl/build_w3_board_seed2.tcl",
    "line": 10,
    "category": "『逐字复用』表述与字节级差异不符",
    "description": "头部声称『其余逐字复用生产流程』，git diff --no-index 显示功能等价但非逐字：srcdir 守卫、LUTLP-1 豁免块、时序门禁块由多行折叠为单行，生产脚本的 P0/P2 修复注释被删，ro_entropy.v 行缩进变化。文件清单、IP 配置、豁免逻辑、时序门禁逐项核对确实一致（同源/同约束/同豁免/同时序门禁的实质成立），『逐字』一词过强。",
    "evidence": "#   3) 其余逐字复用生产流程（同源/同约束/同豁免/同时序门禁） ‖ diff 例: -if {![file isdirectory \"$SRC/rtl\"]} {（生产，4 行块） vs +if {![file isdirectory \"$SRC/rtl\"]} { puts \"ERROR: …\"; exit 2 }（seed2，单行）",
    "function_context": "build_w3_board_seed2.tcl 头注 与 build_w3_board.tcl 全文 diff",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P3",
    "file": "build/board_zc706_seed2/ring_sites_seed2.rpt",
    "line": 2,
    "category": "报告格式缺陷（弱化证据力）",
    "description": "前 32 行（每个 gen_ro_ring[N].u_ro_ring 层次实例）SITE 字段为空（行尾悬空空格），实际携带坐标的是 160 行叶子单元；报告标题写 region X1Y0 但文件本身不含任何区域坐标信息，脱离器件网格知识无法自证。建议过滤到叶子单元并在头部附 CLOCKREGION 网格范围一行。",
    "evidence": "u_top/u_ro_array/gen_ro_ring[0].u_ro_ring （SITE 为空） vs :18 u_top/u_ro_array/gen_ro_ring[0].u_ro_ring/n1_inferred_i_1 SLICE_X127Y39",
    "function_context": "ring_sites_seed2.rpt 落位证据导出（foreach c $ringcells）",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P3",
    "file": ".gitignore",
    "line": 30,
    "category": "违反仓库自述工件政策 / 仓库卫生",
    "description": ".gitignore:29-31 自述政策为『Bitstreams: too large for git, but allow in data/bitstreams/』，seed2 却把 13.3MB bit force-add 进 build/（绕过忽略规则而非走豁免目录），与生产 bit 的处理形成不对称（见 P1 项）。同批提交还包含 xsim 二进制（xsimk.exe、.wdb、.sdb、xsim.dbg/reloc 等，合计约 8600 行插入多为二进制），有仓库膨胀风险；与『证据必须落盘』原则一致但与版本库最小化惯例冲突，建议 binaries 改放 data/bitstreams/ 与压缩包。",
    "evidence": "# Bitstreams: too large for git, but allow in data/bitstreams/\n*.bit\n!data/bitstreams/*.bit ‖ diff stat: build/board_zc706_seed2/w3_top_zc706_seed2.bit | Bin 0 -> 13321607 bytes",
    "function_context": ".gitignore 工件策略 与 1760b72 工件提交",
    "sources": [
      "ar-spec-r1"
    ]
  }
]
```

## 二、独立复验通过项（无 finding）

| 主张 | 复验结果 |
|---|---|
| terminal_fsm.v:168 为纯两两序比较 | ✓ `if (puf_freqs[{puf_nib_b,4'd0}+:16] > puf_freqs[{puf_nib_a,4'd0}+:16])` 逐对展开 ×8 |
| 32 环 = ro_array 16 + ro_entropy 16 | ✓ ring_sites 层级 u_top/u_ro_array 与 u_top/u_ro_entropy_array 各 16 环；waiver nets=32 |
| WNS=+1.213ns / DRC 0 错 | ✓ timing.rpt WNS=1.213 WHS=0.055；日志三阶段 DRC 0 Errors |
| SHA256 两 bit 不同 | ✓ 生产 24ED4EED…、seed2 0F4E605D…（本机实测）；git blob=磁盘文件 |
| 落位真实在 X1Y0 | ✓ Vivado 实测 CLOCKREGION_X1Y0=SLICE_X90Y0..X163Y49 ⊇ 全部落点 X125~141/Y35~48 |
| pick 逻辑选中 X1Y0 | ✓ 14 区域 lsort 后 index 7 = X1Y0，与日志一致 |
| a94775f 提交信息各项（pblock 迁移/WNS/DRC/ring_sites/预登记 90~170） | ✓ 与工件逐项相符，无夸大 |

## 三、论文『主张-证据缺口』表（审查问题 4）

| 主张 | 已有证据 | 缺口 |
|---|---|---|
| C1 指纹=bitstream(布局布线)的函数，非硅片的函数 | 同 bit 双板 HD=0/1；模板反推唯一全序；MC ±1%→HD 0~3 | ①环频直读未做（EXPERIMENT_LOG.md:77 自认『闭环缺口：需板端直接回读 16 个 ring_freq 计数值』）；②仅 1 对板、1 个 bitstream 样本；③无第三方 bitstream 对照 |
| C2 布局差异化→排序独立→跨板 HD≈32/64（90~170） | seed2 变体构建+落位证据+时序门禁；X1Y0 网格独立复核通过 | ①板端 P1/P3 数据未采（烧板未做）；②两个独立全序 HD 分布无 MC 归档；③共识预测值引用错源（dieC 实为 224/256） |
| C3 跨板有效熵≈1bit（{7,9} 抛硬币） | 三轮在线翻转位全属近平局对 {7,9} | 样本仅 3 轮；MC 显示相对间距<2% 的环对有 4/256（EXPERIMENT_LOG.md:71）→理论近平局对不止一对，熵上界需系统量化（1~4bit），『≈1bit』精度不足 |
| C4 对称性：生产 bit 板对 tid=2 模板 REJECT（P4） | 无 | prereg:14 自标『可选』且未做；缺 P4 则 REJECT 方向仅单边验证（seed2→旧模板），不能排除 tid 相关服务器侧因素（审计已排除主要 bug 但对称实验是廉价加固） |
| C5 SHA256 不同⇒布局真实差异⇒指纹不同 | 双哈希实测不同（24ED… vs 0F4E…）；git blob 与磁盘一致 | ①生产 bit 未入库（P1 项）→对照不可复现；②bit 不同→排序不同→响应不同的因果链完全依赖未做的 P1 |
| C6 WNS=+1.213ns / DRC 0 错 / 32 环落位 X1Y0 | timing.rpt WNS=1.213 WHS=0.055；三阶段 DRC 0 Errors；X1Y0=SLICE_X90Y0..X163Y49⊇全部落点 | 无缺口（本审查独立复核通过）；仅 build_seed2.log 未入库（P2 项） |
| C7 论文安全主张（板上密钥/spoof/XOR 口径） | 共识附带发现 P2×3 已如实记录 | 论文文本尚未改写（共识:27 已列『16 环 XOR 阵列/双阈值 6/16』口径与 RTL 不符）；超出本审查范围但写论文前必须完成 |

## 四、根因报告数据一致性核对（审查问题 5）

| 关键数字 | 原始出处 | 引用一致性 |
|---|---|---|
| 在线三轮 HD=4/1/3 | 审计:15（离线重算=RESULT 帧 0x04/0x01/0x03） | 共识:17 ✓ 一致 |
| 跨板实测 HD | 假冒实验 log:3-4 → HD=1 / HD=0 | 共识:4『HD=0/1』✓、c348baa ✓；EXPERIMENT_LOG:75『HD≤1~2』✗（2 无出处，见 P3） |
| 对间距中位 29.5% | EXPERIMENT_LOG:71（min 1.16%，p25 17.9%，p75 44.5%，<2% 4/256） | 共识:19 ✓ 一致（同一来源两处引用相符） |
| ±1%→HD 0~3 | EXPERIMENT_LOG:70（MC 1%: mean 0.2 max 3）+:62（系统级 ±1%→1） | 共识:18 ✓ 一致 |
| ±5%→mean 4.5 | EXPERIMENT_LOG:70 | 共识:18 ✓ 一致 |
| 6400 比较位 / 100 CRP | 审计:18（模板 100 响应两两 HD 均值 32.00）+ v3 断言复算 HD=0 | 共识:16 ✓ 算术一致（100×64=6400） |
| log2(16!)≈44bit | 数学事实 44.25 | 共识:20 ✓ |
| dieC 与 ≈32/64 | EXPERIMENT_LOG:52 dieC=224/256；v3:96 G3 均值≈128（输出未归档） | 共识:32 ✗ 张冠李戴（见 P2） |
| E7 ±5%→80/256 vs MC 5%→4.5 | 不同基向量展开（E7 近简并 1x vs 系统级 2.85x） | EXPERIMENT_LOG:74 已注明但表述晦涩——非数值矛盾，建议在文中显式给出两列适用条件 |

## 五、结论段

**总裁决：根因共识的核心机理与实现忠实、无 P0；修复实现目标忠实但在机制与证据完备性上有 1×P1 + 5×P2 需在烧板实验前处置。**

1. **机制忠实性（问题 1）**：共识『布局差异化→排序独立』与 build_w3_board_seed2.tcl 实际所为（PBlock 强制 32 环入 CLOCKREGION_X1Y0）在目标上一致，且落位、时序、DRC、豁免 32 网、SHA256 全部独立复验通过；a94775f 提交信息无夸大。三处表述失真：共识写『不同 placement seed』而实现是 PBlock（P3，预登记已如实披露）；脚本『与生产 bit 对比的直接证据』实为单侧证据（P2）；『其余逐字复用』非逐字（P3）。**1760b72 提交信息『production bit already tracked』为事实性错误（P1）**——生产 bit 从未入库，跨 bit 对照在版本库层面不可复现。
2. **预登记可溯性（问题 2）**：判据可证伪（REJECT/PASS 双向+失败分支），阈值（≥64/≤24）可溯至 threshold.py:87-91 经服务器审计报告背书；但 **90~170/256 预测带无任何可溯推导**（三份调查报告无此数、无独立排序 HD 分布 MC、256 位比较位强相关使二项带宽不适用），且失败分支缺 HD 25~63 灰区、HD>170、P3 FAIL 三条预案，『P1 REJECT 但 HD<64 边缘』自相矛盾（P2）。
3. **范围蔓延/声称未做（问题 3）**：未发现把未做的事写成已做——板端实验在预登记中明确标注『届时生成』，P4 明确标可选未做，环频直读缺口在 EXPERIMENT_LOG:77 自认。真正的缺口是版本库证据完备性：生产 bit、templates.json（根因取证唯一输入）、build_seed2.log、生产侧落位报告四件关键工件均未入库（P1+P2×3）；另提交了 xsim 二进制与 13.3MB bit 绕过 .gitignore 自述政策（P3）。
4. **论文可用性（问题 4）**：见上表 C1~C7。最硬的缺口：环频直读（机理主张的最后一环）、板端 P1/P3/P4 数据（修复主张的全部实验支撑）、独立排序 HD 分布 MC（90~170 带的统计依据）、熵塌缩『≈1bit』的系统量化（近平局对观测上限 4 对 vs 实测翻转仅 {7,9} 一对）。共识+变体+预登记三件套已具备『诚实负结果+干预实验设计』的论文骨架，但今日尚不能把 C2 写成结论，只能写成预登记假设。
5. **数据一致性（问题 5）**：三路调查的关键数字在引用处总体一致（4/1/3、29.5%、±1%→0~3、±5%→4.5、6400 位、44bit 均相符）；两处不符：共识:32 把 ≈32/64 归于『仿真 dieC』而 dieC 实测 224/256（真源是 v3 G3 且输出未归档，P2）；EXPERIMENT_LOG:75『实测 HD≤1~2』较原始记录 0/1 无出处放宽（P3）。

**烧板前最小整改建议（按优先级）**：① 生产 bit 复制入 data/bitstreams/ 并在预登记补登哈希（或更正 1760b72 记录）；② 补生产侧 ring_sites 报告入库，形成双侧落位对照；③ 补『双独立全序→HD 分布』MC（含位相关性）为 90~170 带立靶，并补 P3 FAIL/灰区分支；④ 入库 templates.json 与 v3 运行输出、build_seed2.log 关键行；⑤ 共识:32 更正引用源（G3/理论期望，非 dieC）。
