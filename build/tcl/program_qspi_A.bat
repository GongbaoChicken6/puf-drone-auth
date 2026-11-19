@echo off
chcp 65001 >nul
echo ================================================
echo  QSPI 烧写 - 板A (BOOT_v3.bin)
echo ================================================
set VIVADO=D:\vivado\2026.1\Vivado\bin\vivado.bat
"%VIVADO%" -mode batch -nojournal -nolog -notrace -source "D:\puf-drone-auth\build\tcl\program_qspi_A.tcl"
echo.
echo 完成，按任意键关闭
pause >nul
