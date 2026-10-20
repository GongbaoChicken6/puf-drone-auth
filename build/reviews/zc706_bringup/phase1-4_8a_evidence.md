# Phase 1–4 + 8a 执行证据（执行日 2026-10-20；含 auto-review 内容审查修复记录）

> 计划：docs/process/plans/zc706_migration_plan.md（R3 + 内容审查修正）
> 本文档原则：**只声明可复现的事实**，曲折与事故如实记录（spec-compliance 审查要求）。

## 执行提交链（实际 6+1 笔，非先前简报所称"8 笔"）

| 提交 | 内容 |
|---|---|
| 8e0ac88 | Phase 8a：ENROLL_IDLE_ACCEPT 参数门控注册支持（terminal_fsm/w3_top/tb） |
| a233486 | Phase 1：w3_top_zc706.v wrapper |
| 3f671ac | Phase 2：w3_top_zc706.xdc |
| a29c9cb | Phase 3：build_w3_board.tcl 重定向 |
| c0a32e9 | Phase 4：verify_wrapper.ps1（v1）+ 本证据初版 |
| 8f418cf | 审查修复：*.ps1 强制 CRLF checkout（PS5.1 解码事故，见下） |
| （待提交） | 内容审查 R2 修复批（见 §3） |

## 1. Phase 8a（RTL 注册支持）

| 验证 | 结果 |
|---|---|
| 全量 CI | ✅ 16/16 TB + Python 全门禁，exit 0 |
| tb 默认变体（param=1） | ✅ T1/T2/T3 + TE1（idle 接受→R1、背靠背→R1、超时自清）+ **TE2（重放拒绝）** 全 PASS |
| CI 附加段（-d ENROLL_NEG，param=0） | ✅ [TEN PASS] S_IDLE ignored CHALLENGE——**已入 CI**（内容审查 P2：原为手动一次性，已闭环） |
| 攻击 TB（defect-reviewer 自建，%TEMP） | 修复前 VULNERABLE → **修复后 BLOCKED (guard held)**（本人独立复跑两次） |

## 2. Phase 1–4 交付与验证

- Phase 1（wrapper）：7 处改动全落地。**残留检查实测**（诚实修正）：zc702/D18/C19/GPIO_SW_N/W6/6'h00 零命中；**LVDS_25 命中 1 处=「禁抄 ZC702 的 LVDS_25」告警注释（故意保留）**；裸模式 W7 命中 2 处=ZC706 按键名 SW7 误伤（计划已把模式改为 \bW7\b）。
- Phase 2（XDC）：与计划 R3 逐行一致。**本文件已随 2026-10-20 真实构建全程通过**（synth/opt/place/route/bitstream 全链 DRC 0 错，见 §3 P0 行终态）。
- Phase 3（tcl）：重定向完整，grep zc702 零命中。
- Phase 4（门禁 v2，含内容审查修复）：**覆盖口径=xvlog/xelab 语法 + XDC↔wrapper 端口交叉检查 + xsim.dir 预清 + env 守卫；不含 synth/IP/时序/DRC**。实测 exit 0：`XDC port cross-check OK (10 wrapper ports all covered)` + `Compiling module work.w3_top(ENROLL_EN=1)` + 快照 `w3_top_zc706_chk`（初版证据误写 w3_zc706_chk，已更正）。

## 3. 内容审查（三代理：defect-reviewer/spec-compliance/silent-failure）发现与修复

| 级别 | 发现 | 修复 |
|---|---|---|
| P0 | build_w3_board.tcl srcdir 契约断裂（计划传仓库根，tcl 要 src；实测 14s 即 12-172） | tcl 加 $SRC/rtl 守卫 + 用法注释；计划命令改传 src |
| P0 | clk_wiz_0 IP 集成断裂（synth 8-439）+ w2_waiver 豁免从未生效（XDC 读取时 nets 不存在→静默匹配 0；generate 块分隔符是 '.' 非 '/'）——脚本史上从未可端到端跑 | ✅ **终态：generate_synth_checkpoint=0 全局综合 + XCI 显式入 sources_1 + 综合后应用豁免（-hierarchical {*u_ro_ring/n1}，32 网响亮校验）+ WNS 时序门禁。2026-10-20 全链通过：`BITSTREAM_SUCCESS WNS=1.060`，DRC 0 错，write_bitstream completed，产物 w3_top_zc706.bit（13.3MB）；利用率 4459 LUT(2.04%) / 6545 FF(1.50%)（对照 ZC702 基线 4190/6133，增量=ENROLL+MMCM，合理）**。w2_waiver.xdc 头注释已补勘误说明 |
| P1 | 8a 注册分支可被「压制 RESULT→超时→注册挑战→重放」绕过 P2-1 守卫（攻击 TB 实证 VULNERABLE） | 两分支清 calc_done_flag + TE2 回归锁入 CI；复跑攻击 TB=BLOCKED |
| P1 | verify_wrapper 覆盖口径过Claim（xvlog 过但 synth 死） | v2 重写：诚实口径 + XDC 端口交叉检查 + 预清 + env 守卫 |
| P2 | TEN 不在 CI（手动一次性，工件已被并发 CI 清掉） | ci_regression.ps1 新增 ENROLL_NEG 段（[PASS] 实测） |
| P2 | TE1 断言只查 msgid 不查 pay_len | 两轮均加 len==32 断言 |
| P2 | 构建无时序门禁（WNS<0 仍 BITSTREAM_SUCCESS） | route 后 WNS<0 → TIMING_FAILED exit 4 |
| P2 | 证据文档"grep 零命中"与复跑不符 | 本文档 §2 如实改写 |
| P3 | tcl 残留 UG850/保姆教程陈旧注释；XDC 头验证口径误导；wrapper auth_btn 注释无来源；xsim 工作库污染窗口；env 黑洞；快照名漂移 | 全部修复（见对应文件） |

## 4. verify_wrapper.ps1 事故记录（诚实链）

c0a32e9（10-20 09:26）入库 v1 = LF 行尾 + UTF-8 无 BOM + 中文注释 → **PS5.1 按 ANSI/GBK 解码吃掉换行，param( 被吞进注释，脚本解析崩溃**——当时仅手动跑过等价命令未整跑脚本，故未暴露。8f418cf（09:34）修复：工作区转 CRLF + .gitattributes `*.ps1 text eol=crlf`（防他机重签出复发）。v2（本次）再加交叉检查后整跑复验 exit 0。教训已沉淀：**入库≠可运行；门禁脚本必须整跑**。

## 5. 上板操作携带项（Phase 8 现场必读）

1. **每次 enroll 前按 SW13 复位终端**（S_SESSION 驻留态忽略 0x0091；自证认证 PASS 后直接 enroll 会停滞退种）。
2. **站端锁步**：enroll 驱动必须等上一轮 R1 frame_done 后再发下一批种子（rx_ok_latch 非等待态 1 拍即清，抢发=帧静默丢弃）。
3. **安全注记（W5 报告如实声明）**：ENROLL_EN=1 = 站方可主动发起 PUF 查询（注册语义，物理近邻假设）。
4. **Plan B 备案**：若 8a 路径出意外，站端逐轮全认证流采集（每轮按键+4 CRP，75 轮），不动 RTL。
5. XDC 终验 = Phase 5 首次综合 DRC（前身约束集已过 0 错 0 警）。

## 6. 备注

- rtl-guardrails 的 check_style.py 未随技能安装（结构规则已手工遵守）；如后续补装可 --fix 规整。
- 执行日实际为 **2026-10-20**（此前口头/初版证据写 10-19 有误——spec-compliance 审查指出提交时间戳 09:26-09:34 +0800）。
