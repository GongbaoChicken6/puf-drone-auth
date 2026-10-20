# verify_wrapper.ps1 -- 板级 wrapper 离板门禁（xvlog + xelab + XDC 端口交叉检查）
# 用法: powershell -File build\ps1\verify_wrapper.ps1 [-Wrapper w3_top_zc706]
#
# ⚠ 覆盖口径（诚实声明，auto-review P1 修正）：本门禁 = 语法/端口一致性检查。
#    它 **不** 覆盖：Vivado synth（IP 集成类错误只有真实构建能抓，见 build_w3_board.tcl
#    曾因 clk_wiz_0 集成断裂而 synth 8-439 的教训）、时序、DRC。CI 全绿也不代表这些。
# 语义：不带 -d PUF_MODEL_SIM（走真 ro_array 板级网表，组合环 WARNING 属设计使然）；
#    clk_wiz_0 stub 写 %TEMP%（不入仓库）；编译前预清 xsim.dir（防陈旧工作库，
#    silent-failure P3：xelab 对幸存 sdb 无源码陈旧检查）。
# 环境要求：TEMP/SystemDrive 环境变量必须存在（Vivado loader 缺它们会零输出静默退 1）。
param(
    [string]$Wrapper = "w3_top_zc706"
)
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..\..")
$vivado = "D:\vivado\2026.1\Vivado\bin"
if (-not (Test-Path "$vivado\xvlog.bat")) {
    Write-Host "VIVADO NOT FOUND at $vivado"; exit 1
}
if (-not $env:TEMP -or -not $env:SystemDrive) {
    Write-Host "ENV GUARD: TEMP/SystemDrive missing (Vivado loader would exit 1 with zero output)"; exit 1
}

# ---- Step 0: XDC<->wrapper 端口交叉检查（P1 silent-failure：XDC 端口名写错只降级
#      为 critical warning + 引脚悬空，bitstream 照常生成 = 板上静默失败）----
$xdcPath = "src\rtl\w3_protocol\$Wrapper.xdc"
$vPath   = "src\rtl\w3_protocol\$Wrapper.v"
if (-not (Test-Path $xdcPath)) { Write-Host "XDC NOT FOUND: $xdcPath"; exit 1 }
if (-not (Test-Path $vPath))   { Write-Host "WRAPPER NOT FOUND: $vPath"; exit 1 }
$xdcRaw = Get-Content $xdcPath -Raw -Encoding UTF8
$vRaw   = Get-Content $vPath   -Raw -Encoding UTF8
$wrapPorts = [regex]::Matches($vRaw, "(?m)^\s*(?:input|output)\s+wire\s+(?:\[[^\]]+\]\s*)?([A-Za-z_][A-Za-z_0-9]*)") | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique
$portErr = 0
foreach ($p in $wrapPorts) {
    if ($xdcRaw -notmatch [regex]::Escape($p)) {
        Write-Host "XDC-CHECK FAIL: wrapper port [$p] not referenced in XDC"; $portErr++
    }
}
$xdcTokens = [regex]::Matches($xdcRaw, "get_ports\s+(?:\{([^}]+)\}|([^\s\]]+(?:\[\d+\])?))") | ForEach-Object { ($_.Groups[1].Value + $_.Groups[2].Value).Trim() } | Sort-Object -Unique
foreach ($t in $xdcTokens) {
    if ($t -match "\*") {
        # wildcard token (led_* / term_id_dip[*]): prefix-match against wrapper ports
        $prefix = $t -replace "[\*\]\[]+$", ""
        $hit = $false
        foreach ($wp in $wrapPorts) { if ($wp.StartsWith($prefix)) { $hit = $true; break } }
        if (-not $hit) {
            Write-Host "XDC-CHECK FAIL: wildcard token [$t] matches no wrapper port"; $portErr++
        }
    } else {
        $base = $t -replace "\[.*$", ""
        if ($base -and ($wrapPorts -notcontains $base)) {
            Write-Host "XDC-CHECK FAIL: XDC token [$t] (base=$base) not a wrapper port"; $portErr++
        }
    }
}
if ($portErr -gt 0) { Write-Host "VERIFY_WRAPPER_FAIL (XDC port cross-check, $portErr issue(s))"; exit 1 }
Write-Host "XDC port cross-check OK ($($wrapPorts.Count) wrapper ports all covered)"

# ---- Step 1: 预清工作库（防陈旧 sdb elaboration）----
if (Test-Path xsim.dir) { Remove-Item xsim.dir -Recurse -Force -ErrorAction SilentlyContinue }

# ---- Step 2: clk_wiz_0 仿真 stub（与真 IP 端口一致）----
$stub = Join-Path $env:TEMP "clk_wiz_0_stub.v"
@'
module clk_wiz_0 (input wire clk_in1_p, input wire clk_in1_n, input wire reset,
                  output wire clk_out1, output wire locked);
  assign clk_out1 = clk_in1_p;
  assign locked   = ~reset;
endmodule
'@ | Set-Content -Path $stub -Encoding ascii

# ---- Step 3: xvlog + xelab ----
$rtl = @(
    "src\rtl\w1_ratio\ro_ring.v", "src\rtl\w1_ratio\ro_div.v",
    "src\rtl\w2_array\ro_array.v", "src\rtl\w2_array\challenge_decode.v",
    "src\rtl\w2_array\ro_entropy.v",
    "src\rtl\common\crc16_mcrf4xx.v", "src\rtl\common\mavlink_frame.v",
    "src\rtl\common\frame_parser.v", "src\rtl\common\byte_fifo.v",
    "src\rtl\common\uart_tx.v", "src\rtl\common\uart_rx.v",
    "src\rtl\common\speck64_96.v",
    "src\rtl\w3_protocol\terminal_fsm.v", "src\rtl\w3_protocol\w3_top.v",
    "src\rtl\w3_protocol\$Wrapper.v"
)
Write-Host "=== verify_wrapper: xvlog ($Wrapper + 14 RTL + clk_wiz stub) ==="
& "$vivado\xvlog.bat" @rtl $stub
if ($LASTEXITCODE -ne 0) { Write-Host "VERIFY_WRAPPER_FAIL (xvlog exit $LASTEXITCODE)"; exit 1 }
Write-Host "=== verify_wrapper: xelab $Wrapper (real ro_array netlist) ==="
& "$vivado\xelab.bat" -debug typical $Wrapper -s "$($Wrapper)_chk"
if ($LASTEXITCODE -ne 0) { Write-Host "VERIFY_WRAPPER_FAIL (xelab exit $LASTEXITCODE)"; exit 1 }

Write-Host "VERIFY_WRAPPER_PASS"
exit 0
