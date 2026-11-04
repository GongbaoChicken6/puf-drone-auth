[English](./README.md) | **中文**

# puf-drone-auth — PUF-Based Hardware Fingerprint Mutual Authentication for UAV Fleets

> **仓库**：https://github.com/GongbaoChicken6/puf-drone-auth（已公开，tag v1.0-submission）

 AMD 自主选题赛道参赛作品 · 两块 AMD ZC706 (xc7z045ffg900-2) 实测闭环 · MIT License

基于 16 环环形振荡器 PUF（RO-PUF）的无人机身份认证系统：芯片制造微差即硬件指纹，**密钥不预存、不落地**——上电由指纹现场派生；HF-IDA 六类消息双向鉴别；双阈值（6/16）判决 + 待定区自动加测；Speck64/96 全硬件应答；433 MHz 无线链路实测。

核心实测结论（详见 metrics/metrics.csv 与 report/design_report.docx）：

| 指标 | 数值 |
|---|---|
| 板间指纹偏差均值 | 145.8/256 = **57.0%**（本尊重测 ≈0） |
| 假冒终端 | **全部被拒**（跨板 REJECT HD≈140，无 CONFIRM） |
| 断电重放 | 旧报文重发即拒 |
| 有线认证时延 | 23~32 ms；无线（433 MHz）全程 57 ms；识别假冒 36 ms |
| 资源/时序（ZC706 Routed） | LUT 4375（2.00%），WNS +1.873 ns @100 MHz |

## 目录对照（指南 3.3.5.4：推荐结构非强制，自组织须在 README 给出对照说明）

本包采用自组织结构。**推荐结构的三项（README.md / src / sim）与 3.3.5.2/3.3.5.3 的 skill/、report/ 均按原名落位**；其余目录按 3.3.5.1 工程包五要素展开。逐条目对照如下（覆盖包内全部顶层条目）：

| 本包条目 | 对应指南要素 | 内容说明 |
|---|---|---|
| README.md | 3.3.5.4 推荐结构 · README.md | 本文件（简介+复现步骤+目录对照） |
| src/ | 3.3.5.4 推荐结构 · src/ | RTL 源码+约束（src/rtl，含 XDC）、PS 侧 Python 基站（src/python） |
| sim/ | 3.3.5.4 推荐结构 · sim/ | 18 个测试台（sim/tb）+ 测试向量 + 验证结果（sim/results，含 CI 18/18 自证）；独立仿真入口见 build/ps1/ |
| build/ | 3.3.5.1 · 上板工程/综合实现报告/构建脚本 | 正式 bit×2、Vivado 综合与烧写 tcl、**ZC706 Routed 实现/时序报告**、w1→w2→w3_synth 演进对比报告 |
| scripts/ | 3.3.5.1 · 可复现的构建脚本 / 运行脚本 | CI 全量门禁（ci_regression.ps1）、向量生成、威胁验证脚本 |
| tests/ | 3.3.5.1 · 仿真或验证结果 | pytest 全套（111 passed 记录见 metrics/logs/1101_pytest_all.txt） |
| tools/ | 3.3.5.1 · 运行脚本 | 指标分析（puf_metrics/puf_sac）、契约同步检查、HC-12 配置工具 |
| web/ | 3.3.5.1 · 上位机应用（PS 侧软件） | PC 基站桥（bridge）+ 演示监控台前端（dist 自足离线） |
| data/ | 3.3.5.1 · 实测输出与参考结果的比对数据 | 注册模板/挑战池/设备密钥（公开演示钥）/ML 实验数据/bit 哈希锚/克隆攻击根因档案 |
| metrics/ | 3.2.5 式指标目录（自愿采用） | metrics.csv（唯一权威指标汇总）+ logs/（23 份原始日志） |
| docs/ | 3.3.5.1 · 设计文档 | 系统设计（project_design.md）、接口协议契约（protocol_contract.md）、原理可视化页（visualization.html） |
| skill/ | 3.3.5.2 · 技能包 | PYNQ 可复用技能×5 + 踩坑清单 + 工作流（适用范围/用法/失效条件见其 README） |
| report/ | 3.3.5.3 · 设计报告 | design_report.docx / design_report.pdf / figures（23 张 PNG，按图号命名）/ llm_log（整理版协作记录 collaboration_record.md） |
| LICENSE | 3.3.3.3 · 开源协议 | MIT |
| requirements.txt | 3.3.5.1 · 依赖清单 | PC 侧 Python 依赖 |

## 复现步骤

**环境**：Vivado 2026.1、Python 3.13、两块 AMD ZC706（xc7z045ffg900-2，各接 USB JTAG 与 USB-TTL 串口）。
> 注意：scripts/ci_regression.ps1 与 build/ps1/*.ps1 中的 `$vivado` 为本机路径 `D:\vivado\2026.1\Vivado\bin`，请在你的机器上修改。

1. **依赖**：`pip install -r requirements.txt`
2. **综合/实现重建**：Vivado batch 运行 `build/tcl/build_w3_board.tcl`（终端一）与 `build/tcl/build_w3_board_seed2.tcl`（终端二·专属布局变体）。源码与约束全部来自 `src/rtl`，clk_wiz IP 由脚本现场生成。产物与随包 `build/board_zc706*/` 的 Routed 报告比对。
3. **仿真**：`build/ps1/run_xvlog_w3.ps1` → `build/ps1/run_xsim_w3.ps1`；全量 18 个测试台的静态通过记录见 `metrics/logs/1101_ci_regression_full.txt`（18/18 PASS）与 `sim/results/`。
4. **PC 侧**：`pytest`（111 通过记录：metrics/logs/1101_pytest_all.txt）；全量门禁 `scripts/ci_regression.ps1`（含 bit 哈希锚校验，依赖文件均已随包原位）。
5. **上板演示**：`vivado -mode batch -source build/tcl/program_zc706.tcl -tclargs <bit> [jtag_sn]` 烧写两块板 → 启动 web 基站：
   ```
   python web/bridge/web_bridge.py --repo-root . --data-dir <一个全新的空目录> --loopback --serial-port COM<x> --serial-baud 115200 --port 8642
   ```
   **⚠ 必须带 --data-dir 指向全新空目录**：缺省值指向包内 data/，会触发内置的过期终端清理（不可逆删除实测模板/挑战池，破坏复现数据）。浏览器打开 http://127.0.0.1:8642/console.html ，板侧按 SW13 复位 → SW7 发起认证：绿灯=PASS，红灯=REJECT（详见 report/design_report.docx 演示章节）。
6. **实测比对**：metrics.csv 每一行都指向 metrics/logs/ 的原始日志；板级操作步骤逐条见 report/design_report.docx。

## 说明

- **外部参考代码**：external/（c_library_v2、fpga_puf、puf-esp32-auth、PUF-lab，pinned commits）不随包分发；如需参考对比，运行 scripts/setup_external.ps1 重建，出处见各文件头署名。
- **data/device_keys**：tid1/2 为公开演示测试密钥（0001020308090a0b10111213），其余为本队演示终端派生密钥——评估者用自己的板重新注册会生成自己的密钥。
- **metrics/logs 中文日志**：文件名已英文化，内容保留原始中文。
- **开源**：本作品以 MIT 协议开源（LICENSE）；公开仓库地址见页首（tag v1.0-submission）。
- **决赛海报**：按 AMD 模板的一页英文 PPT 海报另行提交，不入本包。