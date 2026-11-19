/* ocm.ld -- OCM 低区（0x0000_0000，64K 窗口）裸机布局：XSDB/JTAG 调试加载用
 * 注意：OCM 低 192K 是 FSBL 的运行区，本布局只能在 JTAG(dow) 路径用，
 *       经 BOOT.bin/FSBL 启动的应用必须用 ddr.ld。 */
ENTRY(_start)
MEMORY
{
    ocm (rwx) : ORIGIN = 0x00000000, LENGTH = 64K   /* ZC706 ps7_init 将 OCM 映射在低位（实测 dow 0xFFFC0000 被拒） */
}
SECTIONS
{
    .text : {
        KEEP(*(.text.start))
        *(.text*)
    } > ocm
    .rodata : { *(.rodata*) } > ocm
    .data   : { *(.data*)   } > ocm
    .bss : {
        __bss_start = .;
        *(.bss*) *(COMMON)
        __bss_end = .;
    } > ocm

    /* 栈顶：本区顶端向下留 128B（0xFF80，8 字节对齐），栈向下生长。
     * start.S 只引用这个符号，不再硬编码地址。 */
    __stack_top = ORIGIN(ocm) + LENGTH(ocm) - 0x80;
}
