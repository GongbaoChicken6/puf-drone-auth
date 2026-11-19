[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ws = 'D:/puf-drone-auth/build/vitis_qspi3_192337/zc706_qspi/zynq_fsbl/ps7_init.c'
Write-Output ("workspace ps7_init exists: " + (Test-Path $ws))
$lines = Get-Content $ws
Write-Output "=== QSPI_REF_CTRL / APER / QSPI_RST in BUILT FSBL ps7_init ==="
foreach ($ln in $lines) {
  if ($ln -match 'MASKWRITE\(0XF8000158' -or $ln -match 'MASKWRITE\(0XF800012C' -or $ln -match 'MASKWRITE\(0XF800022C') { $ln.Trim() }
}
Write-Output "=== MIO writes summary ==="
$mio = @()
foreach ($ln in $lines) { if ($ln -match 'MASKWRITE\(0XF80007') { $mio += $ln.Trim() } }
Write-Output ("MIO write lines: " + $mio.Count)
$mio | Select-Object -First 14
Write-Output "=== fsbl.elf ==="
Get-Item 'D:/puf-drone-auth/build/vitis_qspi3_192337/zc706_qspi/zynq_fsbl/build/fsbl.elf' | ForEach-Object { "{0}  {1}B" -f $_.FullName, $_.Length }
