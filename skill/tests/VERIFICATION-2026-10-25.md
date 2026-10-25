# 端到端验证报告(2026-10-25)

延续 2026-10-19 的"校验 → 发现问题 → 修复 → 复验"循环,对技能包
(此时已含第 5 个技能 pynq-board-migration)做全量校验,直至一轮
全查无新问题为止。

## 环境

- Windows 11 Home 26200 / 16GB RAM / Vivado 2026.1
- vivado-mcp-server 2026.9.1(HTTP 18090)+ nodelocked 许可证
- 校验脚本:`tools/mcp-full-verify.py`(7 项)、`tools/mcp-zc706-smoke.py`
  (ZC706 板前门禁 5 项)、`tests/run_tests.py`(离线 18 项)

## 循环结果

| 轮次 | 发现 | 动作 | 复验 |
|---|---|---|---|
| Round 1 | ① 板卡手册号张冠李戴:ZC702 手册实为 **UG850**、ZC706 实为 **UG954**(原写反;原引的 UG952 是 Artix-7 AC701 的手册,与 Zynq 板无关),共 9 处;② delta 表 FMC 行原为 TODO,已可由文献落实;③ `__pycache__/*.pyc` 与 `tests/_tmp/` 运行垃圾被 git 跟踪并混入交付 zip | 全局纠正为 UG850/UG954;FMC 行填实(ZC702=2×FMC 均 LPC;ZC706=J4 HPC 带 GTX + J5 LPC);新增 .gitignore 并移除跟踪(commit c184195) | 离线套件 18/18;全仓 UG952 零残留 |
| Round 2 | 全查(套件复跑 / 文档引用清点 / 器件号清点 / 交叉一致性)——无新问题 | 新增本报告留档 | 见下表 |

## 全绿明细

| 检查 | 结果 | 证据 |
|---|---|---|
| 离线套件 | PASS 18/18 | `run_tests.py` 修复前后各跑一遍;VALIDATION_LOG.md 自动留档(已含纠正后的 UG850/UG954) |
| MCP 端到端 | PASS 7/7 | `mcp-full-verify.py`(2026-10-24 23:54):真实综合 129s、真实 xsim 仿真 20s,AND 门真值表 4/4 向量全对 |
| ZC706 板前门禁 | PASS 5/5 | `mcp-zc706-smoke.py`(2026-10-25 00:05):`get_parts` 列出 xc7z045ffg900-1/-2/-3;目标器件 xc7z045ffg900-2 真实综合 124s 通过 |
| 引用一致性 | PASS | 全仓文档号清点:UG850×8 / UG954×10 / **UG952×0**;UG585(TRM)、DS190(家族概览)、UG901/906/949(工作流引用)语境核对无误 |
| 器件号一致性 | PASS | 全仓器件号恰好 3 个已核实型号:xc7z020clg484-1 / xc7z020clg400-1 / xc7z045ffg900-2,无杂号 |
| 打包 | PASS | `pynq-skill-20261025.zip` 由 HEAD 以 `git archive` 重打,zipfile 完整性校验通过 |

注:除 UG850/UG954 章节事实为文献核实外,上表所有验证均为本机真实
执行并留档;板上项(live 冒烟、DMA 基准、真实迁移 G3–G5)仍为
⏳ 待板,未回填前不声称已测。
