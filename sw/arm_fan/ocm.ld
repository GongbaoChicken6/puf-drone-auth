ENTRY(_start)
MEMORY
{
    ocm (rwx) : ORIGIN = 0xFFFC0000, LENGTH = 64K
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