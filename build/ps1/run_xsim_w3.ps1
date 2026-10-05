# W3 协议模块仿真（CRC + 帧构造器全部用例）
# 用法: .\build\ps1\run_xsim_w3.ps1
$ErrorActionPreference = "Continue"
Set-Location "D:\puf-drone-auth"
$vivado = "D:\vivado\2026.1\Vivado\bin"

& "$vivado\xvlog.bat" src\rtl\common\crc16_mcrf4xx.v src\rtl\common\mavlink_frame.v sim\tb\tb_crc16.v sim\tb\tb_mavlink_frame.v 2>&1 | Select-String "ERROR" | ForEach-Object { $_.Line }
if ($LASTEXITCODE -ne 0) { Write-Host "XVLOG FAILED"; exit 1 }

& "$vivado\xelab.bat" -debug typical tb_crc16 -s tb_crc16_sim 2>&1 | Select-String "ERROR" | ForEach-Object { $_.Line }
& "$vivado\xelab.bat" -debug typical tb_mavlink_frame -s tb_mf_sim 2>&1 | Select-String "ERROR" | ForEach-Object { $_.Line }

& "$vivado\xsim.bat" tb_crc16_sim -runall --onerror quit 2>&1 | Select-String "PASS|FAIL" | ForEach-Object { $_.Line }
& "$vivado\xsim.bat" tb_mf_sim -runall --onerror quit 2>&1 | Select-String "PASS|FAIL" | ForEach-Object { $_.Line }