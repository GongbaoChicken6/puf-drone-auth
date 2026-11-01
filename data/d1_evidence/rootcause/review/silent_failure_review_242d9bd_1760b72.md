# 静默失败/假绿灯审查 · 242d9bd..1760b72（ar-silent-r1）

生成：2026-11-01 | 仓库只读，产物仅写入本目录

## 结论（ar-silent-r1 · 静默失败/假绿灯猎捕 · 242d9bd..1760b72）

总体判断：本区间的工程文化明显高于仓库历史水位——预登记判据、v3 的正向 assert、TB 的 DONE/FAIL 双哨兵+看门狗、INJECT_FREQS 注入回显、矩阵日志逐 run 记录 exit=0、E6 挂死按『超时不算数』收证，都是 w2_waiver 教训的正确延续。但按同一标准复检，仍猎得 5×P1 / 4×P2 / 7×P3：

P1 五条中，两条是【已实际发生】的假证据/假陈述：
1) ring_sites_seed2.rpt 实测 32/192 行 SITE 为空——『报告存在但无信息』模式已然落地，且脚本对空站点、区域归属零断言；
2) 1760b72 提交信息宣称 production bit already tracked，实测 build/board_zc706 在 git 全历史为空——唯一性实验的基线 bit 只存在于本地，证据链在仓库层面断裂。
另三条是【下一次就会咬人】的门禁绕过：
3) exit-6 门禁按 cell 数（阈值 32 ≈ 实际 192 的 1/6）而非环数计数，部分环漏迁的坏 bit 可绿灯出厂直达烧板；
4) v3 分析脚本 F 段存在空集合假绿灯（0 帧解析 ⇒『CRC 全过』+退出码 0），而它注定被复跑于烧板后的 seed2 日志；
5) 预登记 P1 成功带 90~170 与『环振搬死 ⇒ R1≡0 ⇒ 对均衡模板 HD≈128』不可区分（本仓库 E7 自己的数据：恒 0 响应对真响应 HD=124 落在带内），且 P2/P3 对恒定响应同样全 PASS——不补『模板两两 HD≈32』对照项与 P3/P4/超时/HD>170 失败分支，烧板可能把坏修复错判为『根因修复实锤』。

对本次已交付产物的影响边界（诚实声明）：本次构建本身是健康的——日志实测 waiver nets=32、ring cells=192、区域 X1Y0、终态 WNS=+1.213/WHS=+0.055/DRC 0 Errors、rings 落位聚簇 X125-141/Y34-51 与 X1Y0 相容；上述 P1 中仅 #1（证据降级）、#2（基线缺失）已在现产物上发生，#3-#5 为门禁与流程缺口，尚未造成错误结论，但都会在烧板对账这一最昂贵的环节才暴露（或永不暴露）。

修复优先级建议（最小改动）：
A. build_w3_board_seed2.tcl：环级断言（32 个不同 gen_ro_ring 索引、两数组各 16）+ route 后断言每环 SITE 非空且 CLOCK_REGION==X1Y0 + WHS 门禁；
B. 立即 force-add 生产 bit（如 seed2 bit 同法）与 build_seed2.log，修正 1760b72 的错误陈述（追加 commit 说明）；
C. v3 脚本加 assert len(chal)>0、len(chal)==len(r1f)，并以正向哨兵行（如 V3_VERIFY_OK n=3）收尾；
D. 预登记补对账项『seed2 自模板两两 HD≈32（排除恒定响应）』与失败分支（P3 FAIL / P4 不符 / HD>170 / auth 超时），并明确各分支的下一步动作；
E. EXPERIMENT_LOG.md 的 5200/1450 混写与 w2_waiver.xdc 双 CRITICAL WARNING 的驯化风险登记为已知项。

## Findings JSON

```json
[
  {
    "severity": "P1",
    "file": "build/tcl/build_w3_board_seed2.tcl",
    "line": 66,
    "category": "gate-too-loose / partial-match-bypass",
    "description": "exit-6 门禁按【单元数】而非【环数】计数：阈值 32 是 LEAF LUT 数量级（实际匹配 192=32 个层次实例+160 个叶子），仅为实际值的 1/6。若 filter 因层次改名/综合优化退化成只匹配到某个子集（例如仅 ro_entropy 的 96 个 cell，或 7 个环的全部 cell=42 个），门禁照样通过，脚本继续 add_cells_to_pblock 只搬迁部分环，随后照常打印 BITSTREAM_SUCCESS——『部分重定位的坏 bit』拿到绿灯直达烧板。正确门禁应断言 32 个不同的 gen_ro_ring[N] 索引全覆盖（ro_array 16 + ro_entropy 16）。",
    "evidence": "if {[llength $ringcells] < 32} { puts \"ERROR: SEED2 ring cell match too few: [llength $ringcells]\"; exit 6 }  ← 实测日志：SEED2 ring cells: 192 (32 rings x ~5 LUT = ~160)",
    "function_context": "SEED2 差异化：环振单元 PBlock 重定位（第 63-78 行）；实际构建日志 build_seed2.log 第 1637 行打印 192",
    "sources": [
      "ar-silent-r1"
    ]
  },
  {
    "severity": "P1",
    "file": "build/tcl/build_w3_board_seed2.tcl",
    "line": 92,
    "category": "degraded-evidence / report-exists-but-informless",
    "description": "『落位证据』rpt 对 32 个环层次单元的 get_property SITE 返回空串：实测 ring_sites_seed2.rpt 192 行中恰有 32 行（全部 gen_ro_ring[N].u_ro_ring 实例行）SITE 字段为空、仅有尾随空格。这正是用户问的『报告存在但无信息』模式——已经实际发生，不是假设。脚本对空 SITE、对『站点是否落在 $pick 区域』没有任何断言；若未来某次构建 ringcells 未落位，rpt 会整份空白仍照常写出、bitstream 照常生成。表头 \"(region X1Y0)\" 只是对 $pick 意图的回显，不是对实测落位的陈述。",
    "evidence": "foreach c $ringcells { puts $rf \"$c [get_property SITE $c]\" }  ← rpt 实测第2行（JSON原样）：\"u_top/u_ro_array/gen_ro_ring[0].u_ro_ring \"（行尾一个空格，SITE 为空）；192 行中 32 行空 SITE、160 行 SLICE_X125..141/Y34..51",
    "function_context": "SEED2 落位证据生成（第 89-93 行），文件头注释自称『32 环的物理站点（与生产 bit 对比的直接证据）』",
    "sources": [
      "ar-silent-r1"
    ]
  },
  {
    "severity": "P1",
    "file": "build/board_zc706/w3_top_zc706.bit",
    "line": 0,
    "category": "provenance / missing-baseline-artifact",
    "description": "commit 1760b72 的提交信息声称 \"production bit already tracked\"，但 git ls-files / git log --all 证明 build/board_zc706 下从未有任何文件入库——生产 bit（SHA256 24ED4EED…8173，仅存在于本地工作树）不在仓库里。后果：seed2 bit 已入库而它必须与之对比的生产基线没有入库，全新 clone 无法复核『两 bit 布局不同』的核心前提，跨配置唯一性实验的基线证据链断裂；提交信息本身构成一条假陈述（provenance 层面的假绿灯）。",
    "evidence": "1760b72 artifact: layout-variant-B bitstream + placement/timing evidence (force-added past *.bit ignore; production bit already tracked)  ← 实测：git log --all --oneline -- build/board_zc706 输出为空；git ls-files '*.bit' 仅含 seed2 bit 与 data/bitstreams/ 下 W1 时代两枚",
    "function_context": "仓库产物入库策略：seed2 bit 已 force-add 越过 ignore，生产 bit 未同样处理",
    "sources": [
      "ar-silent-r1"
    ]
  },
  {
    "severity": "P1",
    "file": "data/d1_evidence/rootcause/rtl_r1_order_reconstruction_v3.py",
    "line": 60,
    "category": "vacuous-pass / empty-set-green",
    "description": "F 段（在线验证，根因链『在线三轮 HD=4/1/3 全命中』的证据来源）存在空集合假绿灯：正则匹配 0 帧或所有帧解析抛异常时，chal/r1f/resf 均为空列表，脚本照常打印『F1. 官方解帧: CHALLENGE=0 RESPONSE_R1=0 RESULT=0（CRC 全过）』——0 帧『全过』是空洞真；F2 的 zip 循环静默迭代 0 次，脚本以退出码 0 结束。except Exception: continue 还会吞掉全部 CRC 失败。该脚本注定要在烧板后对新的 1101_seed2 日志复跑：一旦新日志格式变化（时间戳/RAW 排版差异）导致 0 匹配，复跑会『成功』地什么都不验证。缺少 assert len(chal)>0 与 len(chal)==len(r1f) 正向哨兵。",
    "evidence": "frames = re.findall(r\"\\[(?:WIRE [0-9:.]+)\\] (?:TX|RX)RAW ([0-9a-f]+)\", log) … try: mid, f = HFIDAProtocol.parse(bytes.fromhex(hx)) except Exception: continue … print(f\"F1. 官方解帧: CHALLENGE={len(chal)} RESPONSE_R1={len(r1f)} RESULT={len(resf)}（CRC 全过）\")",
    "function_context": "v3 脚本 F 段（第 50-62 行）；同脚本第 46-48 行对反推全序已有正向 assert（好文化），但 F 段没有",
    "sources": [
      "ar-silent-r1"
    ]
  },
  {
    "severity": "P1",
    "file": "data/d1_evidence/rootcause/seed2_board_preregistration.md",
    "line": 11,
    "category": "confounded-acceptance / failure-branch-blindspot",
    "description": "P1 成功判据（REJECT 且 HD 90~170 ⇒『唯一性成立=根因修复实锤』）无法区分『独立环排序』与『退化恒定响应』：本仓库自己的 E7 证据证明全等频/死环阵列 R1≡0（chipM R1=0000000000000000），而 tid=1 模板 ones 占比≈0.5，恒 0 响应对模板的 HD≈128±少量——正落在 90~170 预登记带内且≥64 判 REJECT；更糟的是 P2/P3 也拦不住它（setkey/enroll 存下的就是恒 0 模板，auth 对自模板 HD=0 ≤24 照样 PASS）。即：一块环振被搬死的 seed2 板会四项全绿被判『修复实锤』。已知鉴别器（服务器审计用过的『模板两两 HD≈32 ⇒ 计数有真实非平凡展开』）未写入对账清单。失败分支同样不完整：只覆盖 P1-PASS、P1-REJECT-但-HD<64、WNS<0；未覆盖 P2 enroll 失败、P3 自认证 FAIL（HD>24）、P4 对称性不符、HD>170（响应偏置/退化）、auth 超时/无 RESULT 帧（w2_waiver 文化：超时不算数，但预案没写）。",
    "evidence": "| P1 | seed2 板对 tid=1 模板（生产排序）跑 auth 1 | **REJECT**，total HD 落在 90~170/256（独立排序理论中位 127；≥64 即 REJECT） | 唯一性成立=根因修复实锤 |  ← 对照本仓库 sim/EXPERIMENT_LOG.md E7 实测：| M 全等频 | 3000 | 全 5209 | 0000000000000000 | 124 |（恒 0 响应对真响应 HD=124，落在 90~170 带内）",
    "function_context": "预登记判据表（第 9-14 行）与失败分支预案（第 16-19 行），烧板验收的对账依据",
    "sources": [
      "ar-silent-r1"
    ]
  },
  {
    "severity": "P2",
    "file": "build/tcl/build_w3_board_seed2.tcl",
    "line": 91,
    "category": "verification-gap / no-post-route-assertion",
    "description": "布局门禁只有『约束命令是否报错』，没有『结果是否生效』：route_design 之后没有任何断言检查 32 环实测站点位于 CLOCKREGION_$pick（可用 get_property CLOCK_REGION 或站点坐标断言），也没有与生产 bit 落位的差异对照（生产侧落位证据在仓库中根本不存在，build/board_zc706 为空）。本次运行靠 Vivado 对 pblock 的硬约束兜底（叶子站点聚簇 X125-141/Y34-51 与 X1Y0 相容），但『不同区域 ⇒ 不同环序 ⇒ 指纹可区分』这一修复核心前提在构建层零验证，唯一验收是烧板实验；若 pblock 因某种原因未生效（如 resize_pblock 只告警不报错的边界），脚本仍会 BITSTREAM_SUCCESS。",
    "evidence": "# SEED2 落位证据：32 环的物理站点（与生产 bit 对比的直接证据）\nset rf [open $OD/ring_sites_seed2.rpt w]\nputs $rf \"# seed2 ring cell placement (region $pick)\"  ← 表头只是回显意图 $pick，全脚本无任何 get_property CLOCK_REGION / 区域归属断言",
    "function_context": "SEED2 落位证据生成与区域选择（第 63-93 行）",
    "sources": [
      "ar-silent-r1"
    ]
  },
  {
    "severity": "P2",
    "file": "data/d1_evidence/rootcause/seed2_board_preregistration.md",
    "line": 22,
    "category": "evidence-availability / ignored-evidence",
    "description": "预登记把 rootcause/build_seed2.log 列为证据文件，但 .gitignore 第 8 行 *.log 使其永不被常规提交（git check-ignore 实证命中）。该日志承载全部承重哨兵打印（waiver nets: 32、ring cells: 192、relocate region: X1Y0、DRC 0 Errors、BITSTREAM_SUCCESS WNS=1.213）——关键证据只存在于本地磁盘，仓库里已提交的 timing.rpt/utilization.rpt 不含这些哨兵。若不 force-add（如 seed2 bit 那样），烧板后对账时证据链是断的。",
    "evidence": "- 构建：rootcause/build_seed2.log、board_zc706_seed2/ring_sites_seed2.rpt  ← 实测：git check-ignore -v → .gitignore:8:*.log    data/d1_evidence/rootcause/build_seed2.log；git ls-files 无此文件",
    "function_context": "预登记『证据文件』清单（第 21-23 行）",
    "sources": [
      "ar-silent-r1"
    ]
  },
  {
    "severity": "P2",
    "file": "data/d1_evidence/rootcause/rtl_r1_order_reconstruction_v3.py",
    "line": 62,
    "category": "silent-truncation",
    "description": "zip(chal, r1f) 静默截断：若日志中 RESPONSE_R1 帧少于 CHALLENGE 帧（串口丢帧/超时中止在 1101 日志里真实发生过），多出的挑战轮静默不验证、无任何计数告警；配合上一条的 except-continue，被验证轮数可以无声缩水。resf[i] 不存在时打 \"?\" 尚可见，但轮数不匹配本身应 fail-loud。",
    "evidence": "for i, (seeds, r1s) in enumerate(zip(chal, r1f)):",
    "function_context": "v3 F2 在线验证循环（第 62-75 行）",
    "sources": [
      "ar-silent-r1"
    ]
  },
  {
    "severity": "P2",
    "file": "build/tcl/build_w3_board_seed2.tcl",
    "line": 86,
    "category": "latent-gate-gap / hold-not-gated",
    "description": "时序门禁只查 max-delay（setup/WNS），不查 hold：本次构建日志中间态实测出现过 WHS=-0.270 / THS=-326.550（Phase 2.3，后被 Post Hold Fix 修到 +0.055）——说明该设计 hold 违例是真实近失事件而非理论。对一个以『环频计数精确比较』为全部输出的设计，终态 WHS<0 的捕获路径意味着板上静默错指纹，而脚本会照打 BITSTREAM_SUCCESS。建议同时取 -delay_type min 的 SLACK 做门禁（本次终态 timing.rpt WHS=0.055 合格，属门禁缺口而非现实事故）。",
    "evidence": "set wns [get_property SLACK [get_timing_paths -delay_type max]]\nif {$wns < 0} { puts \"TIMING_FAILED WNS=$wns\"; exit 4 }  ← build_seed2.log 第2155行实测：INFO: [Route 35-416] Intermediate Timing Summary | WNS=2.204 | TNS=0.000 | WHS=-0.270 | THS=-326.550|",
    "function_context": "时序门禁（第 84-87 行），继承自 build_w3_board.tcl 的 P2 修复",
    "sources": [
      "ar-silent-r1"
    ]
  },
  {
    "severity": "P3",
    "file": "data/d1_evidence/rootcause/rtl_r1_order_reconstruction.py",
    "line": 79,
    "category": "print-not-assert (superseded)",
    "description": "v1 脚本把方向矛盾对数只打印不断言：矛盾非零时仍会给出一个『全序』并继续 D 段，结论靠人眼读 HD。第 69 行行内注释还留有作者写票方向时的困惑（『(a>b 时 a 是大号？注意) —— 见下修正』）。已被 v3 的 assert（胜场严格递减 + 复算 HD=0）修复，但 v1 仍以『证据』身份留仓，复跑者若拿错版本无自校验保护。",
    "evidence": "print(f\"   矛盾对数（同对两方向都有票）：{contradictions}，矛盾票占比：{mismatch_votes/total_votes:.5f}\")  ← 无 assert；对照 v3 第46行 assert all(wins[order[i]] > wins[order[i + 1]] for i in range(15)), \"胜场非严格递减：计票方向错！\"",
    "function_context": "v1 B 段比较观测统计（第 53-79 行）",
    "sources": [
      "ar-silent-r1"
    ]
  },
  {
    "severity": "P3",
    "file": "data/d1_evidence/rootcause/analyze_template2.py",
    "line": 15,
    "category": "silent-truncation / width-assumption",
    "description": "hd() 用 zip 静默截断、bits() 固定 n=64：若模板条目是短十六进制串/整数（数据损坏或格式变更），逐位展开高位全 0、两两 HD 只按对齐部分计算——短数据会被读成『低 HD/恒 0 位』而非报错，正是『空数据均值=0 被当成证据』的变体。当前真实数据是 64bit hex 故未触发，属遗留凶险；tid 缺失的 KeyError 与空列表除零则会响亮失败（好）。",
    "evidence": "def hd(a, b):\n    return sum(1 for x, y in zip(a, b) if x != y)  ← zip 截断；def bits(x, n=64) 固定位宽无长度校验",
    "function_context": "模板取证 v2 两两 HD 统计（第 14-15、30-34 行）",
    "sources": [
      "ar-silent-r1"
    ]
  },
  {
    "severity": "P3",
    "file": "data/d1_evidence/rootcause/sim/EXPERIMENT_LOG.md",
    "line": 22,
    "category": "doc-data-mismatch",
    "description": "实验记录声称注入 fixture 『matched: 全 5200；matched_wiggle: 5200±1』，但入库的实际 RTL fixture 是 1450/1450±1（freq_matched.mem、freq_matched_wiggle.mem，run_matched 日志 INJECT_FREQS 16×1450 实证）。5200 是 mc_hd_curve.py（Python 蒙特卡洛）用的值，两者被混写。结论侥幸不受影响（全等频⇒R1≡0 具尺度不变性），但按记录复现 INJECT_FREQS 必然对不上，削弱证据可复现性。",
    "evidence": "common105: f*1.05；matched: 全 5200；matched_wiggle: 5200±1。  ← freq_matched.mem 实际第2行起 16×\"1450\"；run_matched/xsim.log：INJECT_FREQS 1450 1450 … 1450",
    "function_context": "EXPERIMENT_LOG.md fixture 公式段（第 21-22 行）",
    "sources": [
      "ar-silent-r1"
    ]
  },
  {
    "severity": "P3",
    "file": "src/rtl/w2_array/w2_waiver.xdc",
    "line": 10,
    "category": "legacy-landmine (known, mitigated in script)",
    "description": "w2_waiver 教训的源头 XDC 仍带原静默模式且被 seed2 脚本继续加载：本次构建日志中它两次实弹命中已知模式（综合前/实现前 XDC 解析各一次 WARNING 12-1023 No nets matched + CRITICAL WARNING 17-55 set_property expects at least one object）。靠脚本综合后重应用+32 网校验兜底，属已文档化的已知项；但『每次构建都出现 2 条 CRITICAL WARNING』会驯化读者，若未来有人按『清零 CRITICAL WARNING』整改而误删脚本内豁免，32 个 LUTLP-1 将回到 bitstream DRC 才炸（或更糟：在只跑 synth 的 dev 流里全程静默）。",
    "evidence": "set_property ALLOW_COMBINATORIAL_LOOPS TRUE [get_nets -hierarchical -filter {NAME =~ \"*gen_ro_ring*/u_ro_ring/n1\"}]  ← build_seed2.log 第298行：WARNING: [Vivado 12-1023] No nets matched for command 'get_nets -hierarchical -filter {NAME =~ \"*gen_ro_ring*/u_ro_ring/n1\"}'.（第1613行重复）",
    "function_context": "XDC 第 2-6 行头注释已自证此坑并由 build_w3_board*.tcl 兜底",
    "sources": [
      "ar-silent-r1"
    ]
  },
  {
    "severity": "P3",
    "file": "build/tcl/build_w3_board_seed2.tcl",
    "line": 60,
    "category": "gate-threshold-mismatch",
    "description": "exit-5 门禁用 ==0 而非 !=32：注释明说 expect 32，但 1..31 个部分匹配同样通过（例如层次名部分变化后只匹配到个别环）。后果被下游 write_bitstream 的 LUTLP-1 DRC 兜住（响亮失败），故降为 P3；但既然 puts 已宣称期望值，断言就应与期望一致——这是 w2_waiver 文化『响亮校验数量』的不彻底执行（生产脚本同款）。",
    "evidence": "puts \"LUTLP-1 waiver nets: [llength $loopnets] (expect 32 = ro_array 16 + ro_entropy 16)\"\nif {[llength $loopnets] == 0} { puts \"ERROR: LUTLP-1 waiver matched ZERO nets -- ring waiver broken\"; exit 5 }",
    "function_context": "LUTLP-1 豁免应用（第 57-61 行）；实测日志 1632 行：LUTLP-1 waiver nets: 32",
    "sources": [
      "ar-silent-r1"
    ]
  },
  {
    "severity": "P3",
    "file": "build/tcl/build_w3_board_seed2.tcl",
    "line": 69,
    "category": "untested-empty-path",
    "description": "get_clock_regions 为空列表时（如器件未正确打开的异常路径），lindex 返回空串 → pick=\"\" → pbrange=\"CLOCKREGION_:CLOCKREGION_\"，正确性完全依赖 resize_pblock 对非法区域名报错来触发 exit 7；若该版本只告警不报错，pblock 静默为空、布局不受约束、脚本照常 BITSTREAM_SUCCESS。本次实测 14 个区域（X0Y0..X0Y6/X1Y0..X1Y6）中位取到 X1Y0 正常，但空列表分支从未被测试且无前置 [llength $allcr] > 0 守卫；另外 pick 也未断言与生产 bit 环簇区域不同（后者无证据可查，见 build/board_zc706 空仓）。",
    "evidence": "set allcr [lsort [get_clock_regions]]\nputs \"SEED2 clock regions available: $allcr\"\nset pick [lindex $allcr [expr {[llength $allcr] / 2}]]",
    "function_context": "SEED2 区域选择（第 67-78 行）；实测日志 1641 行打印 14 区域、1644 行 pick=X1Y0",
    "sources": [
      "ar-silent-r1"
    ]
  },
  {
    "severity": "P3",
    "file": "data/d1_evidence/rootcause/sim/tb_puf_path_inject.v",
    "line": 146,
    "category": "error-then-continue-then-success-sentinel",
    "description": "R1 帧超时分支只打印 \"[T] ERROR: R1 frame timeout\" 后继续执行，最终仍会打印 INJECT_R1（可能含陈旧 tx_captured 内容）与成功哨兵 TB_PUF_INJECT_DONE。当前被 2ms 全局看门狗（打印 TB_PUF_INJECT_FAIL）的时序净兜住（300k 拍 guard≈3ms 晚于看门狗触发），真挂死场景 FAIL 会先赢；但『错误打印→继续→成功哨兵』的结构使正确性依赖两个 initial 的时长配平，属脆弱模式——超时分支应直接 $fatal/打印 FAIL 哨兵终止。",
    "evidence": "if (guard >= 300000)\n    $display(\"[T] ERROR: R1 frame timeout (%0d bytes)\", nbytes);  ← 无 $finish；后续第184行仍打印 $display(\"TB_PUF_INJECT_DONE\"); 看门狗 #2_000_000 打印 TB_PUF_INJECT_FAIL",
    "function_context": "wait_r1_frame 任务（第 138-149 行）与全局看门狗（第 188-192 行）",
    "sources": [
      "ar-silent-r1"
    ]
  }
]
```
