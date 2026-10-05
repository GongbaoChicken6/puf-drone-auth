# One-click build + (optionally) program board & measure VIO
# Usage: .\build\ps1\run_build.ps1 [-Measure]
# All paths are now in the project repo (D:\puf-drone-auth) - no Chinese path staging needed.
param(
    [string]$Part = "xc7z020clg484-1",
    [switch]$Measure,
    [string]$RepoRoot = "D:\puf-drone-auth"
)

$vivado = "D:\vivado\2026.1\Vivado\bin\vivado.bat"
$srcDir = "$RepoRoot\src\rtl\w1_ratio"
$tclDir = "$RepoRoot\build\tcl"
$outDir = "D:\fpga_work\w1_auto"

Write-Host "=== PUF Drone Auth Build ==="
Write-Host "Repo root: $RepoRoot"
Write-Host "Source:    $srcDir"
Write-Host "Part:      $Part"
Write-Host ""

# Build bitstream
& $vivado -mode batch -nolog -nojournal -notrace -source "$tclDir\build_w1.tcl" -tclargs $Part $outDir $srcDir

if ($LASTEXITCODE -ne 0) {
    Write-Host "BUILD FAILED (exit $LASTEXITCODE)"
    exit $LASTEXITCODE
}

Write-Host "BUILD OK: $outDir\w1_auto.runs\impl_1\ro_ratio_top.bit"

# Optionally program board and collect VIO readings
if ($Measure) {
    $bit = "$outDir\w1_auto.runs\impl_1\ro_ratio_top.bit"
    $csv = "$outDir\w1_readings.csv"
    & $vivado -mode batch -nolog -nojournal -notrace -source "$tclDir\measure_w1.tcl" -tclargs $bit 10 $csv
}
