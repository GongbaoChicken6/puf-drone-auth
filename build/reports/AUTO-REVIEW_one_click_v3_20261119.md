# auto-review 报告 · demo_one_click v3（2026-11-19 17:20）

审查方式：**降级单代理多视角串行**（本会话无 subagent 派遣原语；Team 任务板可见但无 spawn）——
依次以【缺陷审查 / 规格合规 / 静默失败 / 类型安全 / 测试缺口】五视角过一遍，再以【共识综合】去重定级。

审查范围：`scripts/demo_one_click.ps1`（v2→v3 全量重写）、`web/bridge/web_bridge.py`（认证入口不变式）、
`src/python/server/crp_pool.py`（limit_to）、`web/bridge/enroll_real.py`（录入后限池）、仓库种子数据（模板/池）。

## 发现与处置（P0=0 / P1=2 全修 / P2=2 全修 / P3=2 记录）

| 级别 | 发现 | 证据 | 处置 |
|---|---|---|---|
| P1 | 模板检查只数对数，不验证指纹匹配——换 bit 后模板失配要到演示当场点验证才暴露 | `bit_manifest` 只能发现 bit 变了，不能发现"变了但没重录"的 REJECT | 新增**认证冒烟**（第7步，poll+select 真跑五帧判 PASS）；实测 tid1=PASS hd=1 / tid2=PASS hd=0 |
| P1 | 桥启动把仓库 `pool_2` 播种进沙箱 → 可抽到无模板种子 → `KeyError: 'no template for seed'` | 17:12 真板实录两轮 KeyError；清沙箱池后重启又复现（POOL_EMPTY） | 双修：①`_auth()` 抽种子前幂等执行 `limit_to(template keys)` 不变式；②删除仓库 `data/crp_datasets/pools/pool_2.json`（备份 .bak_n13_keep） |
| P2 | 脚本字符串拼接 bug：`Warn "a" + $b` 被解析成两参数，冒烟结果被吞 | 修复前输出 `tid2 认证冒烟异常: `（空） | 改为 `Warn ("..." + ...)`；修复后输出完整 `SMOKE PASS hd= 0` |
| P2 | v2 只烧板A/单口，与今天双板+多口现实脱节；SW7 已坏的板A 无可用按键 | v2 事实卡：bitA=v4、无 --serial-multi、无 --tid-port、只烧 SN_A | v3：板A 烧 v4b（三键）、板B 烧 seed2b（差异化+三键）、双口归类、`--serial-multi`+`--tid-port`、双密钥、双模板 |
| P3 | `Die()` 用 MessageBox，非交互环境可能阻塞 | 无 headless 用例 | 保留（演示现场人工运行）；已在脚本注释中说明 |
| P3 | 冒烟每板约 14s（poll 2.5s + 五帧 11s），双板约 30s | 实测 | 接受：换 bit 静默失配的代价远高于 30s |

## 误报驳回 0 项（本轮未出现自相矛盾发现）

## 回归证据

- `python -m pytest tests/ -q`：**220 passed / 1 skipped / 3 subtests**（web_bridge/crp_pool 改动后）
- `verify_wrapper`：**VERIFY_WRAPPER_PASS**（RTL 三键改动）
- 真实彩排（-NoBurn，双板在线）：**8/8 步全绿**
  - COM11→tid2、COM6→tid1 自动归类正确
  - 多口模式 `1=COM6,2=COM11`
  - setkey tid1/tid2 均 ok
  - 模板 tid1=100 对 / tid2=32 对
  - 冒烟 tid1 PASS hd=1、tid2 PASS hd=0

## 已知行为（演示口径）

- **按键**：板A/板B 都按 **SW8（右）**；板A 的 SW7 触点已坏勿按；SW7/SW9 为冗余备键。
- **换 bit 铁律**：任何重跑实现的 bit 都会让模板失效 → 必须 `-Enroll` 重录。
- **仓库种子**：`data/templates` 与 `data/crp_datasets/pools` 的 tid2 数据已移除（备份保留），沙箱自持久化。
- **回退**：SW11 拨回 `00000` + JTAG 8 秒重烧，链路零损失。

（完）
