/* flight_ctrl.c -- Zynq PS 端 ARM 飞控状态机（2026-11-19）
 * 功能：经 EMIO 监视 PL 认证结果，驱动飞行状态机，经 PS UART1 输出实时状态
 * 状态：LOCKED → ARMED → TAKEOFF → CRUISE → (auth drop) → LOCKED
 * 运行：OCM 裸机，XSDB JTAG 加载，UART1@115200 输出
 */

/* ===== PS UART1 (Cadence UART, ZC706 板载 USB-UART) ===== */
#define UART1_BASE   0xE0001000UL
#define UART1_CR     (*(volatile unsigned int *)(UART1_BASE + 0x00))
#define UART1_MR     (*(volatile unsigned int *)(UART1_BASE + 0x04))
#define UART1_BAUDGEN (*(volatile unsigned int *)(UART1_BASE + 0x18))
#define UART1_BAUDDIV (*(volatile unsigned int *)(UART1_BASE + 0x34))
#define UART1_SR     (*(volatile unsigned int *)(UART1_BASE + 0x2C))
#define UART1_FIFO   (*(volatile unsigned int *)(UART1_BASE + 0x30))

#define UART_SR_TFULL  0x10  /* TX FIFO full */
#define UART_SR_TEMPTY 0x08  /* TX FIFO empty */

/* ===== PS GPIO (EMIO 输入: auth_pass) ===== */
#define GPIO_BASE    0xE000A000UL
#define DATA_2_RO    (*(volatile unsigned int *)(GPIO_BASE + 0x68))
#define DIRM_2       (*(volatile unsigned int *)(GPIO_BASE + 0x284))

#define AUTH_PASS_BIT 0x1  /* EMIO GPIO[0] = auth_pass */

/* ===== 飞行状态机 ===== */
typedef enum {
    ST_LOCKED = 0,
    ST_ARMED,
    ST_TAKEOFF,
    ST_CRUISE,
    ST_LAND,
    ST_COUNT
} flight_state_t;

static const char *state_names[] = {
    "LOCKED",
    "ARMED",
    "TAKEOFF",
    "CRUISE",
    "LAND"
};

/* 简单延时（~1ms @ 666MHz，粗略即可） */
static void delay_ms(volatile unsigned ms)
{
    while (ms--) {
        for (volatile unsigned i = 0; i < 80000; ++i)
            __asm__ volatile ("nop");
    }
}

/* UART 输出 */
static void uart_putc(char c)
{
    while (UART1_SR & UART_SR_TFULL);
    UART1_FIFO = (unsigned int)(unsigned char)c;
}

static void uart_puts(const char *s)
{
    while (*s) {
        if (*s == '\n') uart_putc('\r');
        uart_putc(*s++);
    }
}

static void uart_put_hex(unsigned int val)
{
    static const char hex[] = "0123456789ABCDEF";
    uart_puts("0x");
    for (int i = 28; i >= 0; i -= 4)
        uart_putc(hex[(val >> i) & 0xF]);
}

/* 读取认证状态（EMIO GPIO 输入） */
static int auth_passed(void)
{
    return (DATA_2_RO & AUTH_PASS_BIT) != 0;
}

int main(void)
{
    flight_state_t state = ST_LOCKED;
    unsigned int state_timer = 0;
    unsigned int tick = 0;
    unsigned int last_pass = 0;

    /* 初始化 UART 横幅 */
    uart_puts("\n\n=================================\n");
    uart_puts("  PUF Drone Flight Controller\n");
    uart_puts("  ARM Cortex-A9 @ OCM bare-metal\n");
    uart_puts("=================================\n\n");
    uart_puts("[FC] init: EMIO GPIO_I[0] = auth_pass\n");
    uart_puts("[FC] init: UART1 @ 115200 baud\n");
    uart_puts("[FC] state: LOCKED (waiting for auth PASS)\n\n");

    for (;;) {
        delay_ms(100);  /* 100ms tick */
        tick++;
        state_timer++;

        unsigned int pass = auth_passed();

        /* 检测认证状态变化 */
        if (pass != last_pass) {
            if (pass) {
                uart_puts("\n[FC] *** AUTH PASS DETECTED ***\n");
                uart_puts("[FC] Transition: LOCKED -> ARMED\n\n");
                state = ST_ARMED;
                state_timer = 0;
            } else {
                uart_puts("\n[FC] *** AUTH LOST / REJECT ***\n");
                uart_puts("[FC] Transition: -> LOCKED (motor off)\n\n");
                state = ST_LOCKED;
                state_timer = 0;
            }
            last_pass = pass;
        }

        /* 飞行状态机 */
        switch (state) {
        case ST_LOCKED:
            /* 每 5 秒打印心跳 */
            if (tick % 50 == 0) {
                uart_puts("[FC] LOCKED. Waiting for auth... (tick=");
                uart_put_hex(tick);
                uart_puts(")\n");
            }
            break;

        case ST_ARMED:
            uart_puts("[FC] ARMED. Motor idle. Escalating...\n");
            if (state_timer >= 20) { /* 2 秒后起飞 */
                uart_puts("[FC] Transition: ARMED -> TAKEOFF\n\n");
                state = ST_TAKEOFF;
                state_timer = 0;
            }
            break;

        case ST_TAKEOFF:
            if (state_timer % 5 == 0) { /* 每 500ms 报高度 */
                unsigned int alt = state_timer / 10;  /* 模拟高度 = 秒数 */
                uart_puts("[FC] TAKEOFF. Altitude: ");
                uart_put_hex(alt);
                uart_puts("m and climbing...\n");
            }
            if (state_timer >= 50) { /* 5 秒后进入巡航 */
                uart_puts("\n[FC] Transition: TAKEOFF -> CRUISE\n\n");
                state = ST_CRUISE;
                state_timer = 0;
            }
            break;

        case ST_CRUISE:
            if (tick % 10 == 0) { /* 每 1 秒报状态 */
                uart_puts("[FC] CRUISE. Motor: ON. Altitude: stable.\n");
            }
            break;

        case ST_LAND:
            if (state_timer % 5 == 0) {
                uart_puts("[FC] LAND. Descending...\n");
            }
            if (state_timer >= 30) {
                uart_puts("[FC] LANDED. Motor off.\n\n");
                state = ST_LOCKED;
                state_timer = 0;
            }
            break;

        default:
            state = ST_LOCKED;
            break;
        }
    }
    return 0;
}