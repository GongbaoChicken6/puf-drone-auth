# SD 卡自举 · 板A 烧录执行清单（2026-11-19 交接版）

> 一句话结论：把 `BOOT_SD_FINAL_V4_FC.bin` 拷进 FAT32 U 卡根目录、改名 `BOOT.BIN`，断电插 J30、SW11 拨 `00110`、上电，**DS35 慢闪 = 成功**。
> 本文自包含：产物 sha256、判据、失败分支、回退、重建命令全在里面，照着执行即可，不需要再看别的文档。

---

## 0. 开工前先读这三条（能省 30 分钟白折腾）

1. **串口判据的线不一样，别在 COM6 等 FSBL banner。**
   - 演示用的 **COM6 / COM11 是两块板 J58 PMOD 上的 CH340 USB-TTL**（PL 的 uart_tx 驱动，跑认证协议/按键请求）。
   - FSBL banner 和 ARM 飞控日志走的是**板载 CP2103（U52，mini-B 口 J21）**，设备管理器里名称为 “Silicon Labs CP210x”。
   - 当前 PC 上只枚举到两个 CH340（COM6=板A、COM11=板B），**没有任何 CP210x** → 说明 J21 现在没插线。这种情况下判据只剩 **DS35 心跳** + **JTAG 可连**，不要在 COM6 上等 banner（等不到不等于失败）。
2. **SW11 只在上电瞬间被采样锁存**：拨完必须断电-上电，带电拨动无效。
3. **失败随时可退**：SW11 拨回 `00000`，JTAG 8 秒重烧，演示链路零损失。

---

## 1. 交付物（已落盘，sha256 已冻结）

目录：`D:\puf-drone-auth\build\sd_boot\`

| 文件 | 大小(B) | sha256 | 用途 |
|---|---|---|---|
| **BOOT_SD_FINAL_V4_FC.bin** | 13,410,976 | `A9441C80E43D6E11206F480755E81480D16F022DFC765A72F0D560CB835DDB0C` | **最终版（板A）**：FSBL + v4 ARM bit + ARM 飞控 ELF（DDR@0x10000000） |
| BOOT_SD_STAGE1_V4.bin | 13,409,280 | `3053A6EE752666D28CACAB2BB9C3B2D50C37DF43EF8A896985FD822DC47C39DC` | 阶段一（排障用）：FSBL + v4 bit，**无** ARM 应用 |
| BOOT_SD_BOARDB_SEED2.bin | 13,409,280 | `F5A1473A36BB7716AF09C8AFD425071CD2DD3052E331E3893DE0C86429026991` | 可选（板B）：FSBL + seed2 bit，无应用 |
| verify_sd_boot.ps1 | — | — | 离线验收脚本，跑一遍出 16 条 `=PASS` |
| verify_report_20261119.txt | — | — | 上面脚本最近一次的落盘报告 |

打包用的原料（同目录，供核对/重建）：

| 文件 | 大小(B) | sha256 |
|---|---|---|
| fsbl_zc706.elf（复用老师那份 FSBL） | 279,344 | `B893A313997A92E97BD8BB108332A3F068D0442B0EA967093E40D940C57B478E` |
| w3_top_zc706_v4.bit（demo 现行 v4 bit） | 13,321,607 | `504B042D85E028E6F7101A98A00CA5EF8C0DA9C857277DFE1B1F0C1ECE421958` |
| flight_ctrl_ddr.elf（ARM 飞控，DDR 版） | 11,084 | `36810A5A4A0D3A1C1FA65E566F46FA9413E56AEB2DF1337DAD23E7FD95497D36` |
| REF_BOOT_verified.bin（老师实测成功的原版） | 13,409,280 | `3B3D7CD684FA62AE68DAD358F211660EFE417D855D9B5AEC6242D66A0630CA34` |

### 1.1 先跑一遍离线验收（5 秒，不碰硬件、不碰卡）

```powershell
powershell -ExecutionPolicy Bypass -File D:\puf-drone-auth\build\sd_boot\verify_sd_boot.ps1
```

期望最后一行：`ALL_CHECKS_PASS`（16 条逐项 PASS：三份输入 sha256、镜像 sha256/大小、3 分区结构、ELF 装载地址 0x10000000、ELF 内 sp 字面量 0x1000FF80、飞控 banner 只在最终版里、stage1 里没有 banner、板B 镜像 2 分区，以及**与老师实测成功镜像只差 4 字节**的复现性证明）。
任一条 FAIL → 不要上板，先把报告发回来。

---

## 2. 为什么长这样（三个决策，执行时不用重想）

1. **ARM 应用必须放 DDR（0x10000000），不能放 OCM(0x0)。**
   `readelf -l fsbl_zc706.elf` 实测：FSBL 自己 `LOAD 0x00000000, FileSiz 0x14008, MemSiz 0x18490` —— 它就住在 OCM 低区。若把应用装到 0x0，FSBL 在搬运自己的过程中会把自己盖掉。所以打 BOOT.bin 用的是 `flight_ctrl_ddr.elf`（DDR 版），不是 JTAG 调试用的 `flight_ctrl.elf`（OCM 版）。
2. **FSBL 直接复用老师那份，不重编。**
   用本机 bootgen 2026.1 + 老师的 FSBL + 老师原 bit、同样的分区文件名重打一份对照镜像（`REPRO2_BOOT.bin`），与老师实测成功那份 SD 镜像**逐字节只差 4 字节**——差的只是 FSBL 里内嵌的编译时间字符串（`10:34:01` → `15:02:03`）。这条证明打包链路与成功样本等价（见 `verify_report_20261119.txt` 的 `C8_REPRO_VERIFIED`）。
3. **bit 用 `board_zc706_arm_v4`**（demo 现行版，WNS=0.986），不是 v5/seed2。

---

## 3. 执行 A：写卡（PC 侧，约 5 分钟）

> 板上 J30 卡槽**电脑看不见**，必须用读卡器写。

1. 读卡器插卡。卡要求：**≤32GB SDHC、FAT32、MBR 分区表、单分区**（exFAT/SDXC 的卡 BootROM 不认）。
2. **只读确认**（不改任何东西）：

```powershell
Get-Disk | Where-Object BusType -eq 'SD' | Select-Object Number,FriendlyName,PartitionStyle,Size
Get-Volume | Where-Object DriveType -eq 'Removable' | Select-Object DriveLetter,FileSystem,Size,SizeRemaining
```

   判读：`PartitionStyle=MBR`、`FileSystem=FAT32`、容量 ≤32GB。
   若为 exFAT/NTFS 或 GPT → 需要格式化。**格式化会清空整张卡**，必须先问用户确认，命令（把 `N` 换成 Get-Disk 里的 Number）：

```powershell
Clear-Disk -Number N -RemoveData -Confirm:$false
New-Partition -DiskNumber N -UseMaximumSize -AssignDriveLetter | Format-Volume -FileSystem FAT32 -NewFileSystemLabel PUF
```

3. 复制 + 改名（把 `X:` 换成卡的实际盘符）：

```powershell
Copy-Item 'D:\puf-drone-auth\build\sd_boot\BOOT_SD_FINAL_V4_FC.bin' 'X:\BOOT.BIN' -Force
Get-FileHash 'X:\BOOT.BIN' -Algorithm SHA256
# 必须等于 A9441C80E43D6E11206F480755E81480D16F022DFC765A72F0D560CB835DDB0C
```

   文件名**必须**是 `BOOT.BIN`（BootROM 按 8.3 短名找）。
4. 安全弹出（别拔了就走）：

```powershell
(New-Object -ComObject Shell.Application).Namespace(17).ParseName('X:').InvokeVerb('Eject')
```

---

## 4. 执行 B：上板（2 分钟，顺序不能乱）

1. **SW1 断电**（铁律：严禁带电插拔/带电拨码）
2. SD 卡插板上 **J30**（弹簧卡入，注意方向）
3. **SW11 拨 `00110`**：pole3 UP + pole4 UP，其余 DOWN
   - 真 SW11 在板中部偏右（UG954 Figure 1-3 callout 29）；**MGT J35 旁边那组 5 位 DIP 不是 SW11**。
4. **SW1 上电**

---

## 5. 执行 C：判据（三层，从快到慢）

| 层 | 判据 | 通过含义 |
|---|---|---|
| 1（上电 15s 内） | **DS35 约 0.75 秒慢闪** | PL 已配置 + 设计在跑 = 自举成功，直接进决赛可用状态 |
| 2（可选，需 J21 插线） | CP210x 串口 115200 出现 `Xilinx First Stage Boot Loader` banner；随后出现 `[FC] init:` / `[FC] state: LOCKED` | banner = BootROM 已从卡读到镜像；`[FC]` = ARM 飞控也被 FSBL 装载并跳转成功 |
| 3（旁证） | Vivado Hardware Manager 能连上 JTAG | SW11 不影响调试链 |

- **快闪（≈3 次/秒）= 设计判定的故障态**（见 demo_led 灯语）；**不闪 = 完全没跑起来**。
- DS35 接在 1.5V bank（XDC：\`PACKAGE_PIN A17 … LVCMOS15\`），**亮度本来就偏暗**，手机录像看着更弱是正常的——以"规律慢闪"为准，不要拿亮度判失败。
- **必须复验一次**：断电 **30 秒** → 再上电 → 仍慢闪。铁律：断电重放才算数。

---

## 6. 失败分支（每层 10 分钟止损）

| 现象 | 解读 | 动作 |
|---|---|---|
| 不闪 + 无 banner | BootROM 没读到卡 | ① 确认 SW11 真的是 `00110`（位没错）② 换第二张卡重写 ③ 确认卡是 FAT32/MBR 且文件就是根目录 `BOOT.BIN` |
| 换卡后仍不闪 | 卡被 BootROM 挑剔 | 换**小容量 SDHC（4–8GB）**再试；仍不行 → 走"彻底不通"分支 |
| 有 banner，但 DS35 不闪 | FSBL 起来了，bit 装载失败 | 换 `BOOT_SD_STAGE1_V4.bin`（无应用）重写重试；若 stage1 也不闪 → 打包问题，重跑第 1.1 节验收脚本 |
| DS35 慢闪，但串口没有 `[FC]` | PL OK，ARM 应用没跑起来（本次唯一未上硅验证的环节） | **演示不受影响**：PL 侧认证+风扇全在，直接用；ARM 飞控问题另查（JTAG 连上后可读 PC/寄存器） |
| 彻底不通（两张卡都不行） | 本板 SD 通道异常 | **止损**：SW11 回 `00000`，走第 7 节回退 |

**总止损线：换两张卡共 20 分钟仍不闪 → 关闭实验，回 JTAG 方案，不要在装箱日继续耗。**

---

## 7. 回退（30 秒，随时可用）

1. SW1 断电 → SW11 拨 `00000` → 上电
2. 仓库根目录执行 `.\scripts\demo_start.ps1 -SerialPort COM6`（JTAG 烧 v4+seed2 bit，并给板A链式加载 arm_fan.elf）
3. ⚠ **SD 自举成功后就不要再跑 demo_start.ps1 的烧写段**：它会把板A拉回 JTAG 烧写状态（同 bit，但 ARM 侧换成 arm_fan.elf，且断电后需再烧）。SD 自举演示时 PC 侧只起 web 桥（见第 9 节）。

---

## 8. 成功后要做的事（证据必须落盘）

1. 拍/录 **DS35 慢闪** 10 秒（手机即可）。
2. 若 J21 有插线：串口 115200 抓 banner + `[FC]` 状态机日志。
3. **断电 30 秒复验的第二遍**同样录一份 → 存 `D:\puf-drone-auth\data\d1_evidence\finals_demo\sd_boot_20261119\`。
4. 把结果填进本文档第 13 节"实测记录"表，并把 `verify_report_20261119.txt` 一起留在同目录。

---

## 9. 与现在演示流程的差异（口径统一）

| 项 | JTAG 方案（现状） | SD 自举方案（成功后） |
|---|---|---|
| 上电后 | 需 PC 跑 demo_start.ps1 烧 bit+ELF | 自动跑，PC 不参与 |
| 断电重启 | 需重新烧（约 30s） | 直接可用 |
| PC 侧命令 | `.\scripts\demo_start.ps1 -SerialPort COM6` | **只起桥**（下面是双口版） |

SD 自举演示时 PC 侧只跑桥：

```powershell
python web\bridge\web_bridge.py --repo-root . --data-dir <新建的空目录> --serial-port COM6,COM11 --port 8642 --access-gate --access-label "1=板A,2=板B" --open
```

（`--data-dir` 必须指向**新建空目录**，铁律 5：绝不碰仓库 `data\`。）

---

## 10. 坑速查（前人实测，别再踩）

1. BIF／文件路径**禁空格**（引号也救不了），也**禁中文路径**（本机 `D:\文件\...` 会让 bootgen 解析崩，所以打包工作目录固定在 `D:\puf-drone-auth\build\sd_boot`）。
2. zynq 架构下 bit 分区**禁属性**：`[fpga]`、`[destination_device = pl]` 都会被 bootgen 拒绝，直接写文件名即可。
3. SD 卡必须 **FAT32 / MBR / ≤32GB**，文件名必须 `BOOT.BIN`。
4. 板上 J30 卡槽电脑不可见，必须读卡器写。
5. 插拔卡、拨 SW11 之前先 **SW1 断电**。
6. SW11 编码：`00000`=JTAG / `00010`=QSPI / **`00110`=SD**（UG954 Table 1-2）。原 runbook 里"QSPI 固化后 = 00110"是错的。
7. QSPI 固化已两轮实证死亡（BootROM 读 flash 硬件级问题），**别再试**。
8. FSBL banner 在 **J21 CP2103**，不在演示用 COM6（J58 CH340）。

---

## 11. 附录 A：本次改了什么代码（为什么这一版值得烧）

**修掉一个静默错配的坑**：`sw\arm_fan\start.S` 原来把栈顶地址写死在指令里——

- OCM 版（JTAG 调试用）：`ldr sp, =0x0000FF88`
- DDR 版（BOOT.bin 用）：`ldr sp, =0x1000FF88`

但两版 ELF 共用同一份 `start.S`：谁最后编谁就改掉栈顶，另一版会静默拿到错误栈——

- DDR 布局拿到 OCM 栈 → 压栈踩 FSBL 自己的 OCM 代码/数据；
- OCM 布局拿到 DDR 栈 → 经 FSBL 从 SD 启动时 DDR 尚未初始化就压栈，直接挂死。

**改法**：`start.S` 改 `ldr sp, =__stack_top`，由链接脚本各自定义：

- `ocm.ld`：`__stack_top = ORIGIN(ocm) + LENGTH(ocm) - 0x80` = `0x0000FF80`
- `ddr.ld`：`__stack_top = ORIGIN(ddr) + LENGTH(ddr) - 0x80` = `0x1000FF80`

**重建后的三条正向哨兵**（`sw\arm_fan\build_flight.log`，脚本 `build_flight.ps1`）：

```
flight_ctrl.elf      [S1] ENTRY=0x00000000 PASS   [S2] __stack_top=0x0000FF80 PASS   [S3] ldr sp literal=0x0000FF80 PASS
flight_ctrl_ddr.elf  [S1] ENTRY=0x10000000 PASS   [S2] __stack_top=0x1000FF80 PASS   [S3] ldr sp literal=0x1000FF80 PASS
ALL_CHECKS_PASS
```

并且这个 `0x1000FF80` 也验到了 BOOT.bin 里的应用载荷上（`C6_ELF_SP`）。

改动文件：
- `D:\puf-drone-auth\sw\arm_fan\start.S`（改符号引用）
- `D:\puf-drone-auth\sw\arm_fan\ocm.ld`、`ddr.ld`（新增 `__stack_top`）
- `D:\puf-drone-auth\sw\arm_fan\build_flight.ps1`（新增：一次编两版 + 三条哨兵 + 落盘日志）
- 重建产物：`flight_ctrl.elf`（OCM，`B505157F...`）、`flight_ctrl_ddr.elf`（DDR，`36810A5A...`）

---

## 12. 附录 B：怎么重建（需要改 bit / 改应用时才用）

```powershell
# 1) 重编两版 ELF（自动做三条哨兵，日志 build_flight.log）
powershell -ExecutionPolicy Bypass -File D:\puf-drone-auth\sw\arm_fan\build_flight.ps1

# 2) 把新 ELF 拷进打包目录（文件名必须叫 flight_ctrl_ddr.elf）
copy D:\puf-drone-auth\sw\arm_fan\flight_ctrl_ddr.elf D:\puf-drone-auth\build\sd_boot\ /Y

# 3) 重新打包（在 sd_boot 目录里跑）
cd /d D:\puf-drone-auth\build\sd_boot
D:\vivado\2026.1\Vitis\bin\bootgen.bat -image sd_final.bif -arch zynq -w -o BOOT_SD_FINAL_V4_FC.bin

# 4) 验收（sha256 变了会报 FAIL，是设计如此——把期望值改成新的再跑）
powershell -ExecutionPolicy Bypass -File .\verify_sd_boot.ps1
```

BIF 内容（`sd_final.bif`，注意路径禁空格/中文、bit 分区不带属性）：

```
the_ROM_image:
{
[bootloader]fsbl_zc706.elf
w3_top_zc706_v4.bit
flight_ctrl_ddr.elf
}
```

---

## 13. 实测记录（执行时填，证据路径写上）

| 时间 | 镜像/卡 | 现象 | 结论 | 证据路径 |
|---|---|---|---|---|
|  |  |  |  |  |
|  |  |  |  |  |
|  |  |  |  |  |

---

## 14. 交接口令（原样发给另一个对话即可）

```
接手 ZC706 板A 的 SD 卡自举烧录。所有产物和文档都已落盘，你只需要按文档执行并回填证据，不要重新设计。

1) 先读并严格按 D:\文件\ssssssss\FPGA\SD_BOOT_烧录清单_20261119.md 执行（第 0 节的三条前置必读）。
2) 第一步先跑离线验收（不碰硬件、不碰卡）：
   powershell -ExecutionPolicy Bypass -File D:\puf-drone-auth\build\sd_boot\verify_sd_boot.ps1
   必须看到 ALL_CHECKS_PASS 才能继续；有任何 FAIL 立刻停下来汇报，不要上板。
3) 要烧的镜像是 D:\puf-drone-auth\build\sd_boot\BOOT_SD_FINAL_V4_FC.bin
   （sha256 A9441C80E43D6E11206F480755E81480D16F022DFC765A72F0D560CB835DDB0C，13,410,976 B）
   拷进 FAT32/MBR/≤32GB 的 SD 卡根目录，改名 BOOT.BIN，用电脑读卡器写（板上 J30 电脑不可见）。
4) 板侧顺序：SW1 断电 → 插 J30 → SW11 拨 00110（pole3+pole4 UP，其余 DOWN，真 SW11 在板中部偏右）→ 上电。
5) 判据优先级：DS35 约 0.75s 慢闪 = 成功（必须再断电 30 秒复验一次）。FSBL banner/飞控日志只在 J21 CP2103 那个串口上，不要在 COM6（J58 CH340）上等 banner。
6) 任何失败按第 6 节分支处理，止损线是换两张卡 20 分钟；不行就按第 7 节回退：SW1 断电 → SW11 拨 00000 → 跑 .\scripts\demo_start.ps1 -SerialPort COM6。
7) 每个结论都要有落盘证据（视频/串口 log 存 D:\puf-drone-auth\data\d1_evidence\finals_demo\sd_boot_20261119\），并把现象填回文档第 13 节的表。
8) 不要重新打包、不要改 bit、不要动仓库 data\ 目录；若确需重建，严格按文档第 12 节。
```

---
(完)
