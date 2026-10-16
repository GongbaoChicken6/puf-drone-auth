# A1 阶段 4 共识综合报告（CONSENSUS — auto-review 终审）

- 轮次：consensus（第 5 轮，终审）
- 对象：A1 阶段 4 PC 侧集成（Speck64/96 替换 HMAC 作为 R2 算法），工作区未提交改动
- 输入：defect.json / spec.json / silent.json / tests.json / tests_r2.json / types.json / silent_r2.json / FIXLIST.md（四轮修复轨迹）
- 方法：空间+根因去重 → 证据源比对 → 8 条 P2 全部在当前工作区独立复验（重读代码 + 实跑测试 + 主动探针）→ deferred 逐条裁决 → 门禁判定

---

## 一、本轮独立验证证据（不采信 FIXLIST 自述）

| 验证项 | 命令/操作 | 结果 |
|---|---|---|
| 测试套件 | `python tests\test_a1_phase4.py`（direct 模式） | **Ran 44 tests / OK / exit=0**；类内用例普查 6+10+4+2+5+1+9+5+1+1 = 44，与输出一致 |
| 黄金向量 | 独立复算 `Speck6496(0001020308090a0b10111213).encrypt(a1..a8)` | R2 = `7b45b0545e59aa94` ✓（与 tb_terminal_fsm 黄金值一致） |
| S1 fail-closed 探针 | 剥离 python 目录后运行守卫逻辑（%TEMP% 探针，仓库零污染） | 守卫触发 → "PYTHON NOT FOUND ON PATH"，probeExit=1（fail-closed）✓ |
| R2N1 代码位置 | 重读 protocol.py | `_update_session_c2` 位于 on_response L481（评分 L482-484 之前）与 on_extra_response L524（累加 L528-529 之前）✓ |
| R2N1 回归测试 | 重读 tests L688-713 | 4×7=28 灰区 + 失败尝试(3×8, 错误 C2→ProtocolError) + 干净重试 → 断言 `(MSG_RESULT, RESULT_PASS, hd=28)`（旧行为 REJECT hd=52），在 44/44 内通过 ✓ |
| mypy | 两种模式重跑 | 3 个报错全部为 import 配置/stub 噪声（types-pyserial 缺失、相对导入解析、模块名碰撞）；`--explicit-package-bases` 后仅剩 2 个 stub 缺失；**改动逻辑 0 类型错误** |
| 工作区卫生 | `git status --porcelain` | 无 `%SystemDrive%/` 杂散目录（R2N7 ✓）；.gitignore 新增 `data/device_keys/`（密钥材料防误提交 ✓） |

---

## 二、8 条 P2 修复复验结论（全部 FIXED-VERIFIED）

| ID | 发现（原报） | 复验结论 | 本轮证据（当前工作区实读/实跑） | 确认代理 | 证据独立性 |
|---|---|---|---|---|---|
| S1 | CI Python 段假通过（python 缺失时继承 xsim 的 exit 0） | **FIXED-VERIFIED** | ci_regression.ps1 L63-65 `Get-Command python` 守卫、L66/L69 每次 native 调用前 `$LASTEXITCODE=1` 复位、L73 失败回显 -Last 40；本轮 PATH 剥离探针实证守卫 fail-closed | silent（原始）, silent-r2（4 组 PS5.1 探针）, consensus（本轮） | 三方独立（不同探针方法，同源结论） |
| S2 | DeviceKeyStore.save() OSError 逃逸链杀死 REPL/跳过串口清理 | **FIXED-VERIFIED** | repl except `(ValueError, KeyError, OSError)`（main.py:734-740）；_flush_c2_state 内 try/except OSError→`[WARN]`（480-484）；main() 嵌套 try/finally 保证 transport.close() 必达（812-821）；_ensure_device_key 已在 cmd_auth try 内（571-572）；专项测试 2 条在 44/44 内通过 | silent, silent-r2, consensus | 三方独立 |
| T1 | main 层胶水零覆盖（_ensure/_flush/cmd_setkey/cmd_c2reset/repl） | **FIXED-VERIFIED** | TestMainGlue 9 用例实存（tests:429-618）且随 44/44 通过；断言落盘状态而非仅执行（tests-r2 逐条核对 + 本轮类普查） | tests（原始）, tests-r2（VERIFIED）, consensus | 两方独立 + 本轮复跑 |
| T2 | on_response/on_extra_response 迟到 C2 分支未测（R2 安全敏感） | **FIXED-VERIFIED** | `_update_session_c2`（protocol.py:603-626）过重放窗+冲突检测；TestLateC2 5 用例（含 None 回退 R2=Speck(K,0^8) 精确钉住、HSM 故障→RESULT_ERROR 帧）；MUT-C 变异对照实证保护真实 | tests, tests-r2, consensus | 两方独立 + 本轮复跑 |
| T3 | "重启后重放窗生效"无 E2E | **FIXED-VERIFIED** | TestRestartReplayE2E（tests:383-427）：实例 #1 落盘 → 全新 store/HSM/protocol 磁盘再水化 → 旧 C2 收 RESULT_REPLAY、新 C2 收 CHALLENGE；通过 | tests, tests-r2, consensus | 两方独立 + 本轮复跑 |
| N1 | 灰区路径 on_extra_response（含 _update_session_c2 第二调用点）零覆盖 | **FIXED-VERIFIED** | TestGrayZone 5 用例（tests:636-731）：灰区+完美补测→PASS 且 R2==黄金值、持续错误→REJECT、迟到绑定、R2N1 回归、冲突/重述；MUT-A 缺口已关闭（本轮 5 用例全过） | tests-r2（原始+MUT-A 实证）, consensus | 两方独立 |
| TYPES-01 | HSM.respond 基类签名宣称 None 合法但 SpeckHSM 抛 KeyError（类型层 LSP 冲突） | **FIXED-VERIFIED**（契约文档化方案） | hsm.py L65-72 基类 docstring 显式 CONTRACT：per-terminal 后端 MUST 将 None 视为前置条件缺失并抛 KeyError；"签名默认值 ≠ 对 keyed 后端合法"；SpeckHSM 行为与契约一致；唯一生产调用点 protocol.py:638 恒传 int | types（原始）, consensus | 两方独立 |
| R2N1 | on_extra_response 先累分后验 C2 → 失败尝试污染会话 → 更正重试静默 REJECT | **FIXED-VERIFIED** | 见第一节：两调用点均验证前置 + 回归测试精确断言 PASS/hd=28 | silent-r2（原始，实测复现）, consensus（本轮复验） | 两方独立（silent-r2 构造复现；本轮代码位序+测试断言复核） |

> 门禁关键结论：**P2 = 0（8/8 本轮独立复验通过，非仅凭 FIXLIST）**。

---

## 三、P3 修复复验（合并组，全部 FIXED-VERIFIED）

| 合并组 | 原始来源（去重） | 复验证据 |
|---|---|---|
| load() 错误上下文不对称 + 漏网路径 | defect#6 ≡ silent-P3.1 ≡ R2N5（terminals 非映射）≡ TYPES-04（"1_0"/"+7" 非规范键） | main.py:280-323：JSON 坏/非对象/非映射 schema/record 损坏/key 长度/c2 长度全部包成带路径 ValueError；L297-303 规范键校验 `tid_str == str(int(tid_str))`；测试 test_terminals_not_a_mapping_rejected / test_noncanonical_terminal_key_rejected 在 44/44 内 |
| DeviceKeyStore 并发竞态 + 读写锁不一致 | defect#5 ≡ FIXLIST-P3#2 ≡ TYPES-03 | L267 RLock；5 个变更方法持锁（366/388/419/434）；读方法 all_keys:403 / c2_history:409 同样持锁 |
| 部分提交（save 失败不回滚） | R2N2 | key_for:372-379 / set_key:392-399 / set_c2_history:423-430 / clear_c2_history:437-442 四处回滚；test_mutator_rolls_back_on_save_failure 在 44/44 内 |
| 铸钥污染 + 负数 id | silent-P3.3 ≡ silent-P3.4 | _ensure_device_key 预检 tid<0/无模板（456-458）；cmd_enroll 注册后铸钥（553-555）；cmd_setkey 拒绝负 id（625-627）；N2 测试钉住时序 |
| HSM 异常穿透 + 无诊断 | silent-P3.5 ≡ R2N3 | _finish_pass try/except→RESULT_ERROR 帧+BLOCKED（protocol.py:637-649）；`except Exception as exc` + stderr 打印类型与消息（R2N3） |
| 解析长度校验 | defect#3（parse 侧）≡ FIXLIST-P3#6 ≡ R2N4 | 0x0090=16B / 0x0093=10B / 0x0094=5B 精确校验（protocol.py:387-417）；TestParseLengthValidation 在 44/44 内 |
| CI 诊断截断 | tests-P3（-Last 4） | L73 `-Last 40` |
| 回绕断言过弱 + E2E 随机噪声 | tests-P3 ×2 | 精确断言 C2==00..07（tests:771-774）；判决路径全部 flip_prob=0.0（292/305/334/345/354/366/377 等） |
| has_key/terminal_ids/c2=None 旁路覆盖 | tests-P3 | 被 TestMainGlue（has_key/terminal_ids）与 TestLateC2（c2=None 回退）吸收 |
| N2/N3/R2N6/R2N7 | tests-r2 / silent-r2 | test_cmd_enroll_mints_key_after_enrollment、test_repl_spoof_rejects_impostor、[ERROR] 行含 `type(exc).__name__`（main.py:740）、杂散目录已删（git status 无 `%SystemDrive%/`） |
| 契约码表滞后 | spec-1 | protocol_contract.md L61 登记 4=REPLAY（含 RTL 兼容性说明） |
| defect#2（迟到 c2 休眠绕过） | defect | _update_session_c2 关闭该旁路（迟到 C2 必过 _remember_c2 窗口）——被 T2/R2N1 工作吸收，FIXED |

---

## 四、去重与同源判定说明

- **同源命中按单源对待**：defect#8（flush OSError P3 早期报告）≡ silent S2（P2 完整版）——同一根因链，保留 S2 为代表；TYPES-10（先评分后验 C2）≡ R2N1（P2，累加路径实证升级）——同根因，保留 R2N1。
- **独立证据标高置信**：S1 有三方独立探针（silent 复现 / silent-r2 4 组通道 / consensus PATH 剥离）；R2N1 有构造复现 + 本轮位序复核 + 回归测试断言。
- **误报清单**：空（与 FIXLIST 一致，本轮无需驳回项）。

---

## 五、deferred 裁决（逐条）

| 项 | 裁决 | 理由 |
|---|---|---|
| C2_REPLAY_WINDOW=128 vs 256（defect#1） | **DEFERRED-ACCEPTED** | aged-replay（>128 前的 C2）即便过窗，仍被 PUF 挑战/应答（CRP 池单次使用，attacker 无法算 R1）与 R2 签发门槛拦截，实际影响=池消耗 DoS；改 256 的代价是真实终端每次计数回绕都需人工 c2reset（可用性损失）；权衡已写入 protocol.py:144-157 注释 |
| start_auth c2=None → R2=Speck(K,0^8)（defect#4） | **DEFERRED-ACCEPTED** | 回退明文 0^8 已在 _finish_pass docstring 文档化并被 test_no_c2_fallback_r2_is_speck_of_zero_block 精确钉住；无生产调用方走该路径 |
| TYPES-09 畸形 C2 ValueError 穿透（≡ defect#3 残余） | **DEFERRED-ACCEPTED** | wire 侧已被 parse 16B 校验拦截（0x0090 c2 恰 8B）；REPL 直调有 except ValueError 兜底；"畸形输入→帧" 的统一化属 W3 帧级服务器重构 |
| SerialTransport 随机 C2（silent-P3.6） | **DEFERRED-ACCEPTED** | 既有 W3 占位且代码内已声明待接收环路落地；串口互认证在该环落地前本就不可用，非阶段 4 范围 |
| loopback secret 每进程随机（spec-2） | **DEFERRED-ACCEPTED** | 阶段规格只要求 device key 持久化（已满足）；跨重启演示走 setkey+真 RTL 终端，已记录供 W4/演示规划 |
| hsm.py 裸 except ImportError（silent-P3.4） | **DEFERRED-ACCEPTED** | speck.py 仅 stdlib，掩码风险纯理论；双路径 bootstrap 是既定模式 |
| 0600 测试 Windows 空转（tests-P3） | **DEFERRED-ACCEPTED** | 平台限制；POSIX 分支已断言，Windows ACL 无法在可移植 unittest 中表达 |
| TYPES-02 残余（KeyError 混装两类错误） | **DEFERRED-ACCEPTED** | R2N3 已给 stderr 类型诊断（NameError 与缺钥可区分）；异常层级化（HSMError 族）留给 W3/W4 重构，当前 REPL 捕获族覆盖正确 |
| TYPES-05 flush 写放大 | **DEFERRED-ACCEPTED** | N 终端 N 次全量写，演示规模（N 个位数）无实际影响；批量接口属优化 |
| TYPES-06/07/08/11（tuple 语义/int 强转/字符串状态机/isinstance 分派） | **DEFERRED-ACCEPTED** | 设计观察项，无运行期缺陷；mypy 逻辑层 0 错误 |
| N4 观察项（main() 仅镜像覆盖 / setkey 非 Speck 分支 / repl 分发表） | **DEFERRED-ACCEPTED** | 镜像接线已覆盖关键行为；直接 main() 测试与分支补测为 nice-to-have |

---

## 六、最终发现状态汇总（合并后）

| 严重度 | 数量 | 明细 |
|---|---|---|
| P0 | **0** | — |
| P1 | **0** | — |
| P2 | **0**（8/8 FIXED-VERIFIED：S1/S2/T1/T2/T3/N1/TYPES-01/R2N1） | — |
| P3 OPEN | **1** | **D-7**：DeviceKeyStore.set_c2_history 对无 key 终端静默丢数据——save() 仅遍历 `self._keys`（main.py:343），为 keyless 终端 set 的 c2_history 在下次 save 落盘时被静默丢弃，API 声称"Replace and persist"（main.py:413-417）与实际不符。生产路径不可达（_flush_c2_state 只迭代有钥终端），仅 API 误用陷阱；defect 批次已报，四轮修复未覆盖、亦未入 deferred 清单。建议 W4 加 guard（无 key 终端 set_c2_history → ValueError）或 docstring 显式声明前置条件 |
| P3 DEFERRED-ACCEPTED | 12 组 | 见第五节 |

---

## 七、最终门禁判定

> **PASS**
>
> P0 = 0，P1 = 0，P2 = 0（8 条 P2 全部经本轮独立复验为 FIXED-VERIFIED），P3 = 1 OPEN（D-7，非阻断）+ 12 组 deferred-accepted。
>
> 回归证据：44/44 OK（exit 0）；黄金向量独立复算一致；S1 门禁 fail-closed 探针通过；mypy 仅环境 stub 噪声。

### 提交建议

1. **可以提交**：7 个变更文件（.gitignore、ci_regression.ps1、docs/protocol_contract.md、hsm.py、main.py、protocol.py、tests/）整体构成完整可回滚的阶段 4 交付；`data/device_keys/` 已被 .gitignore 正确排除——提交前确认 `git status` 无任何密钥文件被暂存。
2. **可选预提交微修**（2 行）：D-7 的 set_c2_history 加 keyless guard；不修则登记为 W4 待办（不阻断本次提交）。
3. `build/reviews/` 为审查产物（未跟踪）：按团队惯例随证据归档提交或保留本地，勿混入代码提交。
4. 提交信息建议引用：A1 阶段 4（SpeckHSM + C2 重放窗 + DeviceKeyStore 持久化），P1-2/P1-3 关闭，回归 44/44。
