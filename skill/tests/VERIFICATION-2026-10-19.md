# 端到端验证报告(2026-10-19)

按"校验 → 发现问题 → 修复 → 复验"流程,对本技能包与本地工具链做了
四轮全链路真实验证(非纸面检查;综合与仿真均为真实运行,日志留档)。

## 环境

- Windows 11 Home 26200 / 16GB RAM / Vivado 2026.1(xc7z020clg484-1)
- vivado-mcp-server 2026.9.1(HTTP 18090 / stdio-bridge)+ nodelocked 许可证
- 校验脚本:`tools/mcp-full-verify.py`(工作区),7 项检查自动判分

## 四轮结果

| 轮次 | 结果 | 发现/动作 |
|---|---|---|
| 第 1 轮 | 4/7 | 综合中途 Vivado 无声退出;离线测试 13/13 通过 |
| 第 2 轮 | 4/7 | `maxThreads 1` 无效(非多线程问题);日志+WER 定位到 RADAR_PRE_LEAK_64 |
| 第 3 轮 | 6/7 | 页面文件 1.6GB→8-16GB(需提权重启)后**综合通过**;仿真报 Spawn failed → 定位到 Win11 策略变量 |
| 第 4 轮 | **7/7** | 取消 `NoDefaultCurrentDirectoryInExePath` 后**原生仿真通过** |

## 第 4 轮明细(全绿)

| 检查项 | 结果 | 证据 |
|---|---|---|
| MCP 握手 | PASS | serverInfo: vivado-mcp-server 2026.9.1 |
| 工具注册 | PASS | 11 个工具完整 |
| Vivado 拉起 | PASS | 6s 启动,TCL 模式 |
| 版本/器件 | PASS | Vivado v2026.1;get_parts 含 xc7z020clg484-1 |
| **真实综合** | PASS | 55s,Z-7020 AND 门,0 错误,Synthesis 许可正常检出/释放 |
| **真实仿真** | PASS | 8s,launch_simulation 原生流程,xsim 真值表 4/4 向量全对(TB_PASS,$finish 30ns) |
| 优雅关闭 | PASS | vivado_stop 成功 |

## 过程中发现并修复的机器级问题(与技能包本身无关)

1. **B6 提交内存耗尽**:页面文件被"优化软件"压至 1.6GB,综合必炸。
   修复:固定 8192-16384MB(提权+重启),综合由随机死 → 稳定通过。
2. **B7 Win11 策略**:`NoDefaultCurrentDirectoryInExePath=1` 继承进
   Vivado 进程树,cmd 不再从当前目录解析裸脚本名,launch_simulation
   必炸。修复:启动包装脚本取消该变量(start-mcp.cmd)。
3. **B5 许可证搜索路径**:Vivado 不搜 %APPDATA%\Xilinx,须
   `XILINXD_LICENSE_FILE` 显式指路(此前已修复并验证)。

三个坑的完整排查链均已沉淀至 `pitfalls/pynq-pitfalls.md`(B5/B6/B7),
均附触发条件、定位实验、修复方法与通用性说明,可直接被其他队伍复用。

## 结论

技能包 13/13 离线测试通过;工具链 7/7 端到端真实验证通过。
具备交付条件。板上(live)项目仍按 README 标注为"待板",不冒充已测。
