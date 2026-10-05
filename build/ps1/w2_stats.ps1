
$files = @(
  'D:\puf-drone-auth\src\rtl\w2_array\ro_array.v',
  'D:\puf-drone-auth\src\rtl\w2_array\challenge_decode.v',
  'D:\puf-drone-auth\src\rtl\w2_array\w2_top.v',
  'D:\puf-drone-auth\src\rtl\common\uart_tx.v',
  'D:\puf-drone-auth\src\rtl\common\uart_rx.v',
  'D:\puf-drone-auth\src\rtl\w2_array\w2_waiver.xdc',
  'D:\puf-drone-auth\sim\tb\tb_challenge_decode.v'
)
foreach ($f in $files) {
  $bytes = [System.IO.File]::ReadAllBytes($f)
  $hasBom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
  $lines = (Get-Content $f).Count
  Write-Output ("{0}  lines={1}  BOM={2}" -f $f, $lines, $hasBom)
}
Move-Item 'D:\puf-drone-auth\build\run_xvlog_w2.ps1' 'D:\puf-drone-auth\build\ps1\run_xvlog_w2.ps1' -Force
Move-Item 'D:\puf-drone-auth\build\run_xsim_w2.ps1' 'D:\puf-drone-auth\build\ps1\run_xsim_w2.ps1' -Force
Write-Output "moved helper scripts to build\ps1\"
