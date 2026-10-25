# 通用 PYNQ 技能包（Generic PYNQ Skill Package）

面向 PYNQ 框架的通用技能包：**不与本队题目绑定，换题目、换板卡可用**
（对应 2026 FPGA 创新设计赛道选题指南 3.3.2 / 3.3.5.2）。覆盖选题指南
列举的全部四个正例方向：Overlay 加载校验与 register_map 范式、DMA 搬运
与缓存一致性、接口契约生成主机代码/测试骨架、黄金参考比对与性能资源
自动报告；另附**板卡迁移技能**（本队 ZC702→ZC706 中途换板的真实需求
驱动，通用 A→B）、两类扩展交付物（提示词工作流、案例模板）与本队踩坑清单。

- 许可证：MIT（见 LICENSE）
- 工具链基线：Vivado 2026.1（脚本对报告文本的解析兼容 2020+ 格式）
- 目标平台：Zynq-7000（ZC702 / PYNQ-Z2 实测路径）；UltraScale+ 逐项
  标注差异（如 DMA 缓存一致性）
- 语言：目录/文件名纯英文；脚本人人可读，注释即文档

## 快速开始（陌生队伍 3 分钟接入）

```bash
# 1) 静态体检你的 overlay（任何 PC，无需板卡、无需装 pynq）
python pynq-overlay-load-verify/scripts/overlay_doctor.py --overlay-dir <你的overlay目录>

# 2) 写接口契约 -> 生成驱动 + 测试骨架（任何 PC）
python pynq-interface-contract/scripts/gen_driver_stub.py \
    --hwh <你的.hwh> --contract <你的contract.json> --out-dir gen
pytest gen/ -v                    # 离板跑生成的测试

# 3) 上板冒烟（板上）
#    见 pynq-overlay-load-verify/SKILL.md 第 3 步（寄存器写回读）
# 4) 数据比对 / 报告收割（任何 PC）
python pynq-golden-report/scripts/golden_compare.py --got out.csv --golden ref.csv
python pynq-golden-report/scripts/collect_report.py --util u.rpt --timing t.rpt
```

没有 overlay？只做 RTL？→ 第 4 项（golden-report）与 prompt-workflows、
pitfalls 对纯 RTL 工程同样适用。

## 目录与逐项说明

按评价标准（3.3.5.2），每项给出：适用范围 / 使用方法 / 失效条件 /
已验证效果 / 来源。详见各目录 SKILL.md。

### 1. pynq-overlay-load-verify — Overlay 加载与校验
- **适用范围**：任何带 .hwh 的 PYNQ overlay（Zynq-7000 与
  UltraScale+）；上板前体检、上板后寄存器冒烟、overlay 变更换名核对。
- **使用方法**：`overlay_doctor.py` 静态模式（PC 上秒级，含 REGISTERS
  节点解析——与 pynq `hwh_parser` 构建 register_map 的同一数据源）→
  板上 `--live --regspec` 寄存器写回读。详见 SKILL.md。
- **失效条件**：仅 .tcl 元数据的老式 overlay（会被静态检查警告）；
  无 AXI-Lite 接口的纯流式 IP（live 模式跳过并说明）。
- **已验证效果**：静态解析在 Vivado 2026.1 真实 .hwh 导出上验证
  （tests/VALIDATION_LOG.md）；live 冒烟流程与本队 ZC702 上板流程一致。
- **来源**：.bit/.hwh 不同源、IP 改名后主机代码失配等高频事故模式
  的流程化收敛（SKILL.md 内 Common errors 表）。

### 2. pynq-dma-coherence — DMA 搬运与缓存一致性
- **适用范围**：任何经 AXI HP 口用 AXI DMA 搬数据的 overlay
  （HLS 流内核、视频/数据流）；Zynq-7000 必须，UltraScale+（CCI +
  dma-coherent）为无操作但保留可移植性。
- **使用方法**：`dma_smoke.py` 板上 loopback 冒烟+吞吐基准
  （`--dry-run` 在 PC 上预览调用序列）；错误指纹表按数据模式直接
  定位失效类（缓存纪律/流未通/错位）。
- **失效条件**：overlay 里没有可回环的 AXI DMA（脚本会拒绝并说明）；
  需要 Scatter-Gather 的场景未覆盖（当前为 simple 模式）。
- **已验证效果**：脚本逻辑离板验证（--dry-run + 代码审查，见
  VALIDATION_LOG.md）；板上数字须由使用者在自己板卡实测——本包
  如实标注"板载数字待本队 DMA 里程碑回填"，不编造基准。
- **来源**：缓存失效模式整理自 UG585 与 PYNQ buffer 文档（官方
  doc-search 检索交叉核对），指纹分类法为本队整理。

### 3. pynq-interface-contract — 接口契约 → 主机代码/测试骨架
- **适用范围**：任何 AXI-Lite IP（HLS 内核、自定义 RTL 外设）的
  PS 侧驱动生成；多人协作时作为"可执行接口规范"。
- **使用方法**：契约 JSON（寄存器+操作）+ .hwh（真实基地址）→
  `gen_driver_stub.py` 生成 driver + pytest 骨架；离板跑逻辑测试，
  上板跑 `-m board` 冒烟。
- **失效条件**：IP 名与 .hwh 不一致（生成器警告而非静默用 0）；
  复杂位域打包（子字段结构）暂不生成 accessor（写整字）。
- **已验证效果**：生成-测试闭环离板验证（tests/ 用合成 HLS 风格契约
  跑通 pytest 全绿，含"坏寄存器必被检出"的反向测试）。
- **来源**：本队手写 MMIO 偏移两次与 RTL 漂移的教训——把接口契约
  变成生成物与测试物。

### 4. pynq-golden-report — 黄金比对 + 性能/资源自动报告
- **适用范围**：任何产出数值的计算（板上/仿真/软件参考）与任何
  Vivado 工程（资源、时序收割）；CI 可直接用退出码。
- **使用方法**：`golden_compare.py`（CSV/向量/二进制，容差门禁，
  行列数不匹配判 FAIL）；`collect_report.py`（utilization 含
  -hierarchical、timing_summary → 单文件 Markdown 指标表，
  自动标注"综合后=估算"）。
- **失效条件**：GUI 复制的表格文本（须 `report_* -file` 输出）；
  golden 与被测同源（自证只证确定性，不证正确性——SKILL.md 红线）。
- **已验证效果**：两个脚本都在真实数据上验证——合成通过/失败用例
  + **本队 Vivado 2026.1 真实综合/实现报告**（tests/ 收录解析输出）。
- **来源**：本队 W1/W2/W3 轮次报告收割实践的脚本化。

### 5. pynq-board-migration — 板卡迁移（A→B，ZC702→ZC706 实例）
- **适用范围**：任何 Zynq-7000 板对板迁移（换板、双板并行开发、移植
  审查）；跨家族（7 系→UltraScale+）按 references 的加行方法扩展。
- **使用方法**：五道门禁按序执行——G1 盘点"板耦合 vs 可移植"（口诀：
  **端口名随行,引脚位置永不搬运**）→ G2 从核实过的器件表换 part
  （`retarget_check.py --boards`，两级陷阱行：pynq-z2 与 zybo-z7-20
  **完整型号相同(xc7z020clg400-1)却是两块板**；zc702 与 pynq-z2
  同硅片不同封装 clg484/clg400）→ G3 用目标板 master XDC 重新生成约束，`--old-xdc/--new-xdc`
  离线核对端口集合完整性 → G4 重建（目标板 preset 配 PS7 + 布线后
  时序签核）→ G5 `--hwh --expect-part` 器件门禁 + 本包离线回归，
  最后才约板子做 live 冒烟。
- **失效条件**：.hwh 无 PART 属性时器件门禁报 UNKNOWN（退出码 2，
  绝不静默放行）；G3 只核对端口集合与电平类变化，不验证时序（那是
  G4 的事）。
- **已验证效果**：两道离线门禁（端口兼容/器件核对）含正反两方向
  全部离板实测（tests/ T8a–T8e，含"迁移漏掉一个端口必被检出"）。
  **目标器件 xc7z045ffg900-2 已在本机完成板前门禁**：get_parts 确认
  存在 + 该器件上真实综合冒烟通过（Vivado 2026.1，2026-10-24）——
  板到之前器件/许可/工具链已全部就绪。真实 ZC702→ZC706 迁移待板后回填。
- **来源**：本队中途换板（ZC702→ZC706）的真实叙事需求；器件号经
  UG850/UG954 核实，ZC702 侧为本队综合实测。方法见
  `references/board-delta-method.md`（每行带来源标签的增量表）。

### 6. prompt-workflows/ — 提示词工作流（2 个）
- **适用范围**：算法→软硬件划分决策；综合/实现报告瓶颈定位。
- **使用方法**：模板直接粘给任意大模型 agent；迭代规则（带数据
  回填、只改被推翻的行）写在文件内。
- **失效条件**：无量化目标时划分模板会退化为"全放 PS"（模板已
  声明）；综合未通过时不适用瓶颈模板。
- **已验证效果**：流程在本队开发过程走通（划分表与 W 系列报告
  诊断即其产物）；非统计性验证，已如实标注。
- **来源**：本队与 AI 协作的实际流程提炼。

### 7. templates/ — 案例模板（2 个）
- overlay_notebook_template.py：上板首触 notebook（加载→静态→
  冒烟→功能→golden→DMA），Jupyter/VS Code 通用（# %% 单元）。
- report_template.md：竞赛设计报告章节骨架（对照 3.3.5.3 每节的
  证据类型）。
- **失效条件**：notebook 模板假定 .bit/.hwh 同目录；报告模板随
  官方评分细则更新需对齐。

### 8. pitfalls/pynq-pitfalls.md — 踩坑清单
- 结构化（现象/触发/排查/来源），逐条标注【本队实测】【文献】
  【文档+本队】，不混淆 hearsay 与实测。

## 验证状态总表（实事求是）

| 项目 | 离板可测部分 | 板上部分 | 验证记录 |
|---|---|---|---|
| overlay-load-verify | 静态解析 ✅ 已测 | live 冒烟 ⏳ 待板 | tests/VALIDATION_LOG.md |
| dma-coherence | --dry-run ✅ 已测 | 冒烟/基准 ⏳ 待板 | 同上 |
| interface-contract | 生成+pytest ✅ 已测 | board 标记 ⏳ 待板 | 同上 |
| golden-report | 全部 ✅ 已测（含真实报告） | —（本就离板工具） | 同上 |
| board-migration | 两道离线门禁 ✅ 已测（正反双向） | 真实 ZC702→ZC706 迁移 ⏳ 待板 | 同上 |
| prompt-workflows | 流程走通 ✅（非统计验证） | — | 文内使用记录 |
| pitfalls | 逐条来源标注 | — | 文内 |

✅=已在本机真实执行并有输出留档；⏳=需要板卡，尚未回填，绝不冒充已测。

## 换题目/换板卡怎么复用

1. 换板卡（项目本身跟着板子走）：先走 `pynq-board-migration/SKILL.md`
   五道门禁——迁移是工程级动作，不是"改个 part"。
2. 换板卡（只复用本包工具）：overlay_doctor/golden-report/collect_report
   与板卡无关；
   dma-coherence 在 UltraScale+ 读 references/cache-coherency.md 的
   差异节；contract 生成只需新板工程的 .hwh。
3. 换题目：只有"接口契约"和"golden 来源"是题目相关的输入，其余
   全部通用。两个演示题目见 tests/（HLS 风格加密内核契约）与本队
   项目（PUF 认证终端，真实报告数据）。

## 调研结论（为什么长这样）

2026-10 我们对公开 skill 生态做了扫描（skills.sh 全站 sitemap 约
2 万条目、anthropics/skills 官方库、awesome-claude-skills 等awesome
列表、GitHub/Gitee 检索）：**没有成熟的通用 PYNQ skill**——现有
FPGA 相关 skill 集中在 Vivado Tcl/RTL 仿真/约束（AMD Ross 官方 51
个亦然），PYNQ 主机侧（overlay 体检、DMA 纪律、契约生成、报告收割）
是空白。本包即按此空白设计，四个技能对应选题指南 3.3.5.2 列举的全部
四个正例方向；关键 API 事实（DMA TLAST 语义、2^14 传输上限、.hwh
REGISTERS 结构）经 PYNQ 文档与 `pynq/lib/dma.py` 源码核对后写入。

## 与官方 Ross 的关系

本包独立于 AMD Ross（不依赖、不重复其 51 个官方 skill：Vivado/HLS/
调试向）。互补点：本包 prompt-workflows 建议 agent 结合官方
amd-doc-search MCP（https://ross.amd.com/mcp/doc-search）检索 UG 章节
佐证，减少幻觉；该 MCP 已由本队从本机真实握手验证（v0.11.6，
工具 vivado_doc_search）。本地 vivado-mcp-server（2026.9.1）亦已
从本机完成握手/工具列表/调用/Vivado 拉起全链路校验并写入工作区
`.mcp.json`（stdio-bridge 模式）。许可证已导入并实测：用户级环境变量
`XILINXD_LICENSE_FILE` 指向 `%APPDATA%\Xilinx\Xilinx.lic`（setx 永久
生效），经 vivado_start + 真实综合端到端验证（Z-7020 AND 门，0 错误，
Synthesis 许可证正常检出/释放）——详见 tools/vivado-mcp-server/README.md
与 pitfalls B5。
