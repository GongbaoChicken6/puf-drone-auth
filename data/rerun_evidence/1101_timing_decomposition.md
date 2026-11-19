# 板B端到端时序分解（论文表1-1/表3-3 回填素材，Phase 5.4）

来源：W3_BoardB_Bringup_Report_20261027/logs/serve_fix.log（2026-10-27 22:52，串口修复后 serve 2/2 PASS，毫秒级 [WIRE] 时间戳）
口径：PC 侧收/发时刻差，含 UART 115200 线上时间；tid=2，HD=0（4×8B 响应全零偏差）。

## 第1轮（22:52:48）
| 段 | 间隔 | 说明 |
|---|---|---|
| ACCESS_REQUEST RX → CHALLENGE TX | +31ms | 基站处理+发送 |
| CHALLENGE TX → RESPONSE_R1 RX | **+16ms** | 板侧 PUF 测量+响应上线 |
| R1 RX → RESULT TX | **0ms** | 基站比对+判决即时 |
| RESULT TX → CONFIRM RX | **+16ms** | 板侧 R2 复算+确认 |
| **CHALLENGE→CONFIRM 合计** | **32ms** | 六帧交互核心段 |
| ACCESS→CONFIRM 全程 | 63ms | 含首次接入处理 |

## 第2轮（22:52:55，同构）
CHALLENGE→R1 +16ms；R1→RESULT 0ms；RESULT→CONFIRM +15ms；**CHALLENGE→CONFIRM 31ms**。

## 论文写法建议
- 表1-1/表3-3 增行：单次认证耗时——仿真口径约14ms（不含串口）+ **实板端到端 CHALLENGE→CONFIRM 31~32ms（含串口传输，tid=2 两轮实测，来源 serve_fix.log）**
- 摘要"约14ms"可并列"实板端到端约32ms"。
