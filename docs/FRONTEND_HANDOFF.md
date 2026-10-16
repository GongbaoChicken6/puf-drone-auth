# 前端探索 · 上下文交接文档（FRONTEND_HANDOFF）

> 生成：2026-10-13，由主项目会话整理（PUF 无人机认证，仓库 D:\puf-drone-auth，HEAD 207b82a，74 commits）。
> 用途：在**独立新会话**中进行前端方向探索时的一次性上下文注入。读完本文即可开工，无需回读全部项目历史。
> 性质：未提交的新增文件（主仓库其余工作区干净）。

## 0. 项目 30 秒背景（前端视角）
- **竞赛**：2026 全国大学生嵌入式芯片与系统设计竞赛 FPGA 赛道，**截止 2026-11-04 18:00（现余约 23 天）**
- **系统**：ZC702 FPGA 上的 PUF 硬件指纹 + HF-IDA 双向认证（MAVLink v2 帧，433MHz 电台/串口），PC 侧 Python 基站
- **现状**：RTL/协议/单测全部仿真级完成（12 TB CI 全绿，A1 Speck 统一 R2 六阶段完成）；**板级验证 = 0**（板卡电源故障排查中，另一会话处理）；PC 侧持续串口接收循环未完成（SerialTransport 一问一答已有）；W4 实验 / 报告 / 视频未开始
- **对前端的意义**：演示与数据可视化是当前**零硬件依赖**就能推进、且直接服务答辩与 G5 门禁（互斥演示/ROC-EER/报告）的高价值方向

## 1. 现有前端资产（全部零依赖静态 HTML，无任何框架/构建）
| 文件（docs/ 下） | 行数（含空行） | 内容 | 备注 |
|---|---|---|---|
| project_status.html | 339 | 总进度环 48%、六周时间线、模块卡、代码统计、审查历史、下一步 | 数据硬编码，2026-10-12 手动刷新过 |
| project_flow.html | 206 | 收发链路图、12 TB 用例矩阵、16 轮审查、排期 | 同上 |
| mindmap.html | 239 | 思维导图分支 + 手写 SVG 贝塞尔连线（原生 JS） | 唯一有 JS 交互的 |
| architecture.html | 356 | 四级验证状态（📝代码/🧪仿真/🔧板级/🌐联调）架构图、10 项待办、诚实进度条 | 板级/联调均标 0 |
| flowchart.svg / architecture.svg | ~11KB | 手写 SVG 流程/架构图 | 报告插图底稿 |

**风格 tokens（project_status.html :root，四份基本一致，沿用可保持视觉统一）**：
- 背景 `--bg:#0a0e1a / --bg2:#0e1420 / --bg3:#131a2a`，边框 `--border:#1e2840`
- 文字 `--text:#dfe7f3 / --muted:#7b8ba8 / --dim:#4a5a78`
- 强调 `--green:#00d68f / --cyan:#22d3ee / --amber:#f59e0b / --red:#ef4444 / --blue:#3b82f6`
- 字体 `'Segoe UI', system-ui, -apple-system, sans-serif`；卡片 12px 圆角 + 1px 边框 + 深色分层
- 组件模式：进度环（SVG stroke-dasharray）、时间线、模块卡网格、四级徽章、审查条目（P0-P3 配色）

## 2. 前端可消费的数据源（真实性分级——**禁止杜撰数据**）

### 2.1 已存在的真实数据（立即可用）
- **build/reviews/ 下 40+ 份结构化 JSON**：A1 六阶段审查（a1p4/p5/p6/p6b/a1full：CONSENSUS、FIXLIST、trace_matrix、interop_run 等）、教程五轮审查（tutorial/）、待办复核（todo-recheck/ 8 份，含 claims_v2.md 权威待办清单）
- **协议黄金帧**：docs/protocol_contract.md §4——7 条帧逐字节 hex（ACCESS_REQUEST/CHALLENGE/RESPONSE_R1/RESULT/CONFIRM/EXTRA_CHALLENGE/RESULT_A1_GOLDEN），帧格式/CRC 规格在 §1-§3
- **CI/测试统计**：12 套 TB 名单（scripts/ci_regression.ps1）、1175 组测试向量（sim/testvectors/speck_random.mem）、44 个单测（tests/test_a1_phase4.py）、线性金丝雀结论
- **Vivado 报告**：build/reports/utilization_w3_synth.rpt、timing_w3_synth.rpt（LUT/FF/时序实测）
- **git 元数据**：74 commits 完整历史（无 remote，已有本地 bundle 备份 ×2 在 D:\文件\ssssssss\FPGA\）
- **已核设计指标**（docs/project_design.md）：有效熵 ~44 bit、认证延迟 ~14ms、LUT 490~653、RO 配对空间 C(16,2)=120、Speck64/96 参数与黄金 R2=7b45b0545e59aa94

### 2.2 loopback / 纯 PC 可生成（无需板卡，演示数据主渠道）
- `python -m src.python.server.main --loopback`：完整认证流状态机（注册→挑战→响应→判定→CONFIRM，含灰区加测/重放拒绝分支）——**实时事件流的天然来源**
- src/python/evaluation/：hamming_analysis / compare_devices / quantizer（CSV 输出）→ HD 分布、跨设备比较类图表
- B6 ML 攻击实验（实验 A 合成 arbiter+LR 基线、实验 B 排序重构 ~120 CRP）**尚未编码**——前端图表可与实验产出同步设计（design.md §W4 有完整实验设计与结论口径）

### 2.3 需上板才有（当前阻塞，只做占位设计）
- W1 VIO 指纹比值读数（data/w1_readings/ 目前为空）、16 环真实频率、温度-reliability 曲线、多终端并发数据、真串口/电台流量

## 3. 候选前端方向（按竞赛价值 × 可行性排序）
1. **竞赛演示控制台（最强推荐）**：PC 基站 Web UI——终端注册表、CRP 池水位、实时五帧认证流动画、HD 评分仪表、PASS/REJECT 大字判定、审计日志。数据源先 loopback、后接真串口。直接服务 W5 G5「互斥演示」与答辩录屏。
   - 数据桥建议：Python 侧薄 HTTP/WS 层（FastAPI 或零依赖 http.server + 轮询 JSON），复用既有 protocol.py 状态机，勿重写协议逻辑
2. **实验数据可视化页**：PUF 16 环指纹热图、HD 分布直方图、ROC/EER 曲线、温度 reliability 曲线、ML 攻击准确率曲线——同时可作为 report/figures/（目前为空）的插图来源
3. **静态看板自动化**：四份手写 HTML 的数字是硬编码、每次手动刷新（10-12 刚刷过一轮 74/168）——可改为从 JSON/git 单一来源生成
4. **报告插图**：升级 flowchart/architecture SVG 为更精细的图（服务 W5 报告）

## 4. 技术选型约束
- **离线能力是硬指标**（竞赛/答辩环境可能无网）：零依赖静态 HTML+原生 JS 可行；Vite+Vue/React 打包成静态产物也可行；**避免需要运行时 Node 服务或 CDN 的形态**
- 现有代码风格：无框架、无构建、手写 SVG；新前端放**独立目录（建议 web/ 或 dashboard/）**，勿覆盖 docs/ 四份看板
- Python 环境 3.13（pycache 实证），README 声明 3.10+
- 视觉沿用 §1 tokens；所有展示数字须溯源到 §2 来源，mock 必须显式标注"MOCK"

## 5. 禁区与协作边界
- **不改** src/rtl、sim/、scripts/ci_regression.ps1（CI 12 TB 全绿是生命线）；不碰 build/reviews/（入库审查证据，只读）
- 板卡事实以 docs/HANDOFF_SUMMARY.md §三 为准（LED=DS15~DS18 对应 P17/P18/W10/V7；USB 三口 J17 Mini-B UART / U23 Micro-B JTAG / J1 Mini-B PS USB）——旧文档/旧克隆中的 Y11/T22 等是已废弃错值
- 串口未打通：SerialTransport 一问一答存在（main.py:183-232/812-823）但无持续接收循环、C2 为桩——前端演示一律先用 loopback 数据
- 仓库纪律：小步提交、提交信息写清动机、审查产物入 build/reviews/

## 6. 快速上手
- 仓库：`D:\puf-drone-auth`（HEAD 207b82a，master，无 remote）
- 看板预览：浏览器直接打开 docs/*.html
- 基站自测：`python -m src.python.server.main --loopback`（真串口：`--port COM3 --baud 115200`，需硬件）
- 权威文档：docs/HANDOFF_SUMMARY.md（总交接）、docs/protocol_contract.md（帧级契约）、docs/project_design.md（设计 + W4/W5 计划）、build/reviews/todo-recheck/claims_v2.md（当前待办全集）

## 7. 需在新会话先与用户确认的三件事
1. 探索方向：演示控制台 / 数据可视化 / 看板自动化（可组合，推荐 1+2）
2. 技术栈：零依赖静态 vs 构建工具链（均须离线可运行）
3. 代码落位与命名（建议 web/），以及是否需要与未来串口接收循环的对接约定（事件 schema）
