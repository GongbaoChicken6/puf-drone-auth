# W4 实验周 · 计划书 v1.1

> 状态：经 3 代理计划审查（P1R 事实/P2R 技术/P3R 完备性，2026-10-13）修订｜编制 2026-10-13
> 依据：HANDOFF_SUMMARY(2026-10-10/13) + claims_v2.md + project_design.md v3.0 + W3 PC 闭环 dd36c5e + 板卡会话 55f2213/9000413
> 代码基线：HEAD dd36c5e（77 commits / 171 files，CI 12 TB + 63 单测全绿）
> 时间窗：10-13 → 10-24（W5 冻结 10-25 起；11-03 晚提交；11-04 18:00 硬死线）
> v1.1 修订：纳入审查 1×P0+8×P1+10×P2+8×P3（新增 W4-P0 CI 作业化；热稳定窗/看门狗/上板脚本扩源/tie-off 口径/KDF 冻结/PoC harness/审查轮预算/会话协议）

---

## 0. 输入快照与兼容基线（不可破坏项）

| 项 | 现状 | W4 必须保持 |
|---|---|---|
| CI | 12 TB + speck 自测 + 63 单测 + 金丝雀 + 1175 向量 + 契约同步 | TB/单测数量单调不减；全绿是每阶段出口条件 |
| 串口 PC 侧 | serial_server.py（接收循环/on_confirm/enroll 配对）19 单测 | 接口不变；W4 只改终端语义层 |
| 板级适配 | wrapper + XDC 引脚全核（UART=FMC1_LPC L21/L22）+ build_w3_board.tcl | RTL 改动后同步扩上板脚本（见 §2 P2-T3），"零豁免"口径修正为：全引脚约束 + 仅保留**设计使然**的 LUTLP-1 环振组合环豁免（w2_waiver，其头注释自证无豁免必被挡） |
| 板卡 | DS13 电源故障排查中（另一会话）；电台未购 | 板上项做成"就绪待板"独立通道，口径先冻结 |
| 并行会话 | 板卡会话 + 前端会话共用仓库（现有未跟踪 web/、docs/FRONTEND_HANDOFF.md 归前端会话自行处置） | §4 R5 协议 |
| 黄金值 | R2=7b45b0545e59aa94（三 TB）；C2=A0+j 步进 | R1/C2/K 语义变更必须脚本化再生 + 证据入库 |

## 1. 目标与范围

**P0 必做（纯 PC + 仿真，不等板卡）**
- G0 CI 健康化（W4 首项，HANDOFF deferred）：超时作业化 + RemoteException 包装
- G1 PUF 响应语义落地：位级冻结 + puf_model 黄金模型 + 契约 §8
- G2 RTL PUF 真实接入（B5a 单路 16 环，替换种子直通桩）
- G3 PC 全链适配：loopback 换 RO 语义、注册配对实测、互操作 harness 固化
- G4 安全包：P1-1 真密钥派生（KDF 全规格冻结）+ 熵混合、P1-5 终端跨断电重放、P2-1 加固、预认证池 DoS、运维加固、**威胁 PoC harness 固化**
- G5 ML 攻击实验（B6，20 分）

**P1 需板卡（口径先冻结）**：温度（全温区 reliability ≥85%，允许比常温降 5%）、唯一性（HD≈32 口径）、多终端 0~3、无线联调、AI 扩展、XDC 启用+clk_wiz_0+正式比特流。

**P2 stretch**：B5b XOR-4、C2 回绕、DPAPI、nonce 随机化。
**非目标**：PS 侧软件、PL 侧 HSM 硬件实例 0（报告素材）、真电台协议栈改造。

## 2. 阶段分解（含审查轮与返工预算）

### W4-P0 CI 健康化（0.5 天，立即）
| 任务 | 产出 | 验收 |
|---|---|---|
| T1 ci_regression.ps1 每 TB xelab/xsim 包超时作业（Start-Job + Wait-Job -Timeout，超时判 FAIL 并续跑后续 TB） | 脚本更新 | 人为挂死一个 TB 的注入实验证据（build/reviews/w4/） |
| T2 日志 RemoteException 包装行处理（PS 5.1 ErrorRecord 字符串化的既有 P3） | 脚本微调 | CI 日志无 RemoteException 噪音 |

### W4-P1 语义与黄金模型（0.5 天）
| 任务 | 产出 | 验收 |
|---|---|---|
| T1 puf_model.py（src/python/evaluation/）：16 环频率向量设备模型 + LFSR/Fisher-Yates 解码模型 + R1(seed)=8 轮×8 对比较位 + 噪声/温度模型 | 模块+自测 | **新冻结 3 个对拍种子**（tb_challenge_decode 现仅 SEED_FIX+全零，需同步扩 TB 3 用例），pair_table hex 双侧逐 bit 一致后写入契约 §8 |
| T2 契约 §8「PUF 响应语义」+ check_contract_sync 扩展 | 契约+门禁 | 契约同步绿 |

### W4-P2 RTL PUF 接入（2 天 + 0.5 天审查返工）
| 任务 | 产出 | 验收 |
|---|---|---|
| T1 terminal_fsm：PUF 子接口端口；S_PROC_SEEDS 拆 S_PUF_DECODE→S_PUF_MEASURE（**含 W2 冻结的 7 轮热稳定窗**，WARMUP_WINS=7 参数）→S_PUF_PACK（4 种子 32B→S_TX_R1；灰区 3 种子 24B→S_TX_R1_EXTRA）；**S_PUF_* 三态挂看门狗**（超时→S_BLOCKED） | 改后 RTL（guardrails 全规则） | xvlog/xelab + 新 tb_puf_path（含看门狗/热窗/窗口边界/毛刺） |
| T2 可注入端口：c2_boot_seed[63:0] / device_key_in[95:0] / use_ext_key。**V2001 无端口默认值 → 既有 TB 补两行 tie-off，黄金 C2/R2 期望值零改动**（诚实口径，非"TB 零改动"） | 端口+TB tie-off | tb_gap 黄金用例通过（期望值文件不变） |
| T3 w3_top 集成 + `PUF_MODEL_SIM` stub；**build_w3_board.tcl 同步扩源**（ro_ring/ro_div/ro_array/challenge_decode 四文件 + w2_waiver.xdc 挂 constrs，脚本头注释同步"设计使然豁免"口径） | 集成+脚本 | ifdef 两态 elab；上板脚本 dry-run 源清单核对 |
| T4 TB 黄金再生：4 个既有 TB 期望 R1 由 scripts/gen_puf_fixtures.py（调 puf_model）生成 .mem；**补 tb_speck 输入毛刺用例**（HANDOFF 计划偏差，审查后补入）；tb_challenge_decode 扩 3 对拍种子 | TB+脚本 | CI 12→13 TB 全绿（+tb_puf_path）；黄金再生证据入库 |

### W4-P3 PC 侧全链适配（1 天 + 0.5 天审查返工）
T1 SimulatedTerminal 重写为 ROPairingPUF 薄壳（温度可调噪声）；T2 interop 固化 tests/test_interop_rtl_model.py（复用 tests/test_serial_server.py 既有 WireTransport 模式，必要时提取公共测试工具）；T3 评估工具对齐 64-bit R1 + reliability 统计口径。验收：单测绿 + loopback 端到端 PASS + interop 入 CI。

### W4-P4 安全包（2 天 + 0.5 天审查返工）
| 任务 | 产出 | 验收 |
|---|---|---|
| T1 P1-1+熵混合（**设计书 §5v2 全规格**：key_seed 全 8B、K 两段 Speck 构造、0x0096 KEY_SEED 帧通道、拨码 11 进注册模式、key_valid 防断电回退；时间紧降级路径同节） | 双侧实现+帧+契约 | 黄金 K 向量双侧一致；断电重派生无 NSA 回退 |
| T2 P1-5：ro_entropy 上电熵采样→c2_boot_seed；**验收机制=终端 S_VERIFY_R2 比对失败→BLOCKED**（服务器重放窗与此路径无关，v1.0 口径错误已纠正） | RTL+熵采样 | PoC 重放用例：换电重启后旧 RESULT 帧被终端拒绝 |
| T3 P2-1：calc_done_flag（sp_done 置位→S_VERIFY_R2 入口校验→**校验完成后**清零，与帧无关）+ 非法态陷阱 | RTL | tb_gap 新增注入用例 |
| T4 DoS 三子项：per-tid 令牌桶限速（池消耗前）+ 暂存-释放语义文档 + 池补充 SOP | 限速+文档 | 洪泛单测：池不耗尽 |
| T5 运维：setkey getpass/0600 导入、c2reset/setkey 审计、DeviceKeyStore mtime 检测、SimulatedHSM 决策（**三选项**：删 / 补最小单测 / save_secret 对齐 0600 原子写基线） | 加固 | 单测+审计样本 |
| T6 **威胁 PoC harness 固化 scripts/threat_poc.py**（重放/穷举口径/注入三用例，替代一次性 a1p4 证据） | 脚本入 CI 可选 | M2/G4 复测命令 = `python scripts/threat_poc.py` exit 0 |

### W4-P5 ML 攻击实验（1.5 天）
实验 A 合成 arbiter+LR（sklearn 1.8）／实验 B 排序重构（puf_model 数据，~120 CRP 口径）；产出 data/ml_attack/*.json + report/figures 图 + 结论文案（design.md 冻结版逐字）。验收：复现命令 + 数字一致。

### W4-P6 板上实验（待板卡，口径冻结见设计书 §8）
上板五步：XDC 取消注释 → clk_wiz_0 → build_w3_board（扩源后脚本）→ BIST → 验证点①②③；温度/唯一性/多终端/无线/AI 按 §8 口径执行，数据落 data/w4_readings/。

### W4-P7 W5 前置（利用松弛，M3 后穿插）
D13 报告骨架起草（失败分析章节现成）+ D14 Skill ≥2 脚本候选（PUF 评估/MAVLink 回环）启动。

## 3. 里程碑与 G4 门禁（含审查轮）

| 里程碑 | 日期 | 判据（技术 + 审查） |
|---|---|---|
| M1 仿真级 PUF 全链 | **10-17** | P0-P3 完成 + auto-review 审查轮（1-3 轮，P0/P1 清零）+ CI 全绿 |
| M2 安全包闭环 | 10-20 | P4 完成 + 审查轮 + **scripts/threat_poc.py 三用例 exit 0**（或口径诚实化记录） |
| M3 ML 数据就绪 | 10-22 | P5 完成 + 数字复核 |
| M4 板上尽力 + 冻结 | 10-24 | 板上项完成或降级决策记录 + 审查轮 + 进入 W5 |

G4 总门禁：CI 全绿（TB≥13 + 单测≥80，超时作业化生效）｜**仿真 reliability ≥97% 明确为"工具链+语义自检口径"（stub 噪声模型自证），PUF 物理指标以板上实测为准**｜threat_poc.py exit 0｜ML 可复现｜HANDOFF/看板同步。

## 4. 风险与降级

| # | 风险 | 概率 | 缓解/降级 |
|---|---|---|---|
| R1 | 板卡不复活 | 中 | 板上项降级：仿真数据 + 预录 + 报告诚实标注 |
| R2 | 真环不可仿真（零延迟组合环） | 确定 | stub 方案；真环只在板上验证（诚实边界，G4 措辞已区分） |
| R3 | 单路 97% 达不到 | 中 | 差分布局/stable mask 先行；触发即提前 B5b XOR-4（合并 90% 口径）；**热稳定窗保留 W2 冻结值** |
| R4 | 时间溢出 | 中 | 裁剪顺序：P4-T5 → P7 → B5b；KDF 降级路径见设计书 §5v2 |
| R5 | 并行会话冲突 | 低 | **协议**：①提交=显式路径 add + 前置 git status；②HANDOFF 记账=追加式（每会话新增带时间戳小节，禁改他人小节，冲突以 git 为准）；③每里程碑 git bundle 备份（无 remote 的替代）；④前端产物（web/、FRONTEND_HANDOFF.md）由前端会话自行提交 |
| R6 | ro_entropy 熵不足 | 中 | 报告标注有效熵 + server 128 窗兜底；nonce 随机化 stretch |

## 5. 兼容性矩阵（v1.1 修正）

| 载体 | W4 变更 | 兼容策略 |
|---|---|---|
| terminal_fsm.v | 新端口 + 3 新态 + 热窗/看门狗 + key/c2 注入 | 参数默认=旧行为；**既有 TB 补 tie-off（黄金值零改动）** |
| w3_top.v | 例化 PUF 模块 + ifdef stub + 注册模式（拨码 11） | wrapper/XDC 端口不变 |
| build_w3_board.tcl | **扩 4 源文件 + w2_waiver.xdc**（v1.0"不受影响"为错误） | "设计使然豁免"口径写入脚本头 |
| sim/tb | 4 TB 黄金再生 + tb_speck 毛刺 + tb_challenge_decode 扩种子 + 新 tb_puf_path | CI 只增；再生脚本入库 |
| protocol_contract.md | §8 PUF 语义 + 0x0096 帧（若主案） | check_contract_sync 扩展；§7 变更控制流程触发 |
| main.py/tests | SimulatedTerminal 换语义 + interop + PoC harness | REPL 接口不变 |
| docs/data | 契约/HANDOFF/看板 + ml_attack/w4_readings | 每里程碑同步 |
