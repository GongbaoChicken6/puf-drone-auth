# demo_two_board.ps1 -- 2026-11-16 双板演示一键启动（PASS板B + REJECT板A）
# 用法: powershell -ExecutionPolicy Bypass -File D:\puf-drone-auth\build\tcl\demo_two_board.ps1
$ErrorActionPreference = 'Continue'
$repo = 'D:\puf-drone-auth'
Set-Location $repo
Write-Host '[1/5] 清理残留进程'
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'web_bridge|start_bridge|watch_and_select|sse_short|auto_select' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Stop-Process -Name hw_server,cs_server,vivado -Force -ErrorAction SilentlyContinue
Start-Sleep 2
Write-Host '[2/5] 启动 hw_server'
Start-Process -FilePath 'D:\vivado\2026.1\Vitis\bin\hw_server.bat' -WindowStyle Hidden
Start-Sleep 5
Write-Host '[3/5] 烧写双板 bit'
$vivado = 'D:\vivado\2026.1\Vivado\bin\vivado.bat'
$tcl = Join-Path $repo 'build\tcl\program_zc706.tcl'
$okA = $false; $okB = $false
foreach ($b in @(@{N='板A';Bit=(Join-Path $repo 'build\board_zc706\w3_top_zc706.bit');SN='210251A0195C'}, @{N='板B';Bit=(Join-Path $repo 'build\board_zc706_seed2\w3_top_zc706_seed2.bit');SN='210251A04F2C'})) {
  $out = & $vivado -mode batch -nojournal -nolog -notrace -source $tcl -tclargs $b.Bit $b.SN 2>&1 | Out-String
  if ($out -match 'PROGRAM_OK') { Write-Host ($b.N + ': PROGRAM_OK') -ForegroundColor Green; if ($b.N -eq '板A') { $okA = $true } else { $okB = $true } }
  else { Write-Host ($b.N + ': FAILED') -ForegroundColor Red }
}
Stop-Process -Name hw_server -Force -ErrorAction SilentlyContinue
Start-Sleep 1
Write-Host '[4/5] 探测串口'
$ports = [System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object
Write-Host ('可用: ' + ($ports -join ', '))
$comA = 'COM6'; $comB = 'COM9'
foreach ($p in $ports) {
  $dev = Get-PnpDevice -Class Ports -ErrorAction SilentlyContinue | Where-Object { $_.FriendlyName -match [regex]::Escape($p) }
  if ($dev.FriendlyName -match 'USB 串行设备|LinkE') { $comA = $p }
  if ($dev.FriendlyName -match 'CH340') { if ($p -ne $comA) { $comB = $p } }
}
Write-Host ('板A: ' + $comA + ' / 板B: ' + $comB)
Write-Host '[5/5] 启动桥(数据目录=仓库data,带已录入的板B模板)'
$args = @('-u','D:\puf-drone-auth\build\tcl\start_bridge2.py')
Start-Process -FilePath python -ArgumentList $args -WindowStyle Hidden -RedirectStandardOutput (Join-Path $repo 'build\logs\bridge_demo_live.log') -RedirectStandardError (Join-Path $repo 'build\logs\bridge_demo_live.err.log')
Start-Sleep 7
foreach ($tid in 1,2) {
  try { Invoke-RestMethod -Uri 'http://127.0.0.1:8642/api/setkey' -Method Post -ContentType 'application/json' -Body ('{"terminal_id":' + $tid + ',"key_hex":"0001020308090a0b10111213"}') | Out-Null; Write-Host ('setkey tid=' + $tid + ' OK') } catch { Write-Host ('setkey tid=' + $tid + ' 失败') }
}
try {
  $s = Invoke-RestMethod -Uri 'http://127.0.0.1:8642/api/status' -TimeoutSec 5
  Write-Host ('模板: ' + (($s.templates | ForEach-Object { $_.terminal_id + ':' + $_.n_pairs }) -join ', '))
  Write-Host ('池: ' + (($s.pools | ForEach-Object { $_.terminal_id + ':' + $_.remaining }) -join ', '))
  $q = Invoke-RestMethod -Uri 'http://127.0.0.1:8642/api/access/queue' -TimeoutSec 5
  Write-Host ('闸门: enabled=' + $q.enabled)
  Write-Host ''
  Write-Host '浏览器打开: http://127.0.0.1:8642/console.html' -ForegroundColor Cyan
  Write-Host '演示: 板A SW13->SW7 / 板B SW13->SW7 -> 弹窗选 Board A(REJECT) -> 选 Board B(PASS)'
  if (-not ($okA -and $okB)) { Write-Host '注意: 有板子烧写失败,检查JTAG/上电' -ForegroundColor Yellow }
} catch { Write-Host '桥自检失败,查看 build/logs/bridge_demo_live.err.log' -ForegroundColor Red }