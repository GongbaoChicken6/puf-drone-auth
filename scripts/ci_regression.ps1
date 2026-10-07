# ci_regression.ps1 -- Full regression: ALL RTL + ALL TBs (W1+W2+W3)
# Usage: .\scripts\ci_regression.ps1
# Exit 0 = all pass, exit 1 = any failure

$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")
$vivado = "D:\vivado\2026.1\Vivado\bin"
# Fail fast with an honest message instead of stale-exit-code "OK"s when
# the toolchain is missing (ci_gate review M2 experiment).
if (-not (Test-Path "$vivado\xvlog.bat")) {
    Write-Host "VIVADO NOT FOUND at $vivado"; exit 1
}

# ALL RTL files (W1 + W2 + W3)
$rtl = @(
    "src\rtl\w1_ratio\ro_ring.v", "src\rtl\w1_ratio\ro_div.v",
    "src\rtl\w2_array\ro_array.v", "src\rtl\w2_array\challenge_decode.v",
    "src\rtl\w2_array\w2_top.v",
    "src\rtl\common\crc16_mcrf4xx.v", "src\rtl\common\mavlink_frame.v",
    "src\rtl\common\frame_parser.v",  "src\rtl\common\byte_fifo.v",
    "src\rtl\common\uart_tx.v",       "src\rtl\common\uart_rx.v",
    "src\rtl\common\speck64_96.v",
    "src\rtl\w3_protocol\terminal_fsm.v", "src\rtl\w3_protocol\w3_top.v"
)
# ALL TB files
$tbs = @(
    "sim\tb\tb_speck.v",
    "sim\tb\tb_gap_regression.v",
    "sim\tb\tb_challenge_decode.v",
    "sim\tb\tb_crc16.v", "sim\tb\tb_mavlink_frame.v", "sim\tb\tb_frame_parser.v",
    "sim\tb\tb_byte_fifo.v", "sim\tb\tb_uart_tx.v", "sim\tb\tb_terminal_fsm.v",
    "sim\tb\tb_tx_chain.v", "sim\tb\tb_level3_protocol.v", "sim\tb\tb_w3_top.v"
)
$tbNames = @("tb_speck", "tb_gap_regression",
             "tb_challenge_decode","tb_crc16","tb_mavlink_frame","tb_frame_parser",
             "tb_byte_fifo","tb_uart_tx","tb_terminal_fsm","tb_tx_chain","tb_level3_protocol",
             "tb_w3_top")

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
if ($fail -gt 0) { exit 1 }

Write-Host "=== CI: Python (Speck self-test + A1 phase-4 unit tests) ==="
# Silent-failure review P2: a missing python must fail the gate, not
# inherit $LASTEXITCODE=0 from the last xsim run (PS 5.1 never sets it
# on CommandNotFoundException).
# -CommandType Application: a python.ps1/function shim on PATH resolves via
# bare Get-Command but runs as a script (no native exit code -> stale reads;
# ci_gate review M4 false-pass experiment).
if (-not (Get-Command python -CommandType Application -ErrorAction SilentlyContinue)) {
    Write-Host "PYTHON NOT FOUND (or not a native executable) ON PATH"; exit 1
}
# Sentinel probe: prove exit codes actually propagate before trusting them.
& python -c "import sys; sys.exit(5)" > $null 2>&1
if ($LASTEXITCODE -ne 5) {
    Write-Host "PYTHON SENTINEL FAILED (exit codes unreliable: shim?)"; exit 1
}
# NOTE: do NOT pre-assign $LASTEXITCODE here.  A/B on this very script:
# with the old "$LASTEXITCODE = 1" presets the speck self-test gate read
# a stale 1 and failed (build/reviews/a1p5/ci_second_run_python_gate_fail.log);
# with them removed the identical run is green (ci_final_run.log).  The
# exact PowerShell scoping mechanism was NOT reproduced under bare
# "powershell -File" (reviewer experiment), so treat presets here as
# harmful-in-context rather than relying on any theory.  The Get-Command
# guard above already covers the only case the presets defended against
# (command-not-found leaving a stale code); a WindowsApps stub that fails
# to launch exits 9009, which IS a fresh exit code.
& python "src\python\common\speck.py" > $null 2>&1
if ($LASTEXITCODE -ne 0) { Write-Host "PYTHON SPECK SELF-TEST FAILED"; exit 1 }
# Stringify each line: PS 5.1 wraps native stderr as ErrorRecords under 2>&1,
# which pollutes the evidence log with "RemoteException" markers (review P3).
$out = & python "tests\test_a1_phase4.py" 2>&1 | ForEach-Object { "$_" }
$pyCode = $LASTEXITCODE
if ($pyCode -ne 0) {
    $out | Select-Object -Last 40 | ForEach-Object { Write-Host "  $_" }
    Write-Host "PYTHON UNIT TESTS FAILED"; exit 1
}
$out | Select-Object -Last 4 | ForEach-Object { Write-Host "  $_" }
$out2 = & python "scripts\test_r2_nonlinearity.py" 2>&1 | ForEach-Object { "$_" }
$canCode = $LASTEXITCODE
if ($canCode -ne 0) {
    $out2 | Select-Object -Last 40 | ForEach-Object { Write-Host "  $_" }
    Write-Host "R2 NONLINEARITY CANARY FAILED"; exit 1
}
$out2 | Select-Object -Last 3 | ForEach-Object { Write-Host "  $_" }
$out3 = & python "scripts\gen_speck_vectors.py" --check 2>&1 | ForEach-Object { "$_" }
if ($LASTEXITCODE -ne 0) {
    $out3 | Select-Object -Last 10 | ForEach-Object { Write-Host "  $_" }
    Write-Host "SPECK VECTOR FRESHNESS CHECK FAILED"; exit 1
}
# One audible line on success so the evidence log proves the check ran.
$out3 | Select-Object -Last 1 | ForEach-Object { Write-Host "  $_" }
Write-Host "  OK"
exit 0