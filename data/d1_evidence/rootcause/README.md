# rootcause/ 证据包导览（auto-review 后补，2026-11-01）

> **历史取证存档。** 本文记录的“双板均 PASS、唯一性存疑”是修复前的历史状态。最终结论与修复验证见 1102 交叉认证 2×2 矩阵（设计报告 3.2.3 节），板端原始日志 `metrics/logs/1102_seed2_uniqueness.log`（结果矩阵）与 `metrics/logs/1102_crossboard_hd_stats.log`（跨板 HD 统计）。

## 环境清单
- Vivado 2026.1（D:\vivado\2026.1，xvlog/xelab/xsim + 板级构建）；iverilog 14.0（E5 交叉复核）；Python 3.13（numpy/pyserial）；Windows（路径分隔符注意）
- 输入锚点：templates_snapshot_tid1_20261101.json（=取证当时 data/templates/templates.json 只读快照，SHA256 02CEF985…C23B3）；metrics/logs/1101_spoof_bothpass_uniqueness_suspect.log（在线帧原文；文件名已英文化）
- 相关提交：c348baa(finding) 062c776(consensus) a94775f(build+prereg) 1760b72(bit，含失实陈述已由 be87350/2b02634 勘误) ce7fc78(v3断言)

## 复现矩阵（报告数字 ← 脚本 ← 输入）
| 报告数字 | 脚本 | 输入 | 照抄命令（仓库根下） |
|---|---|---|---|
| 模板两两HD均值32.0/无卡死位 | analyze_template2.py | data/templates/templates.json（运行库） | python data/d1_evidence/rootcause/analyze_template2.py |
| 全序反推 [4,11,15,…] 复算HD=0；在线三轮4/1/3 | rtl_r1_order_reconstruction_v3.py（权威版） | 同上 + 1101日志 | python data/d1_evidence/rootcause/rtl_r1_order_reconstruction_v3.py（末行须见 F_ASSERT_OK） |
| v1（已废弃，仅反推段可参考；114行字面量损坏重跑=97） | rtl_r1_order_reconstruction.py | 同上 | 见文件头废弃横幅 |
| 蒙特卡洛 k 曲线（±1%→mean0.2） | sim/mc_hd_curve.py（seed=20261101） | — | python data/d1_evidence/rootcause/sim/mc_hd_curve.py |
| E5 真环零延迟（R1≡0） | sim/e5_raw.log（16 环计数全 0） | sim/tb_ro_real_x.v | 复跑命令见 sim/EXPERIMENT_LOG.md §E5 |
| 系统级注入矩阵（pm1=0/pm5=7 勘误后） | sim/e_system_matrix.log | sim/freq_*.mem | 见 sim/run_*/xsim.jou 内完整 xsim 命令（含 cwd） |
| 双 bit 布局零重叠 | build/board_zc706_seed2/ring_sites_seed2.rpt；生产侧结论见 1101_ROOTCAUSE_consensus.md 勘误段 | 两个 bit | seed2 站点坐标见 rpt；生产布局复跑落位为 X1Y4/X1Y5，零站点重叠 |
| 预登记带宽（中位129 p5-p95 87-168） | 原 MC 计算脚本未随包分发；数值固化在 seed2_board_preregistration.md「带宽推导」段 | 模板快照 | 见 seed2_board_preregistration.md |

## 注入机制说明
系统级注入利用 ro_array_sim 的 cwd 默认路径机制（+PUF_FREQ_FILE 经 xsim.bat 传参在 cmd 下被 '=' 拆参不可用）；run_*/ 目录为当时的运行快照，xsim.jou 记录完整命令与 cwd。

## 编码说明
e_mc_curve.log 为 UTF-16LE、e7_raw.log 为 GBK（原始工具输出原样保留，证据哈希不变）；UTF-8 副本：e_mc_curve_utf8.txt / e7_raw_utf8.txt。

## 已知边界（如实声明，非本包缺陷）
- CI 不编译 w3_top_zc706.v（clk_wiz IP；wrapper 由三元素文本锁覆盖，见 ci_regression.ps1 M-LOCK）——板级构建是 wrapper 语法的唯一把关。
- 当前两枚 bit 未内嵌 USERID（生产 bit 为不可重建基线；seed2 已验证入库）。build_w3_board_seed2.tcl 已加入 USERID 属性，自 seed3 起生效。
- ring_sites_seed2.rpt 为历史证据（含 32 行层次空行）；新构建脚本已改为仅叶子+区域计数。
- 仿真侧真环不可仿（零延迟组合环，E5/E6 实证）——硅相关性只能板端验证，本包已用落位对比+线上帧弥补。
