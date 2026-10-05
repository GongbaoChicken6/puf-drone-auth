
$ErrorActionPreference = 'Continue'
New-Item -ItemType Directory -Force -Path "$env:TEMP\w2_xvlog" | Out-Null
Set-Location "$env:TEMP\w2_xvlog"
$files = @(
  'D:\puf-drone-auth\src\rtl\common\uart_tx.v',
  'D:\puf-drone-auth\src\rtl\common\uart_rx.v',
  'D:\puf-drone-auth\src\rtl\w2_array\ro_array.v',
  'D:\puf-drone-auth\src\rtl\w2_array\challenge_decode.v',
  'D:\puf-drone-auth\src\rtl\w2_array\w2_top.v',
  'D:\puf-drone-auth\sim\tb\tb_challenge_decode.v'
)
& 'D:\vivado\2026.1\Vivado\bin\xvlog.bat' -work work @files
Write-Output "XVLOG_EXIT=$LASTEXITCODE"
