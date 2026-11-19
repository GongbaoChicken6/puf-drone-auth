/* start.S -- ARM 裸机启动（OCM / DDR 两种链接布局共用同一份源码）
 *
 * 栈顶 = 链接脚本给出的 __stack_top（ocm.ld / ddr.ld 各自按自己的存储区
 * 顶端向下留 128B，8 字节对齐）。禁止再把地址写死在启动代码里。
 *
 * 历史坑（2026-11-19 修）：此处曾硬编码 0x0000FF88（OCM 版）与
 * 0x1000FF88（DDR 版），而两版 ELF 共用这一份 start.S —— 谁后编谁改栈顶，
 * 另一版就会静默错配：
 *   - DDR 布局拿 OCM 栈 0x0000FF88 -> 踩 FSBL 自己的 OCM 代码/数据区；
 *   - OCM 布局拿 DDR 栈 0x1000FF88 -> 一旦经 FSBL 从 SD 启动，DDR 尚未
 *     初始化就压栈，直接挂死。
 * 改成符号引用后，链接脚本是唯一权威，编译顺序不再影响正确性。
 */
.section .text.start
.global _start
_start:
    ldr   sp, =__stack_top
    ldr   r0, =__bss_start
    ldr   r1, =__bss_end
    mov   r2, #0
1:  cmp   r0, r1
    strlo r2, [r0], #4
    blo   1b
    bl    main
hang:
    wfe
    b     hang
