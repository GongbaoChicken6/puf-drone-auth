# Runbook：板子恢复后QSPI收尾（按序执行，每步证据已落盘）

> 前提：JTAG USB已插回（建议板子断电状态下插线再上电，避开TXS0108E闩锁问题）
> 完整根因分析见同目录 qspi_session_20261115_lead.md

## 第0步 环境自检（30秒）

    # 确认只有一个hw_server；有多个先 Stop-Process -Name hw_server,cs_server -Force
    & 'D:\vivado\2026.1\Vivado\bin\vivado.bat' -mode batch -source D:\puf-drone-auth\build\tcl\list_jtag_targets.tcl -log D:\puf-drone-auth\build\logs\lt.log -journal D:\puf-drone-auth\build\logs\lt.jou -notrace
    # 期待 TARGET: localhost:3121/xilinx_tcf/Digilent/210251A04F2C (板B) / 210251A0195C (板A)

注意：hw_server没起时先起（Vitis\bin\hw_server.bat 后台）。多个hw_server/cs_server会锁JTAG（老坑）。

## 第1步 活体探针：flash到底回不回话（1分钟）

    & 'D:\vivado\2026.1\Vitis\bin\xsdb.bat' D:\puf-drone-auth\build\tcl\qspi_probe3.tcl
    # 看输出：RXD_00_03 与 LIN_0xFC000000
    #   - LIN读出非全FF/非全00（如 AA995566 等）→ flash活着，u-boot环节问题 → 第2步
    #   - 全FF/全00/读取错误 → 需先跑一次 program_flash 让FSBL重新初始化再测（probe3测的是上次残留状态）

## 第2步 program_flash 重试矩阵（每轮约2-5分钟，自动落盘build/logs/pf_retry_*.log）

    powershell -File D:\puf-drone-auth\build\tcl\qspi_retry_matrix.ps1 -BoardSN 210251A04F2C -BootBin D:/puf-drone-auth/build/BOOT_B_v3.bin

- 4轮顺序：x4-dual_stacked/128 → x4-single/128 → x8-dual_parallel/128 → x4-dual_stacked/256
- 任何一轮出现 "Flash Operation Successful" 即停（哨兵 PF_SUCCESS_ATTEMPT=n）
- 板A恢复后同法烧 BOOT_v3.bin（bit=w3_top_zc706）

## 第3步 QSPI启动验证（烧写成功后）

1. SW11 从 JTAG(00000) 拨到 QSPI 启动位（UG954 Table 1-2；QSPI=00001，注意是SW11不是SW4）
2. SW1 OFF → 等5秒 → ON（JTAG USB保持插着！）
3. 通过标准（三选一即算PASS，建议全做）：
   - DS35 心跳灯恢复闪烁（PL从flash自举成功）
   - COM6/COM11 收到 AUTH_POLL 后正常回帧（五帧链路）
   - JTAG连上后 get_hw_devices 显示 xc7z045 已配置（非空白）
4. 全程录屏/拍照落盘

## 第4步 若第2步全失败（备选：自建烧写通道）

- Vitis 新时间戳workspace建baremetal app（模板hello_world），改main为XQspiPs流程：
  XQspiPs初始化(基址0xE000D000) → 读JEDEC(0x9F)确认0x20BA18 → 擦扇区 → 从DDR搬运BOOT.bin写flash
- BOOT.bin 13.4MB 先经JTAG的dow命令下到DDR(0x100000)再启动app写flash（用xsdb.bat）
- BSP已有驱动基础设施，工作量约1-2小时

## P2 万用表测试卡（顺手做，2分钟）

芯片：U40 = TXS0108E，TSSOP-20（PW封装）。
关键引脚：pin1=OE, pin2=VCCA(=VADJ 2.5V), pin11=GND, pin19=VCCB(=VCC3V3 3.3V)。

| 测点 | 拔USB前 | 拔USB后(J58断时) | 结论指向 |
|---|---|---|---|
| U40 pin2 (VCCA) | ~2.5V | 若=0V | VADJ轨被杀（查U48 UCD90120A/J18）|
| U40 pin19 (VCCB) | ~3.3V | 若=0V | 3.3V主轨问题（不太可能，其他外设会全死）|
| U40 pin1 (OE) | 高(约VCCB) | 若=低 | OE被USB侧信号拉死 |
| J58 pin1/pin5 | 有摆动或~2.5/3.3V | 0V且前3项正常 | 芯片闩锁本体问题 |

补充：UG954记载J18跳线在位（默认）时，VADJ的开启时机/电压由系统控制器控制（经JTAG USB链路访问）——机制上与USB有耦合嫌疑的就是这一环。
