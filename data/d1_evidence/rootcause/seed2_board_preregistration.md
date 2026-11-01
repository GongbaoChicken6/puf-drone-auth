# 布局变体B（seed2）板端验收判据 · 预登记 v2（2026-11-01 18:20 修订版）

> v1（17:25）经 auto-review 五路复审后升级：钉死工件哈希、MC 立靶带宽、补非退化对照与完整失败分支、定义结果回填。**烧板前若现场重算任一哈希与本文件不符，预登记即失效，须重立靶。**

## 工件锚点（钉死）

| 工件 | SHA256 |
|---|---|
| 生产 bit（基线，已补录 data/bitstreams/w3_top_zc706_prod_20261027.bit，原件 build/board_zc706/） | `24ED4EED6A175C980FF718529647EC2F3AF7ABA3650E8F6B58461EF18F468173` |
| seed2 变体 bit（build/board_zc706_seed2/w3_top_zc706_seed2.bit） | `0F4E605D481E81C825C2F028F78B9428EE0214C3ABCDF25FE294EF433ABB9D3B` |
| 模板快照（rootcause/templates_snapshot_tid1_20261101.json，tid=1 100 CRP） | `02CEF985FCF6760E862DD4DAA4AFE634EF1DDCAA41269351AF90ABE6007C23B3` |
| 基线提交 | 1760b72（勘误见 consensus 附录） |

## 背景（已按复审修正）

- 生产 bit 与 seed2 bit：**PUF 响应通路文件同源**；差异 = ①32 环振单元 PBlock 迁入 CLOCKREGION_X1Y0（生产自然布局经原样复跑实测落 X1Y4/X1Y5，零站点重叠）；②生产 bit 早于 uart_rx 修复 6b942af（不在 PUF 响应通路，+4 LUT，如实披露）。
- 布局差异证据以**落位对比+载荷差异+复跑确定性**为准（整文件 SHA256 因头部时间戳不作布局论证，见 consensus 勘误）。
- 根因预测：环频排序由布局决定 ⇒ 独立布局 ⇒ 独立排序 ⇒ 响应位约半数翻转。
- **带宽推导（MC 立靶，review/lead_verify_and_mc_band.log）**：用 tid=1 真实 enrolled 配对表，2000 次独立随机全序的轮 HD（4 种子×64bit=256 位）：min=34，p5=87，**中位 129**，p95=168，max=202；落 [90,170] 占 89.8%；**低于 64（不 REJECT）概率 0.2%**（位相关性使二项带不适用，此为实证分布）。

## 预登记判据（烧板后逐条对账）

| # | 实验 | 预期 | 判定含义 |
|---|---|---|---|
| P1 | seed2 板对 tid=1 模板 auth 1 | **verdict=REJECT（硬判据，HD≥64）**；HD 预期落 90~170（MC p5~p95 外延） | 唯一性成立=根因修复实锤 |
| P2 | setkey 2 → enroll 2 100（铁律：先 setkey） | 100 CRP 入库 | |
| **P2c** | tid=2 模板非退化对照（复用 analyze_template2 逻辑） | **两两 HD 中位 ∈ [25,40]**（恒定/退化响应 ≈0 → 拦截） | 排除"环振被搬死"假修复 |
| P3 | seed2 板 auth 2（自模板） | **PASS，HD ≤ 24** | 自一致性 |
| P4（可选） | 生产 bit 板对 tid=2 模板 auth | REJECT，HD 90~170 | 对称性 |

## 失败分支预案（完整版）

| 情形 | 解读 | 下一步 |
|---|---|---|
| P1 PASS（HD≤24） | 排序未变：PBlock 不足以致变 或 烧错 bit（先核对烧写哈希记录！） | 核对 bit → 换双区域拆分/逐环 LOC 重建 seed3 |
| P1 HD 落 25~63（灰区）或 64~89 | 罕见但合法（MC 下界 34；0.2% 概率 <64） | **换种子再跑 auth 1 两次**取中位后再判；仍灰区→记录数据、重建 seed3 |
| P1 REJECT 但 HD>170 | 超出 p95：响应偏置或部分退化 | 先看 P2c；P2c 正常则记录（仍为 REJECT，主张成立但需复核带宽） |
| P2 enroll 失败/超时 | 链路问题（对账昨晚 FAQ） | 重烧 bit 再 enroll（超时不算数） |
| **P2c 中位 ≈0** | **退化恒定响应（环振被搬死）——假修复** | 立即停，逐环 LOC 重定位方案重建 |
| P3 FAIL（HD>24） | 自一致性破坏（温度/噪声/时序） | 检查 WHS 记录（+0.055）、重跑；连续 FAIL 停实验 |
| 任何 auth 超时/无 RESULT 帧 | 链路/状态机问题 | 重烧 bit 复位 FSM 再试；超时不算数 |

## 烧板防错规约

烧写前由 Lead 现场重算待烧 bit SHA256 与本文件锚点比对（不一致=停）；烧写目标板 JTAG 序列号记录进回填表；烧写命令一律绝对路径。

## 结果回填表（实验后填写，未填完实验不算关闭）

| # | verdict | 实测 total HD | 日志文件:行 | 操作者 | 日期 | bit SHA(烧写时) |
|---|---|---|---|---|---|---|
| P1 | | | | | | |
| P2 | —（100 CRP） | | | | | |
| P2c | —（中位=__） | | | | | |
| P3 | | | | | | |
| P4 | | | | | | |

## 证据文件（均已入库）

- 构建：rootcause/build_seed2.log、build/board_zc706_seed2/{ring_sites_seed2.rpt, timing.rpt, utilization.rpt, MANIFEST.txt}
- 立靶：review/lead_verify_and_mc_band.{py,log}
- 复审：review/（五路报告 + rerun_*）
