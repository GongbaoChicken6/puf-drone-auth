/* arm_fan v4 -- ARM 监视程序（OEN-PWM 写入在 v4 中不再驱动 OBUFT——EMIO GPIO_O 硅上不可信）
 * 保留原因：读 auth_pass 做状态监视，答辩叙事 'PL 认证+PS 监视' 仍成立
 * 转 = OEN=0 释放(Hi-Z，L9110 内部上拉导通)；停 = OEN=1 且 DATA=0 驱动低
 * 调速 = OEN 上的软件 PWM（供电电压不敏感，4.5V/5V 通用） */
#define GPIO_BASE   0xE000A000UL
#define DATA_2      (*(volatile unsigned int *)(GPIO_BASE + 0x48 ))
#define DATA_2_RO   (*(volatile unsigned int *)(GPIO_BASE + 0x68 ))
#define DIRM_2      (*(volatile unsigned int *)(GPIO_BASE + 0x284))
#define OEN_2       (*(volatile unsigned int *)(GPIO_BASE + 0x288))
#define ARM_PWM  (1u << 0)   /* bit0: OEN 位——板上实测 1=释放(转) 0=驱动低(停) */
#define ARM_SEL  (1u << 1)   /* bit1: 接管选择，恒驱动高 */
#define PWM_PERIOD 20u
#define RAMP_STEP  30u
#define DUTY_MIN   6u
#define DUTY_MAX   20u
static void delay_tick(void)
{
    for (volatile unsigned i = 0; i < 60000u; ++i)
        __asm__ volatile ("nop");
}
int main(void)
{
    unsigned duty = 0, ramp = 0;
    DIRM_2 |= (ARM_PWM | ARM_SEL);
    OEN_2  = (OEN_2 & ~ARM_PWM) | ARM_SEL;    /* bit0=0 驱动低=停；bit1 驱动(sel) */
    DATA_2  = (DATA_2 | ARM_SEL) & ~ARM_PWM;  /* sel=1 接管；pwm 数据位恒 0 */
    for (;;) {
        unsigned pass = (DATA_2_RO & 1u);  /* auth_pass */
        if (pass) {
            if (duty == 0) duty = DUTY_MIN;
            else if (duty < DUTY_MAX && ++ramp >= RAMP_STEP) { duty++; ramp = 0; }
        } else {
            duty = 0; ramp = 0;
        }
        for (unsigned t = 0; t < PWM_PERIOD; ++t) {
            if (t < duty) OEN_2 |=  ARM_PWM;   /* 释放 = 转（OEN=1，板上实测） */
            else          OEN_2 &= ~ARM_PWM;   /* 驱动低 = 停（OEN=0+DATA=0） */
            delay_tick();
        }
    }
}
