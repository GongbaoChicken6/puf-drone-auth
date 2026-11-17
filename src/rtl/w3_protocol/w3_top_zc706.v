`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Design Name: bawan-yhy
// Module Name: w3_top_zc706
// Description:
//  ZC706（xc7z045ffg900-2）板级 wrapper：200MHz 差分时钟（H9/G9，bank34=
//  VCC1V5_PL 1.5V 固定轨，DIFF_SSTL15）经 clk_wiz_0 降为 100MHz 单端，
//  配 w3_top 协议顶层。仅综合/实现用，不参与仿真与 CI（clk_wiz_0 IP 不在
//  仓库，上板前由 build_w3_board.tcl 生成；离板语法门禁=build/ps1/
//  verify_wrapper.ps1，stub 写 %TEMP%）。
//
//  引脚事实卡（UG954 v1.8 + 板卡文件 + IBIS pkg 三方核验，详见
//  docs/process/plans/zc706_migration_plan.md §0.5）：
//    时钟  clk_p=H9 clk_n=G9（DIFF_SSTL15，禁抄 ZC702 的 LVDS_25）
//    复位  SW13=A8（LVCMOS15！）      认证按键 SW7=AK25（LVCMOS25）
//    拨码  SW12=AB17/AC16/AC17/AJ13（LVCMOS25，ON=1，板上 4.7k 下拉）
//    UART  PMOD1(J58)：txd=AJ21(J58.1) rxd=AB21(J58.5)，经 TXS0108E
//          3.3V<->2.5V 电平移位（⚠ 勿插 J57——那是 I2C 扩展器）
//    LED   result=Y21(DS8)/W21(DS10)（亮）；busy=G2(DS9)/心跳=A17(DS35)
//          （1.5V bank 偏暗——NDS331 裕量，bring-up 首查可见性）
//  ⚠ 共 4 颗 LVCMOS15（G2/A17/K15/A8）：XDC 写成 25 即 DRC BIVB-1。
//  ⚠ ENROLL_EN=1：板级注册模式（Phase 8a，站端驱动 enroll 背靠背挑战）。
//////////////////////////////////////////////////////////////////////////////////

module w3_top_zc706 # (
    parameter BAUD      = 115_200 ,   // UART 波特率
    parameter TIMEOUT_S = 2            // 协议超时（秒）
  )
  (
    // 差分时钟（200MHz，经 clk_wiz_0 降为 100MHz）
    input  wire         clk_p         ,   // H9，200MHz 差分正端（DIFF_SSTL15）
    input  wire         clk_n         ,   // G9，200MHz 差分负端

    // 复位与控制
    input  wire         sys_rst_btn_n ,   // SW13 PL_CPU_RESET（A8）板上实测：空闲0/按下1（高有效，2026-10-22 23:27 health 实证；端口名沿用 _n 是历史命名，勿按名推极性）
    input  wire         auth_btn      ,   // SW7 GPIO_SW_LEFT（AK25）板上实测：空闲0/按下1（2026-10-22 23:27 health 实证，推翻 UG954 图纸解读）
    input  wire [3:0]   term_id_dip   ,   // SW12 pin1..4（ON=1 / OFF=0）

    // UART（PMOD1 J58，经 TXS0108E 电平移位，USB-TTL 3.3V 直插）
    output wire         radio_txd     ,   // AJ21 = J58.1
    input  wire         radio_rxd     ,   // AB21 = J58.5

    // LED（高电平点亮；finals-demo N1: result/busy 经 demo_led 灯语增强）
    output wire         led_busy      ,   // G2  = DS9（偏暗，仅指示）
    output wire [1:0]   led_result    ,   // Y21/W21 = DS8/DS10（闪序增强后的结果码）
    output wire         led_heartbeat ,   // A17 = DS35（偏暗，~0.75Hz）

    // N7(finals-demo): PMOD J58 外接大灯/蜂鸣器（3.3V 侧经 TXS0108E；断电插拔）
output wire [2:0]   ext_led       ,   // 绿2/红/琥珀（10mm 大灯）
inout  wire         ext_fan       ,   // J58.3 三态输出：ARM 释放(Hi-Z)=L9110上拉导通 / 驱动低=停
    output wire         ext_buzzer        // 有源蜂鸣器（高=响）
  );

//---------------- 时钟适配 ---------------//
wire clk_100m;                        // clk_wiz_0 输出的 100MHz 单端
wire mmcm_locked;                     // MMCM 锁定指示

clk_wiz_0 u_mmcm (
    .clk_in1_p ( clk_p          ),   // 200MHz 差分正端
    .clk_in1_n ( clk_n          ),   // 200MHz 差分负端
    .reset     ( sys_rst_btn_n   ),   // IP 复位高有效 <- 按键高有效直连（板上按下=1）
    .clk_out1  ( clk_100m       ),   // 100MHz 单端输出
    .locked    ( mmcm_locked    )    // 锁定指示
);

//---------------- 复位组合 ---------------//
// 按键高有效（按下=复位）取反 AND MMCM 已锁定（锁定前持续复位，双保险）
wire rst_n = ~sys_rst_btn_n & mmcm_locked;

//---------------- 灯语增强内部网（finals-demo N1/N7） ---------------//
// demo_led 纯消费 result 码生成闪序，不改 terminal_fsm/w3_top 语义——
// 18 个既有 TB 不受影响（CI wrapper 三元素锁不触碰本区）。
wire [1:0] led_result_raw;
wire       led_busy_raw;
wire [3:0] ext_led_pl;                 // demo_led 原始外灯输出（bit0 可能被 PS 接管）

//---------------- 协议顶层 ---------------//
w3_top # ( .FREQ_HZ   ( 100_000_000 ),   // 板上时钟 100MHz
           .BAUD      ( BAUD        ),
           .TIMEOUT_S ( TIMEOUT_S   ),
           .ENROLL_EN ( 1           ),   // Phase 8a：板级注册模式
           .SEED_GATE_EN ( 1        )    // P1-5 熵门控恢复（2026-10-23）：曾因"熵卡死屏蔽按键"
                                         //   误判旁路(=0)——该依据已被板上实测翻案（设计从未
                                         //   出复位，E_IDLE 是复位假象），豁免已撤销，详见
                                         //   build/reviews/zc706_bringup/HANDOFF_20261023_根因翻案.md
) u_top (
    .sys_clk       ( clk_100m              ),
    .sys_rst_n     ( rst_n                 ),
    .radio_txd     ( radio_txd             ),
    .radio_rxd     ( radio_rxd             ),
    .auth_btn      ( auth_btn              ),
    .term_id_sw    ( { 4'h0, term_id_dip } ),   // SW12 有 4 位，高 4 位 tie 0
    .led_busy      ( led_busy_raw          ),
    .led_result    ( led_result_raw        ),
    .led_heartbeat ( led_heartbeat         )
);

//---------------- 灯语增强（finals-demo N1/N7） ---------------//
demo_led # (
    .FLASH_HALF_MS ( 125           ),
    .FREQ_HZ       ( 100_000_000   )
) u_demo_led (
    .clk         ( clk_100m        ),
    .rst_n       ( rst_n           ),
    .result_in   ( led_result_raw  ),
    .busy_in     ( led_busy_raw    ),
    .led_result  ( led_result      ),
    .led_busy    ( led_busy        ),
    .ext_led     ( ext_led_pl     ),
    .ext_buzzer  ( ext_buzzer      )
);

//---------------- PS 飞控执行器 v2（2026-11-17 板载5V供电：三态释放方案） ---------------//
// 供电路线：L9110 VCC 直接取 J63.13(5V)——"转"不再依赖 3.3V 压阈值：
//   转 = ARM 置 OEN=0 释放引脚(Hi-Z) -> L9110 内部上拉拉向 5V -> 导通
//   停 = ARM 置 OEN=1 且 DATA=0 驱动低
//   调速 = 在释放/拉低间软件 PWM（对供电电压不敏感，4.5V/5V 通用）
// EMIO: GPIO_O[1]=arm_sel(接管) GPIO_T[0]=PS三态(OEN取反) GPIO_I[0]=auth_pass
// 默认安全：PS 未上程序 -> arm_sel=0 -> 强制驱动(T=0)走原 demo_led 路径，行为同旧 bit。
wire [3:0] ps_gpio_o;
wire [3:0] ps_gpio_i;
wire [3:0] ps_gpio_t;

assign ps_gpio_i[0]   = ( led_result_raw == 2'b01 );   // 01=通过 10=拒绝 11=阻断
assign ps_gpio_i[3:1] = 3'b000;

ps7_core u_ps7 (
    .GPIO_I ( ps_gpio_i ),
    .GPIO_O ( ps_gpio_o ),
    .GPIO_T ( ps_gpio_t )    // bit0 = ~OEN：1=悬空(释放=L9110上拉导通) 0=驱动
);

wire fan_val = ps_gpio_o[1] ? ps_gpio_o[0] : ext_led_pl[0];
wire fan_t   = ps_gpio_o[1] ? ps_gpio_t[0] : 1'b0;      // ARM 未接管时恒驱动

assign ext_fan     = fan_t ? 1'bz : fan_val;            // J58.3 (AK21) 三态输出
assign ext_led[2:0] = ext_led_pl[3:1];                  // 其余大灯位不变（重排：0<-1,1<-2,2<-3）

endmodule
