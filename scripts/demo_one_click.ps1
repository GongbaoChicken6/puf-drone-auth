# demo_one_click.ps1 -- N12(finals-demo) 一键启动:烧板→串口识别→链路自检→起桥(闸门开)→补密钥→模板就绪→开前端
# 终态:板子直接按 SW13(如非空闲)→ SW7,前端弹出"待接入 板A",点"开始验证"即播五帧动画。
# 用法:
#   .\scripts\demo_one_click.ps1                    # 全自动
#   .\scripts\demo_one_click.ps1 -SerialPort COM6   # 显式指定串口
#   .\scripts\demo_one_click.ps1 -NoBurn            # 跳过JTAG烧写(板已烧且未断电)
#   .\scripts\demo_one_click.ps1 -SerialPort none   # 彩排(loopback,无硬件)
#   .\scripts\demo_one_click.ps1 -Enroll            # 强制重新录入tid1模板
# 持久演示沙箱: .demo_state\ (gitignored) 模板/池跨重启保留。
param(
    [ValidatePattern('^(auto|none|COM\d+)$')]
    [string]$SerialPort = 'auto',
    [ValidateRange(1, 65535)]
    [int]$Port = 8642,
    [switch]$NoBurn,
    [switch]$NoLinkTest,
    [switch]$NoBrowser,
    [switch]$Enroll
)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$KEY_HEX = '0001020308090a0b10111213'
$SN_A   = '210251A0195C'

function Step([int]$n, [string]$msg) { Write-Host ('[{0}/7] {1}' -f $n, $msg) -ForegroundColor Cyan }
function Ok([string]$msg)  { Write-Host "      $msg" -ForegroundColor Green }
function Warn([string]$msg){ Write-Host "      $msg" -ForegroundColor Yellow }
function Die([string]$msg) {
    Write-Host "[demo_one_click] 失败: $msg" -ForegroundColor Red
    try {
        Add-Type -AssemblyName System.Windows.Forms | Out-Null
        [System.Windows.Forms.MessageBox]::Show($msg, '一键启动失败', 'OK', 'Error') | Out-Null
    } catch { }
    exit 1
}

# ---------- [1/7] 残留清理 ----------
Step 1 '清理残留进程'
Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'web_bridge\.py' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Ok "已杀残留桥 pid=$($_.ProcessId)" }
Get-Process hw_server -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 600

# ---------- [2/7] 串口识别 ----------
Step 2 '识别 PC 侧 HC-12 串口'
$com = $null
if ($SerialPort -eq 'none') {
    Ok '彩排模式(loopback):跳过串口/烧写/链路自检'
} else {
    if ($SerialPort -ne 'auto') { $script:CandList = @($SerialPort); Ok "显式指定: $SerialPort" }
    else {
        $cands = Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue |
            Where-Object { $_.DeviceID -match '^USB\\' -and $_.Name -match '\(COM\d+\)' }
        $ports = @($cands | ForEach-Object { if ($_.Name -match '(COM\d+)') { $Matches[1] } } | Select-Object -Unique)
        if ($ports.Count -ge 1) { $script:CandList = $ports; Ok "串口候选: $($ports -join ', ')(多个时由链路自检自动裁决)" }
        else { Die '未探测到 USB 串口(扫描一切带COM号的USB设备,插哪个口/变几号都行)。检查: PC侧HC-12的USB转接板是否插好; 若COM号与蓝牙撞名(设备管理器改COM10)后重试' }
    }
}

# ---------- [3/7] JTAG 烧写(板A) ----------
Step 3 'JTAG 烧写板A(v4 bit + ARM 监视器)'
if ($SerialPort -eq 'none' -or $NoBurn) {
    Warn '跳过烧写(板子必须仍带电持有bit;断电过请去掉 -NoBurn)'
} else {
    $jtag = Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue |
        Where-Object { $_.DeviceID -match 'VID_0403' -or $_.Name -match 'Digilent|JTAG' }
    if (-not $jtag) {
        Warn 'JTAG 不在线 -- 跳过烧写;若板子断电过bit已丢,链路自检会暴露'
    } else {
        $vivado = 'D:\vivado\2026.1\Vivado\bin\vivado.bat'
        $tcl = Join-Path $repo 'build\tcl\program_zc706.tcl'
        $bitA = Join-Path $repo 'build\board_zc706_arm_v4\w3_top_zc706.bit'
        $out = & $vivado -mode batch -nojournal -nolog -notrace -source $tcl -tclargs $bitA $SN_A 2>&1 | Out-String
        if ($out -match 'PROGRAM_OK') { Ok '板A bit PROGRAM_OK' }
        else { Warn '板A 烧写未确认(板子可能未上电) -- 继续,由链路自检裁决' }
        Get-Process hw_server -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        $elf = Join-Path $repo 'sw\arm_fan\arm_fan.elf'
        $atcl = Join-Path $repo 'sw\arm_fan\arm_fan.tcl'
        if ((Test-Path $elf) -and (Test-Path $atcl)) {
            $aout = & 'D:\vivado\2026.1\Vitis\bin\xsdb.bat' $atcl 2>&1 | Out-String
            if ($aout -match 'ARM_FAN_OK') { Ok 'ARM 监视器 ELF ARM_FAN_OK' } else { Warn 'ELF 未加载(不阻断)' }
        }
    }
}

# ---------- [4/7] 无线链路自检 ----------
Step 4 'AUTH_POLL 链路自检(PC - HC-12 - 板A)'
$com = $null
if ($SerialPort -eq 'none') {
    Warn '跳过链路自检'
    $com = 'LOOPBACK'
} elseif ($NoLinkTest) {
    if ($CandList.Count -gt 1) { Die "多个串口候选($($CandList -join ', '))且 -NoLinkTest 跳过自检,无法裁决 -- 去掉 -NoLinkTest 或 -SerialPort COMx 指定" }
    $com = $CandList[0]
    Warn "跳过链路自检(使用 $com)"
} else {
    $py = @'
import sys, time
sys.path.insert(0, r'REPOSTR')
import serial
from src.python.server.protocol import HFIDAProtocol
P = HFIDAProtocol()
poll = P.pack(P.MSG_AUTH_POLL, terminal_id=1, nonce=int(time.time()) & 0xFFFF)
rx = b''
for attempt in (1, 2):
    with serial.Serial(PORTSTR, 115200, timeout=0.2) as s:
        time.sleep(0.3); s.reset_input_buffer(); s.write(poll); s.flush()
        t0 = time.time()
        while time.time() - t0 < 2.5:
            n = s.in_waiting
            if n: rx += s.read(n)
            else: time.sleep(0.02)
        if rx.startswith(b'\xfd'): break
mid, fl = P.parse(rx)
print('LINK_OK', P.msg_name(mid), 'tid', fl.get('terminal_id'))
'@
    $tmp = Join-Path $env:TEMP 'puf_linktest.py'
    $fails = @()
    foreach ($c in $CandList) {
        Set-Content -Encoding utf8 $tmp ($py.Replace('PORTSTR', ("'" + $c + "'")).Replace('REPOSTR', $repo))
        $r = & python $tmp 2>&1 | Out-String
        if ($r -match 'LINK_OK ACCESS_REQUEST') { $com = $c; Ok ("板A 经 $c 应答正常: " + ($r -replace "\r?\n", ' ').Trim()); break }
        else { $fails += "$c 无应答"; Warn "$c 无应答,试下一个" }
    }
    Remove-Item $tmp -ErrorAction SilentlyContinue
    if (-not $com) { Die ("全部候选链路不通: " + ($fails -join '; ') + ' 排查: 板子12V/DS22亮; SW11=00000且已烧bit; 两侧HC-12同C001/115200; 板侧HC-12供电共地') }
}

# ---------- [5/7] 演示沙箱(持久) ----------
Step 5 '准备演示沙箱(.demo_state, 模板跨启动保留)'
$state = Join-Path $repo '.demo_state'
if (-not (Test-Path (Join-Path $state 'templates'))) {
    New-Item -ItemType Directory -Path (Join-Path $state 'templates') -Force | Out-Null
    $legacy = 'C:\Users\17395\AppData\Local\Temp\puf_demo_serial_20261118_2302'
    if (Test-Path (Join-Path $legacy 'templates\templates.json')) {
        Copy-Item -Recurse -Force "$legacy\*" $state
        Ok '已从昨晚沙箱播种(tid1 模板100对)'
    } else { Ok '新建空沙箱(首次将自动录入)' }
} else { Ok '沿用现有 .demo_state(模板保留)' }

# ---------- [6/7] 起桥 ----------
Step 6 '启动 web 桥(真串口 + 接入闸门)'
$bargs = @('-u','web/bridge/web_bridge.py','--repo-root','.','--data-dir',$state,'--port',"$Port")
if ($SerialPort -ne 'none') { $bargs += @('--serial-port', $com) }
$bargs += @('--access-gate','--access-label','1=板A,2=板B')
if (-not $NoBrowser) { $bargs += '--open' }
$log = Join-Path $state ('bridge_' + (Get-Date -Format HHmmss) + '.log')
$proc = Start-Process -FilePath 'python' -ArgumentList $bargs -WorkingDirectory $repo -RedirectStandardOutput $log -RedirectStandardError ($log + '.err') -PassThru -WindowStyle Hidden
$up = $false
foreach ($i in 1..20) {
    Start-Sleep -Seconds 1
    if ($proc.HasExited) { Die "桥提前退出(exit=$($proc.ExitCode)); 日志: $log.err" }
    foreach ($p in $Port..($Port + 5)) {
        try {
            $r = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$p/api/status" -TimeoutSec 2
            if ($r.StatusCode -eq 200) { $script:BoundPort = $p; $up = $true; break }
        } catch { }
    }
    if ($up) { break }
}
if (-not $up) { Die "桥 20s 未就绪; 日志: $log.err" }
if (-not $BoundPort) { $BoundPort = $Port }
Ok "桥就绪: http://127.0.0.1:$BoundPort/console.html (pid $($proc.Id))"

# ---------- [7/7] 补密钥 + 模板就绪 ----------
Step 7 '补板内密钥 + 确认 tid1 模板'
if ($SerialPort -ne 'none') {
    try {
        $k = Invoke-WebRequest -UseBasicParsing -Method POST -ContentType 'application/json' -Body ('{"terminal_id":1,"key_hex":"' + $KEY_HEX + '"}') "http://127.0.0.1:$Port/api/setkey" -TimeoutSec 5
        Ok "setkey tid1: $($k.Content)"
    } catch { Warn 'setkey 失败(板子不在? 已带电密钥不受影响)' }
}
$hasTpl = $false
try {
    $st = (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/api/status" -TimeoutSec 3).Content | ConvertFrom-Json
    $hasTpl = [bool]($st.templates | Where-Object { "$($_.terminal_id)" -eq '1' -and $_.n_pairs -ge 30 })
} catch { }
if (-not $hasTpl -or $Enroll) {
    if ($SerialPort -eq 'none') { Warn '彩排模式: 跳过录入' }
    else {
        Warn 'tid1 模板缺失/强制录入 -> 自动录入(约2分钟,请勿按板子按键; 板子须空闲,必要时先按SW13)'
        try {
            Invoke-WebRequest -UseBasicParsing -Method POST -ContentType 'application/json' -Body '{"terminal_id":1,"n":100,"measurements":3}' "http://127.0.0.1:$Port/api/enroll_real" -TimeoutSec 15 | Out-Null
        } catch { }
        $done = $false
        foreach ($i in 1..90) {
            Start-Sleep -Seconds 3
            try {
                $st = (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/api/status" -TimeoutSec 3).Content | ConvertFrom-Json
                if ($st.templates | Where-Object { "$($_.terminal_id)" -eq '1' -and $_.n_pairs -ge 30 }) { $done = $true; break }
            } catch { }
            Write-Host '.' -NoNewline
        }
        Write-Host ''
        if ($done) { Ok '录入完成: tid1 模板就绪' } else { Die '录入超时(4.5分钟)。确认板子空闲(SW13)后加 -Enroll 重跑' }
    }
} else { Ok 'tid1 模板在位(无需录入)' }

Write-Host ''
Write-Host '=================================================' -ForegroundColor Green
Write-Host " 一键就绪: http://127.0.0.1:$Port/console.html" -ForegroundColor Green
if ($SerialPort -eq 'none') {
    Write-Host ' [彩排模式] 前端为 loopback 演示, 无真板' -ForegroundColor Yellow
} else {
    Write-Host ' 板子操作: 按 SW13(仅当非空闲) -> 按 SW7' -ForegroundColor Green
    Write-Host ' 前端弹"待接入 板A" -> 点【开始验证】-> 五帧动画 -> PASS' -ForegroundColor Green
    Write-Host ' 伪基站演示: 攻击PC 点按钮 -> 本机弹全屏红色警报' -ForegroundColor Green
}
Write-Host " 桥日志: $log" -ForegroundColor Gray
Write-Host '=================================================' -ForegroundColor Green
exit 0
