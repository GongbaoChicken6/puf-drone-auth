# A1 阶段 5 共识综合（CONSENSUS — 终审）

> 终审代理：consensus（独立于三位审查员；全部结论以本轮重新读取文件 + 重跑真实命令的实测为准）
> 输入：canary_stats.json（1×P2+4×P3）、p5_spec.json（4×P3）、ci_gate.json（1×P0+1×P2+3×P3），共 14 项原始发现
> 环境：Windows PowerShell 5.1（系统唯一解释器，无 pwsh7）、Python 3.13.5（C:\Users\<user>\AppData\Local\Programs\Python\Python313）、Vivado 2026.1 路径 D:\vivado\2026.1
> 实验位置：$env:TEMP\a1p5_consensus\（仓库内零新增文件，仅本 CONSENSUS.md）

## 门禁判定

**PASS**

- P0 = 0（1 项原始 P0 已修复并本轮复验通过，计 FIXED-VERIFIED）
- P1 = 0（原始即为 0）
- P2 = 0（2 项原始 P2 已修复并本轮复验通过，计 FIXED-VERIFIED）
- P3 存量：9 项 FIXED-VERIFIED + 3 项 DEFERRED-ACCEPTED（含 1 项流程性移交阶段 6）
- 终审新增 2 项 P3 备注（不阻塞，见 §5）

## 1. 六组修复逐一复验

### 修复 1 [P0] gen_speck_vectors.py --check 恒真且销毁证据 → **VERIFIED**

代码结构（本轮全文读取）：
- `build_content()`（L136-166）：纯计算向量与内容，唯一副作用 `os.makedirs(OUT_DIR, exist_ok=True)`，不触碰 OUT_FILE；
- `generate()`（L169-190）：唯一写文件路径（含统计打印与 `_cross_impl_check`）；
- `check()`（L214-231）：`expected, _ = build_content()` 纯计算 → 读盘比对 → 永不写；L230 stale 分支现可达。

实测（篡改-检查-恢复三段，mem 文件 sha256 前 16 位追踪）：
| 步骤 | 结果 |
|---|---|
| pristine --check | exit 0，"PASS: ... up to date (1175 vectors)"，sha=b22a4af3b084af1c |
| 篡改 NSA_KAT 行 ct 首字符 '4'→'0' | 文件变更（sha=59d3eed5a96e7b33） |
| stale --check | **exit 1**，"FAIL: ... is stale (run gen_speck_vectors.py to regenerate)"，**文件保持篡改态 sha 未变（证据不再被销毁）** |
| 恢复备份后 --check | exit 0 PASS，文件字节 === 原件 |
| git status --porcelain -- sim/testvectors | 空（仓库无残留变更） |

### 修复 2 [P2] 金丝雀宽扇入逃逸 → **VERIFIED**

代码核对（本轮全文读取 + 数学复验）：
- **C4** `check_exact_linear`（L126-139）+ `gf2_span_contains`（L104-123）：以最高置位为 pivot 的 GF(2) basis 归约（插入时消元至 pivot 空缺），查询时按 pivot **从高到低**对 target 消元——标准且正确；每 basis[piv] 最高位恰为 piv（插入过程保证），从高到低消元不回扰高位。basis = 64 输入列 + 全 1 常数列（L134，覆盖仿射常数项）；N=256 样本 > 65 未知量 → 完全线性/仿射映射残差必为 0（FAIL），随机列落入 ≤65 维子空间概率 2^(65-256)（零假阳性声明成立）。
- **负对照 3 类**（L157-180）：(a) ~C2 对角仿射（order1 饱和或 C4=64）；(b) 宽扇入 GF(2)（rows=`rng.getrandbits(64)|1` 保证非退化，要求 C4=64）；(c) xor-tree 折叠（要求 C4=64）。escaped≠0 即 exit 1。
- **per-key 独立样本流**（L214）：`rng = random.Random(SEED ^ int.from_bytes(key[0:8], "little"))`。
- **docstring**（L22-24）：检测边界诚实声明（能抓=任意完全线性/仿射含宽扇入/CRC 类、对角仿射、1 轮饱和；抓不住=≥2 轮轮数削减与高阶非线性）。
- **统计注释修正**（L18-21）：C1 族错误率 ~4.1e-3、期望最大值 2.9/4.1/4.9σ、C3 实测典型 ~5.0σ 边际 1σ——与 canary_stats 审查的独立复算值（4.054e-3 / 2.88/4.08/4.85σ）一致。
- **输出措辞**（L238-240）：弱化为 "PASS: no affine/GF(2)-linear structure detected; order-1/2 bit correlations within noise bounds"。

实测：两次运行均 exit 0，输出**逐字节一致**；`[C0] ... 3/3 caught`；两密钥数值互异（W3-demo order1=0.2031 vs fixed-random order1=0.2109）证明独立采样生效（旧版共享样本时两密钥同值 0.2344）；两密钥 exact-linear bits 均 0/64。

### 修复 3 [P2] 证据漂移（定稿日志 ↔ 最终工件） → **VERIFIED**（附 1 项 P3 新备注，见 §5-N1）

ci_12tb_final_run.log（UTF-16LE 解码后）核对：
- "=== 12/12 PASS, 0 FAIL ===" 且逐行 12 个 [PASS]（含 tb_w3_top）；
- "Ran 44 tests in 0.234s" + "OK"；
- 金丝雀两行与**当前脚本本轮实跑逐字符一致**（W3-demo: balance 3.00s | order1 0.2031 @bit46->25 | order2 0.2734 @(42,53)->2 | exact-linear bits 0/64；fixed-random: 2.25s | 0.2109 @bit24->46 | 0.2656 @(29,56)->51 | 0/64）——证据日志确由最终工件生成；
- "CANARY PASS: no affine/GF(2)-linear structure detected..."（新措辞）；"PASS: ...speck_random.mem is up to date (1175 vectors)"（--check 可闻行入日志）。
- 备注：日志含 "System.Management.Automation.RemoteException" 一行（已知未修项，见 §3）。

### 修复 4 [P3×5] CI 加固 → **VERIFIED**

逐项（scripts/ci_regression.ps1 本轮全文读取 + TEMP 实验）：
1. `Get-Command python -CommandType Application`（L72-73）：**PROBE C** 实证 PATH 仅含 python.ps1 shim 时 bare 解析 ExternalScript、-CommandType Application 解析失败 → 守卫打印 "PYTHON NOT FOUND (or not a native executable)" exit 1（M4 shim 假通过路径被第一道防线关闭）。
2. 哨兵探针（L76-78）：命令为 `& python -c "import sys; sys.exit(5)"`（非首版 SyntaxError 的 'exit 5'），`$LASTEXITCODE -ne 5` 即拒。**PROBE A** 实证真 python：exit 5→读 5、exit 0→读 0；**PROBE B4** 实证即便 shim 绕过第一道（PATH 后段有真 python 时），shim 调用留下陈旧 0 ≠ 5 → 哨兵第二道拦截。双道防线齐备。
3. Vivado 存在性检查（L10-12）：`Test-Path "$vivado\xvlog.bat"` → "VIVADO NOT FOUND at ..." exit 1（M2 的 "Compile OK + 11 FAIL" 自相矛盾诊断路径关闭）。
4. --check 成功可闻行（L113-114）：落实且定稿日志实际出现 "PASS: ...1175 vectors"。
5. $out 字符串化（L94/L101/L108 三处 `| ForEach-Object { "$_" }`）+ tb_challenge_decode.v 头注释同步：L12-13 已改为 "全部通过打印 TB_CHALLENGE_DECODE_PASS，否则打印 TB_CHALLENGE_DECODE_FAIL 并列出错项（CI 门禁约定 TB_<模块名>_PASS）"，L172 附历史成因注释。

### 修复 5 [P3] tb_w3_top 接入 CI → **VERIFIED**

- $tbs 与 $tbNames 均 12 项（L26-37，含 sim\tb\tb_w3_top.v / tb_w3_top）；$rtl 补 "src\rtl\w3_protocol\w3_top.v"（L23）。
- 定稿日志逐行含 "[PASS] tb_w3_top" 且 "=== 12/12 PASS, 0 FAIL ==="。

### 修复 6 [P3] P5_CONTEXT 机制叙述 → **VERIFIED**

- P5_CONTEXT 缺陷 2 现文："机制声明修正（p5_spec 审查证伪了最初叙述）：裸 powershell -File 复刻加回预置不复现失败，'脚本作用域阴影'在无管道上下文不成立；失败仅在预置 × 本项目 CI 的实际调用上下文（外层管道捕获）组合下出现，**精确机制未定**。处置结论与环境无关地成立：预置零防御价值……"——不再以作用域阴影为定论，A/B 双证（ci_second_run_python_gate_fail.log vs ci_12tb_final_run.log）保全。
- ci_regression.ps1 L80-89 注释同步修正（"The exact PowerShell scoping mechanism was NOT reproduced under bare powershell -File ... treat presets here as harmful-in-context rather than relying on any theory"）——错误心智模型已在代码与文档两处消除。
- 附带备注（P3 观察并入 §5-N2）：P5_CONTEXT "全量回归证据"小节仍指向 ci_full_run.log（11 TB 中间态、旧金丝雀数值 order1 0.2344），与 README 的权威声明（ci_12tb_final_run.log）不一致，建议阶段 6 刷新该小节指针。

## 2. 已知未修的终审裁决

| # | 项 | 裁决 | 理由 | 要求 |
|---|---|---|---|---|
| D1 | xsim/python 段无超时（CI 挂死风险） | **DEFERRED-ACCEPTED**（维持 P3） | 挂死 ≠ 假通过：门禁 fail-closed 语义无损，仅不终止；修复需 Start-Job 作业化改造，PS 5.1 作业的退出码传播与本次审查的预置问题同族，贸然改动有引入新假失败模式的风险；当前 CI 为本地手动触发，挂死可见可杀 | W4/正式 CI 化第一优先级；作业化时退出码传递必须按本次哨兵方法论重新验证 |
| D2 | 定稿日志仍含一行 System.Management.Automation.RemoteException（"Ran 44 tests"与"OK"之间） | **DEFERRED-ACCEPTED**（维持 P3） | $out 字符串化已落实（三处 ForEach），残留行为来自 PS 5.1 管道传输层的类型名标记，证据语义无损（"Ran 44 tests"/"OK" 完整，退出码取 $LASTEXITCODE 不经此行）；根除需仅捕获 stdout 或 cmd /c 包装，会改变日志形态并可能丢 stderr 诊断 | W4 顺手处理即可，不阻塞阶段 6 提交 |
| D3 | HANDOFF_SUMMARY 阶段 5 仍 ⬜（p5_spec F3） | **DEFERRED→阶段 6**（流程性） | 本轮复核 L50-53 确实仍为 ⬜，但 HANDOFF 文档更新本就是阶段 6 任务清单的组成部分；阶段 5 范围内不提前改写是流程正确而非遗漏 | 阶段 6 一并更新：L50-53 勾选 + L162 CI 描述同步 12 TB + §五 TB 计数 11→12 + L167-169 下一步推进 |

## 3. 三份发现合并去重最终清单（14 项原始 + 2 项终审新增）

| # | 来源 | 严重度 | 位置 | 内容 | 处置 |
|---|---|---|---|---|---|
| 1 | ci_gate P0 | P0 | gen_speck_vectors.py L195 | --check 恒真且静默重写销毁 stale 证据（CI 假通过） | **FIXED-VERIFIED**（修复 1：build_content/generate/check 三分；篡改→exit1 且文件保持篡改态→恢复 PASS→git 干净，全实测） |
| 2 | canary P2 | P2 | test_r2_nonlinearity.py L147 | 宽扇入 GF(2) 线性映射逃逸全部 C1-C3，声明过强 | **FIXED-VERIFIED**（修复 2：C4 精确 GF(2) 判定数学复核正确 + 负对照 3 类 3/3 实测全抓 + 措辞弱化） |
| 3 | ci_gate P2 | P2 | ci_full_run.log | 证据日志由旧版金丝雀生成（工件漂移） | **FIXED-VERIFIED**（修复 3：ci_12tb_final_run.log 金丝雀行与当前脚本实跑逐字符一致、12/12+44+1175 全在；ci_full_run.log 降级为谱系保留） |
| 4 | canary P3 | P3 | test_r2_nonlinearity.py L2 | 检测边界（≥2 轮轮数削减不可检）未文档化 | **FIXED-VERIFIED**（docstring L22-24 诚实声明能抓/抓不住） |
| 5 | canary P3 | P3 | test_r2_nonlinearity.py L14 | 统计注释数值错误（族错误率偏小 24 倍、期望最大值区间不符） | **FIXED-VERIFIED**（L18-21 修正为 4.1e-3 与 2.9/4.1/4.9σ，与审查复算一致） |
| 6 | canary P3 | P3 | test_r2_nonlinearity.py L129 | 双密钥复用同一样本流 | **FIXED-VERIFIED**（L214 per-key 种子派生；实测两密钥数值互异） |
| 7 | canary P3 | P3 | ci_regression.ps1 L75 | 日志 RemoteException 污染行 | **DEFERRED-ACCEPTED**（§2-D2；$out 字符串化部分落实，外层标记仍在，语义无损） |
| 8 | p5_spec P3-F1 | P3 | P5_CONTEXT.md L12 | "作用域阴影"机制声明被三重实验证伪 | **FIXED-VERIFIED**（修复 6：叙述改为"预置×调用上下文、精确机制未定"，双证据保全） |
| 9 | p5_spec P3-F2 | P3 | ci_regression.ps1 L86 | --check 成功路径零输出（证据不可审计） | **FIXED-VERIFIED**（L113-114 可闻行；定稿日志实含 "PASS: ...1175 vectors"） |
| 10 | p5_spec P3-F3 | P3 | HANDOFF_SUMMARY.md L50 | 阶段 5 完成态未回写 | **DEFERRED→阶段 6**（§2-D3，流程性） |
| 11 | p5_spec P3-F4 | P3 | tb_w3_top.v | 第 12 个 TB 不在 CI（"全量"口径 11/12） | **FIXED-VERIFIED**（修复 5：$tbs/$tbNames 12 项 + $rtl 补 w3_top.v + 定稿日志 [PASS] tb_w3_top、12/12） |
| 12 | ci_gate P3 | P3 | ci_regression.ps1 L63 | python.ps1/function shim 四段假通过（M4） | **FIXED-VERIFIED**（-CommandType Application + 哨兵双道，PROBE A/B/C 三组实测） |
| 13 | ci_gate P3 | P3 | ci_regression.ps1 L49 | Vivado 缺失诊断误导 + 无超时 | **拆分**：Vivado 检查 **FIXED-VERIFIED**（L10-12）；无超时 **DEFERRED-ACCEPTED**（§2-D1） |
| 14 | ci_gate P3 | P3 | tb_challenge_decode.v L12 | 头注释残留旧标记约定 | **FIXED-VERIFIED**（L12-13 同步 + L172 历史注释） |
| N1 | 终审新增 | P3 | README.md / ci_12tb_final_run.log | "CI-EXIT=0" 无日志字面行：五个日志均不含该行（退出码为运行者终端外部记录），README 表格措辞易读作日志内容。日志结构上蕴含 exit 0（零 FAILED 行 + 终行 "  OK"，脚本 L115 后唯一语句 exit 0），判定不受影响 | 建议：运行器把退出码 echo 进日志尾（一行）；阶段 6 微调 README 措辞 |
| N2 | 终审新增 | P3 | P5_CONTEXT.md "全量回归证据"小节 | 该小节仍指向 ci_full_run.log（11 TB 中间态 + 旧金丝雀数值 0.2344），与 README 权威指针（ci_12tb_final_run.log）不一致，直读者会先看到已废弃证据 | 建议：阶段 6 刷新该小节指向定稿日志并同步 12/12+新数值 |

## 4. 计数汇总

- 原始发现：14 项 = P0×1 + P2×2 + P3×11
- FIXED-VERIFIED：11 项（含 #13 的 Vivado 半项）
- DEFERRED-ACCEPTED：2 项（#7 RemoteException、#13 的超时半项，即 D1/D2）
- DEFERRED→阶段 6：1 项（#10 HANDOFF 回写，D3）
- 终审新增：2 项 P3（N1/N2），均不阻塞
- **门禁：P0=0、P1=0、P2=0（原始 P0/P2 全部 FIXED-VERIFIED）→ PASS**

## 5. 结论

三份独立审查的全部 P0/P2（恒真向量门禁、金丝雀宽扇入盲区、证据工件漂移）经本轮在最终代码上的独立实验全部复验通过；CI 的 python 解析链经三组探针（真实/混合/shim-only PATH）确认双道防线闭合；金丝雀双跑逐字节可复现且三类退化负对照 3/3 被抓；向量门禁的 stale-不销毁-不重写性质经篡改实验直接证明。遗留三项 P3 均为可接受的 defer（挂死超时、日志包装行、文档回写时机），另记两项终审 P3 备注（CI-EXIT 表述精度、P5_CONTEXT 证据指针滞后）。A1 阶段 5 达到提交门禁，建议进入阶段 6（文档回写 + 提交），并把 D1 超时作业化列入 W4 首项。
