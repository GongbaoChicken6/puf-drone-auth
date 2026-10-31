# 致板B队友：D1 夜间进度同步 + 你的并行任务（2026-10-31 23:40）

> 先 `git pull` 到最新（HEAD 含 program_zc706.tcl 修复 + 今晚全部证据）。有问题拍照/截图发群里。

## 一、全局战况

| 项 | 状态 |
|---|---|
| 四块 HC-12 | ✅ 全部毕业：A对 C001、B对 C006，均 FU3/115200/+20dBm，严格判据双向零误码 |
| 板 A（tid=1） | ✅ 烧bit → re-enroll（100 CRP，64/64 位 100% 稳定）→ serve 对照 CONFIRM（五帧完整，首轮过）|
| 板 A 剩余 | Step5 无线 CONFIRM（明天收尾）|
| 板 B（tid=2） | **轮到你**：烧 bit → setkey 2 → enroll 2 → serve → 无线 |
| 烧写脚本 | program_zc706.tcl 已修复 JTAG 链 arm_dap 在前选错器件的 bug（勿用旧版）|

## 二、你的任务清单（按序）

### 1. 烧 bit —— 每次上电都要烧（断电即丢，8 秒的事）
```
vivado -mode batch -source build/tcl/program_zc706.tcl -tclargs build/board_zc706/w3_top_zc706.bit
```
验收：输出 `PROGRAM_OK: xc7z045 <- ...`。（交接包 prog_w3_b.tcl 也可）

### 2. 线缆 re-enroll tid=2（三根线直连 J58，USB-TTL 的 VCC 不接）
- J58 pin1(板TX)→适配器RX、pin5(板RX)→适配器TX（交叉）、pin9→GND
- REPL 依次输入（```python -m src.python.server.main --port 你的COM --baud 115200```）：
```
setkey 2 0001020308090a0b10111213
enroll 2 100
```
- ⚠⚠ **铁律：setkey 2 必须在 enroll 2 之前**。跳过 = 自动铸随机钥 = 恒 BLOCKED 且无任何报错
- **今晚新教训**：接线过程中若断过电，重上电后必须重烧 bit，否则 enroll 直接超时（0/44 字节）——板 A 踩过这个坑

### 3. serve 对照
REPL 输入 `serve` → 按板B SW7 → 验收：`CONFIRM tid=2 OK` + **DS8 单亮**（enroll 后首轮 DS8+DS10 双亮是已知现象，再按一次即过）

### 4. 无线（模块到手后）
- **B板模块（背面标 B，C006）已配置毕业，直接用，无需任何配置**
- 板B J58 三线：模块RXD←pin1、模块TXD→pin5、GND←pin9；**VCC 用独立 3.3-5V（≥200mA）**，SET 悬空，天线装上
- B-PC 模块接你的 USB-TTL，同上供电规则
- ⚠ **供电铁律（今晚实测三连坑）**：HC-12 的 VCC 一律接 **5V/VCC 脚或独立电源**，绝不接适配器 3V3 脚（小 LDO 扛不住 +20dBm 发射尖峰：轻则出杂散 0xFE 字节，重则整个适配器 USB 重启）；**绝不接 J58 pin11**

## 三、排障速查（今晚新增条目置顶）

| 症状 | 原因 | 解决 |
|---|---|---|
| enroll 超时 got 0/44 | bit 没了（断电/接线重启过）| 重烧 bit 再试 |
| 对发收到杂散 0xFE/0x00 | HC-12 停在 AT 模式或供电毛刺 | 查 SET 是否接地；VCC 换 5V |
| USB 适配器反复失联 | 适配器 5V 路径弱（个体差异）| 换适配器或独立供电 |
| serve 无输出 | RX/TX 接反 | 断电对调 pin1/pin5 |
| RESULT_REPLAY | 撞重放窗 | REPL: c2reset 2 |
| COM 号变了 | CH340 拔插漂移 | 每次重开前设备管理器确认 |

## 四、假冒实验协调（重要）

板B假冒实验（论文核心数据）在**主 PC** 上做：板B接主PC、SW12 拨 0001 冒充 tid=1、对主PC上板A的模板 → 预期 REJECT + hd≈32。与你的 enroll 2 **不冲突**（两台 PC 的模板库独立）。

**但板B只有一块**：建议你先完成上面 1-3（线缆毕业），然后把板B交给主PC做假冒实验，之后再拿回做无线步骤 4。互相在群里报进度即可。

## 五、板A今晚数据（对照组参考）

- re-enroll：100 CRP、stable bits 64/64（100.0%）、每挑战测 3 次
- serve：ACCESS_REQUEST→CHALLENGE→RESPONSE→RESULT→CONFIRM 五帧完整，首轮 CONFIRM
- 全部证据日志在 `data/d1_evidence/1031_板A_*.log`（已入库）

---
*生成：2026-10-31 23:40，主PC助手。问题随时发群。*
