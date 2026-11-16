/* arm_fan main.c -- ARM 核机载飞控（2026-11-16 老师要求：ARM 控电机）
 * EMIO(bank2): bit0=arm_pwm(出) bit1=arm_sel(出) bit0=auth_pass(入, RO 寄存器)
 * 语义：认证 PASS -> 风扇 30% 起转渐升至 100%（起飞时序）；REJECT/掉认证 -> 停转
 * 运行：OCM 裸机，XSDB 经 JTAG 加载，断电即失（与 bit 一致）
 * 寄存器依据：xgpiops_v3_13 官方驱动
 */
#define GPIO_BASE   0xE000A000UL
#define DATA_2      (*(volatile unsigned int *)(GPIO_BASE + 0x48 ))
#define DATA_2_RO   (*(volatile unsigned int *)(GPIO_BASE + 0x68 ))
#define DIRM_2      (*(volatile unsigned int *)(GPIO_BASE + 0x284))
#define OEN_2       (*(volatile unsigned int *)(GPIO_BASE + 0x288))

#define ARM_PWM  (1u << 0)
#define ARM_SEL  (1u << 1)

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
    OEN_2  |= (ARM_PWM | ARM_SEL);
    DATA_2 |=  ARM_SEL;
    DATA_2 &= ~ARM_PWM;

    for (;;) {
        unsigned pass = DATA_2_RO & 1u;

        if (pass) {
            if (duty == 0) duty = DUTY_MIN;
            else if (duty < DUTY_MAX && ++ramp >= RAMP_STEP) { duty++; ramp = 0; }
        } else {
            duty = 0; ramp = 0;
        }

        for (unsigned t = 0; t < PWM_PERIOD; ++t) {
            if (t < duty) DATA_2 |=  ARM_PWM;
            else          DATA_2 &= ~ARM_PWM;
            delay_tick();
        }
    }
}