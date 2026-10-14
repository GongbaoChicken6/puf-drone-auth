# CRP 池运维 SOP + 暂存-释放语义（W4-P4 T4）

> 编制 2026-10-14｜依据审查 B-P2 F5（限速只削峰不防池耗尽）+ A/B/C 三代理 T4 验收缺口
> 代码：src/python/server/crp_pool.py + src/python/server/protocol.py

## 1. 池模型

每个终端一个 CRP 池（默认 pool_size=100 个种子）。状态三集：

| 集合 | 含义 | 由谁改 |
|---|---|---|
| `_available` | 已注册（有模板）可用的种子 | `reserve()` 铸造 / `add()` 导入 / `release()` 回滚 |
| `_used` | 已消费（不可再抽） | `draw()` 加入 / `unuse()` 退回 |
| 剩余 = available − used | 还能支撑的认证次数 | — |

**每次认证消耗**：主轮 4 个（`N_CHALLENGES`）；灰区追加 3 个（`N_EXTRA_CHALLENGES`）。

## 2. 暂存-释放语义（staging-release，本次新增）

**问题（B-P2 F5）**：`draw()` 把种子永久记入 `_used`。攻击者只需周期性发 ACCESS_REQUEST，即使被限速（10 次/分），约 90 秒仍能排空 100 种子池，且 `_used` 持久化 → 永久失效，必须重新注册。

**修复**：种子在会话进行期间处于「暂存」态（`protocol._staged`），只有三种归宿：

| 归宿 | 触发 | 池影响 |
|---|---|---|
| **提交**（commit） | 认证 `RESULT_PASS` | 种子永久消费（正常路径） |
| **释放**（release） | 认证 `RESULT_REJECT`（R1 打分不达标 / CONFIRM_FAIL） | `unuse()` 退回，池不缩水 |
| **清扫**（sweep） | 会话停滞超过 `SESSION_TIMEOUT_S`（默认 30s） | `unuse()` 退回（防「开会话后沉默」向量） |

**净效果**：池只在认证**成功**时缩小。攻击者洪泛失败认证不再消耗池，只消耗服务端 CPU（由令牌桶限制）。

**函数对照**（易混，务必区分）：

- `release(seeds)` —— 移除**从未注册**的种子（注册中断回滚，方向：available → 丢弃）
- `unuse(seeds)` —— 退回**已抽取未消费**的种子（暂存释放，方向：used → available）

## 3. 攻击成本对比（100 种子池）

| 攻击方式 | 修复前 | 修复后 |
|---|---|---|
| 洪泛失败认证 | ~90s 排空（永久） | **不消耗池**（种子释放） |
| 洪泛正确认证 | 每次减 4 | 每次减 4（**设计使然**——真实认证必须消耗 CRP） |
| 开会话后沉默 | 每次减 4（永久） | 30s 后自动退回 |

**残余风险（诚实标注）**：拥有合法 PUF 的攻击者若真能通过认证，仍会消耗池——这是 CRP 语义的固有成本，非缺陷。缓解：池容量规划 + 余量告警（下表）。

## 4. 余量告警阈值

| remaining_pct | 级别 | 动作 |
|---|---|---|
| > 50% | 正常 | — |
| 20~50% | 注意 | 记录；运行 `repl` 查看各终端状态 |
| < 20% | **告警** | 触发重新注册流程（§5） |
| = 0 | **耗尽** | 该终端认证返回 `RESULT_POOL_EMPTY`（专用码，非 PUF 失败） |

阈值来源：项目风险表「池耗尽（< 20% 剩余）触发告警」。

## 5. 池补充 SOP（重新注册）

池耗尽后**唯一**恢复手段是重新注册该终端（CRP 池不能凭空扩充——模板与种子的对应关系只能由设备实测建立）：

```
# 1) 确认耗尽（可查看剩余）
python -m src.python.server.main      # REPL 内执行状态命令

# 2) 设备上电，确认能被注册（拨码/链路正常）

# 3) 重新注册：reserve 新种子 + 采集模板 + 写库
#    enroll 内部：reserve(n) -> 逐批 CHALLENGE/RESPONSE -> majority 表决 -> templates.enroll
#    中途失败会自动 release() 回滚未注册的种子（见 enroll.py）

# 4) 旧种子处理：reset() 清空 _used（重新注册即视为新一轮）
```

**注意**：重新注册会**替换**该终端的模板与池，此前的会话凭据作废，需重新 `setkey` 下发设备密钥。

## 6. 相关测试

| 测试 | 覆盖 |
|---|---|
| `tests/test_dos_flood.py::test_flood_does_not_exhaust_pool` | 50 请求洪泛池不耗尽 |
| `tests/test_dos_flood.py::test_rate_limit_recovers` | 限速 61s 后恢复（令牌桶懒充值） |
| `tests/test_dos_flood.py::test_failed_auth_returns_seeds_to_pool` | 失败认证退回种子（暂存释放） |
| `tests/test_dos_flood.py::test_stalled_session_swept_and_seeds_returned` | 停滞会话清扫 |
