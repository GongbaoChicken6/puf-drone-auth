[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Continue'
Write-Output '## E1 SHA256: factory vs workspaces (claim: all old FSBLs from factory no-QSPI XSA)'
$files = @(
  'D:/vivado/2026.1/data/embeddedsw/lib/spm_templates/SPM_ZC_706_HwPlatform/system.xsa',
  'D:/puf-drone-auth/build/vitis_103840/zc706/hw/system.xsa',
  'D:/puf-drone-auth/build/vitis_qspi_173620/zc706_qspi/hw/system.xsa',
  'D:/puf-drone-auth/build/qspi_xsa/zc706_qspi.xsa',
  'D:/puf-drone-auth/build/qspi_xsa_v3/zc706_qspi_v3.xsa'
)
foreach ($f in $files) {
  if (Test-Path $f) { $h = (Get-FileHash $f -Algorithm SHA256).Hash.ToLower(); "{0}  {1}B  {2}" -f $h.Substring(0,16), (Get-Item $f).Length, $f } else { "MISSING  $f" }
}
Write-Output '## E2 v2 log: XSA degenerate root error (claim: FCLK->GP0_ACLK)'
Select-String -Path 'D:/puf-drone-auth/build/logs/qspi_xsa_v2.log' -Pattern 'BD 41-758|41-1031|handoff|XSA_SIZE|XSA_SENTINEL|VALIDATE' | ForEach-Object { $_.Line.Trim() } | Select-Object -First 10
Write-Output '## E3 v3 log: fixed chain'
Select-String -Path 'D:/puf-drone-auth/build/logs/qspi_xsa_v3.log' -Pattern 'VALIDATE_OK|GENERATE_OK|XSA_SIZE|XSA_SENTINEL|hw_handoff|XSA_WRITE_OK' | ForEach-Object { $_.Line.Trim() } | Select-Object -First 10
Write-Output '## E4 vitis_qspi_173620 FSBL ps7_init MIO0-13 (claim: also no-QSPI)'
$p = 'D:/puf-drone-auth/build/vitis_qspi_173620/zc706_qspi/zynq_fsbl/ps7_init.c'
$out = @(); foreach ($ln in (Get-Content $p)) { if ($ln -match 'MASKWRITE\(0XF80007') { $out += $ln.Trim() } }
$out | Select-Object -First 14
Write-Output '## E5 vitis_qspi3_192337 (good) FSBL ps7_init MIO0-13'
$p2 = 'D:/puf-drone-auth/build/vitis_qspi3_192337/zc706_qspi/zynq_fsbl/ps7_init.c'
$out2 = @(); foreach ($ln in (Get-Content $p2)) { if ($ln -match 'MASKWRITE\(0XF80007') { $out2 += $ln.Trim() } }
$out2 | Select-Object -First 14
Write-Output '## E6 old main.c patch evidence (claim: wrong 0xB87 patch)'
Select-String -Path 'D:/puf-drone-auth/build/vitis_103840/zc706/zynq_fsbl/main.c' -Pattern 'B87|QSPI_1 uses|add ALL pins' | ForEach-Object { ("L" + $_.LineNumber + ": " + $_.Line.Trim()) } | Select-Object -First 8
Write-Output '## E7 artifacts'
foreach ($f in @('D:/puf-drone-auth/build/vitis_qspi3_192337/zc706_qspi/zynq_fsbl/build/fsbl.elf','D:/puf-drone-auth/build/BOOT_v3.bin','D:/puf-drone-auth/build/BOOT_B_v3.bin')) {
  if (Test-Path $f) { "{0}B  {1}  {2}" -f (Get-Item $f).Length, (Get-Item $f).LastWriteTime, $f } else { "MISSING $f" }
}
Write-Output '## E8 live-register logs on disk (claim: FSBL applied on hardware)'
foreach ($lg in @('D:/puf-drone-auth/build/logs/qspi_regs_live2.log','D:/puf-drone-auth/build/logs/qspi_probe2.log')) {
  if (Test-Path $lg) {
    "--- $lg ---"
    $raw = [System.IO.File]::ReadAllBytes($lg)
    $t = [System.Text.Encoding]::Unicode.GetString($raw) -replace ([string][char]0), ''
    if ($t -notmatch 'MIO_PIN_00') { $t = [System.Text.Encoding]::UTF8.GetString($raw) }
    ($t -split [Environment]::NewLine) | Where-Object { $_ -match 'APER|MIO |QSPI_REF|QSPI_CFG|IRQ_STAT|0xF8000700|:   0000' } | Select-Object -First 24
  } else { "MISSING $lg" }
}
Write-Output '## E9 program_flash B log key lines (claim: FSBL ran, u-boot probe failed)'
Select-String -Path 'D:/puf-drone-auth/build/logs/program_flash_B_v3.log' -Pattern 'Running FSBL|Finished running FSBL|BOOT_MODE|sf probe|Failed to initialize|ARM_CLK_CTRL|IO_PLL' | ForEach-Object { $_.Line.Trim() } | Select-Object -First 12
