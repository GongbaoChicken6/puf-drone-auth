# ci_timeout_experiment.ps1 -- W4-P0 T1 acceptance experiment.
# Injects a deliberately hung TB (first in the list), runs ci_regression.ps1
# with a 20 s simulation timeout and a minimal file set, and proves:
#   1. the hung TB is judged [TIMEOUT][FAIL] (not an infinite CI hang),
#   2. the following TB (tb_crc16) still runs and PASSes,
#   3. the script exits 1 honestly.
# The hang TB is temporary (auto-deleted); nothing is left in sim/tb.
# Usage: powershell -File scripts\ci_timeout_experiment.ps1 [-HangTimeoutS 20]

param([int]$HangTimeoutS = 20)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$hangTb = "sim\tb\tb_ci_hang_tmp.v"
# Single-quoted here-string: no variable expansion of $display/$finish.
# A single huge #delay would be skipped instantly by the event-driven
# simulator -- the forever toggler keeps events flowing forever, which
# is a genuine real-time hang; the contradictory wait() never releases.
@'
// TEMPORARY hang TB -- W4-P0 timeout experiment (auto-deleted, never committed)
module tb_ci_hang_tmp;
    reg hang_clk = 1'b0;
    initial begin
        forever #1000 hang_clk = ~hang_clk;   // events forever: real-time hang
    end
    initial begin
        #1;
        wait (hang_clk === 1'b1 && hang_clk === 1'b0);  // never true
        $display("TB_HANG_PASS");
        $finish;
    end
endmodule
'@ | Set-Content -Path $hangTb -Encoding ASCII

try {
    # powershell.exe -File array parameters must be comma-joined single tokens.
    & powershell -ExecutionPolicy Bypass -File scripts\ci_regression.ps1 -SimTimeoutS $HangTimeoutS -RtlList "src\rtl\common\crc16_mcrf4xx.v" -TbList "$hangTb,sim\tb\tb_crc16.v" -TbNameList "tb_ci_hang_tmp,tb_crc16"
    $code = $LASTEXITCODE
} finally {
    Remove-Item $hangTb -Force -ErrorAction SilentlyContinue
    if (Test-Path $hangTb) { Write-Host "[WARN] hang TB cleanup failed: $hangTb still present" }
    Remove-Item xsim.dir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item *.pb -Force -ErrorAction SilentlyContinue
}
Write-Host ""
Write-Host "EXPERIMENT EXIT CODE: $code (expected 1: hang TB fails, tb_crc16 passes)"
exit $code