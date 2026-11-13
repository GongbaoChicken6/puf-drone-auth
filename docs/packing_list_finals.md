# 决赛装箱清单（11-19 出发前核对 · R4 修订版）

## 板卡
- [ ] 板A ZC706（JTAG SN: 210251A0195C）+ 12V 电源适配器
- [ ] 板B ZC706（JTAG SN: 210251A04F2C）+ 12V 电源适配器
- [ ] 双板 bit 备份 U 盘（build/ 完整目录 + scripts/ + tools/attack/ + docs/）

## 通信
- [ ] HC-12 无线模块 ×4（C001 对×2 + C006 对×2）
- [ ] USB-TTL 转接板 ×2（CH340/CP210，装好排针）
- [ ] USB Micro-B 线 ×2（JTAG 口，烧 bit/QSPI 用）

## 现场串口分配（⚠️ 决赛日必读）
| 设备 | 串口 | HC-12 信道 | 用途 |
|---|---|---|---|
| 板A ↔ 主笔记本 | COM6 | C001 | 真基站 ↔ 终端一 |
| 攻击端 ↔ 主笔记本 | COM9 | C001 | 伪基站注入（同信道） |
| 板B ↔ 主笔记本 | (备选) | C006 | 终端二 |

## 主笔记本启动命令
```powershell
# 演示日标准启动（不要加 --loopback！）
.\scripts\demo_start.ps1 -SerialPort COM6
```

## 攻击端（同一笔记本第二串口 或 第二笔记本）
- [ ] Python 3.13 + pip install pyserial
- [ ] **完整仓库克隆**（fake_result_attack.py 需要 src/python/ 依赖树）
- [ ] 实跑验证：`python tools/attack/fake_result_attack.py --port COM9 --passive`（出发前一次）
- [ ] HC-12 模块配好 C001 信道（tools/hc12/hc12_config_c001.py）

## 外接显示（N7）—— 接线表
| J58 脚 | 器件 | 颜色 | 限流 |
|---|---|---|---|
| J58.3 | 10mm LED | 绿1 | 330Ω |
| J58.7 | 10mm LED | 绿2 | 330Ω |
| J58.2 | 10mm LED | 红 | 330Ω |
| J58.4 | 10mm LED | 琥珀 | 330Ω |
| J58.6 | 有源蜂鸣器 3.3V | — | — |
- [ ] 杜邦线母对母 ×8（J58 排针连接）
- [ ] ⚠️ **断电接线**（R4 红线：PMOD 严禁带电插拔）

## 笔记本电脑
- [ ] 主笔记本（Vivado 2026.1 + Python 3.13 + 仓库 D:\puf-drone-auth）
- [ ] Chrome/Edge 浏览器收藏 http://127.0.0.1:8642/console.html

## 文档
- [ ] 设计报告 PDF（32 页）
- [ ] 答辩 Q&A 手卡（docs/qa_card_finals.md 打印版）
- [ ] 演示解说词（docs/demo_script_v2.md 打印版）
- [ ] 板级操作手册 v2（docs/zc706_board_runbook.md 打印版）
- [ ] 集成指南（docs/integration_guide.md，评委翻阅用）

## 海报/视频
- [ ] 英文海报打印版（Poster_PUF_EN_print.pptx → PDF）
- [ ] 演示视频备份 U 盘（H264 版）

## 现场配置备忘
- SW4 = 01（板载 USB JTAG）
- SW11 = 00110（QSPI 启动——若已固化）或 00000（JTAG——每轮需重烧）
- SW12 = 板A 0001 / 板B 0010
- 每次按 SW7 前按 SW13（旧习惯，可选——"REJECT 后直接巡检"环节不按）
