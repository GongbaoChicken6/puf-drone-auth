# W3 协议模块语法检查（审查 F4：新模块必须进工具链）
# 用法: .\build\ps1\run_xvlog_w3.ps1
$ErrorActionPreference = "Continue"
Set-Location "D:\puf-drone-auth"
$xvlog = "D:\vivado\2026.1\Vivado\bin\xvlog.bat"

$files = @(
    "src\rtl\common\crc16_mcrf4xx.v",
    "src\rtl\common\mavlink_frame.v",
    "sim\tb\tb_crc16.v",
    "sim\tb\tb_mavlink_frame.v"
)
& $xvlog @files 2>&1 | Select-String "ERROR|CRITICAL" | ForEach-Object { $_.Line }
Write-Host "xvlog exit: $LASTEXITCODE"
exit $LASTEXITCODE
