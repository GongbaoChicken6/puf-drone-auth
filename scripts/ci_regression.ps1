# ci_regression.ps1 -- Full regression: compile + simulate all TBs
# Usage: .\scripts\ci_regression.ps1
# Exit 0 = all pass, exit 1 = any failure

$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")
$vivado = "D:\vivado\2026.1\Vivado\bin"

$rtl = @("src\rtl\common\crc16_mcrf4xx.v", "src\rtl\common\mavlink_frame.v",
         "src\rtl\common\frame_parser.v",  "src\rtl\common\byte_fifo.v",
         "src\rtl\common\uart_tx.v",       "src\rtl\common\uart_rx.v",
         "src\rtl\w3_protocol\terminal_fsm.v")
$tbs = @("sim\tb\tb_crc16.v", "sim\tb\tb_mavlink_frame.v", "sim\tb\tb_frame_parser.v",
         "sim\tb\tb_byte_fifo.v", "sim\tb\tb_uart_tx.v", "sim\tb\tb_terminal_fsm.v",
         "sim\tb\tb_tx_chain.v", "sim\tb\tb_level3_protocol.v")
$tbNames = @("tb_crc16","tb_mavlink_frame","tb_frame_parser","tb_byte_fifo",
             "tb_uart_tx","tb_terminal_fsm","tb_tx_chain","tb_level3_protocol")

Write-Host "=== CI: Compile ==="
Remove-Item xsim.dir -Recurse -Force -ErrorAction SilentlyContinue
& "$vivado\xvlog.bat" @rtl @tbs 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "COMPILE FAILED"; exit 1 }
Write-Host "  OK"

Write-Host "=== CI: Elaborate ==="
for ($i = 0; $i -lt $tbNames.Count; $i++) {
    & "$vivado\xelab.bat" -debug typical $tbNames[$i] -s "ci$i" 2>&1 | Out-Null
}
Write-Host "  OK"

Write-Host "=== CI: Simulate ==="
$pass = 0; $fail = 0
for ($i = 0; $i -lt $tbNames.Count; $i++) {
    $result = & "$vivado\xsim.bat" "ci$i" -runall --onerror quit 2>&1 | Select-String "TB_.*PASS"
    if ($result) { Write-Host "  [PASS] $($tbNames[$i])"; $pass++ }
    else { Write-Host "  [FAIL] $($tbNames[$i])"; $fail++ }
}

Write-Host "`n=== $pass/$($tbNames.Count) PASS, $fail FAIL ==="
Remove-Item xsim.dir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item *.pb -Force -ErrorAction SilentlyContinue
if ($fail -gt 0) { exit 1 } else { exit 0 }
