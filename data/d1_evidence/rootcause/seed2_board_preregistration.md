# 布局变体B（seed2）板端验收判据 · 预登记（2026-11-01 17:25，构建进行中、烧板之前立靶）

## 背景
生产 bit 与 seed2 bit：同 RTL/同约束/同时序门禁，唯一差异 = 32 个环振单元 PBlock 重定位到不同时钟区域。
根因预测（三路调查共识）：环频排序由布局决定 => 布局变体的排序应与生产 bit 独立 => 指纹可区分。

## 预登记判据（烧板后逐条对账）

| # | 实验 | 预期 | 判定 |
|---|---|---|---|
| P1 | seed2 板对 tid=1 模板（生产排序）跑 auth 1 | **REJECT**，total HD 落在 90~170/256（独立排序理论中位 127；≥64 即 REJECT） | 唯一性成立=根因修复实锤 |
| P2 | seed2 板 setkey 2 → enroll 2 100（铁律：先 setkey 再 enroll） | 100 CRP 入库 | |
| P3 | seed2 板 auth 2（自己模板） | **PASS**，HD ≤ 24 | 自一致性保留 |
| P4（可选）| 生产 bit 板对 tid=2 模板 auth | **REJECT**，HD 90~170 | 对称性证明 |

## 失败分支预案
- P1 得 PASS（HD≤24）：seed2 排序与生产仍相同（PBlock 不足以致变）→ 改用双区域拆分环阵列或逐环 LOC 重定位，重建再测
- P1 REJECT 但 HD<64 边缘：排序部分相关 → 记录数据，追加 seed3 变体
- 时序失败（WNS<0）：脚本已内置门禁直接退出，不会产出坏 bit

## 证据文件
- 构建：rootcause/build_seed2.log、board_zc706_seed2/ring_sites_seed2.rpt
- 板端：d1_evidence/1101_seed2_唯一性实验.log（届时生成）
