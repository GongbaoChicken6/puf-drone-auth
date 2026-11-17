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
}