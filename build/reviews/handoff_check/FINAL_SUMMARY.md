【项目】PUF 无人机硬件指纹双向认证 · 截止 2026-11-04（余约 16 天，今天 10-19）
【仓库】D:\puf-drone-auth · HEAD b0f3e21
【权威文档】docs/HANDOFF_SUMMARY.md 开头「板卡迁移交接记录」节
【注意】工作区有另一会话的凭据脚本(cred*.ps1/gh_auth.ps1)和前端文件，建议 git stash

═══ 决定 ═══

ZC702 故障(PWRGOOD 不亮) → 换两块 ZC706(实验室各有)。
PC = 基站，两块 ZC706 = 终端 1/2。一份 wrapper + 一份 XDC + 一份比特流烧两板。
终端区分 = DIP 拨码(4 位，用低 2 位设 terminal_id)。PUF 天然不同(两颗不同芯片)。
PYNQ-Z2 已排除。

═══ ZC706 全部引脚(三方验证+repo_verify 逐字比对+completeness 补充 UART)═══

时钟：  clk_p=H9  clk_n=G9  (LVDS 200MHz 差分) ← wrapper 零改动
LED：   Y21(LVCMOS25)  G2(LVCMOS15!)  W21(LVCMOS25)  A17(LVCMOS15!)
拨码：  AB17 AC16 AC17 AJ13 (全 LVCMOS25, 4位)
按键：  AK25(LVCMOS25)  K15(LVCMOS15!)  R27(LVCMOS25)
复位：  A8 (LVCMOS15!)
UART：  radio_txd=AE12 (FMC LPC LA02_P, LVCMOS25)
        radio_rxd=AF12 (FMC LPC LA02_N, LVCMOS25)
        ⚠ ZC702 的 L21/L22 不能沿用！ZC706 FMC 引脚完全不同
        ⚠ FMC 的 VADJ 电压需查 UG954 确认(本机无该文档)
⚠ 共 4 颗 LVCMOS15 引脚(G2/A17/K15/A8)，XDC 必须逐个写对
器件: xc7z045ffg900-2
板卡文件: D:\vivado\2026.1\...\boards\Xilinx\zc706\1.5\

═══ 迁移步骤 ═══

Step 1. 创建 w3_top_zc706.v（参考 w3_top_zc702.v）
        改动：时钟引脚名 H9/G9、复位 A8(LVCMOS15)、LED 引脚、
        UART 引脚 AE12/AF12、term_id_dip 从 [1:0] 改 [3:0](ZC706 有 4 位拨码)
        ⚠ wrapper 不在 CI 编译清单——语法错误 CI 抓不到，必须手动 xvlog
Step 2. 创建 w3_top_zc706.xdc（从 zc706/1.5/part0_pins.xml 逐引脚填）
        ⚠ 保留 LUTLP-1 豁免（w2_waiver.xdc，环振组合环，设计使然）
Step 3. 更新 build_w3_board.tcl（part=xc7z045ffg900-2 + wrapper 文件名 + XDC 文件名）
Step 4. xvlog+xelab 验证
        ⚠ clk_wiz_0 stub 不在仓库，需临时写在 %TEMP%（5 行）：
        module clk_wiz_0(input clk_in1_p,clk_in1_n,reset, output clk_out1,locked);
          assign clk_out1=clk_in1_p; assign locked=~reset; endmodule
Step 5. 生成比特流 → 同一份 .bit 烧两块板
        ⚠ 先确认 ZC706 的 JTAG 连接器线型和电源接口（仓库无记载）
        ⚠ pyserial 为可选依赖，需 pip install pyserial
Step 6. 板 A 拨码=ID1，板 B 拨码=ID2
Step 7. 两板 FMC→USB-TTL→PC 双 COM 口
        ⚠ 433MHz 电台未购买——双终端演示依赖 2×USB-TTL(3.3V)直连
        关键文件：src/python/server/serial_server.py、enroll.py、tools/check_contract_sync.py
Step 8. PUF 真接入 + 两板分别注册模板（W4 核心）
        ⚠ 这是最大单项（8~12h/板），含 CRP 重采 + 阈值复核
        W4 计划书(docs/process/plans/)记录了 ENABLE_KEY_DERIVE=0 等安全边界
        ⚠ 注册语义必须与终端响应语义配对（配错必 REJECT）

═══ 已有资产(零改动)═══

w3_top.v + 15 个 RTL 模块 + 16 个 TB + Python(109 单测) + CI ✅
w3_top_zc702.v(参考) + w3_top.xdc(底稿) + build_w3_board.tcl
教程: docs/process/tutorials/w1_tutorial.md (527 行)
前端: docs/FRONTEND_HANDOFF.md (独立交接)

═══ 竞赛信息 ═══

赛道: §3.3 自主选题(初级组) | PYNQ Skill 加分(推荐不强制)
审查: build/reviews/tutorial/(5) + board_diff/(3) + handoff_check/(2)