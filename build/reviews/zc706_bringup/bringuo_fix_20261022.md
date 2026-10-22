# ZC706 bring-up 修复证据（2026-10-22）

## 故障与根因
- 现象：心跳闪（时钟/配置正常）但按 SW7 认证按键后 L/C/R LED 无任何反应
- 根因 1（已实证修复）：消抖器 btn_state/btn_prev 复位值 1'b0 与板级空闲电平 1 不符 → 复位释放 ~10ms 幽灵 0→1 沿；TB 反极性建模掩盖
- 根因 2（疑似，未实证）：真实硅片环振阵列未起振 → ro_entropy seed_acc==0 fail-closed → re_seed_valid 恒 0 → auth_start_pulse 被 & re_seed_valid 门控永久屏蔽
- 用户观察佐证：按住 SW13 时 DS35"0"灯亮 = 时钟停止致心跳计数器冻结高电平（时钟在跑的铁证）

## 修复内容（auto-review M1-M12 全处置）
| 项 | 内容 |
|---|---|
| 极性修复 | btn_state/btn_prev 初值+复位值 → 1'b1；两 TB 极性改板级真实极性（空闲1/按下0/松开触发） |
| 门控旁路 | w3_top 新参数 SEED_GATE_EN（默认1=原语义；板级 wrapper 传0=bring-up 旁路），豁免条目见 migration_plan |
| M1 旁路 TB | tb_w3_top_seedgate 三 DUT：旁路放行 / 门控 fail-closed 压制 / 零熵被拒集成 |
| M3 回归锁 | 两 TB 加复位后 220k 拍静默窗断言 + 按住期零触发断言（变异实证旧 TB 全盲） |
| M4 故障口 | ro_entropy 新增 seed_fault 输出（零熵被拒独立指示）+ tb_ro_entropy T14 零种子用例 |
| M5 观测出口 | 心跳编码：seed_fault=1 时 hb_cnt[24] 快闪 ~3Hz（正常 0.75Hz），runbook LED 表已载 |
| M8 竞态守卫 | terminal_fsm seed_load 重装载限定 S_IDLE（旁路参数空间下新开的 1 拍竞态） |
| M2/M6/M7 文档 | migration_plan 豁免条目（时限/撤销/代价/跟踪任务）+ Phase7②/8-6 与 runbook Stage6 挂起标注 + 契约偏离记录 |
| M10/M12 | keyloop 看门狗 50ms→120ms；wrapper 缩进对齐 |

## 验证
- 全量 CI：**17/17 PASS**（含新 tb_w3_top_seedgate 5.1s；ENROLL_NEG 锁 + 威胁 PoC + 金丝雀 + 契约同步全绿）
- Vivado 构建：BITSTREAM_SUCCESS **WNS=2.023**（board_zc706_build2.log，21:00:49 产出 w3_top_zc706.bit）
- 板上烧写：21:02 program OK（End of startup status: HIGH），修复版已上板
- auto-review：4 子代理 + 共识综合（synthesis_round1），FAIL(P0×1+P1×4+P2×2+P3×5) → 本批全处置

## 待办（豁免条目跟踪任务）
板上读 seed_fault（心跳频率）裁决环振假设 → 未起振则 VIO/ILA 采 16 环计数 → 修复后恢复 SEED_GATE_EN=1 → 重跑 Stage 6 闭合 P1-5 板级实证
