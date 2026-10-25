# PYNQ / Vivado / Ross 踩坑清单（结构化）

> 类型：踩坑清单 ｜ 评价口径：每条含 现象 / 触发条件 / 排查步骤 / 来源。
> 来源标注（实事求是）：
> - 【本队实测】= 本队机器上真实发生过、有记录
> - 【文献】= 官方文档/官方 wiki 明文，尚未在本队复现
> - 【文档+本队】= 文献记载且本队流程中亦遇到同类情形

## A. PYNQ / Overlay

### A1. Overlay 加载后没有任何 IP 属性
- 现象：`Overlay("x.bit")` 成功，`ol.<ip>` 不存在 / ip_dict 空。
- 触发：.bit 旁没有同名 .hwh（旧版 .tcl 流程或拷贝时漏掉）。
- 排查：`overlay_doctor.py --bit x.bit` 静态检查会直接指出；
  确认 Vivado export 时勾选 .hwh（2017.3+ 默认有）。
- 来源：【文献】pynq.readthedocs.io overlay 章节 + 通用工程实践。

### A2. 寄存器读写全部失败 / 读回全 0 / 全 F
- 现象：MMIO/register_map 写读不吻合。
- 触发：.bit 与 .hwh 不同源（地址漂移）；PL 时钟未使能（FCLK 关闭）；
  GP 口未勾；寄存器实际只读。
- 排查：先静态（时间戳比对）；板上 `cat /sys/kernel/debug/pinctrl`
  无关，直接看 BD 的 FCLK_RESET 与 GP 使能；单寄存器读回定位。
- 来源：【文档+本队】。

### A3. DMA 输出"有时对有时错"
- 现象：小 buffer 全对，大 buffer 或多次运行后出现散点错误。
- 触发：缺少 flush（发送方向）/invalidate（接收方向），缓存不一致。
- 排查：dma_smoke.py 的失败指纹表（散点错=缓存纪律；全零=流没通；
  固定偏移=长度/位宽）。
- 来源：【文献】UG585 + PYNQ buffer 文档；指纹法为本队整理。

### A4. allocate 返回的 buffer DMA 搬不动
- 触发：numpy 切片/转置产生非 C 连续视图，物理不连续。
- 排查：断言 `buf.c_contiguous`；需要变换先复制到新 allocate。
- 来源：【文献】pynq.buffer 文档。

### A5. Jupyter 连不上板子
- 触发：板卡 IP 变了 / 9090 端口未起 / image 版本不对。
- 排查：ping -> `ssh xilinx@<ip>`（默认密码 xilinx）-> 
  `jupyter notebook list`；官方 image 即插即用的前提是官方板卡。
- 来源：【文献】。

## B. Vivado / 环境（本队踩得最痛的）

### B1.【本队实测】中文路径下综合崩溃
- 现象：synth_design 中途崩溃，0xC0000374（堆损坏）。
- 触发：工程/工作目录含非 ASCII 字符（如 D:\文件\...）。
- 排查/解决：同一流程换纯 ASCII 路径成功（本机已对照复现）。
  竞赛提交目录名也要求纯英文（指南 3.3.5.4），一致遵守。
- 备注："官方不支持非 ASCII 路径"为推断，未见官方明文——但结论
  （一律纯英文路径）不变。

### B2.【本队实测】license 验证失败
- 触发：2026.1 license 校验更严，学校邮箱注册的账号可能失败。
- 解决：换非学校域名个人邮箱重新注册（培训渠道建议）。

### B3.【本队实测】VSIX 双击安装失败
- 现象：弹出 Visual Studio 的 VSIX Installer，NoApplicableSKUsException。
- 解决：VS Code 扩展面板 "···" -> Install from VSIX。

### B4. 综合后时序 ≠ 签核
- 触发：拿 synth 后 WNS 写进报告当结论。
- 排查：签核一律用布线后 report_timing_summary（UG906 方法学）；
  collect_report.py 自动给 synth 状态报告打"估算"标签。
- 来源：【文献】UG906。

### B5.【本队实测】license 文件放了，Vivado 仍报 "no valid license"
- 现象：.lic 拷入 `%APPDATA%\Xilinx\` 后，Vivado 启动即退
  （exit 42），报 "a valid license was not found"。
- 根因①：Vivado 不把 `%APPDATA%\Xilinx\` 当默认搜索路径，
  必须显式指定；根因②：nodelocked HOSTID 绑的可能是
  "Microsoft Wi-Fi Direct 虚拟网卡"的 MAC（与物理 WLAN MAC 只差
  一位，如 E0/E1），极易误判成"锁了别人的机器"而放弃排查——
  实测该虚拟网卡 MAC 是可以被许可检查匹配的。
- 排查：① `Get-NetAdapter -IncludeHidden` 列全部适配器核对
  HOSTID 是否真的不在本机；② 用户级环境变量显式指路：
  `setx XILINXD_LICENSE_FILE "C:\Users\<用户>\AppData\Roaming\Xilinx\Xilinx.lic"`
  （对之后新起的进程生效，含 MCP 拉起的 Vivado）。
- 验证：设变量后 vivado_start 成功，Z-7020 综合真实跑通
  （0 错误，日志含 "Releasing license: Synthesis"）。
- 通用性：nodelocked 许可证换机/重装驱动/网卡变动都会复发，
  与具体题目无关；凡 "license not found" 先查搜索路径再怀疑 HOSTID。

### B6.【本队实测】Vivado 综合无声暴死（连 AND 门都死）
- 现象：synth_design 每次死在同一位置（"done synthesizing
  module"后、RTL 优化前），进程直接消失：不留 ERROR、不留崩溃
  对话框、MCP 侧只报 "Vivado exited before the end marker"。
  batch 直跑与 MCP 遥控同样死 → 与 MCP/脚本层无关。
- 假阴性排查（都正常，别浪费时间）：磁盘空间、物理内存余量、
  Defender 拦截记录（操作日志 Id 1116/1117）、`set_param
  general.maxThreads 1`（helper 子进程照样起，无效）。
- 根因：**提交内存（commit）耗尽**。事件查看器 → Windows 错误
  报告（Application 日志 Id 1001）里 vivado.exe 带
  `RADAR_PRE_LEAK_64` 签名即实锤。本例：16GB 内存 + 页面文件被
  "优化软件"压到 1.6GB → 提交上限仅 17.3GB，综合时父子两进程
  冲 6-7GB 撞顶，被系统无声处决。
- 排查命令：
  `Get-CimInstance Win32_OperatingSystem`（TotalVirtualMemorySize/
  FreeVirtualMemory = 提交上限/剩余）；
  `Get-CimInstance Win32_PageFileUsage`（AllocatedBaseSize 过小即中招）。
- 解决：虚拟内存改固定 8192-16384MB（注册表 PagingFiles 或系统
  属性 GUI），**重启生效**；验证 = 重跑综合。
- 通用性：与题目无关；任何小内存/被"优化"过的开发机都可能复发。
  上板前跑一次 30 秒综合冒烟即可提前暴露。

### B7.【本队实测】Win11 新版策略令 launch_simulation 必炸
- 现象：launch_simulation 的 compile 步报 `ERROR: [Common 17-180]
  Spawn failed: 系统找不到指定的文件`；而 xvlog/xelab/xsim 本体完好
  （`xvlog.bat --version` 正常输出 Vivado Simulator v2026.1）。
- 根因：Windows 11 新版（build 26100+，本例 26200）进程环境带
  `NoDefaultCurrentDirectoryInExePath=1`（注册表无此键，系进程链
  继承），cmd 不再从**当前目录**解析裸文件名；Vivado 仿真启动器
  恰以裸名调用 compile.bat → 任何工程、任何模式必炸。
- 定位实验（5 分钟五连测，可复用）：Vivado Tcl 会话内
  ① `exec cmd /c echo` ✅；② `cmd /c compile.bat`（裸名）❌；
  ③ `cmd /c .\compile.bat` ✅；④ `where xvlog` ✅
  → 仅"裸名+当前目录"这一种调用被禁，问题不在工具也不在许可。
- 修复（任选其一，均已实测）：
  ① 治本：启动 Vivado/MCP 前取消该变量——cmd 包装脚本
  `set "NoDefaultCurrentDirectoryInExePath="` 再拉起工具
  （本队 tools/vivado-mcp-server/start-mcp.cmd，整棵进程树免疫，
  launch_simulation 原生复活）；
  ② 绕开：命令行三步直跑 `xvlog → xelab -R → xsim`
  （不经过 Vivado 内部派生，实测 TB_PASS）。
- 验证：修复①后 MCP 遥控 launch_simulation 真跑通（Z-7020 AND 门
  测试平台，4/4 真值表向量全对，$finish 30ns）。
- 通用性：与题目无关；新 Win11 机器跑 Vivado 仿真必踩，GUI 模式
  同样中招；队友换机开发前建议先跑一次最小仿真冒烟。

### B8.【文献+方法】换板迁移"只改 part"三连坑（旧 XDC / 手抄 PS7 / 复用旧 bit）
- 现象：换板（如 ZC702→ZC706）后综合能过或仅报可忽略的 DRC 警告，
  板子到手一上电才炸：无输出/DDR 挂死/overlay 加载后 ip_dict 全空。
- 触发三连：
  ① 旧 XDC 原样沿用——引脚位置是**板**的属性不是器件的，换板必错；
  ② PS7 配置（DDR/MIO）从旧板手抄——两板内存型号/接线不同，配置
     不是"差不多"而是不兼容；
  ③ 旧 .bit/.hwh 继续用或只换其一——ip_dict 与硬件失配。
- 排查/解决：走 pynq-board-migration 技能的五道门禁；两道离线门禁
  （`retarget_check.py --old-xdc/--new-xdc` 端口集合核对、
  `--hwh --expect-part` 器件核对）在约板子**之前**就能拦住 ①③。
  同型号 ≠ 同板：pynq-z2 与 zybo-z7-20 完整型号相同（xc7z020clg400-1）
  却是两块板；同硅片 ≠ 同封装：zc702(clg484) 与 pynq-z2(clg400)
  逻辑相同但 XDC 不可互换（厂商文档核实，2026-10）。
- 来源：【文献】UG850/UG954（ZC702/ZC706 板级手册，2026-10 复核纠正）、DS190（家族差异）；
  门禁脚本为本队方法学沉淀（离线正反双向实测，tests/ T8a–T8e）。
  真实迁移复盘待本队 ZC706 到板后回填。

## C. Ross / MCP（官方 AI 助手）

### C1.【本队实测】MCP 握手拿到 0 个工具
- 触发：initialize 的 clientInfo 用了自造客户端名。
- 解决：用标准名（如 claude-code）即返回完整工具集。

### C2.【本队实测】doc-search 参数被 schema 拒绝
- 触发：tool/version 传了字符串。
- 解决：这两个参数是数组（如 ["Vivado Design Suite"]、["2026.1"]）。

### C3.【本队实测】MCP 守护进程"消失了"
- 现象：空闲约 5 分钟后进程退出。
- 说明：正常节能行为，下次调用自动拉起，不是故障。

### C4.【本队实测】长命令（综合）超时
- 说明：连接超时不中断 Vivado；轮询 status 的 is_command_running，
  结束后读 last_completed_code。
