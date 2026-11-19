[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
foreach ($lg in @('D:/puf-drone-auth/build/logs/qspi_regs_live2.log','D:/puf-drone-auth/build/logs/qspi_probe2.log')) {
  Write-Output "===== $lg ====="
  $raw = [System.IO.File]::ReadAllBytes($lg)
  $t16 = [System.Text.Encoding]::Unicode.GetString($raw)
  $t = $t16 -replace ('[' + [char]0 + '-' + [char]8 + [char]11 + [char]12 + [char]14 + '-' + [char]31 + ']'), ''
  if ($t -notmatch 'F8000') { $t = [System.Text.Encoding]::UTF8.GetString($raw) }
  $t = $t -replace ('\s+'), ' '
  foreach ($pat in @('F8000158','F800012C','F8000700','F8000704','F8000724','F8000734','E000D000','E000D004','QSPI_REF','APER','MIO_PIN')) {
    $ms = [regex]::Matches($t, ('.{0,26}' + $pat + '.{0,30}'))
    foreach ($m in ($ms | Select-Object -First 3)) { $m.Value.Trim() }
  }
}
