# SD 卡自举定案：官方 FSBL 链路全通（2026-11-19 21:30）

## 结论
板A 已实现免 JTAG 的 SD 卡开机自举（SW11=00110 上电即跑），认证链路完整可用。
上电现象：INIT(DS35) 黄 + ~0.75s 心跳；按 SW8 立即发出 ACCESS_REQUEST(tid=1)。
PC 侧 LinkE(COM6) 原始监听实收两帧：
```
fd10000000010290000001000000deadbeef93e7adaf972cf2139b48
fd10000001010290000001000000deadbeef94e8aeb0982df314c62f
```

## 三轮排除定位记录（FSBL 是唯一变量）
1. 旧打包链路 fsbl_zc706.elf(279,344B, B893A313)：INIT 红——BootROM/FSBL 阶段死
2. 老师 FSBL + v4c（老师卡提取的 FSBL bin）：INIT 黄但无心跳——FSBL 起来、载不动 2026.1 新 bit
3. 官方 FSBL + v4c + 飞控（AMD 官方 2026.2 zc706 fsbl.elf, 497,524B, DD54BD28）：黄+心跳+SW8 发帧——全通

## 最终镜像（build/sd_boot/）
- BOOT_SD_V4C_OFFFSBL.bin（板A，已在卡上）: 官方FSBL+v4c(三键/点名)+flight_ctrl_ddr.elf, SHA256=8AC7B0E4E2E6E14A2D0E5C03BD44D3D1004FF15E8AFF059276FF49E48A8B3A00
- BOOT_SD_SEED2C_OFFFSBL.bin（板B 备用）: 官方FSBL+seed2c(X1Y0 差异化布局), SHA256=FF0C41611AADC7EDA5A66061FC587777ACFB0F7650AAF1D3F571E257018ABBFB
- BOOT_DEMO_OFFICIAL.bin: 官方FSBL+u-boot 纯 demo（未用上，保留）

官方 FSBL 来源：github.com/Xilinx/soc-prebuilt-firmware（分支 xlnx_rel_v2026.2，zc706-zynq/fsbl.elf）。
教训：16:35 清单把 REF_BOOT_verified.bin 误当老师实测镜像做了打包等价验收——实际老师卡(AC067942, 13,425,664B)才是真基准；
fsbl_zc706.elf 在本板 SD 路径不可用（JTAG 正常故此前未暴露）。

## 演示口径（SD 模式）
- 板A：SW11=00110 + SD 卡，上电即跑；按 SW8 发起认证（前端弹窗/动画与 JTAG 模式完全一致）
- 回退：SW11=00000 + JTAG 重烧，零损失
- 板B 若需 SD 化：烧 BOOT_SD_SEED2C_OFFFSBL.bin（注意换 bit 后模板需重录）