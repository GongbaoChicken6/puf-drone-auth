# build.ps1 -- 编译 ARM 机载飞控 ELF（OCM 裸机）
$ErrorActionPreference = "Stop"
$gcc = "D:\\vivado\\2026.1\\gnu\\aarch32\\nt\\gcc-arm-none-eabi\\bin\\arm-none-eabi-gcc.exe"
if (-not (Test-Path $gcc)) { Write-Host "GCC NOT FOUND: $gcc"; exit 1 }
Set-Location $PSScriptRoot
$args_ = @('-mcpu=cortex-a9','-marm','-g','-O1','-ffreestanding','-nostdlib','-nostartfiles','-T','ocm.ld','start.S','main.c','-o','arm_fan.elf','-Wl,-Map=arm_fan.map')
& $gcc @args_
if ($LASTEXITCODE -ne 0) { Write-Host "BUILD FAIL"; exit 1 }
Write-Host "BUILD_OK arm_fan.elf"
& "D:\\vivado\\2026.1\\gnu\\aarch32\\nt\\gcc-arm-none-eabi\\bin\\arm-none-eabi-size.exe" arm_fan.elf