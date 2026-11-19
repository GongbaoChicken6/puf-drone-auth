# demo_one_click.ps1 -- N12/N13(finals-demo) 一键启动 v3 (2026-11-19)
# 变更(N13):
#   1) 板A 烧 v4b(三键并联: SW7|SW8|SW9), 板B 烧 seed2b(差异化布局+三键)
#   2) 双串口自动归类: 逐口 AUTH_POLL 点名, 回谁 tid 就是谁(板A=COM6/板B=COM11 端口号变了也认)
#   3) 桥走 --serial-multi + --tid-port 路由; 单板自动降级
#   4) setkey tid1/tid2 双补; 模板缺失自动录入(A n=100 / B n=30, B池只有32格)
#   5) bit 清单防呆: .demo_state\bit_manifest.json 记录烧写 bit 的 sha256;
#      换 bit(重跑实现)会让 PUF 模板失效, 启动即告警, -Enroll 一键清模板重录
# 演示按键(决赛口径): 两块板都按 SW8(右) -- 板A SW7 触点已坏, 勿按
# 用法:
#   .\scripts\demo_one_click.ps1                # 全自动(烧双板+起桥+自检)
#   .\scripts\demo_one_click.ps1 -NoBurn        # 跳过JTAG烧写(板已带电持有新bit)
#   .\scripts\demo_one_click.ps1 -SerialPort none  # 彩排(loopback,无硬件)
#   .\scripts\demo_one_click.ps1 -Enroll        # 强制清模板重录(换过bit后用)
#   .\scripts\demo_one_click.ps1 -TidMap '1=COM6,2=COM11'  # 手动指定端口归属
param(
    [ValidatePattern('^(auto|none|COM\d+)$')]
    [string]$SerialPort = 'auto',
    [ValidateRange(1, 65535)]
    [int]$Port = 8642,
    [switch]$NoBurn,
    [switch]$NoBrowser,
    [switch]$Enroll,
    [string]$TidMap = ''
)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$KEY_HEX = '0001020308090a0b10111213'
$SN_A = '210251A0195C'
$SN_B = '210251A04F2C'
$BIT_A = Join-Path $repo 'build\board_zc706_arm_v4b\w3_top_zc706.bit'
$BIT_B = Join-Path $repo 'build\board_zc706_seed2b\w3_top_zc706_seed2.bit'
$state = Join-Path $repo '.demo_state'
$manifest = Join-Path $state 'bit_manifest.json'

function Step([int]$n, [string]$msg) { Write-Host ('[{0}/8] {1}' -f $n, $msg) -ForegroundColor Cyan }
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
function StopBridge {
    Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'web_bridge\.py' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Ok "已杀残留桥 pid=$($_.ProcessId)" }
    Start-Sleep -Milliseconds 600
}

# ---------- [1/8] 残留清理 ----------
Step 1 '清理残留进程'
StopBridge
Get-Process hw_server -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

# ---------- [2/8] JTAG 烧写(板A v4b + 板B seed2b) ----------
Step 2 'JTAG 烧写(板A=v4b 三键 / 板B=seed2b 差异化布局)'
if ($SerialPort -eq 'none' -or $NoBurn) {
    Warn '跳过烧写(板子必须仍带电持有bit; 断电过请去掉 -NoBurn)'
} else {
    foreach ($b in @(@{n='板A'; bit=$BIT_A; sn=$SN_A}, @{n='板B'; bit=$BIT_B; sn=$SN_B})) {
        if (-not (Test-Path $b.bit)) { Warn "$($b.n) bit 不存在: $($b.bit) -- 先建流" ; continue }
        $out = & 'D:\vivado\2026.1\Vivado\bin\vivado.bat' -mode batch -nojournal -nolog -notrace -source 'build\tcl\program_zc706.tcl' -tclargs $b.bit $b.sn 2>&1 | Out-String
        if ($out -match 'PROGRAM_OK') { Ok "$($b.n) PROGRAM_OK" } else { Warn "$($b.n) 烧写未确认(板子未上电?) -- 由链路自检裁决" }
        Get-Process hw_server -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    }
    $elf = Join-Path $repo 'sw\arm_fan\arm_fan.elf'
    $atcl = Join-Path $repo 'sw\arm_fan\arm_fan.tcl'
    if ((Test-Path $elf) -and (Test-Path $atcl)) {
        $aout = & 'D:\vivado\2026.1\Vitis\bin\xsdb.bat' $atcl 2>&1 | Out-String
        if ($aout -match 'ARM_FAN_OK') { Ok '板A ARM 监视器 ELF ARM_FAN_OK' } else { Warn 'ELF 未加载(不阻断)' }
    }
}

# ---------- [3/8] bit 一致性防呆 + 可选清模板 ----------
Step 3 'bit 清单核对(换bit会使 PUF 模板失效)'
$map = @{}   # tid -> COM
if ($Enroll) {
    if (Test-Path (Join-Path $state 'templates\templates.json')) {
        $tp = Join-Path $state 'templates\templates.json'
        Copy-Item $tp ($tp + '.bak_' + (Get-Date -Format yyMMddHHmm)) -Force
        $j = Get-Content $tp -Raw | ConvertFrom-Json
        foreach ($t in @('1','2')) { if ($j.PSObject.Properties.Name -contains $t) { $j.PSObject.Properties.Remove($t) } }
        ($j | ConvertTo-Json -Depth 6) | Set-Content -Encoding utf8 $tp
        foreach ($t in @('1','2')) {
            $pp = Join-Path $state "crp_datasets\pools\pool_$t.json"
            if (Test-Path $pp) {
                $p = Get-Content $pp -Raw | ConvertFrom-Json
                $p.used = @($p.used) + @($p.available) | Select-Object -Unique
                $p.available = @()
                ($p | ConvertTo-Json -Depth 4) | Set-Content -Encoding utf8 $pp
            }
        }
        Ok '已清沙箱 tid1/tid2 模板与池(原文件已备份)'
    }
}
if (Test-Path $manifest) {
    $old = Get-Content $manifest -Raw | ConvertFrom-Json
    $cur = @{}
    if (Test-Path $BIT_A) { $cur['A'] = (Get-FileHash $BIT_A -Algorithm SHA256).Hash }
    if (Test-Path $BIT_B) { $cur['B'] = (Get-FileHash $BIT_B -Algorithm SHA256).Hash }
    $changed = $false
    foreach ($k in $cur.Keys) { if ($old.$k -and ($old.$k -ne $cur[$k])) { $changed = $true } }
    if ($changed) { Warn 'bit 与本沙箱上次录入时的不是同一文件 -> PUF 模板可能失效! 建议加 -Enroll 重录模板' }
    else { Ok 'bit 与模板录入时一致(指纹绑定成立)' }
} else { Warn '无 bit 清单(首次运行), 录入成功后自动生成' }

# ---------- [4/8] 串口归类 ----------
Step 4 '串口归类(点名 tid; 同一口同时应答 tid1+tid2 = 单 HC-12 统一信道)'
$portTids = @{}   # COM -> 应答过的 tid 列表
if ($SerialPort -eq 'none') { Warn '彩排模式(loopback): 跳过串口/桥走仿真' }
elseif ($TidMap) {
    foreach ($kv in ($TidMap -split ',')) { $a = $kv -split '='; if ($a.Count -eq 2) { $map[[int]$a[0].Trim()] = $a[1].Trim() } }
    Ok "手动归属: $TidMap"
} else {
    if ($SerialPort -ne 'auto') { $candList = @($SerialPort) }
    else {
        $cands = Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue |
            Where-Object { $_.DeviceID -match '^USB\\' -and $_.Name -match '\(COM\d+\)' }
        $candList = @($cands | ForEach-Object { if ($_.Name -match '(COM\d+)') { $Matches[1] } } | Select-Object -Unique)
    }
    if ($candList.Count -lt 1) { Die '未探测到USB串口(插哪口/变几号都行). 检查PC侧HC-12转接板+板子12V' }
    $py = @'
import sys, time
sys.path.insert(0, r'REPO')
import serial
from src.python.server.protocol import HFIDAProtocol
P = HFIDAProtocol()
for want in (1, 2):
    poll = P.pack(P.MSG_AUTH_POLL, terminal_id=want, nonce=int(time.time()) & 0xFFFF)
    rx = b''
    try:
        with serial.Serial(r'PORT', 115200, timeout=0.2) as s:
            time.sleep(0.25); s.reset_input_buffer(); s.write(poll); s.flush()
            t0 = time.time()
            while time.time() - t0 < 2.6:
                n = s.in_waiting
                if n: rx += s.read(n)
                else: time.sleep(0.02)
    except Exception as e:
        print('CLASSIFY', want, 'err'); continue
    if rx.startswith(b'\xfd'):
        try:
            mid, fl = P.parse(rx)
            print('CLASSIFY', want, fl.get('terminal_id'))
        except Exception:
            print('CLASSIFY', want, 'parsefail')
    else:
        print('CLASSIFY', want, 'none')
'@
    $tmp = Join-Path $env:TEMP 'puf_classify.py'
    $sharedPort = $null
    foreach ($c in $candList) {
        Set-Content -Encoding utf8 $tmp ($py.Replace('PORT', $c).Replace('REPO', $repo))
        $r = & python $tmp 2>&1 | Out-String
        Remove-Item $tmp -ErrorAction SilentlyContinue
        $hits = @()
        foreach ($line in ($r -split "`n")) {
            if ($line -match 'CLASSIFY\s+([12])\s+([12])') { if ([int]$Matches[1] -eq [int]$Matches[2]) { $hits += [int]$Matches[2] } }
        }
        if ($hits.Count -gt 0) {
            $hits = @($hits | Select-Object -Unique)
            $portTids[$c] = $hits
            Ok ("$c 应答 tid: " + ($hits -join ','))
            if (-not $map.ContainsKey(1) -and ($hits -contains 1)) { $map[1] = $c }
            if (-not $map.ContainsKey(2) -and ($hits -contains 2)) { $map[2] = $c }
        } else { Warn "$c 无应答" }
    }
    foreach ($kv in $portTids.GetEnumerator()) { if ($kv.Value.Count -ge 2) { $sharedPort = $kv.Key } }
    if ($sharedPort) { Ok "共享信道: $sharedPort 同时应答 tid1+tid2 -> 单 HC-12 模式(帧内 tid 区分 A/B)" }
    if ($map.Count -lt 1) { Die '所有候选串口都没应答. 排查: 板子12V+DS22亮; SW11=00000且已烧bit; 三只HC-12同C001/115200/FU3; 板侧HC-12供电共地' }
}

# ---------- [5/8] 起桥 ----------
Step 5 '启动 web 桥(多口路由 + 接入闸门)'
$bargs = @('-u','web/bridge/web_bridge.py','--repo-root','.','--data-dir',$state,'--port',"$Port")
if ($SerialPort -eq 'none') { $bargs += '--loopback' }
else {
    $ports = @($map.Values | Sort-Object -Unique)
    if ($sharedPort) {
        $bargs += @('--serial-port', $sharedPort)
        Ok "单 HC-12 统一信道: --serial-port $sharedPort（下行靠点名、上行靠帧内 tid）"
    } elseif ($ports.Count -gt 1) {
        $bargs += @('--serial-multi', ($ports -join ','))
        $tp = (@($map.Keys | Sort-Object | ForEach-Object { "$_=$($map[$_])" }) -join ',')
        $bargs += @('--tid-port', $tp)
        Ok "多口模式: $tp"
    } else {
        $only = $map.Keys | Select-Object -First 1
        $bargs += @('--serial-port', $map[$only])
        Warn "单板模式: 只有 tid$only ($($map[$only])) 在线"
    }


}
$bargs += @('--access-gate','--access-label','1=板A,2=板B')
if (-not $NoBrowser) { $bargs += '--open' }
$log = Join-Path $state ('bridge_' + (Get-Date -Format HHmmss) + '.log')
$proc = Start-Process -FilePath 'python' -ArgumentList $bargs -WorkingDirectory $repo -RedirectStandardOutput $log -RedirectStandardError ($log + '.err') -PassThru -WindowStyle Hidden
$up = $false; $bound = $Port
foreach ($i in 1..22) {
    Start-Sleep -Seconds 1
    if ($proc.HasExited) { Die "桥提前退出(exit=$($proc.ExitCode)); 日志: $log.err" }
    foreach ($p in $Port..($Port + 5)) {
        try { $r = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$p/api/status" -TimeoutSec 2; if ($r.StatusCode -eq 200) { $bound = $p; $up = $true; break } } catch { }
    }
    if ($up) { break }
}
if (-not $up) { Die "桥 22s 未就绪; 日志: $log.err" }
Ok "桥就绪: http://127.0.0.1:$bound/console.html (pid $($proc.Id))"

# ---------- [6/8] 补密钥 ----------
Step 6 '补板内密钥(tid1/tid2)'
if ($SerialPort -ne 'none') {
    foreach ($t in @($map.Keys | Sort-Object)) {
        try {
            $k = Invoke-WebRequest -UseBasicParsing -Method POST -ContentType 'application/json' -Body ('{"terminal_id":' + $t + ',"key_hex":"' + $KEY_HEX + '"}') "http://127.0.0.1:$bound/api/setkey" -TimeoutSec 5
            Ok "setkey tid$t : $($k.Content)"
        } catch { Warn "setkey tid$t 失败(板子不在? 已带电密钥不受影响)" }
    }
}

# ---------- [7/8] 模板自检(可自动录入) ----------
Step 7 '模板就绪自检(tid1>=30对, tid2>=20对; 缺失自动录入)'
$needEnroll = @()
if ($SerialPort -eq 'none') { Warn '彩排模式: 跳过模板检查' }
else {
    $stt = $null
    try { $stt = (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$bound/api/status" -TimeoutSec 4).Content | ConvertFrom-Json } catch { }
    foreach ($t in @($map.Keys | Sort-Object)) {
        $min = if ($t -eq 1) { 30 } else { 20 }
        $n = 0
        if ($stt -and $stt.templates) {
            $e = $stt.templates | Where-Object { "$($_.terminal_id)" -eq "$t" } | Select-Object -First 1
            if ($e) { $n = [int]$e.n_pairs }
        }
        if ($n -lt $min) { $needEnroll += $t; Warn "tid$t 模板只有 $n 对(需>=$min) -> 排队录入" } else { Ok "tid$t 模板 $n 对 OK" }
    }
    foreach ($t in $needEnroll) {
        $nWant = if ($t -eq 1) { 100 } else { 30 }
        Warn "开始录入 tid$t n=$nWant (约1-3分钟, 请勿按按键)"
        try { Invoke-WebRequest -UseBasicParsing -Method POST -ContentType 'application/json' -Body ('{"terminal_id":' + $t + ',"n":' + $nWant + ',"measurements":3}') "http://127.0.0.1:$bound/api/enroll_real" -TimeoutSec 15 | Out-Null } catch { }
        $done = $false
        foreach ($i in 1..80) {
            Start-Sleep -Seconds 3
            try {
                $st2 = (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$bound/api/status" -TimeoutSec 3).Content | ConvertFrom-Json
                $e2 = $st2.templates | Where-Object { "$($_.terminal_id)" -eq "$t" } | Select-Object -First 1
                if ($e2 -and [int]$e2.n_pairs -ge 20) { $done = $true; Ok "tid$t 录入完成: $($e2.n_pairs) 对" ; break }
            } catch { }
        }
        if (-not $done) { Warn "tid$t 录入未确认(可能超时); 可稍后重跑本脚本" }
    }
}

    # 认证冒烟: 模板存在不等于指纹匹配(换bit会静默失配) -> 真跑一轮五帧判 PASS
    $smokePy = @'
import sys, time, json, threading, urllib.request
B = 'BASEURL'; TID = TIDNUM
def post(pth, d):
    return urllib.request.urlopen(urllib.request.Request(B + pth, method='POST', data=json.dumps(d).encode(), headers={'Content-Type': 'application/json'}), timeout=20).read()
evs = []
def w():
    with urllib.request.urlopen(B + '/api/events', timeout=45) as r:
        t0 = time.time()
        for raw in r:
            if time.time() - t0 > 40: break
            l = raw.decode('utf-8', 'replace').strip()
            if l.startswith('data:'): evs.append(l[5:])
threading.Thread(target=w, daemon=True).start(); time.sleep(1)
post('/api/poll', {'terminal_id': TID}); time.sleep(2.5)
try: post('/api/access/select', {'terminal_id': TID})
except Exception as e: print('SMOKE SELECTERR', e)
time.sleep(11)
for e in evs:
    if '"verdict"' in e:
        p = json.loads(e)['payload']
        if p.get('terminal_id') == TID:
            print('SMOKE', p.get('result_name'), 'hd=', p.get('hd'))
            break
else:
    print('SMOKE NONE')
'@
    $stmp = Join-Path $env:TEMP 'puf_smoke.py'
    $smokeFail = @()
    if ($SerialPort -ne 'none') {
        foreach ($t in @($map.Keys | Sort-Object)) {
            Set-Content -Encoding utf8 $stmp (($smokePy.Replace('BASEURL', "http://127.0.0.1:$bound")).Replace('TIDNUM', "$t"))
            $sr = & python $stmp 2>&1 | Out-String
            Remove-Item $stmp -ErrorAction SilentlyContinue
            if ($sr -match 'SMOKE PASS') { Ok ("tid$t 认证冒烟 PASS: " + ($sr -replace '\r?\n', ' ').Trim()) }
            elseif ($sr -match 'SMOKE') { $smokeFail += $t; Warn ("tid$t 认证冒烟异常: " + ($sr -replace '\r?\n', ' ').Trim()) }
            else { Warn "tid$t 冒烟无输出(板子忙?) -- 不阻断, 但演示前请手测一次" }
        }
        if ($smokeFail.Count -gt 0) {
            Warn '认证冒烟失败通常是换过bit而模板是旧bit录的 -> 跑 .\scripts\demo_one_click.ps1 -Enroll 重录'
        }
    }

# ---------- [8/8] bit 清单 + 操作提示 ----------
Step 8 '写 bit 清单 + 操作提示'
try {
    New-Item -ItemType Directory -Path $state -Force | Out-Null
    $mf = @{ at = (Get-Date -Format s) }
    if (Test-Path $BIT_A) { $mf['A'] = (Get-FileHash $BIT_A -Algorithm SHA256).Hash }
    if (Test-Path $BIT_B) { $mf['B'] = (Get-FileHash $BIT_B -Algorithm SHA256).Hash }
    ($mf | ConvertTo-Json) | Set-Content -Encoding utf8 $manifest
} catch { }
$portsTxt = (@($map.Keys | Sort-Object | ForEach-Object { "tid$_=$($map[$_])" }) -join '  ')
Write-Host ''
Write-Host '  ================= 演示就绪 =================' -ForegroundColor Green
if ($SerialPort -ne 'none') { Write-Host "  端口: $portsTxt" -ForegroundColor Green }
Write-Host "  前端: http://127.0.0.1:$bound/console.html" -ForegroundColor Green
Write-Host '  发起认证: 板A 按 SW8(右) | 板B 按 SW8(右)' -ForegroundColor Yellow
Write-Host '  !! 板A 的 SW7 触点已坏, 不要按; SW7/SW9 为冗余备键' -ForegroundColor Yellow
Write-Host '  伪基站演示: python tools/attack/fake_result_attack.py --rogue  (或 http://127.0.0.1:8643)' -ForegroundColor Gray
Write-Host '  不做: 不按SW13; PMOD断电才插拔; 换bit后必须重录模板(-Enroll)' -ForegroundColor Gray
Write-Host '  ============================================' -ForegroundColor Green
