# Phase C 执行记录（合并与交付整理）

**日期:** 2026-10-18 ｜ **依据:** 《前端适配与整合计划》v1.1 §5 ｜ **基线:** HEAD fb29fd2 → 本次三笔新提交

## 执行清单

| 步骤 | 结果 |
|------|------|
| C-0 旧 web.zip 清点删除 | ✅ 333.9MB/15522 条目——含 .dev-data 12476 文件（**内嵌 Edge 浏览器 profile 隐私残留**，已确认）→ 安全删除 |
| .gitignore 修正 | ✅ `dist/`→`/dist/`（锚根，Python build 输出意图不变）；`web/`→`web-over/`（保住工作区忽略、释放合并落位）；check-ignore 三路径逐一验证 |
| README 偏差登记 | ✅ D20–D25 六条（私有依赖/—docs 映射/MODEL 分级/provisionkey+B1-B4/审计修复）——随合并入库 |
| C-1 merge dry-run → Apply | ✅ dry-run：66 新增/1 一致（前端探索报告.md SHA 同）/0 冲突（排除 .out 追加传入）；Apply 后逐文件 SHA 复核通过、既有文件改动=0、无 node_modules/.dev-data/.out 泄漏 |
| 产物归位 | ✅ .out/metrics/*.md → repo metrics/（5 份含 README）；.out/figures/*.png → report/figures/（4 张） |
| 报告 v1.2 勘误 | ✅ 附录 D 七条（dashboards 路径/V6=MODEL/V7=REAL-STATIC/端点增补/桥接 v2/工具/溯源增补）——随 feat 提交入库 |
| 小步提交 | ✅ 3 笔：ed93d87 chore(.gitignore) · 602baf2 feat(web) 66 文件含 dist · 8a2adc7 docs(metrics+figures)；工作区仅剩用户自己的 build/*.ps1 4 个未跟踪 |
| C-2 离线 zip | ✅ web-offline.zip 0.48MB/68 条目（dist+bridge+src+tools+页面+配置+README+报告；经 .NET ZipFile 从 robocopy 暂存打包，排除 node_modules/.dev-data/.out/reviews/合并脚本）；注：PS 5.1 打包条目用反斜杠分隔（Windows 解压无碍；跨平台用 Python zipfile/7z 解） |
| C-4 合并布局彩排 | ✅ 仓库根 `python web/bridge/web_bridge.py --loopback --port 8650`（缺省 --repo-root/--web-dist/--docs-dir 全自动命中）；console/viz/docs 200；S1+S2 实跑通过；viz 徽章 V5=MOCK/V6=MODEL/V7=REAL-STATIC；**零非本地请求**（Playwright request 全监听，127.0.0.1 之外 0 条——离线实证）；1280×720 抽屉按钮可见；三页零页面错误；彩排数据 .rehearsal-data 已清 |

## 遗留与交接
- web-over/ 工作区已无被仓库依赖的内容（.gitignore 已忽略）；可在确认后整目录删除（建议保留至 W5 冻结周结束）。
- web-offline.zip 在仓库根（0.48MB）；竞赛机解压到任意目录 + Python 3.10+ 即 `python web/bridge/web_bridge.py --loopback --open`（README FAQ 5）。
- 下一里程碑：W5 冻结周（10-26 起）——前端只修缺陷；D13 报告可直接引 metrics/ 四表与 report/figures/ 四图。
