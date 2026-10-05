
$ErrorActionPreference = 'Continue'
Set-Location "$env:TEMP\w2_xvlog"
& 'D:\vivado\2026.1\Vivado\bin\xsim.bat' tb_cd_sim -R
Write-Output "XSIM_EXIT=$LASTEXITCODE"
