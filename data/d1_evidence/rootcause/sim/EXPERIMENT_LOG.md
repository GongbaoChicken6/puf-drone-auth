# 仿真注入实验记录 — H1 vs H2 裁决（ar-sim-inject-r1）

时间：2026-11-01 15:51–16:40（Asia/Shanghai）。工具链：Vivado 2026.1 xvlog/xelab/xsim（D:\vivado\2026.1\Vivado\bin），iverilog（scoop）交叉复核。
约束遵守：仓库文件零修改（git status 仅新增 data/d1_evidence/rootcause/ 下未跟踪文件）；全部新增/改造文件在本目录。

## 本目录新增文件（全部仅存于 rootcause/sim）

| 文件 | 说明 |
|---|---|
| ro_ring_timed.v | 行为级带周期环振（HALF_PS 参数，ps）——替代零延迟原语的唯一注入载体 |
| ro_array_timed.v | src/rtl/w2_array/ro_array.v 的副本，唯一改动：u_ro_ring 换成 ro_ring_timed（每环独立周期）；ro_div/同步/边沿/计数/锁存逻辑逐字保留 |
| tb_ro_real_x.v | E5：真 ro_array（零延迟环，en 恒 1） |
| tb_ro_real_en.v | E6：真 ro_array，en 0->1 振荡探针 |
| tb_chip_inject.v | E7：5 颗"芯片"（A/B/C/M/M2）经真 ro_div(/32)+2FF 同步+边沿+1ms 计数窗 |
| tb_puf_path_inject.v | sim/tb/tb_puf_path.v 副本：黄金断言改为打印 R1（terminal_fsm 全链 S_PUF_*），频率向量经 ro_array_sim 默认路径注入 |
| freq_*.mem ×9 | 注入频率向量（确定性公式见下） |
| mc_hd_curve.py | 蒙特卡洛 HD–失配灵敏度曲线（用冻结黄金模型 puf_model，RTL↔模型一致性由 tb_puf_path 黄金锁背书） |
| e6_raw.log / e7_raw.log / e_system_matrix.log / e_mc_curve.log / xvlog.log / xelab.log | 各实验原始输出 |
| run_*/ | 每个 fixture 的隔离运行目录（cwd 相关默认路径机制） |

fixture 公式（i=0..15，deterministic）：base=仓库 sim/testvectors/puf_tb_freqs.mem（3330..9507，2.85 倍展开模拟板上 W1 实测 100~307MHz）；
chip_pk: f'[i]=round(f[i]*(1+d_i/1000)), d_i=((53*i) mod (2k+1))−k（k=5,10,20,50,100 千分率）；common105: f*1.05；matched: 全 5200；matched_wiggle: 5200±1。

## 命令（workdir = rootcause/sim）

    D:\vivado\2026.1\Vivado\bin\xvlog.bat  <repo ro_ring.v ro_div.v ro_array.v challenge_decode.v> ro_ring_timed.v ro_array_timed.v tb_ro_real_x.v tb_ro_real_en.v tb_chip_inject.v
    D:\vivado\2026.1\Vivado\bin\xelab.bat -debug typical tb_ro_real_x   -s snap_ro_x
    D:\vivado\2026.1\Vivado\bin\xelab.bat -debug typical tb_ro_real_en -s snap_ro_en
    D:\vivado\2026.1\Vivado\bin\xelab.bat -debug typical tb_chip_inject -s snap_chip
    xsim snap_ro_x -runall          # E5
    xsim snap_ro_en -runall         # E6（挂死 -> job_kill，日志 e6_raw.log）
    xsim snap_chip -runall          # E7（后台 24 s）
    xvlog -d PUF_MODEL_SIM <全部仓库 RTL> <repo ro_array_sim.v> tb_puf_path_inject.v ; xelab tb_puf_path_inject -s snap_pufinj
    每个 fixture：run_<tag>/sim/testvectors/puf_tb_freqs.mem = fixture 副本，快照拷入 run_<tag>/xsim.dir/，在 run_<tag> 内 xsim snap_pufinj -runall
    （注：xsim.bat 对 --testplusarg NAME=VALUE 会因 cmd 把 '=' 当分隔符而拆参失败，故用 cwd 默认路径机制注入）
    iverilog -g2001 tb_ro_real_x.v <repo 三文件> && vvp   # E5 交叉复核
    python data\d1_evidence\rootcause\sim\mc_hd_curve.py  # MC 曲线（cwd=仓库根）

## 结果汇总

### E5 真环（零延迟，en 恒 1）xsim 与 iverilog 一致
16 环计数全 0 => freq[B]>freq[A] 恒假 => R1 恒 64'h0（与挑战、芯片无关的常数）。

### E6 真环 en 0->1（e6_raw.log）
en=0 期环静态解 ro=1；en 拉高后 xsim 陷入零延迟 delta 环死循环（10 分钟无进展，job_kill 收证）——环振是纯传输延迟现象，事件驱动仿真不可表示。

### E7 带周期环（真 ro_div/同步/计数链，1ms 生产窗，4 黄金种子）
| 芯片 | 每环半周期 ps | 计数（实测/解析一致 ±1） | R1(A) | 与 A 的 HD/256 |
|---|---|---|---|---|
| A ±1% 抖动 | 2967..3024 | 5167..5260 | 232785fa816959b5 | — |
| B = A ±5%/环 | 2822..3124 | 5002..5537 | a9254ddba56ce1f1 | 80 |
| C = A ±10%/环 | 2673..3251 | 4806..5845 | dd987b0d7cb6e6ca | 224 |
| M 全等频 | 3000 | 全 5209 | 0000000000000000 | 124 |
| M2 全等频+5% | 3150 | 全 4960 | 0000000000000000 | 与 M 的 HD = 0 |

### 系统级注入（terminal_fsm 全链，board 级 2.85 倍展开向量，4 种子 256 bit）
| 注入 | 与基线 HD |
|---|---|
| base | R1 = 6677fea45a09061f / d5b6f7144a4181df / 872e6a55e752cf34 / aed5f9a3967ed9c2（=tb_puf_path 黄金，链路正确性锚） |
| ±0.5%/环 | 0 |
| ±1%/环 | 1 |
| ±2%/环 | 1 |
| ±5%/环 | 6 |
| ±10%/环 | 15 |
| 共模 ×1.05（全环） | 0（完全尺度不变性） |
| 全等计数 | R1 恒 0（四种子全零，芯片无关常数） |
| 全等±1 计数 | R1 稀疏非零（A=0000a07c80da5faa 等） |

### 蒙特卡洛（puf_model，300 次/点，均匀 ±k% 每环独立失配）
k=0.1/0.25/0.5% -> mean 0.0 max 0；1% -> mean 0.2 max 3；2% -> mean 0.8 max 8；5% -> mean 4.5 max 15；10% -> mean 10.9 max 27；20% -> 23.1；30% -> 34.8。
共模 ×1.05/×1.10/×0.90 -> HD=0。被比较对相对间距：min 1.16%，p25 17.9%，中位 29.5%，p75 44.5%；<2% 的对仅 4/256。

## 裁决
H1（RTL 响应不依赖频率）不成立：差分频偏注入下 R1 改变（±5% -> HD 6/256@2.85x展开、80/256@±1%展开；±10% -> 15/256）。
H2（频率依赖但芯片间差异被抹平）成立并精确化：R1 只取 16 计数的相对序（尺度不变，共模频偏 HD 恒 0）；当两芯片共享同一系统性环频排序（同一 bitstream 的布线不对称，W1 实测 3x 展开、对间距中位 29.5%）而硅片每环失配仅 ±1% 量级时，HD=0~3 —— 与两板实测 HD≤1~2、轮内漂移 1~4 bit 定量吻合。指纹是 bitstream（布局布线）的函数，不是硅片的函数。
板上全等频退化态（R1 恒 0）已被服务器审计排除（模板两两 HD 约 32 => 环计数有真实非平凡展开）。
闭环缺口：需板端直接回读 16 个 ring_freq 计数值（W2 频率直发或 ILA）以确认排序系统性来源。
