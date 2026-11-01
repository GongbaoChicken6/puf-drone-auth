# seed2（布局变体B）缺陷审查报告 · ar-defect-r1
范围 git 242d9bd..1760b72 · 重点 build/tcl/build_w3_board_seed2.tcl 对照 build_w3_board.tcl · 2026-11-01

## 独立验证实验（本审查新增证据，全部落在 review/ar-defect-r1/）
1. Vivado 2026.1 器件级查询（tmp_geom/）：xc7z045 共 14 时钟区域 X0Y0..X1Y6；X1Y0 行界=SLICE_Y49/50；ring_sites_seed2.rpt 的 160 站点归属=150×X1Y0 + 10×X1Y1（4 个接缝站点 X134/135Y50、X140/141Y51）；CLOCKREGION 型 pblock 的 GRID_RANGES 合法包含这 4 站点（越缝合法、字面表述失准）。
2. 生产脚本原样复跑（rerun_prod/，追加落位导出）：自然布局（无 pblock）160/160 环 LUT 全落 X96..153×Y225..259 = X1Y4(90)+X1Y5(70)；与 seed2 强制区零站点重叠，160/160 迁移 ⇒ 重叠风险实测为零。
3. seed2 复跑（rerun_seed2/，仓库脚本逐字）：ring_sites_seed2.rpt 逐字节相同；bit 载荷（≥256B）0 字节差异、头部仅 5 字节时间戳差异 ⇒ 流程完全确定；同时构成『同布局异哈希』反例（整文件 SHA 6D27AFF5…≠0F4E605D…）。
4. 产物核查：两个 bit 头内嵌时间戳（10/27 08:26:15 vs 11/01 17:29:09）；载荷差异 2.74%（364,823B）；utilization Slice LUTs 4375→4379（=uart_rx 修复 6b942af）、Slice 3242→2817（−13%，强制聚簇致打包变紧）；WNS prod 1.873 / seed2 1.213；WHS 0.059/0.055。

## 缺陷清单
见 seed2_defect_review_ar-defect-r1.json（P1×1，P2×4，P3×5）。

## 结论：变体 bit『布局确已差异化』证据强度 = 强
- 160/160 环 LUT 被强制迁入单一角落（X125-141×Y34-51，~17×18 SLICE 窗口），自然布局在同一 RTL/脚本（去 pblock）下 100% 落在 200 行之外的 X1Y4/X1Y5，零重叠、零例外；
- bitstream 载荷 2.74% 真实差异 + Slice 数 −13% 打包漂移，与全量迁移互洽；
- 复跑确定性成立（落位逐字节、载荷零差异），排除随机性偶然;
- DRC 0 错、无任何 pblock 相关告警/违规，32 条 place 告警鉴定为良性 Place 30-568（每环一条，设计使然）。
削弱项（均为文档/论证层，不动摇物理结论）：『同 RTL』失实（生产 bit 早于 uart_rx 修复 6.9 小时）；SHA256 论证无效（时间戳内嵌）；『全部迁入 X1Y0』字面 94% 真（10 cell 越缝）；证据日志 build_seed2.log 未入库。
边界提醒：『布局已差异化』⇏『环频排序已改变』——后者仍需按预登记 P1（REJECT HD 90~170/256）烧板确证；布局完全迁移使『排序不变』在机理上不再可信，但顺序变化方向不可预知。
