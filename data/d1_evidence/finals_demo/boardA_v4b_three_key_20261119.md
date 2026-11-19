# 板A 按键抢救与 v4b bit（2026-11-19 16:50）

## 背景
板A SW7(AK25) 按键突发失效（探测证死）。为不依赖万用表，把 SW8/SW9 并联进认证重出 bit。

## v4b 改动（build/board_zc706_arm_v4b/w3_top_zc706.bit, BITSTREAM_SUCCESS WNS=1.227）
- w3_top_zc706.v: 新增 auth_btn2(SW8=R27,LVCMOS25) / auth_btn3(SW9=K15,LVCMOS15)，
  wire auth_btn_any = auth_btn | auth_btn2 | auth_btn3 送消抖；其余逻辑与 v4 完全相同
- XDC: 两键引脚 + false_path；ext_fan 回 v4 映射 AK21(J58.3)（v5 换脚已在硅上验证无风扇功能）
- 端口/引脚来源：UG954 v1.8 Table 1-29（SW7=AK25/SW8=R27/SW9=K15/SW13=A8）

## 按键实测（v4b 烧录后逐一按 1 秒）
- 监听窗口 4 次 access.requested tid=1 COM6：16:45:40 / 16:45:43 / 16:46:00 / 16:46:07
- SW8 可用、SW9 可用、SW7 仍死（用户现场确认 SW8 和 SW9 都能触发）
- 三键并联下任按 SW8/SW9 即发起认证 → 板A 恢复物理按键发起

## 关键发现：PUF 模板与 bit 布局绑定
- v4b 重新综合实现后环形振荡器物理位置变化 → 旧模板失效
- 首次认证 REJECT(hd 逐响应含35) → 因模板混入旧bit的100对
- 清空模板重录100对后，认证抽到无模板种子 → KeyError 'no template for seed ...'
- 根因=池中 300 个未录入种子仍可抽；修复=CRPPool.limit_to()（新方法）
  + enroll_real 收尾自动限池（只允许有模板对的种子被抽中）

## 最终验证（限池后，两轮）
- VERDICT PASS hd=0 per=[0,0,0,0]，CONFIRM verified_r2=True，SESSION ×2
- 全量回归 220 passed / 1 skipped

## 演示口径更新
- 板A：按 SW8 或 SW9（任一）发起认证——SW7 已坏，勿按
- 板B：照旧按 SW7
- 铁律新增：换 bit（哪怕只是重跑实现）后必须重录 tid1/tid2 模板
