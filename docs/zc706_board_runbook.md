# ZC706 Board Operation Runbook (finals-demo v2)

## Overview
- Target: 2x AMD Xilinx ZC706 (xc7z045ffg900-2), each with USB JTAG + USB-TTL serial
- Terminal 1 (production layout): JTAG SN 210251A0195C
- Terminal 2 (seed2 variant layout): JTAG SN 210251A04F2C
- Wireless: 433 MHz HC-12 modules (115200 baud)
- Base station: PC (Python) via web bridge

## 1. Power-on Check
1. SW4 = 01 (on-board USB JTAG)
2. SW11 = 00000 (JTAG boot mode) **[JTAG 阶段]** / 00110 **[QSPI 固化后]**
3. Power on. Check DS35 (heartbeat LED, ~0.75 Hz slow blink). Fast blink (~3 Hz) = entropy fault: do NOT proceed.
4. Verify SW12: Terminal 1 = 0001, Terminal 2 = 0010

## 2. Program Bitstream (JTAG mode)
```bash
vivado -mode batch -source build/tcl/program_zc706.tcl -tclargs <bit> [jtag_serial]
```
- Terminal 1: `build/board_zc706/w3_top_zc706.bit`
- Terminal 2: `build/board_zc706_seed2/w3_top_zc706_seed2.bit`
- **Bitstream is volatile in JTAG mode (SW11=00000)**: reprogram after each power cycle.
- **After QSPI flash (§6)**: bitstream persists — no reprogram needed.

## 3. Start Base Station (决赛日：用 demo_start.ps1)
```powershell
# 推荐：一键启动（自动探测串口、建沙箱、自检）
.\scripts\demo_start.ps1 -SerialPort COM6    # 显式指定（决赛日必须，多串口时自动中止要求指定）
# 或手动（不要加 --loopback，否则仿真终端会混入屏幕）:
python web/bridge/web_bridge.py --repo-root . --data-dir <fresh_empty_dir> --serial-port COM6 --serial-baud 115200 --port 8642
```
Open http://127.0.0.1:8642/console.html

## 4. Authentication (per round)
1. Press SW13 (reset) — clears any BLOCKED state **[旧习惯，决赛日可选]**
   ⚠️ 决赛演示"REJECT 后直接巡检"环节**不要按 SW13**——S_BLOCKED 一拍自清回 S_IDLE。
2. Press SW7 (auth trigger) or click web console "巡检" button
3. Observe (finals-demo N1 灯语增强版):
   - **PASS**: DS8 绿灯**快闪 3 次后常亮** + 蜂鸣两短哔 + J58 外接绿灯同步
   - **REJECT**: DS10 红灯 **2Hz 亮灭闪**（持续到下一轮）+ 蜂鸣 600ms 长鸣 + J58 外接红/琥珀交替
   - **BLOCKED**: DS8+DS10 **双亮保持** + 蜂鸣双长哔 + J58 红+琥珀常亮
   - busy: DS9 亮 1-2 秒 = PUF 测量中

## 5. Test Scenarios
| Scenario | Board | SW12 | Expected |
|---|---|---|---|
| Normal auth (T1) | Terminal 1 | 0001 | PASS, HD=0, 绿闪3+常亮 |
| Spoof attack | Terminal 2 | 0001 (impersonate T1) | REJECT, HD~140, 红闪+长鸣 |
| Normal auth (T2) | Terminal 2 | 0010 | PASS, HD=0 |
| Replay | (web console, S3 button) | - | REPLAY rejected |
| **巡检** (finals-demo) | any | any | web 巡检按钮 → 完整五帧 → PASS |
| **伪基站攻击** (finals-demo) | any | any | fake_result_attack → 三重证据同屏 |

## 6. QSPI Flash Solidification (决赛日关键步骤)

### 前置
- SW11 = 00000（JTAG 模式），板已上电，Micro-B 线插「JTAG」口
- 新 bit 已通过 JTAG 烧写并验证灯语正常（步骤 2+4）

### 操作（Vivado Hardware Manager GUI）
1. Vivado → Flow Navigator → **Open Hardware Manager** → **Open Target** → Auto Connect
2. 右键 xc7z045 → **Add Configuration Memory Device**
3. 搜索 `xc7z045` → 选择 **qspi_x4_dual_stacked**（128MB ×2）
4. Configuration file: 浏览到 `build/board_zc706/w3_top_zc706.bit`（板A）或 `build/board_zc706_seed2/w3_top_zc706_seed2.bit`（板B）
5. 点击 **OK** → 等待烧写完成（约 1-3 分钟）
6. **验证**：SW11 拨到 **00110**（QSPI 启动）→ 断电 → 重新上电
7. 检查：DS35 心跳灯亮 → SW7 认证 → 灯语正常 → **QSPI 固化成功**

### 失败回退
- QSPI 烧写失败 → SW11 拨回 **00000**（JTAG 启动）→ 每轮演示前需重新 JTAG 烧写
- QSPI 启动后板不工作 → SW11 拨回 00000 + JTAG 重烧 → 排查后重试

### ⚠️ 注意
- `.bit` 文件直接烧 QSPI（Vivado 2026.1 的 Hardware Manager 自动处理 SPI 格式转换）
- 不需要 MCS 中间文件（旧方案 write_cfgmem 因 SPI_BUSWIDTH 属性不可用已废弃）
- 烧写过程**勿断电**

## 7. External LED/Buzzer (PMOD J58)

### 接线表（⚠️ 断电操作——R4 红线）
| J58 引脚 | 信号 | 颜色/器件 | FPGA Pin | 限流电阻 |
|---|---|---|---|---|
| J58.3 | PMOD1_1 | 绿1 (10mm LED) | AK21 | 330Ω |
| J58.7 | PMOD1_3 | 绿2 (10mm LED) | AB16 | 330Ω |
| J58.2 | PMOD1_4 | 红 (10mm LED) | Y20 | 330Ω |
| J58.4 | PMOD1_5 | 琥珀 (10mm LED) | AA20 | 330Ω |
| J58.6 | PMOD1_6 | 蜂鸣器 (有源 3.3V) | AC18 | — |
| J58.1 | PMOD1_0 | UART txd（已占用） | AJ21 | — |
| J58.5 | PMOD1_2 | UART rxd（已占用） | AB21 | — |

LED 另一端接 J58 的 GND 脚。**⚠️ 勿插 J57（I2C 扩展器口）。**

## 8. Finals-Day Operation Sequence (决赛日操作序列)

1. 上电 → SW4=01, SW11=00110(QSPI 已固化)或 00000(需 JTAG 重烧)
2. 启动基站：`.\scripts\demo_start.ps1 -SerialPort COM6`
3. 浏览器打开 http://127.0.0.1:8642/console.html
4. 演示认证：SW13 复位 → SW7 → 看灯语 → 看屏幕判定
5. 演示巡检：网页点"巡检"按钮 → 完整五帧 → PASS
6. 演示攻击：板B SW12=0001 冒充 → SW7 → 红灯 → BLOCKED
7. 演示伪基站：攻击 PC 跑 fake_result_attack.py → 三重证据
8. 演示无人机：认证 PASS → S8 场景（Shift+8 或全场景连播）
