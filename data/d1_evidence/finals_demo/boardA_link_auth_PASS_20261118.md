# 板A 无线链路调通 + 五帧认证 PASS（2026-11-18 23:05）

## 故障链（当晚全部解决）
1. 桥初起为 loopback（demo_start -SerialPort none）→ 未开串口,SW7 无反应
2. LinkE(VID_1A86&PID_8012) 插入后:CMSIS-DAP 接口代码28(未装驱动,无影响),CDC 串口恢复
3. CDC 被分配 COM6 与蓝牙虚拟口撞名 → PermissionError 打不开 → 重插后可开(仍建议改号 COM10 防复发)
4. web_bridge /api/status 的 link.mode="loopback" 是写死的标签(1223行),不反映真串口状态——
   以 SSE frame.tx/rx 事件为准

## 链路验证（pyserial 直测）
TX AUTH_POLL(fd08..97) → RX 28B ACCESS_REQUEST(tid=1) 解析成功

## 关键操作序列（今晚,可复演）
1. 板A 烧 v4 bit PROGRAM_OK + ARM_FAN_OK(22:41)
2. 桥起 COM6 真串口(python -u web/bridge/web_bridge.py --serial-port COM6 --port 8642 --data-dir 沙箱)
3. setkey tid=1 0001020308090a0b10111213 → {"ok":true}(烧bit清了易失密钥,必须补)
4. enroll_real tid=1 n=100 measurements=3 → 25批×3轮完成,模板 100 pairs / 64 stable_bits
5. poll 认证 → 见下

## 五帧认证 PASS 证据（SSE 实录, run=real-1795014229722）
- frame.rx ACCESS_REQUEST 28B tid=1 (dir term->server)
- frame.rx RESPONSE_R1 44B(4×R1)
- verdict: result=0 PASS, hd=1, hd_per_response=[0,0,0,1], pool 68/500(14%)
- frame.rx CONFIRM 17B status=0
- confirm.done verified_r2=true ← 板端 R2 校验通过(双向认证成立)
- session.update: tid=1 → SESSION

## 待办
- COM6 撞名隐患:建议设备管理器把 USB 串行设备改到 COM10(需管理员/手动)
- 伪基站场景B实拍待第二个 HC-12(攻击PC/或本机第二串口)
