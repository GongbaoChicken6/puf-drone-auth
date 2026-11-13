UG954 v1.8 Table 1-31 GPIO Header Connections (XC7Z045 at U1) -- finals-demo N7 定脚证据
来源: UG954 (v1.8) August 6, 2019, physical page 64 (file page 63)
高清截图: ug954_p64_T1-31_pinout.png / j58_symbol_hd.png (本目录)

Pin   Net Name    J58 Pin   finals-demo 用途
AJ21  PMOD1_0     J58.1     UART txd（既有）
AK21  PMOD1_1     J58.3     ext_led[0] 绿1（新增）
AB21  PMOD1_2     J58.5     UART rxd（既有）
AB16  PMOD1_3     J58.7     ext_led[1] 绿2（新增）
Y20   PMOD1_4     J58.2     ext_led[2] 红（新增）
AA20  PMOD1_5     J58.4     ext_led[3] 琥珀（新增）
AC18  PMOD1_6     J58.6     ext_buzzer（新增）
AC19  PMOD1_7     J58.8     （备用）
锚点自校验: PMOD1_0=AJ21 与 PMOD1_2=AB21 与 XDC 既有 UART 行一致。全 LVCMOS25。
注意: J57 为 I2C PMOD（经 TCA6416），FPGA 信号不出现在 J57——勿插。
