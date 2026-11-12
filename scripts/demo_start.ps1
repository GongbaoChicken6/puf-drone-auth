# demo_start.ps1 -- N9(finals-demo) 一键启动:杀残留桥 -> fresh 沙箱 -> 起桥 -> 自检
# 用法:
#   .\scripts\demo_start.ps1                # 自动探测串口(CH340/LinkE);找不到则回退 loopback
#   .\scripts\demo_start.ps1 -SerialPort COM9   # 指定串口
#   .\scripts\demo_start.ps1 -SerialPort none   # 强制 loopback 演示模式
#   .\scripts\demo_start.ps1 -NoBrowser         # 不自动开浏览器
# 铁律5:--data-dir 永远指向新建空沙箱,绝不碰仓库 data/
param(
    [string]$SerialPort = 'auto',
    [int]$Port = 8642,
    [switch]$NoBrowser,
    [switch]$StrictPort
)
$ErrorActionPreference = 'Stop'
# 控制台中文输出:统一 UTF-8(否则 GBK 终端下日志乱码)
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

# 1) 杀残留桥:按命令行特征匹配 web_bridge.py 的 python 进程
Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'web_bridge\.py' } |
    ForEach-Object {
        Write-Host "[demo_start] 终止残留桥 pid=$($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
Start-Sleep -Milliseconds 600

# 2) 串口探测(不硬编码:COM 号有漂移前科) —— CH340/LinkE/FTDI 特征
$portArg = ''
if ($SerialPort -eq 'auto') {
    $cand = Get-CimInstance Win32_PnPEntity |
        Where-Object { $_.Name -match 'COM\d' -and $_.Name -match 'CH340|CP210|FTDI|USB.*(Serial|UART)' } |
        ForEach-Object { if ($_.Name -match '(COM\d+)') { $Matches[1] } } | Select-Object -Unique
    if ($cand) {
        $p = @($cand)[0]
        Write-Host "[demo_start] 探测到串口候选: $($cand -join ', ') -> 使用 $p"
        $portArg = "--serial-port $p"
    } else {
        Write-Warning '[demo_start] 未探测到 USB 串口 -> 回退 loopback 演示模式'
    }
} elseif ($SerialPort -ne 'none') {
    $portArg = "--serial-port $SerialPort"
}

# 3) fresh 沙箱(铁律5)
$sandbox = Join-Path $env:TEMP ("puf_demo_start_" + (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $sandbox | Out-Null
Write-Host "[demo_start] 沙箱: $sandbox"

# 4) 起桥(默认 --open 自动开浏览器; --strict-port 需显式要求)
# 注意:不能用 $args —— 它是 PowerShell 自动变量,赋值会被吞
$bridgeArgs = @('web/bridge/web_bridge.py','--repo-root','.','--data-dir',$sandbox,
          '--port',"$Port")
if ($portArg) { $bridgeArgs += $portArg.Split(' ') | Where-Object { $_ } }
if (-not $NoBrowser) { $bridgeArgs += '--open' }
if ($StrictPort) { $bridgeArgs += '--strict-port' }
Write-Host "[demo_start] python $($bridgeArgs -join ' ')"
$log = Join-Path $sandbox 'bridge_stdout.log'
$proc = Start-Process -FilePath 'python' -ArgumentList $bridgeArgs -WorkingDirectory $repo `
    -RedirectStandardOutput $log -RedirectStandardError (Join-Path $sandbox 'bridge_stderr.log') `
    -PassThru -WindowStyle Hidden

# 5) 自检:15s 内 /api/status 必须 200(端口可能自愈顺延,按返回 URL 提示)
$ok = $false
foreach ($try in 1..15) {
    Start-Sleep -Seconds 1
    if ($proc.HasExited) { Write-Error "[demo_start] 桥进程提前退出(exit=$($proc.ExitCode)),日志: $log"; exit 1 }
    try {
        $r = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/api/status" -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $ok = $true; break }
    } catch { }
}
if (-not $ok) { Write-Error '[demo_start] 15s 内 /api/status 未就绪,查看沙箱日志'; exit 1 }
Write-Host ''
Write-Host '===============================================' -ForegroundColor Green
Write-Host " 桥已就绪: http://127.0.0.1:$Port/console.html" -ForegroundColor Green
Write-Host " 沙箱: $sandbox | pid: $($proc.Id)" -ForegroundColor Green
Write-Host '===============================================' -ForegroundColor Green
exit 0
