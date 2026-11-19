# N16 双剧本认证流程定案：板B 本身份拒绝接入 + 冒充板A 假冒警报（2026-11-19 20:35）

## 需求
板A=通过认证的机器；板B=被拒绝的机器。板B 用 SW12 拨码切换身份，按 SW8 发起认证：
- SW12=0010（tid2 本身份）→ 显示**被拒绝接入**
- SW12=0001（冒充 tid1 板A）→ 显示**假冒接入**

## 实现（桥侧 N16，前端零改动）
1. `--revoked-tids 2`：tid2 视为已知但已吊销——照常排队/选中，五帧走完
   （随机种子 CHALLENGE，板子正常应答），RESULT 恒为 REJECT，verdict 带
   note="device revoked/unauthorized -- access denied" → 前端拒绝动画。
2. 假冒分类器：verdict REJECT 且平均 HD ≥ TAU_REJECT（板间级，深红）→ 追加
   `channel.intrusion(kind=access, source=impostor-classifier)` → 前端大警报弹窗，
   verdict 附 `impostor: true`。灰区噪声失配不触发（仅深红）。
3. 一键脚本 v3：新增 `-RevokedTids`（默认 '2'）自动传给桥。

## 硅上实测（共享信道 C001，单 HC-12）
```
# 剧本1: 板B SW12=0010 + SW8
PARKED: 板B(tid2) 已排队
VERDICT tid2: REJECT | note: device revoked/unauthorized -- access denied | hd: 255

# 剧本2: 板B SW12=0001(冒充板A) + SW8
PARKED: tid1 已排队
VERDICT tid1: REJECT | hd_per: [33,30,32,30] | impostor: True
IMPOSTOR_ALARM: tid=1 claimed but hardware fingerprint is at inter-device level
                (mean HD 31/64 per response) -- cloned/spoofed identity
```
板间 HD ≈31/64 ≈ 48% —— 与"同布局 HD 5-7%"形成鲜明对照：seed2 差异化布局
正是假冒检测的定量依据（答辩口径：噪声级失配=环境扰动，板间级失配=不是同一台硬件）。

## 演示操作
| 步骤 | 操作 | 前端表现 |
|---|---|---|
| 1 | 板B SW12=0010, 按 SW8, 点【开始验证】 | 排队→五帧→红色 REJECT 拒绝动画 |
| 2 | 板B SW12=0001, 按 SW8, 点【开始验证】 | 排队→五帧→REJECT+假冒接入大警报 |
| 3 | 板B SW12 拨回 0010（收尾复位） | — |

