# QSPI攻关会话报告（2026-11-15 晚，lead对话）

> 状态：链条重建至program_flash一步；FSBL已在真板验证生效；剩u-boot探测+烧写+启动验证。
> 板子当前被用户暂时拔线，等恢复后按文末runbook继续。

## 一、根因链（9次失败的真实原因，层层递进）

### 根因1：XSA空壳（前次"正确路径"断裂点）
- v1脚本(_mk_xsa.tcl 17:31)的BD其实QSPI配置齐全（design_1.bd: QSPI_IO="MIO 1 .. 6"、FBCLK=MIO 8、IO1="MIO 0 9 .. 13"、200MHz）
- 但 write_hw_platform 导出的 zc706_qspi.xsa 只有1513B（仅xsa.json/xsa.xml，Files/为空）
- **真因：PS7的M_AXI_GP0_ACLK未接时钟 → generate_target报 BD 41-758/41-1031 HDL生成失败（当时被catch吞掉）→ 无hw_handoff/design_1.hwh → XSA空壳**
- 修复(v3)：connect_bd_net ps7/FCLK_CLK0 → ps7/M_AXI_GP0_ACLK，validate通过，XSA=319,278B含ps7_init.c(565KB)+hwh ✓

### 根因2：FSBL实际都来自无QSPI的工厂模板
- _vit_build4.py证实：hw_design用的是 D:/vivado/2026.1/data/embeddedsw/lib/spm_templates/SPM_ZC_706_HwPlatform/system.xsa
- 工厂模板ps7_init的MIO9-13 = 0x1200（L0=0，非QSPI1功能）、MIO0=0x1301 → qspi1组完全没mux → 双堆叠上片flash不可见
- build/vitis_fsbl_qspi.elf(17:58)实为vitis_103840工作区(无QSPI XSA)重建的产物
- 修复：新workspace build/vitis_qspi3_192337 + 新XSA → fsbl.elf 586,384B

### 根因3：17:58的MIO手工补丁值错误
- 补丁写0xB87（L0=3，非QSPI功能；QSPI应为L0=2），且漏了MIO 9（板文件IO1组是MIO 0,9..13）
- 另外补的是main.c运行时，不覆盖时钟初始化路径

### 根因4：诊断方法存在两套可疑来源（auto-review修正表述）
- _qspi_diag.tcl/_qspi_fix*.tcl用的STIG寄存器组(FLASH_CMD 0xE000D0A0等)是Zynq UltraScale+ GQSPI机制；Zynq-7000 QSPI无STIG，应用FIFO方式(TXD 0x28/RXD 0x30 + MAN_CS/MAN_STRT)——若"JEDEC=00,00,00"出自这些脚本，则测的是不存在的寄存器，读数无效
- 但失败表里的JEDEC数字更可能来自u-boot/program_flash输出（本次复现的日志里u-boot探测失败就是这种形态）——那属于真实测量：当时MIO9-13未mux（根因2），flash上片不可见、读到全0是预期结果，恰好佐证根因2，而非"flash物理损坏"
- 两种来源殊途同归：都指向配置问题而非硬件损坏；但"历史JEDEC读数全部无效"的说法过强，特此修正为上述区分
- 注：那些diag脚本的输出未落盘（全仓库grep 'JEDEC'零命中），无法逐条核对当时读数来源

## 二、本次已完成的虚拟验证（证据）

| 步骤 | 工件 | 哨兵 |
|---|---|---|
| Vivado BD+XSA v3 | build/qspi_xsa_v3/zc706_qspi_v3.xsa | XSA_SIZE=319278, XSA_SENTINEL=NONSEDEGENERATE, log: build/logs/qspi_xsa_v3.log |
| Vitis FSBL | build/vitis_qspi3_192337/zc706_qspi/zynq_fsbl/build/fsbl.elf | PLATFORM_BUILD_OK, 586,384B, log: build/logs/vitis_fsbl_v3.log |
| ps7_init内容 | MIO0-13=0x1202/0x0202(QSPI L0=2+上拉) | 见本报告附表 |
| bootgen A | build/BOOT_v3.bin | 13,456,128B(fsbl+w3_top_zc706.bit) |
| bootgen B | build/BOOT_B_v3.bin | 13,456,128B(fsbl+seed2.bit) |

## 三、真板（板B）实测证据（19:29-19:33，JTAG断线前）

program_flash运行到u-boot探测:
- FSBL下载并运行成功；回读ARM_CLK_CTRL=0x1F000200、APER等与v3 ps7_init写入值完全一致 → **新FSBL在真板生效**
- 之后program_flash自带的mini-u-boot(zynq_qspi_x4_dual_stacked_128.bin)执行 sf probe 0 0 0 → "Failed to initialize SPI flash at 0:0 (error 0)" → 中止

XSDB活体寄存器读取（关键）：
- MIO 0-13 活值 = v3 ps7_init目标值100%一致（MIO0/1/9-13=0x1202, MIO2-6/8=0x0202）→ **QSPI mux已在硬件上生效**
- APER_CLK(0xF800012C)=0x01EC044D = v3 ps7_init写入值 ✓（QSPI APER bit22=1）
- QSPI_REF_CTRL(0xF8000158)=0x00003F03（非复位值，疑u-boot所写）
- QSPI CONFIG(0xE000D000)=0x800A7CC9（u-boot配置后残留，MAN_CS位已置）
- IRQ_STATUS=0x00000004（RX FIFO非空？→flash可能其实有回话，u-boot没等到/没读走）

推论：MIO/时钟/控制器全部就绪，flash大概率活着（IRQ_STAT有数据位），失败点收窄到u-boot探测环节（速度/时序/堆叠片选/密度参数之一）。

## 四、遗留：u-boot sf probe失败的下一步（板子回来后）

1. 重跑 build/tcl/qspi_probe3.tcl（XSDB, safemrd版）: 读RX FIFO(0xE000D030)+线性窗口0xFC000000 → flash是否alive一目了然
2. program_flash换参数重试（每次约1分钟出结果）：
   - a. -flash_type qspi-x4-single -flash_density 128（下片16MB够装13.4MB镜像；启动只读下片）
   - b. 仍失败则 -flash_type qspi-x8-dual_parallel -flash_density 128（反证拓扑）
   - c. -flash_density 256 两档都试
3. 若u-boot仍探测失败 → 自建烧写通道：vitis建baremetal app(XQspiPs FIFO方式读ID/擦/写)，镜像经JTAG灌DDR → app写flash（有BSP现成驱动，工作量可控）
4. 烧写成功后启动验证：SW11由JTAG(00000)→QSPI位（见UG954 Table 1-2，注意是SW11不是SW4），SW1断电5秒→上电→看DS35心跳+COM串口AUTH_POLL

## 五、P2结论（J58/TXS0108E）

- J58=ZC706 PMOD Port1（bank 9/10/11, VCCO=VADJ 2.5V），经U40(TXS0108E)电平转换到3.3V
  （证据：github VLSI-EDA/PoC ucf/ZC706/PMOD.Port1.ucf 明文"LevelShifted: by U40 (TXS0108E) to 3.3V VCC3V3"+UG954 bank电压表）
- **VCCB=VCC3V3主轨（12V输入派生），不是USB 5V → 交接文档第五节"飞线到12V轨"方案否决**（12V远超TXS0108E绝对最大5.5V，会烧毁；且VCCB本来就不缺电）
- UG954: "All PL and PS power rails are enabled by default... FMC VADJ enabled (U48 UCD90120A pin 37 = logic 0)" → VADJ由U48(UCD90120A电源监控/时序芯片)管理
- 剩余机制假设（待万用表/原理图页37/39定案）：拔JTAG USB瞬态→U48误触发fault→VADJ掉/关→U40 VCCA失电→TXS0108E双侧失电闩锁高阻（该芯片已知行为：单侧掉电需全断电恢复，与"必须断电5秒"症状吻合）
- 决赛对策不变：JTAG USB全程插着；QSPI固化成功后"断电重烧"恢复成本也大幅降低

## 六、本次产出文件清单

- build/tcl/qspi_mk_xsa_v3.tcl（XSA构建，含时钟修复）
- build/tcl/vitis_fsbl_v3.py（FSBL构建）
- build/tcl/check_fsbl_v3.ps1（ps7_init验证）
- build/tcl/qspi_regs_live2.tcl / qspi_probe2.tcl / qspi_probe3.tcl（XSDB活体探针）
- build/tcl/list_jtag_targets.tcl
- build/qspi_xsa_v3/zc706_qspi_v3.xsa（QSPI XSA）
- build/vitis_qspi3_192337/（FSBL工作区）
- build/boot_v3.bif / boot_B_v3.bif / BOOT_v3.bin / BOOT_B_v3.bin
- build/logs/*.log（全部证据日志）
