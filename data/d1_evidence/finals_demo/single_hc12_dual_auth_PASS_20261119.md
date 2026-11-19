# 单 HC-12 共享信道双板先后认证 PASS（2026-11-19 19:56）

## 配置
- 信道/波特率/模式：三只 HC-12 统一 **C001 / 115200 / FU3**（板B侧由 C006 改写，AT+RX 读回断言）
- PC 侧：**单只** HC-12（LinkE CDC = COM6），桥 `--serial-port COM6`（单口模式）
- 板A = v4c bit（三键+点名窗口），板B = seed2c bit（X1Y0 差异化布局+点名窗口）

## 点名过滤验证（单口裸串口）
```
ROLLCALL tid1 -> ANSWER tid=1 (ACCESS_REQUEST)
ROLLCALL tid2 -> ANSWER tid=2 (ACCESS_REQUEST)
ROLLCALL tid1 -> ANSWER tid=1 (ACCESS_REQUEST)
```
每次点名只有目标板应答——共享信道无串扰、无撞包（S_POLL_CHK 点名过滤在硅上成立）。

## 录入（新 bit 布局，旧模板已清）
- tid1：100 对，stable_bits=64，stability 100%
- tid2：32 对，stable_bits=64，stability 100%（enroll 每轮点名开窗在共享信道下正常）

## 先后认证（同一信道、同一只 PC 侧 HC-12）
```
VERDICT tid1 PASS hd=0 per=[0,0,0,0]   CONFIRM tid1 verified_r2=True   <- 板A 先
VERDICT tid2 PASS hd=0 per=[0,0,0,0]   CONFIRM tid2 verified_r2=True   <- 板B 后
```

## 结论
**两块板在同一信道/波特率下可先后与基站完成完整五帧认证**（老师方案验证通过）：
上行靠 ACCESS_REQUEST/CONFIRM 帧内 terminal_id 区分 A/B，下行靠 AUTH_POLL 点名+3s 授权窗口定向。

