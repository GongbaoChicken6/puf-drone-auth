# W3 all protocol modules syntax check
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..\..")
$xvlog = "D:\vivado\2026.1\Vivado\bin\xvlog.bat"

$files = @(
    "src\rtl\common\crc16_mcrf4xx.v",
    "src\rtl\common\mavlink_frame.v",
    "src\rtl\common\frame_parser.v",
    "src\rtl\common\byte_fifo.v",
    "src\rtl\common\uart_tx.v",
    "src\rtl\common\uart_rx.v",
    "src\rtl\w3_protocol\terminal_fsm.v",
    "sim\tb\tb_crc16.v",
    "sim\tb\tb_mavlink_frame.v",
    "sim\tb\tb_frame_parser.v",
    "sim\tb\tb_byte_fifo.v",
    "sim\tb\tb_uart_tx.v",
    "sim\tb\tb_terminal_fsm.v"
)
& $xvlog @files 2>&1 | Select-String "ERROR|CRITICAL" | ForEach-Object { $_.Line }
Write-Host "xvlog exit: $LASTEXITCODE"
exit $LASTEXITCODE

