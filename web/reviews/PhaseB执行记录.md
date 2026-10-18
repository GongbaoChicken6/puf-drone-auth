# Phase B 执行记录（数据与可视化升级 B1–B4）

**日期:** 2026-10-18 ｜ **依据:** 《前端适配与整合计划》v1.1 §4 ｜ **对象:** web-over/web（仓库 server 零改动）

## 变更清单

| # | 内容 | 位置 |
|---|------|------|
| B1 | GET /api/viz/ml：读 data/ml_attack/exp_{a,b}_results.json，source=STATIC + 复现命令回传；MockApp 对应端点显式 MOCK（不读仓库数据） | web_bridge.py 路由 + RealApp.viz_ml / MockApp.viz_ml |
| B2 | GET /api/viz/reliability：ROPairingPUF.measure 缩放+抖动推演 11 点曲线（128 种子，判定口径对齐 threshold.py），source=MODEL；load_server_modules 增暴露 ROPairingPUF；MockApp 端点 MOCK | web_bridge.py + _Mods |
| B3 | sample_hd.py 增 --roc：intra 用全部模板种子、inter 由 8 个确定性冒名器件（seed=42）池化；输出 roc_summary.json（FAR/FRR 全谱 + EER/AUC 插值） | tools/sample_hd.py |
| B4 | tools/gen_metrics.py：四表生成（core/fpga/security/reliability），逐格来源徽章，缺源写「待板」绝不补数 | tools/gen_metrics.py → .out/metrics/ |
| 前端 | Figure 增 MODEL 分级（琥珀实线 chip，与 MOCK 虚线同色系可区分）；types/api 增 MlBundle/ReliabilityData；新图表模块 chart-svg/v6-reliability.ts（双面板：mean HD + 通过率，TAU 参考线）与 v7-ml.ts（双面板：实验 A 贴 Bayes / 实验 B 排序重构）；main-viz 增 loadV67() 独立装载（失败/--mock 维持占位不冒充）+ 探针通道 grades | src/* |

## 验收门禁（全 PASS）

| 门禁 | 结果 |
|------|------|
| py_compile（bridge/sample_hd/gen_metrics）＋ tsc --noEmit ＋ vite build | ✅ 0/0/0 · 0 · 0 |
| /api/viz/ml | ✅ source=STATIC，repro_command 在（ml_attack --exp A） |
| /api/viz/reliability | ✅ source=MODEL，note 含「非上板实测」；页面副标题 tid 7 · 128 种子 · jitter 1.5% |
| viz 徽章 | ✅ **V5=MOCK / V6=MODEL / V7=REAL-STATIC**（探针断言逐字命中）；V6/V7 SVG 均渲染 |
| V2 副标题 | ✅ EER=0.00%（ROC 大样本口径，loopback 理想分离如实呈现，V1 图注保留「不代表真实器件」警示） |
| 四图 PNG 导出落 .out/figures | ✅ v1 73.3KB / v2 110.1KB / v6（黄金模型）112.8KB / v7（W4 实验产物）196.8KB，Playwright 真实下载事件保存 |
| --roc 离线定稿 | ✅ EER=0.00% · AUC=1.0000（intra=500 μ=1.38/max5；inter=4000 μ=36.49/min16，Δμ=35.11）；roc_summary.json 含 FAR/FRR 全谱与 params（impostors=8, seed=42） |
| metrics 四表 | ✅ .out/metrics/{core,fpga,security,reliability}.md + README；FPGA=4443 LUT/8.35% + 6545 FF/6.15%（util_t2fix 最新）；WNS 如实「待板（综合态 NA）」；Core 时延 ~14ms 引 project_flow.html；逐格徽章 |
| mock 纪律 | ✅ --mock 下两新端点 source=MOCK（页面维持占位，不冒充） |
| 页面错误 | ✅ 探针全程零 pageerror |

## 备注
- 导出文件名自动携带数据源（黄金模型/W4 实验产物），且 SVG 内置 <desc> 溯源（Figure.syncDesc 既有机制）。
- 指标表重跑即刷新：python tools/gen_metrics.py --repo-root D:\puf-drone-auth --data-dir <沙箱>。
- Phase C 待办不变：merge dry-run→Apply、C-0 旧 zip 清点删除、C-3 勘误（含 README 偏差 D20+/docs 映射/B1B2 端点登记）、C-2 重打包、断网彩排。
