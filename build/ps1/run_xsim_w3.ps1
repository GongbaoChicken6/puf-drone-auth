# W3 all protocol modules simulation (6 TB suites)
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..\..")
$vivado = "D:\vivado\2026.1\Vivado\bin"

$rtl = @("src\rtl\common\crc16_mcrf4xx.v", "src\rtl\common\mavlink_frame.v",
         "src\rtl\common\frame_parser.v", "src\rtl\common\byte_fifo.v",
         "src\rtl\common\uart_tx.v", "src\rtl\common\uart_rx.v",
         "src\rtl\w3_protocol\terminal_fsm.v")
$tbs = @("sim\tb\tb_crc16.v", "sim\tb\tb_mavlink_frame.v", "sim\tb\tb_frame_parser.v",
         "sim\tb\tb_byte_fifo.v", "sim\tb\tb_uart_tx.v", "sim\tb\tb_terminal_fsm.v")
& "$vivado\xvlog.bat" @rtl @tbs 2>&1 | Select-String "ERROR" | ForEach-Object { $_.Line }
if ($LASTEXITCODE -ne 0) { Write-Host "XVLOG FAILED"; exit 1 }

& "$vivado\xelab.bat" -debug typical tb_crc16 -s s1 2>&1 | Out-Null
& "$vivado\xelab.bat" -debug typical tb_mavlink_frame -s s2 2>&1 | Out-Null
& "$vivado\xelab.bat" -debug typical tb_frame_parser -s s3 2>&1 | Out-Null
& "$vivado\xelab.bat" -debug typical tb_byte_fifo -s s4 2>&1 | Out-Null
& "$vivado\xelab.bat" -debug typical tb_uart_tx -s s5 2>&1 | Out-Null
& "$vivado\xelab.bat" -debug typical tb_terminal_fsm -s s6 2>&1 | Out-Null

& "$vivado\xsim.bat" s1 -runall --onerror quit 2>&1 | Select-String "TB_" | ForEach-Object { $_.Line }
& "$vivado\xsim.bat" s2 -runall --onerror quit 2>&1 | Select-String "TB_" | ForEach-Object { $_.Line }
& "$vivado\xsim.bat" s3 -runall --onerror quit 2>&1 | Select-String "TB_" | ForEach-Object { $_.Line }
& "$vivado\xsim.bat" s4 -runall --onerror quit 2>&1 | Select-String "TB_" | ForEach-Object { $_.Line }
& "$vivado\xsim.bat" s5 -runall --onerror quit 2>&1 | Select-String "TB_" | ForEach-Object { $_.Line }
& "$vivado\xsim.bat" s6 -runall --onerror quit 2>&1 | Select-String "TB_" | ForEach-Object { $_.Line }

