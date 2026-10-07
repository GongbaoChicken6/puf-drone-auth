# A1 阶段 4 修复清单（FIXLIST — 供复审注入）

> 状态：5 条 P2 全部修复 + 9 项 P3 折叠修复；已知误报清单为空（无驳回项）。
> 复审要求：对每个"已修"项必须以本轮重新读取文件/重跑命令的实际结果复验，禁止仅凭本清单判定已解决。

## P2 修复

### P2-S1 CI Python 段假通过（silent）
- 文件: scripts/ci_regression.ps1 Python 段（文件尾部）
- 修复: ①Get-Command python 探测（缺失→"PYTHON NOT FOUND ON PATH"+exit 1）；②每次 python 调用前 `$LASTEXITCODE = 1` 复位（防陈旧 xsim 0 掩盖启动失败）；③失败回显 -Last 4 → -Last 40
- 验证方法: 读文件核对；模拟 `Get-Command python_missing_xyz` 行为；健康路径实跑（33/33 OK, exit 0 已复现）

### P2-S2 DeviceKeyStore.save() OSError 逃逸链（silent）
- 文件: src/python/server/main.py
- 修复: ①repl() 第二个 except 加 OSError（注释"disk full, AV/OneDrive lock"）；②_flush_c2_state 内部 try/except OSError → 打印 "[WARN] C2 replay-window persistence failed"（finally 路径不再上抛）；③main() finally 改嵌套 try/finally，transport.close() 必达；④cmd_auth 的 _ensure_device_key 移入 try 内
- 验证方法: 测试 test_flush_persists_and_swallows_oserror、test_repl_survives_store_oserror（33/33 内）

### P2-T1 main 层胶水零覆盖（tests）
- 文件: tests/test_a1_phase4.py 新增 TestMainGlue（7 用例）
- 覆盖: _ensure_device_key（未知/负数 id 不铸钥、已注册铸钥且幂等）、cmd_setkey（正常+5 组坏输入）、cmd_c2reset、_flush_c2_state（落盘+OSError 吞掉）、repl（OSError 存活、setkey+auth+quit 冒烟含黄金 R2）

### P2-T2 迟到 C2 分支未测（tests）
- 文件: tests/test_a1_phase4.py 新增 TestLateC2（5 用例）
- 覆盖: 迟到绑定驱动 R2、迟到绑定过重放窗（重复→ProtocolError）、会话中 C2 冲突→ProtocolError/重述→PASS、无 C2 回退 R2=Speck(K,0^8) 精确钉住、HSM 故障→RESULT_ERROR 帧（hd=0xFF）
- 配套实现: protocol.py 新增 _update_session_c2（迟到绑定必须过 _remember_c2 窗口；与已绑定值冲突→ProtocolError；重述无害），on_response/on_extra_response 两处调用点替换

### P2-T3 重启后重放窗生效 E2E（tests）
- 文件: tests/test_a1_phase4.py 新增 TestRestartReplayE2E
- 覆盖: 服务器实例 #1（与 main() 相同接线：store→SpeckHSM→protocol→_ensure→auth→_flush）落盘后，用全新 store/HSM/protocol 从磁盘再水化 → 重放旧 C2 必收 RESULT_REPLAY，新 C2 → CHALLENGE

## P3 折叠修复

| # | 项 | 文件 | 内容 |
|---|---|---|---|
| 1 | load() 错误上下文 | main.py | json 坏/非对象/缺 key_hex/int 失败/c2_history 非 8B 全部包成带路径与终端号的 ValueError |
| 2 | 并发 save 竞态 | main.py | DeviceKeyStore 加 threading.RLock；save 及 4 个变更方法持锁（read-mint-persist 原子） |
| 3 | 铸钥污染 | main.py | _ensure_device_key 加 templates.has_terminal + tid>=0 预检；cmd_enroll 改为注册成功后再铸钥 |
| 4 | setkey 负数 id | main.py | tid<0 → [ERROR]（u32 线上域） |
| 5 | HSM 异常转帧 | protocol.py | _finish_pass try/except → RESULT_ERROR 帧 + 会话 BLOCKED（不再让异常穿出锁内路径） |
| 6 | 解析长度校验 | protocol.py | _parse_payload 对 0x0090 要求 16B（短载荷不再静默切片） |
| 7 | 窗口权衡文档化 | protocol.py | C2_REPLAY_WINDOW 注释重写：128<256 周期的取舍、aged-replay 残余暴露仅池消耗、W4 限制（不改为 256，理由在注释） |
| 8 | 回绕精确断言 | tests | _auth_count=0x5F → 断言 C2 == 00..07（原 assertNotEqual 过弱） |
| 9 | E2E 去随机化 | tests | TestEndToEnd/TestLateC2/REPL 冒烟全部 flip_prob=0.0（消除 0.02 噪声灰区 flaky） |
| 10 | 契约码表 | docs/protocol_contract.md | RESULT 码表登记 4=REPLAY（终端对非零码一律拒绝，W3 RTL 兼容） |

## 有意不修（deferred，非误报）

- hsm.py 裸 except ImportError 掩码（P3，当前 speck.py 仅 stdlib，无实际影响）
- SerialTransport 随机 C2 绕过重放窗（既有 W3 占位，接收环路落地时一并处理）
- loopback 终端 secret 每进程随机（观察项：跨重启 PASS 演示需 setkey+真 RTL 终端）
- 0600 权限测试在 Windows 空转（平台限制，POSIX 路径已断言）
- 窗口 128 vs 256：维持 128，权衡已写入注释（共识综合可再裁决）

## 第二轮修复（tests-r2 复审新发现）

tests-r2 以变异实验实证 3/3 P2 已修复，但发现新缺口，本轮已修复：

| # | 项 | 严重度 | 修复 |
|---|---|---|---|
| N1 | 灰区路径 on_extra_response（含 _update_session_c2 第二调用点）零覆盖，MUT-A 实证无保护 | P2 | 新增 TestGrayZone 4 用例：灰区+完美补测→PASS（R2=黄金值）；灰区持续错误→RESULT_REJECT；灰区迟到 C2 绑定；灰区 C2 冲突→ProtocolError/重述→PASS。夹具 _enrolled_pair + _responses_with_flips(n_flips=10 落灰区: TAU_PASS=6/TAU_REJECT=16) |
| N2 | cmd_enroll 注册后铸钥时序无测试，MUT-B 实证 | P3 | test_cmd_enroll_mints_key_after_enrollment：断言模板+HSM+落盘状态 |
| N3 | repl spoof 分支零覆盖 | P3 | test_repl_spoof_rejects_impostor：impostor→REJECT 判决 |

## 第三轮修复（types 审查发现，2026-10-08）

types 审查结论 PASS（mypy 全绿、39/39 复验、黄金向量独立复算），1×P2 + 10×P3，其中 3 项已修：

| # | 项 | 严重度 | 修复 |
|---|---|---|---|
| TYPES-01 | HSM.respond 基类签名宣称 None 合法但 SpeckHSM 对 None 抛 KeyError（类型层 LSP 冲突） | P2 | 基类 docstring 明确契约：per-terminal 后端 MUST 将 terminal_id=None 视为前置条件缺失并抛 KeyError；签名默认值仅表示"对单钥后端无意义"，绝非"对 keyed 后端合法"。生产路径恒传具体 id（protocol.py:621），无行为变更 |
| TYPES-03 | DeviceKeyStore 读方法（all_keys/c2_history）无锁而 4 个变更方法持 RLock，契约不一致 | P3 | 两读方法同样持 self._lock |
| TYPES-04 | load() 裸 int(tid_str) 接受 "1_0"/"+7"/" 9 " 等非规范 JSON 键静默重映射终端 id | P3 | 严格校验 tid_str == str(int(tid_str))，非规范键抛带路径 ValueError |

types 其余 P3（deferred，见共识综合）：TYPES-02（KeyError 混装两类错误 + _finish_pass except Exception 边界）、TYPES-05（flush 写放大）、TYPES-06（tuple 返回语义）、TYPES-07（int 强转 7.9/bool）、TYPES-08（state 字符串状态机）、TYPES-09（畸形 C2 ValueError 穿透 vs 错误帧分裂）、TYPES-10（先评分后验 C2 的中间态）、TYPES-11（hsm_status isinstance 分派）

## 第四轮修复（silent-r2 复审新发现）

silent-r2 复审：9/9 已修项 VERIFIED（含 PS5.1 上 4 组 CI 探针），新发现 1×P2 + 6×P3，本轮全部修复：

| # | 项 | 严重度 | 修复 |
|---|---|---|---|
| R2N1 | on_extra_response 先累分（+=）后验 C2 → 失败尝试污染会话、更正重试双计分 → 静默 REJECT 误判（实测复现） | P2 | on_response 与 on_extra_response 均改为 _update_session_c2 前置（验证/绑定 C2 在任何评分状态变更之前，失败尝试零状态残留）。回归测试 test_gray_failed_c2_attempt_does_not_double_count：4×7=28 灰区 + 失败尝试 3×8 + 干净重试 → 断言 PASS hd=28（旧行为 REJECT hd=52） |
| R2N2 | 变更方法先改内存后 save，save 失败不回滚 → 后续成功 save 静默提交"已报告失败"的操作（setkey 链路最尖锐） | P3 | key_for/set_key/set_c2_history/clear_c2_history 四方法 save 失败时回滚内存变更再 raise。测试 test_mutator_rolls_back_on_save_failure（失败替换+失败新增+后续成功 save → 落盘不含失败项） |
| R2N3 | _finish_pass except Exception 不绑定不记录 → NameError 与缺钥同形 | P3 | except Exception as exc + stderr 打印类型与消息（"[HSM] R2 generation failed: Type: msg"） |
| R2N4 | 0x0093 RESULT 短载荷静默切片 r2、0x0094 CONFIRM 错长度裸 struct.error（违背 parse 文档的 ValueError 承诺） | P3 | 两分支加精确长度校验（10B/5B）→ ValueError。测试 TestParseLengthValidation（CRC 合法的畸形帧 + 全长 sanity） |
| R2N5 | load() 对 "terminals": [] 抛裸 AttributeError（无路径上下文） | P3 | terminals 非映射 → 带路径 ValueError。测试 test_terminals_not_a_mapping_rejected |
| R2N6 | repl [ERROR] 行无异常类型（串口超时与密钥库故障同形） | P3 | [ERROR] {type(exc).__name__}: {exc} |
| R2N7 | 仓库根 %SystemDrive% 杂散缓存目录 | P3 | 已删除（本会话两次，成因是审查探针的 cmd 风格变量未展开；与代码无关） |

## 共识终审后补修（consensus PASS 后）

- **D-7（唯一 P3 OPEN，已修）**: set_c2_history 对无 key 终端现在抛带路径 ValueError（拒绝存一个 save() 会丢弃的窗口），main.py set_c2_history 入口预检。修复后 44/44 保持全绿。

## 回归证据（第四轮修复后 = 当前状态）

- python tests\test_a1_phase4.py → **44/44 OK**（20→33→39→44；direct 与 unittest 模式均 exit 0）
- python src\python\common\speck.py 自测 → exit 0
- python -m py_compile hsm/protocol/main → exit 0
- 契约 RESULT 行已含 4=REPLAY
- types 审查自证：mypy 三文件 0 issue
- 变异对照（tests-r2）：MUT-C 保护有效；MUT-A/B 缺口已关闭
- silent-r2 探针（PS5.1）：CI 门禁三通道 fail-closed 实证
