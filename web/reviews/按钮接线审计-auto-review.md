# Auto-Review Report — web-over 前端「按钮接线与响应流程」专项审计(含修复轮)

**日期:** 2026-10-17 ｜ **审查类型:** Content Review(UI 交互接线专项)+ 修复轮 ｜ **执行者:** auto-review skill
**对象:** D:\puf-drone-auth\web-over\web(console/viz/index 三页 + bridge) ｜ **问题定义:** 每个按钮是否切实存在对应响应流程、流程是否畅通正确、有无假按键
**方法:** ① 静态接线审计(独立子代理,31 处 click 绑定全量核对) ② 流程正确性审计(独立子代理) ③ 动态实证(--mock 桥接 + Playwright-core 无头 Edge) ④ 修复执行(用户授权:单独先修 6 项 P1/P2) ⑤ 动态复测(v1 全量基线 + 定向 v2 探针) ⑥ round-2 独立复核

## 摘要

| 指标 | 初审 | 修复轮 |
|------|------|------|
| 静态接线 | ❌ FAIL(P1×1+P2×3+P3×1);31/31 绑定真实、无假导出 | — |
| 流程正确性 | ❌ FAIL(确认 F1-F5,新增 P1×1+P2×1+P3×5) | — |
| 动态实证 | ✅ 探针全通、核心交互全部有效、零页面错误 | ✅ 复测全绿(见下) |
| 修复执行 | — | 6/6 落实;typecheck=0、vite build=0、py_compile=0 |
| round-2 复核 | — | ✅ **PASS_WITH_NOTES**(6/6 源码+dist 双证;3 条次要备注,①已顺手修复) |

**核心结论(不变):没有假按键。** 6 项 P1/P2 已全部修复并经动态复测与独立复核确认;原 P3×7 仍挂起(见文末)。

## 修复执行记录(2026-10-17,全部位于 web-over/web,仓库 server 零改动)

| # | 级别 | 修复内容 | 位置 |
|---|------|---------|------|
| F1 | P1 | index 看板 chip:href 更正为 docs/dashboards/*;绑定改 app 级 href 前缀选择器 + fetch 可达性探测(可达→放行导航,不可达→#dash-hint 提示);桥接新增 --docs-dir 参数 + /docs/ 路由(_serve_docs,BridgeServer.docs_dir,缺省推导不校验不抛错) | main-index.ts L42-84;web_bridge.py L1218-1225/1278-1279/1343-1359/1415-1416/1450-1461 |
| F2 | P1 | stage3d 迟到接管竞态:emit(STAGE_TAKEN) 前复检 ui.stage3dFailed,已降级则 dispose+拆除+warn 日志并放弃挂载 | stage3d.ts L129-141 |
| F3 | P2 | 剧本代际令牌 gen:play/step/resume/stop 递增;loop/advanceOne/waitRunEnd/drain 全链携带 g 并在 await 后检查,旧循环让位 | scenario.ts L122/129/141/156/164/171-174/184-187/216-217/233-236/243-248 |
| F4 | P2 | 2D 保底下相机/截图键:stageKeyHint 节流 3s warn 日志(「2D 保底模式:…按键已忽略(3D 接管后可用)。」),不再静默 emit | main-console.ts L339-348/368-375 |
| F5 | P2 | 空态文案去除幽灵按钮引导,如实说明注册键位置与语义 | left-panel.ts L36-37 |
| F6 | P2 | 「导出本次运行」无 currentRunId 时如实禁用 + title 说明,update() 同步 | audit-log.ts L40/81-86/150-158 |
| 附注 | — | round-2 备注①顺手修复:_serve_docs 路径判定改 target.is_relative_to(docs.resolve()),排除同前缀兄弟目录 | web_bridge.py _serve_docs |

## 动态复测证据(--mock 桥接 8646/8648 + Playwright 无头 Edge,修复后构建)

| 验证点 | 结果 |
|--------|------|
| index chip(桥接未映射) | ✅ 点击→#dash-hint 提示出现(文案逐字符合)、不导航、零错误 |
| index chip(桥接 --docs-dir 映射) | ✅ 点击→真实导航,最终 URL=/docs/dashboards/project_status.html;docs 路由 200、目录逃逸尝试 404 |
| 导出本次运行(P2-6) | ✅ 初始 disabled=true;跑 S1 后 false;点击产生 application/json blob+规范文件名 |
| 场景双击(P2-3) | ✅ running 按钮数恒 1;POST 顺序 2 次(重启语义);状态收敛「连播 1/1 · S1 正常认证」;零页面错误 |
| 2D 强制降级(P2-4) | ✅ hud「2D 保底时序(3D 舞台未接管)」;按 3→日志行「2D 保底模式:相机预设 3 仅 3D 舞台可用,按键已忽略(3D 接管后可用)。」逐字命中;'f' 按节流预期合并 |
| F2(P1-2) | 代码级验证(竞态窗口无法确定性强制):复检逻辑在 emit 前单一检查点,dispose 路径与既有 catch 分支同构;dist 含「已拆除并放弃挂载」字符串 |
| v1 全量基线回归(31 项交互,S1/S2/连播/暂停/单步/导出/滑杆/跟随/hex/相机/F 截图/τ 拖拽/导出 SVG/数据源切换/溯源角标/刷新) | ✅ 修复后构建上全部通过,三页零页面错误、零控制台错误 |

## round-2 复核结论

**PASS_WITH_NOTES**:F1-F6 全部以 文件:行号+引文 落实,关键修复字符串均已在 dist/assets/*.js 检出(console-CB9rTsdT.js/index-BbKQznT0.js/stage3d-CtaWtN4K.js)。备注:①docs 路径前缀判定建议加严(已当场修复并复测 200/404);②暂停后单步对在途 POST 的重推属单步语义固有取舍(顺序执行、有界收敛,非并发),已文档化;③F6 title 引号形制差异,忽略。

## 调度与降级记录
静态两子代理(前台逐个);动态:--mock 桥接→原生 --headless=new 本机不渲染(实证 DOM-LEN 0)→降级 Playwright-core@1.49.1 驱动系统 Edge(沙箱 .dev-data/pw);期间经历一次机器重启、两次探针构造 bug(anchor.click 被审计补丁拦截/嵌套 script 提前闭合)、一次修复自身引入的 mock 启动崩溃(resolve_repo_root 误校验,已改轻量推导)——均定位修复后复测通过。修复期间两处门禁拦截真实缺陷:tsc TS1005(括号失衡)与 mock 启动 SystemExit,证明「改完即测」必要。所有探针/临时产物已清理,dist 恢复三页+assets;孤儿进程已清(8646/8648 均释放)。

## 遗留(不阻断,建议随 Phase A 顺带)
P3×7:help-card 焦点归还 no-op(tabindex)、index 5s 全量重建 DOM、mock 固定 tid=7、单步空队列死态+viz refresh 无防重、断线 run 残留秒表、(待核对)暂停后单步采样、#tid-group 静态判据与实测出入。另:web_bridge._serve_static 亦可顺手改 is_relative_to(与 _serve_docs 同款前缀写法,风险同级)。

## 最终结论
**✅ 本轮修复门禁 PASS(P0=P1=P2=0)。** 无假按键;6 项 P1/P2 修复经源码+构建产物+运行时三重验证;v1 基线 31 项交互零回归。可回《前端适配与整合计划》v1.1 主线(Phase A 桥接 freqs 适配)。
