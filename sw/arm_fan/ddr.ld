/* ddr.ld -- DDR 低段（0x1000_0000，64K 窗口）布局：BOOT.bin/FSBL 加载用
 * FSBL 的 ps7_init 已初始化 DDR3，故 SD 自举时应用放这里不会与 FSBL 的 OCM 冲突。 */
ENTRY(_start)
MEMORY
{
    ddr (rwx) : ORIGIN = 0x10000000, LENGTH = 64K   /* DDR for FSBL-loaded app */
}
SECTIONS
{
    .text : {
        KEEP(*(.text.start))
        *(.text*)
    } > ddr
    .rodata : { *(.rodata*) } > ddr
    .data   : { *(.data*)   } > ddr
    .bss : {
        __bss_start = .;
        *(.bss*) *(COMMON)
        __bss_end = .;
    } > ddr

    /* 栈顶：本区顶端向下留 128B（0x1000_FF80，8 字节对齐）；与 ocm.ld 同一套符号名 */
    __stack_top = ORIGIN(ddr) + LENGTH(ddr) - 0x80;
}
