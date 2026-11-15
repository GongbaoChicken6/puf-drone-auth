# demo_start.ps1 -- N9(finals-demo) 一键启动:杀残留桥 -> fresh 沙箱 -> 起桥 -> 自检
# 用法:
#   .\scripts\demo_start.ps1                     # 自动探测串口;多候选时中止并要求显式指定
#   .\scripts\demo_start.ps1 -SerialPort COM9    # 指定串口
#   .\scripts\demo_start.ps1 -SerialPort none    # 强制 loopback 演示模式
#   .\scripts\demo_start.ps1 -NoBrowser          # 不自动开浏览器
# 铁律5:--data-dir 永远指向新建空沙箱,绝不碰仓库 data/
# 注意:本脚本按命令行特征杀 web_bridge python 进程,仅供演示机单人使用,
#      不要在共享机器/队友桥运行时执行。
param(
    [ValidatePattern('^(auto|none|COM\d+)$')]
    [string]$SerialPort = 'auto',
    [ValidateRange(1, 65535)]
    [int]$Port = 8642,
    [switch]$NoBrowser,
    [switch]$StrictPort
)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

# 2) JTAG 自动烧 bit（QSPI 替代方案——板子上电后自动加载最新 bitstream）
# 仅当板子通过 USB 连接时执行;找不到 JTAG 目标时跳过(不阻断启动)
if ($SerialPort -ne 'none') {
    Write-Host "[demo_start] JTAG 烧写双板 bit..."
    Get-Process hw_server -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
    $vivado = "D:\vivado\2026.1\Vivado\bin\vivado.bat"
    $tcl = Join-Path $repo "build\tcl\program_zc706.tcl"
    $bitA = Join-Path $repo "build\board_zc706\w3_top_zc706.bit"
    $bitB = Join-Path $repo "build\board_zc706_seed2\w3_top_zc706_seed2.bit"
    foreach ($board in @(
        @{ Name='板A'; Bit=$bitA; SN='210251A0195C' },
        @{ Name='板B'; Bit=$bitB; SN='210251A04F2C' }
    )) {
        if (-not (Test-Path $board.Bit)) { Write-Host "  $($board.Name): bit 不存在,跳过" -ForegroundColor Yellow; continue }
        Write-Host "  $($board.Name): 烧写 $($board.Bit)..."
        $out = & $vivado -mode batch -nojournal -nolog -notrace -source $tcl -tclargs $board.Bit $board.SN 2>&1 | Out-String
        if ($out -match 'PROGRAM_OK') {
            Write-Host "  $($board.Name): PROGRAM_OK" -ForegroundColor Green
        } else {
            Write-Host "  $($board.Name): JTAG 烧写失败(板子可能未连接),跳过" -ForegroundColor Yellow
        }
    }
    # 杀 hw_server 释放端口给串口用
    Get-Process hw_server -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}

# 3) fresh 沙箱(铁律5) —— 提前建,后续探测/自检日志都落这里
$sandbox = Join-Path $env:TEMP ("puf_demo_start_" + (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $sandbox | Out-Null
$probeLog = Join-Path $sandbox 'com_probe.log'
Write-Host "[demo_start] 沙箱: $sandbox"

function Fail([string]$msg) {
    # 设计 N9:失败弹窗 + 完整日志路径(弹窗失败回退控制台)
    Write-Host "[demo_start] 失败: $msg" -ForegroundColor Red
    try {
        Add-Type -AssemblyName System.Windows.Forms | Out-Null
        [System.Windows.Forms.MessageBox]::Show($msg, '演示启动失败', 'OK', 'Error') | Out-Null
    } catch { }
    exit 1
}

# 1) 杀残留桥:逐个报告成败,失败不静默(ar-silent-c1)
$killed = 0; $failed = 0
Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'web_bridge\.py' } |
    ForEach-Object {
        try {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
            $killed++
        } catch {
            $failed++
            Write-Warning "[demo_start] 杀不掉 pid=$($_.ProcessId): $($_.Exception.Message)"
        }
    }
if ($killed -gt 0) { Write-Host "[demo_start] 已终止残留桥 x$killed" }
if ($failed -gt 0) { Fail "有 $failed 个残留桥进程杀不掉(可能需管理员)。请手动结束 python 进程后重试。沙箱日志: $sandbox" }
Start-Sleep -Milliseconds 600
# 端口占用后验:仍被监听则明确报因(ar-silent-c1/defect-c1)
$occ = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($occ) {
    $opid = $occ.OwningProcess
    Fail "端口 $Port 仍被 pid=$opid 占用(非 web_bridge 残留,杀桥步骤管不到它)。请释放端口或用 -Port 换口。"
}

# 2) 串口探测:双源互核 + 候选落盘 + 多候选中止(ar-defect/spec/silent/test-c1)
$portArg = ''
if ($SerialPort -eq 'auto') {
    $wmi = Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match 'COM\d' -and $_.Name -match 'CH340|CP210|FTDI|USB.*(Serial|UART)' } |
        ForEach-Object { if ($_.Name -match '(COM\d+)') { $Matches[1] } } | Select-Object -Unique
    $dotnet = [System.IO.Ports.SerialPort]::GetPortNames() | Select-Object -Unique
    $cand = @($wmi)
    "WMI 候选: $($wmi -join ', ')" | Set-Content -Encoding utf8 $probeLog
    ".NET SerialPort 枚举: $($dotnet -join ', ')" | Add-Content -Encoding utf8 $probeLog
    if (-not $cand) {
        "WMI 无 USB 串口命中;.NET 枚举: $($dotnet -join ', ')(不自动绑定,防误绑主板原生 COM)" | Add-Content -Encoding utf8 $probeLog
        if ($dotnet) {
            Fail "未探测到 USB 特征串口(CH340/CP210/FTDI)。.NET 枚举到: $($dotnet -join ', ') —— 为防误绑主板原生 COM 口不自动绑定,请用 -SerialPort <COMx> 显式指定,或 -SerialPort none 进 loopback。候选已记录: $probeLog"
        }
    "候选日志: $probeLog" | Write-Host
    if ($cand.Count -gt 1) {
        Fail "探测到多个串口候选: $($cand -join ', ')。请用 -SerialPort <COMx> 显式指定(决赛双串口日必须显式)。候选已记录: $probeLog"
    }
    if ($cand) {
        $p = $cand[0]
        Write-Host "[demo_start] 唯一候选 -> 使用 $p"
        "选定: $p" | Add-Content -Encoding utf8 $probeLog
        $portArg = "--serial-port $p"
    } else {
        Write-Warning '[demo_start] 未探测到 USB 串口 -> 回退 loopback 演示模式'
        '未探测到串口,回退 loopback' | Add-Content -Encoding utf8 $probeLog
    }
} elseif ($SerialPort -ne 'none') {
    $portArg = "--serial-port $SerialPort"
}

# 4) 起桥
$bridgeArgs = @('web/bridge/web_bridge.py','--repo-root','.','--data-dir',$sandbox,
          '--port',"$Port")
if ($portArg) { $bridgeArgs += $portArg.Split(' ') | Where-Object { $_ } }
if (-not $NoBrowser) { $bridgeArgs += '--open' }
if ($StrictPort) { $bridgeArgs += '--strict-port' }
Write-Host "[demo_start] python $($bridgeArgs -join ' ')"
$log = Join-Path $sandbox 'bridge_stdout.log'
$errLog = Join-Path $sandbox 'bridge_stderr.log'
$proc = Start-Process -FilePath 'python' -ArgumentList $bridgeArgs -WorkingDirectory $repo `
    -RedirectStandardOutput $log -RedirectStandardError $errLog `
    -PassThru -WindowStyle Hidden

# 5) 自检:探测 $Port..$Port+5(桥默认自愈顺延),校验应答身份(ar-defect-c1)
$ok = $false; $actualPort = $null
foreach ($try in 1..15) {
    Start-Sleep -Seconds 1
    if ($proc.HasExited) {
        $tail = ''
        if (Test-Path $errLog) { $tail = (Get-Content $errLog -Tail 12 | Out-String) }
        Fail (@("桥进程提前退出(exit=$($proc.ExitCode))。stderr 尾部:`n$tail",
               "stdout: $log", "stderr: $errLog") -join "`n")
    }
    foreach ($p in ($Port)..($Port + 5)) {
        try {
            $r = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$p/api/status" -TimeoutSec 2
            if ($r.StatusCode -eq 200 -and $r.Headers['Content-Type'] -match 'json') {
                $ok = $true; $actualPort = $p; break
            }
        } catch { }
    }
    if ($ok) { break }
}
if (-not $ok) {
    $hint = if (-not $StrictPort) { '(桥默认自愈顺延最多 +5 已探测;若仍失败多为串口/防火墙)' } else { '' }
    Fail (@("15s 内 /api/status 未就绪 $hint", "stdout: $log", "stderr: $errLog") -join "`n")
}
if ($actualPort -ne $Port) {
    Write-Warning "[demo_start] 桥自愈顺延到端口 $actualPort(原 $Port 被占)"
}
Write-Host ''
Write-Host '===============================================' -ForegroundColor Green
Write-Host " 桥已就绪: http://127.0.0.1:$actualPort/console.html" -ForegroundColor Green
Write-Host " 沙箱: $sandbox | pid: $($proc.Id)" -ForegroundColor Green
Write-Host '===============================================' -ForegroundColor Green
exit 0
