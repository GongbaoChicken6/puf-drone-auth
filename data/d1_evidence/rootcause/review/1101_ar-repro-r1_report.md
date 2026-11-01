# 可复现性/证据链审查报告 — ar-repro-r1（2026-11-01 17:55）

范围：git 242d9bd..1760b72（c348baa → 062c776 → a94775f → 1760b72，4 提交 184 文件 +8648 行，源码零改动属实）。
方法：全部结论基于本机实测重跑/重算，产物存 review/rerun_*.log；完整 findings JSON 见 1101_ar-repro-r1_findings.json。

## 一、实测复现结果（抽查 + 加验）

| 项 | 报告主张 | 本机重跑 | 判定 |
|---|---|---|---|
| 模板两两 HD 均值（tid=1, 100 CRP） | 32.00（19~48）〔服务器审计:18〕 | analyze_template2.py → 均值 32.0、min 19、max 48、中位 32 | ✅ 逐位一致 |
| 16 环全序反推 | [4,11,15,13,2,10,1,3,9,7,14,6,5,12,8,0]，零矛盾，复算 HD=0〔consensus:16〕 | v3 重跑：全序一致；矛盾 0/120；100 CRP 总 HD=0；胜场严格 15..0 | ✅ 逐位一致 |
| 在线三轮 HD | 4/1/3，翻转位全属 {7,9}〔consensus:17〕 | v3 重跑：[0,1,1,2]/[0,0,1,0]/[1,0,2,0]=4/1/3，翻转对全 (7,9)；与 1101 日志 RESULT 帧 hd=04/01/03 三方对账 | ✅ |
| 蒙特卡洛 k=1% | mean 0.2 max 3（300 次）〔EXPLOG:70〕 | mc_hd_curve.py 重跑：9 个 k 点+共模+间距分位数**全部逐字符一致**（random.Random(20261101) 每 k 点重播种） | ✅ 确定性满分 |
| 加验：6400 比较位/120 对 | consensus:16 | v1 重跑 B 节：6400 次、120/120 覆盖、1 比例 0.4873、矛盾 0 | ✅ |
| 加验：E5 iverilog 交叉复核 | 与 xsim 一致（计数全 0）〔EXPLOG:41-42〕 | 照命令重组重跑 iverilog 14.0 + vvp：16 环全 0、R1 恒 0，与 e5_raw.log 逐行一致 | ✅（但原包未存 vvp 输出，见 F14） |
| 加验：E7 表 vs e7_raw.log | counts/R1/HD=80,224,124,0 | 逐项核对全部一致；实测 vs 解析计数差 ≤1 属实 | ✅ |
| 加验：审计行级引用 | threshold.py:87-91 / main.py:236-258 / template_db.py:354-362 | 三处全命中；respond() 的 impostor 形参确实未用（spoof 空操作成立） | ✅ |
| 加验：构建主张 | WNS +1.213ns、X1Y0、DRC clean | timing.rpt WNS=1.213；ring_sites_seed2.rpt 头部 region X1Y0 + 32×SLICE 落位；build_seed2.log（本机）DRC 0 Errors + BITSTREAM_SUCCESS WNS=1.213 X1Y0 | ✅（但 build_seed2.log 未入库，见 F4） |
| 加验：黄金锚 | base R1=tb_puf_path 黄金〔EXPLOG:59〕 | repo sim/tb/tb_puf_path.v:57-60 四常量与注入基线、mc 重跑 base R1 三方一致 | ✅ 在案 |
| 加验：fixture 公式 | d_i=((53i) mod (2k+1))−k〔EXPLOG:22〕 | 抽验 chip_pm1：i=0 → 3330×0.99=3297=0xCE1 ✓、i=1 → ×1.001=3565=0xDED ✓ | ✅ |

## 二、发现清单（P0×0 / P1×5 / P2×7 / P3×3）

见 1101_ar-repro-r1_findings.json（15 条，每条含逐字证据）。摘要：
- **P1-1** data/templates/templates.json 未入库且无快照哈希 → 第三方克隆后三个模板取证脚本全部无法运行（本机可跑、数字为真，故未升 P0，但对仅持仓库者是复现阻断）。
- **P1-2** 生产 W3 bit 未入库（库内仅 W1 旧 bit），1760b72 提交信息 "production bit already tracked" 失实。
- **P1-3** 生产/seed2 两个关键 bit 均无 SHA256 记录（本审查已测得并写入 findings，建议回填预登记）。
- **P1-4** 预登记引用的 rootcause/build_seed2.log 被 .gitignore(*.log) 拦下未入库（同类 e*_raw.log 已 force-add，唯独漏它）。
- **P1-5** rtl_r1_order_reconstruction.py:114 第 3 轮 R1 字面量抄录损坏（66 字符，多一个 '5'），重跑得 HD=97，与共识 4/1/3、服务器 RESULT 0x03、v3 三方矛盾；其 107 行来源声明对该行不成立。
- **P2×7**：EXPLOG 汇总表 ±1% 行 0≠1、±5% 行 7≠6（:61/:63/:74）；consensus:32 "≈32/64（仿真 dieC 预测）" 引用张冠李戴（dieC=224/256，128 出自 v3-G3/理论中位 127）；EXPERIMENT_LOG 命令占位符非照抄可跑（缓释：xsim.jou/xvlog.log 在案，iverilog 命令本审查重组后一次跑通）；四脚本绝对路径硬编码；报告不引用 commit SHA；rootcause/ 无 README 入口；（第六、七条见 JSON）。
- **P3×3**：e_mc_curve.log UTF-16LE / e7_raw.log GBK 编码未标注；iverilog E5 输出未存档（本审查已补 review/rerun_e5_iverilog.log）；xsim.dir 约 4MB 仿真器二进制入库无说明。

## 三、缺什么才能让论文评审相信（按严重度排序的补齐清单）

1. **（P1）templates.json 快照入库**：把当晚 tid=1 模板（至少 tid=1 的 100 CRP）以只读快照存入 rootcause/（附采集时间、对应板卡 JTAG 号），或最低限度记录其 SHA256 与结构说明。没有它，"全序反推 HD=0" 这根支柱对外部不可复现。
2. **（P1）生产 bit 入库 + 双 bit SHA256 回填**：force-add build/board_zc706/w3_top_zc706.bit（与 seed2 同法绕过 *.bit ignore），并把两个哈希写进预登记——烧板实验的"同 bitstream/变体 bitstream"前提才可独立核验；同时修正 1760b72 提交信息的失实表述（后续提交注明）。
3. **（P1）build_seed2.log force-add 入库**（WNS/DRC/区域的唯一完整过程证据）。
4. **（P1）修正 v1:114**（改为从日志正则提取或修一字面量 + 加与日志比对的断言），或在文件头加"已废弃，以 v3 为准"横幅——避免第三方重跑得到 97 与共识打架。
5. **（P2）改三处数字/引用**：EXPLOG:61（1→0）、:63 与 :74（6→7）、consensus:32（dieC→v3 G3/独立排序理论中位 127）。
6. **（P2）rootcause/README.md**：一张"数字←脚本←输入←命令"复现矩阵 + 环境（Vivado 2026.1 路径、python、iverilog 14.0、Windows）+ run_*/ 快照注入机制说明；命令节把占位符替换为可照抄的完整命令（xsim.jou 里都有现成的）。
7. **（P2）报告补 git 绑定**：三报告落款处加 HEAD SHA（062c776/1760b72）。
8. **（P3）编码与瘦身**：日志统一 UTF-8（或在 README 标注各文件编码）；xsim.dir 二进制移 LFS 或剔除，保留 .jou/.log/mem/R1 输出即可。

## 四、结论段

以"第三方仅拿仓库能否独立复现与核验"为标尺：**本机层面证据链高度可复现**——三项指定抽查数字（32.0 / 全序 / MC 0.2）与十余项加验全部实测吻合，两个含随机性的脚本均固定种子（20261101）且蒙特卡洛曲线逐字符复现，黄金锚、原始帧、行级引用、构建时序证据全部可溯源且相互咬合（RESULT 帧 04/01/03 与预测、审计、v3 三方一致尤其扎实）。**但仓库自包含性有实质缺口**：核心输入 templates.json、生产 bit、build_seed2.log 三个文件不在库中，关键 bit 无哈希绑定，加之一处证据脚本字面量损坏与三处数字/引用瑕疵——今天的第三方克隆只能复现仿真注入与蒙特卡洛部分（sim/ 自包含），模板取证与"同 bitstream"前提则只能采信叙述。上述缺口全部可在一次提交内补齐（补 3 个文件 + 修 4 处文本 + 写 1 个 README），补齐后该证据包可达到评审可独立核验的标准。板端 seed2 实验照预登记执行即可，判据数字本身（中位 127、REJECT≥64）与仿真/理论一致，无需改动。
