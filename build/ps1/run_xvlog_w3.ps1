# W3 protocol modules syntax check
# Usage: .\build\ps1\run_xvlog_w3.ps1
$ErrorActionPreference = "Continue"
Set-Location "D:\puf-drone-auth"
$xvlog = "D:\vivado\2026.1\Vivado\bin\xvlog.bat"

$files = @(
    "src\rtl\common\crc16_mcrf4xx.v",
    "src\rtl\common\mavlink_frame.v",
    "src\rtl\common\frame_parser.v",
    "sim\tb\tb_crc16.v",
    "sim\tb\tb_mavlink_frame.v",
    "sim\tb\tb_frame_parser.v"
)
& $xvlog @files 2>&1 | Select-String "ERROR|CRITICAL" | ForEach-Object { $_.Line }
Write-Host "xvlog exit: $LASTEXITCODE"
exit $LASTEXITCODE
