# 共享信道伪基站竞速攻击·检测全链 PASS（2026-11-19 20:20）

## 拓扑（N15：单 HC-12 共享信道）
- PC 侧仅一只 HC-12（LinkE COM6）；攻击帧经基站电台注入空中（C001 公开空口参数，
  攻击者配同款模块即可入信道——由基站电台模拟其发射），**两块板都能听见注入帧**。
- 攻击 API 内置于桥：`/api/attack/arm`（竞速武装）、`/api/attack/inject`（帧注入）、
  `/api/attack/disarm`；网页控制台 `fake_result_attack.py --via-bridge --rogue-web 8643`。

## 竞速攻击-检测链（板A tid=1 实测）
```
ARMED: ok=True armed_for=1 r2=deadbeefcafe0110
IDS: frame fake RESULT on air            <- R1 后 50ms 钩子注入伪 RESULT
CONFIRM: tid=1 status=1 (FAIL-识破)       <- 板端复算 Speck(K,C2) 发现 R2 伪造
EVENT: confirm.rejected  own_verdict=0    <- 站端自己的 HD 判 PASS,但终端拒绝
EVENT: base.spoof.suspected               <- 矛盾关联:信道上有第二个发言者
VERDICT: ATTACK_DETECTED | hook_fired: True
```

## 排障记录（两次 BOARD_PASSED 的根因）
1. 第一次：竞速钩子补丁锚点未命中被静默吞掉——**钩子从未注入**，板子听到的是真 RESULT。
   教训：String.replace 未命中不报错，补丁必须带 `includes()` 硬验证（本次已加）。
2. 防御性修复（保留）：注入延迟 50ms——零间隙紧跟 R1 发射时 HC-12 尚在 RX→TX 转换，
   帧头会被吞掉；50ms 仍远快于真 RESULT（~400ms），竞速必赢（板侧等待窗 2s）。
   （此条在钩子未触发的两轮中未经空口实证，为防御性设计。）

## 演示操作（决赛口径）
1. 起桥后打开 `http://127.0.0.1:8643/`（伪基站控制台）
2. 目标板 tid 填 1 → 点【⚔ 武装竞速注入】
3. 板A 按 SW8 → 前端点【开始验证】→ 大红警报 + 板端 BLOCKED + 关联告警
4. 【伪基站接入】按钮 = tid77 未注册接入 → access 警报（实测见 single_hc12_dual_auth_PASS）

