# 决赛装箱清单（11-19 出发前核对）

## 板卡
- [ ] 板A ZC706（JTAG SN: 210251A0195C）+ 12V 电源适配器
- [ ] 板B ZC706（JTAG SN: 210251A04F2C）+ 12V 电源适配器
- [ ] 双板 bit 备份 U 盘（build/board_zc706*/w3_top_zc706*.bit + scripts/demo_start.ps1 + tools/attack/）

## 通信
- [ ] HC-12 无线模块 ×4（C001 对×2 + C006 对×2）
- [ ] USB-TTL 转接板 ×2（CH340/CP210，装好排针）
- [ ] USB Micro-B 线 ×2（JTAG 口，烧 bit/QSPI 用）

## 外接显示（N7）
- [ ] 10mm LED 绿 ×2 + 红 ×1 + 琥珀 ×1（330Ω 限流电阻已焊）
- [ ] 有源蜂鸣器 ×1（3.3V）
- [ ] 杜邦线母对母 ×8（J58 排针连接）

## 笔记本电脑
- [ ] 主笔记本（Vivado 2026.1 + Python 3.13 + 仓库 D:\puf-drone-auth）
- [ ] 攻击笔记本（Python 3.13 + tools/attack/fake_result_attack.py + HC-12 配 C001）
- [ ] Chrome/Edge 浏览器收藏 http://127.0.0.1:8642/console.html

## 文档
- [ ] 设计报告 PDF（32 页）
- [ ] 答辩 Q&A 手卡（docs/qa_card_finals.md 打印版）
- [ ] 演示解说词（docs/demo_script_v2.md 打印版）
- [ ] 板级操作手册（docs/zc706_board_runbook.md）
- [ ] 集成指南（docs/integration_guide.md，评委翻阅用）

## 海报/视频
- [ ] 英文海报打印版（Poster_PUF_EN_print.pptx → PDF）
- [ ] 演示视频备份 U 盘（H264 版）

## 现场配置备忘
- SW4 = 01（板载 USB JTAG）
- SW11 = 00110（QSPI 启动，上电自启动）
- SW12 = 板A 0001 / 板B 0010
- 每次按 SW7 前先按 SW13
