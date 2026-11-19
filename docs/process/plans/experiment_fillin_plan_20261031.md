# 实验补数据执行计划（论文回填证据专项）

> 生成：2026-10-31 23:30（make-plan 产出，Phase 0 事实调查由 mp-inv-pc / mp-inv-board 两子代理完成，行号引证见各节）
> 目标：补齐论文全部【待板】空白与未用数据，产出可追溯证据。死线：11-03（保守）/ 11-04 18:00（组委）。
> **状态（2026-10-31 23:50 更新）**：Phase 0 ✅｜Phase 1 ✅ 全绿（13 份证据落盘 data/rerun_evidence/，ML 复跑 JSON 逐字节一致，CI 18/18 重造成功）｜Phase 5.4 ✅（1101_timing_decomposition.md，板A今晚实测 CHALLENGE→CONFIRM 23ms、板B 31-32ms）｜Phase 2 半成（板A re-enroll 100 CRPs + stable 64/64 + serve 1 轮 CONFIRM 已由用户 23:31 完成；**论文口径注意：今晚实跑 100 组≠论文旧文 112 组**；还需补 10 轮 hd=0 统计）｜Phase 3-6 待板边人工执行。
> **5.3 修正**：两板 CRP 池种子独立随机，templates.json 无法直接对比——板间 HD 分布改从 Phase 3 假冒实验的 [DIAG] 每种子 hd 行提取（3-5 轮×4 种子=12-20 个样本）。
> 执行原则（用户既定铁律）：①先全量虚拟验证再上板；②证据必须落盘、断言用正向哨兵（「超时没报错」不算数）；③PMOD/接线严禁带电插拔（SW1 断电操作）；④web 桥一律 --data-dir web/.dev-data 隔离运行。

---

## Phase 0 · 前置核查（5 min，每次开工先跑）

```
Set-Location D:\puf-drone-auth
# 0.1 环境自检（预期 3.13.5 / pyserial 3.5 / sklearn 1.8.0）
python --version; python -c "import serial,sklearn;print(serial.__version__,sklearn.__version__)"
# 0.2 模板库现状（re-enroll 前后各查一次；目标最终含 "1","2"）
python -c "import json;print(sorted(json.load(open('data/templates/templates.json')).keys()))"
# 0.3 密钥库（tid=1 应在；tid=2 需 setkey 后出现）
python -c "import json;print(sorted(json.load(open('data/device_keys/device_keys.json'))['terminals'].keys()))"
# 0.4 COM 口重认（CH340 拔插会漂移，按 VID:PID=1A86:7523 认）
python -c "import serial.tools.list_ports as l; [print(p.device,p.hwid) for p in l.comports()]"
# 0.5 git 现状
git status --short
```

**验收**：0.1 版本与括号内一致；0.4 找到两口（今晚口径 COM6=LinkE/板A、COM9=CH340）。
**反模式**：不要假设 COM 号不变（COM10→11、COM8→9 有前科，W3 报告 §7-8）。

---

## Phase 1 · PC 侧证据补跑（纯 PC，约 25–40 min，可与板级接线并行）

**目的**：补齐 auto-review 发现的 8 条可回填测试运行证据；重造 repo 缺失的 18/18 CI 日志；兼作上板前虚拟验证门禁（铁律①）。
**落盘规则（mp-inv-pc 实测的关键坑）**：「.gitignore:8」全局忽略 *.log → 证据一律 **.txt 后缀**，目录 data/rerun_evidence/。

```
Set-Location D:\puf-drone-auth
New-Item -ItemType Directory -Force data\rerun_evidence | Out-Null

# 1.1 DoS 洪泛（5 用例，<10s；论文表3-2 DoS行【模型】升【实测】的证据）
python -m pytest tests/test_dos_flood.py -v 2>&1 | Tee-Object data\rerun_evidence\1101_dos_flood_pytest.txt
# 1.2 互操作（7 用例，<15s）
python -m pytest tests/test_interop_rtl_model.py -v 2>&1 | Tee-Object data\rerun_evidence\1101_interop_pytest.txt
# 1.3 串口读语义回归（TestServeReadSemantics 1 用例，<5s）
python -m pytest "tests/test_serial_server.py::TestServeReadSemantics" -v 2>&1 | Tee-Object data\rerun_evidence\1101_serve_read_semantics.txt
# 1.4 威胁 PoC（3 case，<10s，纯进程内）
python scripts\threat_poc.py --case all 2>&1 | Tee-Object data\rerun_evidence\1101_threat_poc.txt
# 1.5 pytest 全量（111 用例，<1min；CI 口径之外的补充证据）
python -m pytest tests -q 2>&1 | Tee-Object data\rerun_evidence\1101_pytest_all.txt

# 1.6 变异测试复跑（<30s）——⚠ 先复制目录，绝不原地跑（会覆盖 build/muttest 原始证据）
New-Item -ItemType Directory -Force build\muttest_rerun | Out-Null
Copy-Item build\muttest\*.v build\muttest_rerun\
Push-Location build\muttest_rerun
& "D:\vivado\2026.1\Vivado\bin\xvlog.bat" uart_tx.v uart_rx.v tb_uart_rx.v 2>&1 | Tee-Object ..\..\data\rerun_evidence\1101_muttest_xvlog.txt
& "D:\vivado\2026.1\Vivado\bin\xelab.bat" tb_uart_rx -s sim_mut 2>&1 | Tee-Object ..\..\data\rerun_evidence\1101_muttest_xelab.txt
& "D:\vivado\2026.1\Vivado\bin\xsim.bat" sim_mut -runall 2>&1 | Tee-Object ..\..\data\rerun_evidence\1101_muttest_xsim.txt
Pop-Location

# 1.7 ML 实验 A/B/C 复跑确认（seed=42 与论文口径一致；⚠ 会覆盖 data/ml_attack 6 个入库产物 → 先备份）
Copy-Item data\ml_attack data\ml_attack_backup_1101 -Recurse -Force
python -m src.python.evaluation.ml_attack --exp A --out data\ml_attack --seed 42 2>&1 | Tee-Object data\rerun_evidence\1101_ml_expA.txt
python -m src.python.evaluation.ml_attack --exp B --out data\ml_attack --seed 42 2>&1 | Tee-Object data\rerun_evidence\1101_ml_expB.txt
python -m src.python.evaluation.ml_attack --exp C --out data\ml_attack --seed 42 2>&1 | Tee-Object data\rerun_evidence\1101_ml_expC.txt
# 复跑后 git diff data/ml_attack 应为零变化（环境版本已核对一致）；有差异立即停下查因

# 1.8 全量 CI 门禁（3–6 min；重造 repo 缺失的 18/18 日志；Vivado 硬编码 D:\vivado\2026.1，脚本 :25）
powershell -File scripts\ci_regression.ps1 2>&1 | Tee-Object data\rerun_evidence\1101_ci_regression_full.txt
```

**验收（正向哨兵，逐条 grep 证据文件）**：
- 1.1「5 passed」；1.2「7 passed」；1.3「1 passed」；1.5「111 passed」
- 1.4「THREAT_POC PASS: all 3 case(s) passed」
- 1.6「TB_UART_RX_FAIL errors=3」（变异体**必须** FAIL 才证明测试有效）
- 1.7 每段「ML_ATTACK_DONE」+ git diff data/ml_attack 为空
- 1.8「=== 18/18 PASS, 0 FAIL ===」+ ENROLL_NEG PASS 行
**反模式**：①原地跑 muttest；②ML 复跑前不备份；③证据用 .log 后缀（进不了 git）；④把「命令没报错」当验收——必须 grep 到哨兵行。

---

## Phase 2 · 板 A re-enroll + 对照组多轮统计（~15 min）

**前置**：板 A bit 已烧好（今晚 23:21:24 PROGRAM_OK；断电过则重烧：vivado -mode batch -source build\tcl\program_zc706.tcl -tclargs build\board_zc706\w3_top_zc706.bit，约 8s）。检查 DS35 心跳 **0.75Hz 慢闪**（~3Hz 快闪=seed_fault 禁止 enroll，runbook L284）。

```
Set-Location D:\puf-drone-auth
python -m src.python.server.main --port COM6 --baud 115200 2>&1 | Tee-Object data\d1_evidence\1101_板A_reenroll_serve.txt
```

REPL 序列（main.py HELP_TEXT L810-820 实证语法；serve 必须在 enroll 同一 REPL 里接着输，HANDOFF L39）：
```
setkey 1 0001020308090a0b10111213   # 保险性重复（tid=1 密钥幸存，可跳过）
enroll 1 100                        # ~1min → 112 对；预期 [ENROLL] terminal 1: 112 CRPs stored ... stable bits X/64
status                              # 确认 terminal 1: 112 CRPs + 池余量
serve                               # 按板A SW7 认证，采 10 轮 hd=0 对照数据
```

**注意**（HANDOFF L35-36、runbook L271-272）：enroll 后**第一次按 SW7 可能 DS8+DS10 双亮（一次性 R2 校验失败）→ 再按一次即 PASS，不要据此回滚**；连续多轮双亮才是密钥错。轮节奏：SW13 点一下 → SW7 按住 1s，轮间隔 ≥5s。
**验收**：「CONFIRM tid=1 OK -- mutual authentication complete」≥10 行、全部 hd=0；每轮 C2/hd 抄入 data/rerun_evidence/1101_板A_多轮统计.csv（列：轮次,C2,hd,结果,备注）——同时补论文缺的「板级轮次 N 量化」。
**反模式**：①另起进程跑 serve；②心跳快闪时 enroll。

---

## Phase 3 · 板 B 准备 + 假冒实验（论文最核心空白，~30 min）

**前置**：板 B 烧 bit（断电即丢、谁持有谁烧）：vivado -mode batch -source "paper\paper\交接包\板卡交接_ZC706板B调试\脚本\prog_w3_b.tcl"（线缆串号 210251A04F2C 过滤，成功标志 W3_PROGRAM_OK_BOARD_B；或通用 program_zc706.tcl）。板 B 三根线接**你的 PC** 的 USB-TTL。

```
python -m src.python.server.main --port <板B_COM> --baud 115200 2>&1 | Tee-Object data\d1_evidence\1101_板B_setkey_enroll.txt
```
```
setkey 2 0001020308090a0b10111213   # ⚠ 铁律：必须先于 enroll 2（颠倒是自动铸随机钥 → R2 恒 BLOCKED 且无提示，HANDOFF L76）
enroll 2 100
serve                               # 板B SW7 → CONFIRM tid=2, hd=0（自证板B健康）→ Ctrl-C 退出
```

**假冒实验**（HANDOFF L40-48 原式；认证发生在 tid=1 的基站进程）：
1. 板 B SW12 拨 **0001**（ON=1，冒充板 A），点一下 SW13
2. 主 PC 重开 main.py --port COM6 → serve（tid=1 模板库）→ 按板 B SW7
3. 预期：**REJECT + hd≈32 + DS10 单亮** → 拍照 DS10（IMG_1101_B_假冒REJECT.jpg）
4. 重复 3–5 轮（间隔 ≥5s），日志落盘 data\d1_evidence\1101_板B_假冒实验.txt
5. 结束：板 B SW12 拨回 0010；**全程板 A 不按 SW7**

**验收**：REJECT 行 ≥3 条且 hd 均在 28–36 区间；与 Phase 2 的 hd=0 组成对比表「(A,A)=0 vs (B→A)≈32」→ 表3-1 唯一性/不可克隆两行板上数据。
**反模式**：①跳过/颠倒 setkey 2；②两板同时按 SW7；③只跑 1 轮（论文要分布）。

---

## Phase 4 · 无线 0xFE 毛刺闭环 + 无线 CONFIRM（增值，视时间）

**现状**（今晚实测）：22:52 复测 COM9→COM6 5/5 干净全通；COM6→COM9 每帧固定多一个前导 0xFE 字节（1/5 判 FAIL）——链路基本通，剩发送侧首字节毛刺一个疑点。

排查顺序：
1. **对调定位**：交换两块 HC-12 位置再跑 python data\d1_evidence\1031_relay_check.py COM6 COM9 <log> —— 0xFE 跟模块走=模块问题；跟 COM 口走=USB-TTL/线问题
2. 确认 SET 引脚已脱离 GND 悬空（≥80ms 后进透传）；两块 **5V 独立供电**（勿接 J58 pin11）；J58 pin1/pin5/pin9 接线 + 共地
3. 若确认是固定前导毛刺：MAVLink 帧解析器有噪声前缀容忍（tb_frame_parser T2 已验证），可先以剥离前导法确认「毛刺非断链」
4. 终验：relay_check 双向 5/5 GRADUATED → 板 A 挂 C001 + PC 侧挂 A-PC(C001) → serve → SW7 → **无线 CONFIRM tid=1**

**验收**：「WIRELESS_PAIR_VERDICT: GRADUATED」+ 无线「CONFIRM ... OK」落盘。
**注意**：论文图 2-2 实物照**无线不入镜**（红线#4，图表制作方案 L192）；无线照片单独归证据目录。

---

## Phase 5 · 增值实验（D2/D3 有余力做）

**5.1 断电重放复测 ×3**（runbook Stage 6 L312-353 既定规程）：记 C2 → SW1 断电 5s → 重烧 bit → 新 C2 必不同（上电视熵重采样）→ 旧 RESULT 跨断电必失配 → 截图。10-27 已有三轮零 c2reset 实测可引用；重采按同规程。验收：每轮「旧 C2 被 RESULT_REPLAY 拒」或「C2 已翻新」证据行。
**5.2 温漂简化版**（无既定可执行规程——mp-inv-board 缺口⑤，本计划新设计）：
- 常温组：serve+SW7 10 轮 hd 记录；加热组：暖手宝贴 PL 散热区，红外测温枪每 +5°C 记板面温度，ΔT 至 +15~20°C 再采 10 轮（70°C 硬停、ΔT 上限 30°C，project_design L246-252 口径）
- 验收：两组 hd 均值对比 + 全部仍在通过阈值内（≤6）→ 论文 §1.3-1 温漂【待板】与 §2.2.4(1) 误码率统计一次补齐；个别轮入灰区（7–15）也是有效数据（灰区机制被真实触发）
**5.3 板间 HD 分布**（纯 PC，模板齐后任意时刻）：~15 行脚本从 templates.json 读 tid=1/2，对共同种子算 HD 分布（均值/最小/最大）→ 表3-1 指纹唯一性从【模型】36.49 升格板间实测。
**5.4 33ms 端到端整理**（纯 PC）：从 W3_BoardB_Bringup_Report\logs\serve_fix.log 毫秒时间线抄时序分解表（CHALLENGE→R1 16ms / RESULT→CONFIRM +16ms）→ 回填论文表1-1/表3-3 并列实测口径。

---

## Phase 6 · 照片与截图（随各 Phase 顺手拍）

论文 5 张实物照（锚点：图表制作方案 L192 + 学长样本口径；命名 IMG_日期_板号_项目）：
①双板+PC 基站组网全景（露 SW12：ID1=0001/ID2=0010）②正面全景 ③斜 45° ④PMOD/电平移位接口细节 ⑤双终端并排（**无线不入镜**，红线#4）
实板日志截图 3 张（论文 §3.2.3 待补项）：⑥注册 enroll 输出（[ENROLL] 行）⑦认证通过（CONFIRM 行 + Web 面板）⑧假冒 REJECT（hd≈32 + DS10）。

---

## Phase 7 · 终验与交付

1. **证据↔论文空白映射清点**：对照【待板】8 类逐条打勾（假冒/温漂/误码统计/照片×5/截图×3/断电复测/无线/33ms）
2. **git 入库**：.txt 证据正常 add；.log 证据 git add -f；ML 复跑零差异则保留原产物（备份目录留到提交后删）
3. **台账哨兵**：在论文**真实源**（⚠ 不是 paper/正文 旧 md——PDF 另有更新源）grep「【待板」逐条确认：已填数（带口径）/有意保留
4. **metrics 刷新**：cd web; python tools\gen_metrics.py --repo-root ..（禁手改）
5. 更新本计划各 Phase 状态，向 Lead 报告

---

## 风险与回退
- COM 口漂移 → 每次 Phase 0 重认（VID:PID=1A86:7523）
- 假冒 hd 不落 28–36 → 先确认 Phase 2 对照组健康，再查板 B 模板是否被桥污染（模板键应只含 1/2 + 演示键）
- 无线 0xFE 当晚闭环不了 → 降级：论文无线段维持「链路级中继零误码（10-30 已证）+ 板上列入扩展」，不阻塞主线
- 温漂触发灰区/拒绝 → 如实记录（灰区机制价值证据），勿删数据
- 「1031_烧bit.log」为 UTF-16 编码，读取需按 UTF-16LE 解码（mp-inv-board 缺口⑦）
- prog_w3.tcl 的 HANDOFF 描述与脚本实况不符（实无串号过滤，mp-inv-board 缺口②）：执行认 prog_w3_b.tcl / program_zc706.tcl，文档待修正
