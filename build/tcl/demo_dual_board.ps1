# Dual-board JTAG demo one-shot script (2026-11-16)
# Usage: powershell -File build/tcl/demo_dual_board.ps1
$ErrorActionPreference = 'Continue'

Write-Output '=== 0. Clean old processes ==='
Stop-Process -Name hw_server,cs_server -Force -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'web_bridge' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep 2

Write-Output '=== 1. Start hw_server ==='
Start-Process -FilePath 'D:\vivado\2026.1\Vitis\bin\hw_server.bat' -WindowStyle Hidden
Start-Sleep 4

Write-Output '=== 2. Burn board A ==='
& 'D:\vivado\2026.1\Vivado\bin\vivado.bat' -mode batch -source D:\puf-drone-auth\build\tcl\program_zc706.tcl -tclargs D:\puf-drone-auth\build\board_zc706\w3_top_zc706.bit 210251A0195C -log D:\puf-drone-auth\build\logs\demo_burnA.log -journal D:\puf-drone-auth\build\logs\demo_burnA.jou -notrace
$bA = Select-String -Path D:\puf-drone-auth\build\logs\demo_burnA.log -Pattern 'PROGRAM_OK' -Quiet
Write-Output "Board A: $(if ($bA) {'PROGRAM_OK'} else {'FAILED'})"

Write-Output '=== 3. Burn board B ==='
& 'D:\vivado\2026.1\Vivado\bin\vivado.bat' -mode batch -source D:\puf-drone-auth\build\tcl\program_zc706.tcl -tclargs D:\puf-drone-auth\build\board_zc706_seed2\w3_top_zc706_seed2.bit 210251A04F2C -log D:\puf-drone-auth\build\logs\demo_burnB.log -journal D:\puf-drone-auth\build\logs\demo_burnB.jou -notrace
$bB = Select-String -Path D:\puf-drone-auth\build\logs\demo_burnB.log -Pattern 'PROGRAM_OK' -Quiet
Write-Output "Board B: $(if ($bB) {'PROGRAM_OK'} else {'FAILED'})"

if (-not ($bA -and $bB)) { Write-Output 'BURN FAILED'; exit 1 }

Write-Output '=== 4. Detect serial ports ==='
$ports = [System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object
Write-Output "Available: $($ports -join ', ')"
$comA = 'COM6'
$comB = 'COM11'
foreach ($p in $ports) {
  $dev = Get-PnpDevice -Class Ports -ErrorAction SilentlyContinue | Where-Object { $_.FriendlyName -match [regex]::Escape($p) }
  if ($dev.FriendlyName -match 'LinkE|CP210') { $comA = $p }
  if ($dev.FriendlyName -match 'CH340') { $comB = $p }
}
Write-Output "Board A UART: $comA"
Write-Output "Board B UART: $comB"

Write-Output '=== 5. Start web bridge (dual serial + access gate) ==='
$proc = Start-Process -FilePath python -ArgumentList @('D:\puf-drone-auth\web\bridge\web_bridge.py', "--serial-multi=$comA,$comB", '--access-gate', '--access-label', '1=Board A,2=Board B', '--tid-port', "1=$comA,2=$comB", '--data-dir', 'D:\puf-drone-auth\data', '--port', '8642') -PassThru -WindowStyle Minimized
Start-Sleep 3
Write-Output "Bridge PID: $($proc.Id)"
Write-Output 'Console URL: http://127.0.0.1:8642/console.html'
Write-Output 'Demo steps: press SW7 on both boards -> popup shows 2 machines -> select one'

Write-Output 'DEMO_READY'
