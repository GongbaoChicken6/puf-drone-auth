# Phase A 执行记录（桥接 freqs 适配 + provisionkey 语义 + P3 清理）

**日期:** 2026-10-17 ｜ **依据:** 《前端适配与整合计划》v1.1 §3 ｜ **对象:** web-over/web（仓库 server 零改动）
**执行:** 前端探索会话；全部变更位于 web-over/web（bridge/web_bridge.py、tools/sample_hd.py、src/*.ts）

## 变更清单

**Phase A 核心（五触点 + provisionkey）**
| # | 内容 | 位置 |
|---|------|------|
| A1 | 器件再水化：freqs(16 int) 重建 SimulatedTerminal 并经 _terminals 私有字典注入（README 偏差 D20 待 Phase C 登记）；_auth_count 一并恢复（防 C2 回卷误判 REPLAY） | web_bridge._do_bootstrap |
| A2 | STATE_SCHEMA 升 v2；BridgeState 加载显式校验（v1 → legacy_tids，不复活半套旧状态）；RealApp 在 TemplateDB/CRPPoolRegistry 构造前一次性迁移：凡无 v2 freqs 的模板终端级联清理（池文件+模板段+stability sidecar+状态）——期间修复一处真实 bug：TemplateDB 存储为扁平 {tid:{seed:resp}}，初版误按 "terminals" 包装层清理导致 POOL_EMPTY | BridgeState / RealApp._legacy_stale_tids / _purge_stale_terminals |
| A3 | freqs_sig = sha256("freqs-v1:"+join) 前 16 hex，双侧（web_bridge 与 sample_hd）逐字面同实现；sample_hd.load_device_secret → load_device_freqs（16 int 校验、v2 schema 校验） | web_bridge.freqs_sig / device_sig；tools/sample_hd.py |
| A4 | 注册即 provisionkey 语义：derived_key → store.set_key + hsm.set_key（不再随机铸钥；_do_auth 内 ensure 保留为 no-op 兜底；显式 /api/setkey 仍可覆盖，golden 不受影响） | web_bridge._do_enroll |
| A5 | persist_terminal 落盘 freqs+auth_count；--reset-demo 经同一链路自动恢复 | web_bridge.persist_terminal |

**P3 顺带清理（按钮审计遗留）**
- N4 index 轮询去重（状态未变不重写 DOM，焦点/悬停/dash-hint 不再被 5s 打掉）
- N5 mock 保真：回放脚本按提交的 tid+mode 分流（normal/spoof/replay/gray/evilbase 各自正确事件序列与结果码，evilbase 含终端侧 BLOCKED 日志）
- N6 单步空队列死态 → 可见提示；viz 刷新 loading 防重
- N7 断线 run 残留 → setLink 检测桥接重启（uptime 回退）按中断收尾并留痕
- N7b tid 选择组仅 live 态显示；F5 help-card tabindex=-1（焦点归还生效）
- 附加：_serve_static 路径判定改 is_relative_to（与 _serve_docs 同款加严）

## 验收门禁（全部 PASS）

| 门禁 | 结果 |
|------|------|
| python -m py_compile（bridge + sample_hd） | ✅ 0 / 0 |
| tsc --noEmit ＋ vite build | ✅ 0 / 0（dist 重建，新 chunk 含全部修复） |
| --once s1 首启（全新沙箱：bootstrap→enroll→provisionkey→auth） | ✅ verdict=PASS，confirm.done verified_r2=true，EXIT=0 |
| 重启闭环（第二个独立进程同沙箱 s1） | ✅ freqs/_auth_count 再水化后 PASS，EXIT=0；状态文件 schema=v2、terminals.7.freqs=[6057,7701,…] |
| 八场景套件 | ✅ s1=0 s2=0(REJECT) s3=0(REPLAY) s4=0(gray→PASS) s5=0(序列止于 3=POOL_EMPTY) s6=0(500 对,stable 64/64) s7=0(evilbase) golden=0(R2=7b45b0545e59aa94 逐字命中) |
| v1 迁移（受控夹具：v1 state+扁平模板+池文件） | ✅ purge→重注册→S1 PASS→状态转 v2+freqs、池重建，EXIT=0 |
| sample_hd 双侧一致性 | ✅ EXIT=0；intra μ=1.33（≈注释口径 1.3/64）/ inter μ=23.84 / Δμ=22.51；hd_sample.json 含 device_sig |
| HTTP 消费 | ✅ GET /api/viz/hd → "source":"SAMPLE"（双侧 freqs_sig 匹配，未退回 LIVE） |
| mock 全量回归（v1 探针三页） | ✅ S1/S2/连播/暂停/单步/导出/3D 相机/F 截图全过，三页零页面错误 |

## 备注
- intra μ=1.33 与 main.py 注释口径（flip=0.02→期望 ~1.3bit/64bit）吻合——ROPairingPUF 语义下的实测佐证。
- 迁移 bug（模板扁平结构）由门禁当场拦截并修复——「改完即测」再次生效。
- 遗留：README 偏差表 D20（_terminals/_auth_count 私有依赖）与 /docs 映射说明按计划留待 Phase C 文档对齐一并登记；观察 7a（暂停后单步采样）经查为正常语义（幕执行中采样偏早），无需改码。
