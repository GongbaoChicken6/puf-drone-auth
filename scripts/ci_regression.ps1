# ci_regression.ps1 -- Full regression: ALL RTL + ALL TBs (W1+W2+W3)
# Usage: .\scripts\ci_regression.ps1
# Exit 0 = all pass, exit 1 = any failure

$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")
$vivado = "D:\vivado\2026.1\Vivado\bin"

# ALL RTL files (W1 + W2 + W3)
$rtl = @(
    "src\rtl\w1_ratio\ro_ring.v", "src\rtl\w1_ratio\ro_div.v",
    "src\rtl\w2_array\ro_array.v", "src\rtl\w2_array\challenge_decode.v",
    "src\rtl\w2_array\w2_top.v",
    "src\rtl\common\crc16_mcrf4xx.v", "src\rtl\common\mavlink_frame.v",
    "src\rtl\common\frame_parser.v",  "src\rtl\common\byte_fifo.v",
    "src\rtl\common\uart_tx.v",       "src\rtl\common\uart_rx.v",
    "src\rtl\common\speck64_96.v",
    "src\rtl\w3_protocol\terminal_fsm.v"
)
# ALL TB files
$tbs = @(
    "sim\tb\tb_speck.v",
    "sim\tb\tb_gap_regression.v",
    "sim\tb\tb_challenge_decode.v",
    "sim\tb\tb_crc16.v", "sim\tb\tb_mavlink_frame.v", "sim\tb\tb_frame_parser.v",
    "sim\tb\tb_byte_fifo.v", "sim\tb\tb_uart_tx.v", "sim\tb\tb_terminal_fsm.v",
    "sim\tb\tb_tx_chain.v", "sim\tb\tb_level3_protocol.v"
)
$tbNames = @("tb_speck", "tb_gap_regression",
             "tb_challenge_decode","tb_crc16","tb_mavlink_frame","tb_frame_parser",
             "tb_byte_fifo","tb_uart_tx","tb_terminal_fsm","tb_tx_chain","tb_level3_protocol")

Write-Host "=== CI: Compile ==="
Remove-Item xsim.dir -Recurse -Force -ErrorAction SilentlyContinue
& "$vivado\xvlog.bat" @rtl @tbs 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "COMPILE FAILED"; exit 1 }
Write-Host "  OK"

Write-Host "=== CI: Elaborate ==="
for ($i = 0; $i -lt $tbNames.Count; $i++) {
    & "$vivado\xelab.bat" -debug typical $tbNames[$i] -s "ci$i" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Host "ELAB FAILED: $($tbNames[$i])"; exit 1 }
}
Write-Host "  OK"

Write-Host "=== CI: Simulate ==="
$pass = 0; $fail = 0
for ($i = 0; $i -lt $tbNames.Count; $i++) {
    $output = & "$vivado\xsim.bat" "ci$i" -runall --onerror quit 2>&1
    if ($output | Select-String "TB_.*_PASS" -Quiet) { Write-Host "  [PASS] $($tbNames[$i])"; $pass++ }
    else { Write-Host "  [FAIL] $($tbNames[$i])"; $fail++ }
}

Write-Host "`n=== $pass/$($tbNames.Count) PASS, $fail FAIL ==="
Remove-Item xsim.dir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item *.pb -Force -ErrorAction SilentlyContinue
if ($fail -gt 0) { exit 1 } else { exit 0 }