# 队友上手指南：板 B 无线认证（2026-10-31 D1）

> 前提：仓库已 clone、Python 环境已配好。你的角色 = **板 B 的基站管理员**。

## 你需要领的硬件

| 物品 | 数量 | 用途 |
|------|------|------|
| ZC706 板 B（背面标 B） | 1 | 认证终端 |
| HC-12 模块 x2（背面标 **B** 和 **B-PC**，信道 C006） | 2 | 无线对 |
| USB-TTL 适配器（CH340 或 LinkE） | 1 | PC 侧串口 |
| 12V 电源适配器 | 1 | 板子供电 |
| JTAG 线 + Vivado 环境 | 1 | 烧 bit |
| 杜邦线（公对母）x4 | 4 | 板侧接线 |

## 第一步：烧 bit（板 B 上电 + JTAG）

在仓库根目录执行：

    vivado -mode batch -source scripts/prog_w3_b.tcl

- 预期：8 秒烧完，终端无 ERROR
- FPGA 是易失的：断电后每次都要重烧
- 如果报 no active target：确认板子已通电（DS22 亮）、JTAG 线插好

## 第二步：线缆 re-enroll 板 B（恢复模板）

关键背景：模板库被 web 桥覆盖，真板模板丢失。需用线缆重新录入板 B 指纹。
此步不用 HC-12，三根杜邦线直连。

接线（板 B 断电状态下）：

    J58 pin1（板TX）-> USB-TTL 的 RX
    J58 pin5（板RX）-> USB-TTL 的 TX
    J58 pin9（GND） -> USB-TTL 的 GND
    （USB-TTL 的 VCC 不接！）
    接好线后板 B 上电。

在仓库根目录（假设 USB-TTL 枚举为 COM5，用设备管理器确认你的实际口）：

    python -m src.python.server.main --port COM5 --baud 115200

REPL 中依次输入：

    setkey 2 0001020308090a0b10111213
    enroll 2 100

等约 1 分钟，采集 100 CRP，看到 enroll complete 即成功。
验证（可选）：输入 serve，按板 B 的 SW7，终端显示 CONFIRM + hd=0 即线缆认证通过。

## 第三步：切换到无线

1. 板 B 断电（SW1 OFF）
2. 拔掉三根杜邦线，换 HC-12 模块（背面标 B）：

    HC-12(B) RXD <- J58 pin1（板 TX）
    HC-12(B) TXD -> J58 pin5（板 RX）
    HC-12(B) GND <- J58 pin9（GND）
    HC-12(B) VCC -> 独立 3.3-5V 供电（勿接 J58 pin11！）
    HC-12(B) SET -> 悬空（不接）

3. PC 侧：USB-TTL 上接 HC-12（背面标 B-PC），VCC/GND/TX/RX 四线 + SET 悬空
4. 板 B 上电

## 第四步：无线认证

    python -m src.python.server.main --port <你的COM口> --baud 115200
    REPL: serve

按板 B 的 SW7：
- 终端显示 VERDICT: PASS, hd=0 + CONFIRM -> 无线认证成功
- 板上 DS8 单亮 -> 通过

## 常见问题

| 症状 | 原因 | 解决 |
|------|------|------|
| serve 无输出 | 串口线 RX/TX 接反 | 断电对调 pin1/pin5 的两根线 |
| AMBIGUOUS 错误 | 串口被其他程序占用 | 关掉串口助手/另一个 serve |
| RESULT_REJECT | C2 重放窗脏 | REPL 输入 c2reset 2 清窗重试 |
| DS10 单亮 | 认证被拒 | 检查模板是否用本板的（不是板 A 的） |
| 上一轮通过这轮不通过 | 挑战池种子轮换 | 正常，多按几轮 SW7 |

## 你的板 B 信息速查

| 项 | 值 |
|----|-----|
| 终端号 tid | 2 |
| SW12 默认拨码 | 0010 |
| 密钥 | 0001020308090a0b10111213 |
| 无线信道 | C006 |
| 波特率 | 115200 |

遇到任何问题直接拍照/截图发群里。