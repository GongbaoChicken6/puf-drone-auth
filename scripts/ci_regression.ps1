# ci_regression.ps1 -- Full regression: ALL RTL + ALL TBs (W1+W2+W3)
# Usage: .\scripts\ci_regression.ps1
# Exit 0 = all pass, exit 1 = any failure
#
# W4-P0 (2026-10-13): every native tool call (xvlog/xelab/xsim) now runs
# inside a background job with a hard timeout -- a hung TB can no longer
# hang the whole CI (it is judged FAIL and the remaining TBs still run).
# Python output captures go through "cmd /c ... 2>&1" so PS 5.1 never
# wraps native stderr into ErrorRecords (kills the "RemoteException"
# noise lines in evidence logs).  The *-Files/*-Names parameters are
# test-only overrides used by scripts/ci_timeout_experiment.ps1;
# production runs use the defaults below.

param(
    [int]$CompileTimeoutS = 600,
    [int]$ElabTimeoutS    = 300,
    [int]$SimTimeoutS     = 300,
    [string]$RtlList   = $null,      # test-only: comma-separated RTL file list
    [string]$TbList    = $null,      # test-only: comma-separated TB file list
    [string]$TbNameList = $null      # test-only: comma-separated TB top names
)

$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")
$vivado = "D:\vivado\2026.1\Vivado\bin"
# Fail fast with an honest message instead of stale-exit-code "OK"s when
# the toolchain is missing (ci_gate review M2 experiment).
if (-not (Test-Path "$vivado\xvlog.bat")) {
    Write-Host "VIVADO NOT FOUND at $vivado"; exit 1
}

# ---------------------------------------------------------------------
# Timed native runner (W4-P0): Start-Job + Wait-Job -Timeout.
# The job body receives $File/$Arguments explicitly -- scriptblocks sent
# to jobs lose the parent scope, so NO closure variables may be used.
# Stop-Job kills the job's PowerShell; the xsim/xelab child normally
# dies with it (and every TB has its own watchdog/final events).  An
# orphaned simulator child is a documented residual risk we accept
# rather than killing xsim processes by name (a concurrent Vivado
# session in another conversation must never be shot down).
# ---------------------------------------------------------------------
function Invoke-TimedNative {
    param([string]$File, [string[]]$Arguments, [int]$TimeoutS, [string]$Label, [string]$WorkDir)
    $job = Start-Job -ScriptBlock {
        param($f, $a, $wd)
        Set-Location $wd
        $lines = & $f @a 2>&1 | ForEach-Object { "$_" }
        [pscustomobject]@{ Lines = @($lines); Code = $LASTEXITCODE }
    } -ArgumentList $File, $Arguments, $WorkDir
    if (Wait-Job $job -Timeout $TimeoutS) {
        $state = "$($job.State)"
        $res = Receive-Job $job
        Remove-Job $job -Force
        if ($null -eq $res -or $null -eq $res.Code) {
            # Tool never started (CommandNotFoundException leaves
            # $LASTEXITCODE $null inside the job) or the job failed:
            # MUST count as failure -- [int]$null would silently be 0
            # and green-light a compile/elab that never ran (review P1).
            return @{ TimedOut = $false; Code = -1; Lines = [string[]]@(
                "[ERROR] $Label produced no exit code (tool not started / job state=$state)") }
        }
        return @{ TimedOut = $false; Code = [int]$res.Code; Lines = [string[]]$res.Lines }
    }
    # Stop-Job has no -Force in PS 5.1.  Kill the job's whole process
    # tree first (the hung xsim lives under the job's powershell) --
    # strictly scoped to OUR job pid, a concurrent Vivado session in
    # another conversation is never touched.
    # Preserve whatever the hung tool already printed (review P3): a
    # non-blocking receive BEFORE the kill keeps the last lines for
    # root-cause diagnosis instead of discarding them.
    $partial = @()
    try { $partial = @(Receive-Job $job -Keep -ErrorAction SilentlyContinue | ForEach-Object { "$_" }) } catch { }
    $treePid = $job.ChildJobs[0].ProcessId
    $created = @{}
    $desc = @()
    $frontier = @($treePid)
    for ($d = 0; $d -lt 5 -and $frontier.Count -gt 0; $d++) {
        $next = @()
        foreach ($p in $frontier) {
            $kids = Get-CimInstance Win32_Process -Filter "ParentProcessId=$p" -ErrorAction SilentlyContinue
            if ($null -eq $kids -and $d -eq 0) {
                Write-Host "[WARN] CIM child query returned nothing for pid $p -- orphan child possible"
            }
            foreach ($k in @($kids)) {
                $created[[int]$k.ProcessId] = $k.CreationDate
                $next += [int]$k.ProcessId
            }
        }
        $desc += $next; $frontier = $next
    }
    $killed = 0
    foreach ($p in ($desc | Sort-Object -Descending -Unique)) {
        $now = Get-CimInstance Win32_Process -Filter "ProcessId=$p" -ErrorAction SilentlyContinue
        if (-not $now) { continue }                          # already gone
        if ($now.CreationDate -ne $created[$p]) { continue } # PID reused: never kill
        Stop-Process -Id $p -Force -ErrorAction SilentlyContinue; $killed++
    }
    if ($killed -eq 0 -and $desc.Count -gt 0) { Write-Host "[WARN] timeout kill-list emptied before firing -- PID churn?" }
    Stop-Job $job -ErrorAction SilentlyContinue
    Remove-Job $job -Force
    return @{ TimedOut = $true; Code = -1;
              Lines = [string[]](@("[TIMEOUT] $Label exceeded $TimeoutS s -- job killed") + @($partial | Select-Object -Last 10)) }
}

# ALL RTL files (W1 + W2 + W3)
$rtl = @(
    "src\rtl\w1_ratio\ro_ring.v", "src\rtl\w1_ratio\ro_div.v",
    "src\rtl\w2_array\ro_array.v", "src\rtl\w2_array\challenge_decode.v",
    "src\rtl\w2_array\ro_entropy.v",
    "src\rtl\w2_array\w2_top.v",
    "src\rtl\common\crc16_mcrf4xx.v", "src\rtl\common\mavlink_frame.v",
    "src\rtl\common\frame_parser.v",  "src\rtl\common\byte_fifo.v",
    "src\rtl\common\uart_tx.v",       "src\rtl\common\uart_rx.v",
    "src\rtl\common\speck64_96.v",
    "src\rtl\w3_protocol\terminal_fsm.v", "src\rtl\w3_protocol\w3_top.v"
)
# ALL TB files
$tbs = @(
    "sim\tb\tb_speck.v",
    "sim\tb\tb_gap_regression.v",
    "sim\tb\tb_challenge_decode.v",
    "sim\tb\tb_crc16.v", "sim\tb\tb_mavlink_frame.v", "sim\tb\tb_frame_parser.v",
    "sim\tb\tb_byte_fifo.v", "sim\tb\tb_uart_tx.v", "sim\tb\tb_uart_rx.v", "sim\tb\tb_terminal_fsm.v",
    "sim\tb\tb_tx_chain.v", "sim\tb\tb_level3_protocol.v", "sim\tb\tb_w3_top.v",
    "sim\tb\ro_array_sim.v",
    "sim\tb\tb_puf_path.v",
    "sim\tb\tb_key_derive.v",
    "sim\tb\tb_w3top_keyloop.v",
    "sim\tb\tb_ro_entropy.v",
    "sim\tb\tb_w3_top_seedgate.v"   # M1(auto-review): SEED_GATE_EN 旁路/门控双向锁定
)
$tbNames = @("tb_speck", "tb_gap_regression",
             "tb_challenge_decode","tb_crc16","tb_mavlink_frame","tb_frame_parser",
             "tb_byte_fifo","tb_uart_tx","tb_uart_rx","tb_terminal_fsm","tb_tx_chain","tb_level3_protocol",
             "tb_w3_top", "tb_puf_path", "tb_key_derive", "tb_w3top_keyloop", "tb_ro_entropy",
             "tb_w3_top_seedgate")
# Test-only overrides (W4-P0 timeout experiment).  Deliberately plain
# [string] + internal split: powershell.exe -File does NOT split commas
# for array parameters (that is -Command behaviour), so accepting one
# comma-separated token is the only CLI-proof shape.
if ($RtlList)    { $rtl     = @($RtlList    -split ',' | ForEach-Object { $_.Trim() }) }
if ($TbList)     { $tbs     = @($TbList     -split ',' | ForEach-Object { $_.Trim() }) }
if ($TbNameList) { $tbNames = @($TbNameList -split ',' | ForEach-Object { $_.Trim() }) }
# Override guard: $tbs may carry helper modules (ro_array_sim.v) that are
# not standalone tops, so instead of count equality every named top must
# have a matching file in the list.
if ($TbList -or $TbNameList) {
    foreach ($name in $tbNames) {
        if (-not ($tbs | Where-Object { $_.EndsWith("$name.v") })) {
            Write-Host "OVERRIDE MISMATCH: no file for top '$name' in TbList"; exit 1
        }
    }
}
$overridesActive = [bool]($RtlList -or $TbList -or $TbNameList)
if ($overridesActive) {
    Write-Host ">>> OVERRIDE ACTIVE (test-only subset run -- NOT a full regression)"
    if ($RtlList)    { Write-Host ">>>   RTL : $rtl" }
    if ($TbList)     { Write-Host ">>>   TBs : $tbs" }
    if ($TbNameList) { Write-Host ">>>   Tops: $tbNames" }
}

# M-LOCK(auto-review #3): wrapper 3-element text lock - wrapper is NOT compiled by xsim
# (clk_wiz IP); polarity/gating regressions (.reset inverted revive / SEED_GATE_EN(0)
# bypass reopen) are intercepted here, closing the "CI green, board broken" gap.
# NOTE: keep this block pure ASCII - the script is UTF-8 without BOM and Windows
# PowerShell 5.1 parses it as ANSI (non-ASCII here once broke the parser).
Write-Host "=== CI: Wrapper 3-element lock ==="
$wtext = Get-Content -Raw -Encoding UTF8 "src\rtl\w3_protocol\w3_top_zc706.v"
$wchecks = @(
    @{ pat = '\.reset\s*\(\s*sys_rst_btn_n\s*\)';              desc = 'clk_wiz .reset direct (active-high, no invert)' },
    @{ pat = 'rst_n\s*=\s*~\s*sys_rst_btn_n\s*&\s*mmcm_locked'; desc = 'rst_n = ~sys_rst_btn_n & mmcm_locked' },
    @{ pat = '\.SEED_GATE_EN\s*\(\s*1\s*\)';                     desc = '.SEED_GATE_EN(1) (P1-5 gating, bypass revoked)' }
)
$wfail = 0
foreach ($c in $wchecks) {
    if ($wtext -notmatch $c.pat) {
        Write-Host "  [FAIL] WRAPPER_LOCK: $($c.desc) -- w3_top_zc706.v element regressed!"
        $wfail++
    }
}
if ($wfail -gt 0) { Write-Host "WRAPPER_LOCK_FAIL ($wfail issue(s))"; exit 1 }
Write-Host "  [PASS] wrapper 3-element lock (reset direct / rst_n invert / SEED_GATE_EN=1)"

Write-Host "=== CI: Compile ==="
Remove-Item xsim.dir -Recurse -Force -ErrorAction SilentlyContinue
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$res = Invoke-TimedNative -File "$vivado\xvlog.bat" -Arguments (@("-d", "PUF_MODEL_SIM") + @($rtl) + @($tbs)) -TimeoutS $CompileTimeoutS -Label "xvlog compile" -WorkDir (Get-Location).Path
if ($res.TimedOut -or $res.Code -ne 0) {
    $res.Lines | Select-Object -Last 20 | ForEach-Object { Write-Host "  $_" }
    Write-Host "COMPILE FAILED (timeout=$($res.TimedOut))"; exit 1
}
Write-Host ("  OK ({0:n1}s)" -f $sw.Elapsed.TotalSeconds)

Write-Host "=== CI: Elaborate ==="
for ($i = 0; $i -lt $tbNames.Count; $i++) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $res = Invoke-TimedNative -File "$vivado\xelab.bat" -Arguments @("-debug", "typical", $tbNames[$i], "-s", "ci$i") -TimeoutS $ElabTimeoutS -Label "xelab $($tbNames[$i])" -WorkDir (Get-Location).Path
    if ($res.TimedOut -or $res.Code -ne 0) {
        $res.Lines | Select-Object -Last 20 | ForEach-Object { Write-Host "  $_" }
        Write-Host "ELAB FAILED: $($tbNames[$i]) (timeout=$($res.TimedOut))"; exit 1
    }
}
Write-Host "  OK"

Write-Host "=== CI: Simulate ==="
$pass = 0; $fail = 0
for ($i = 0; $i -lt $tbNames.Count; $i++) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $res = Invoke-TimedNative -File "$vivado\xsim.bat" -Arguments @("ci$i", "-runall", "--onerror", "quit") -TimeoutS $SimTimeoutS -Label "xsim $($tbNames[$i])" -WorkDir (Get-Location).Path
    $secs = $sw.Elapsed.TotalSeconds
    if (-not $res.TimedOut -and $res.Code -eq 0 -and ($res.Lines | Select-String "TB_.*_PASS" -Quiet)) {
        Write-Host ("  [PASS] {0} ({1:n1}s)" -f $tbNames[$i], $secs); $pass++
    } else {
        if ($res.TimedOut) { $res.Lines | Select-Object -First 1 | ForEach-Object { Write-Host "  $_" } }
        else { $res.Lines | Select-Object -Last 10 | ForEach-Object { Write-Host "  $_" } }
        Write-Host "  [FAIL] $($tbNames[$i])"; $fail++
    }
}

Write-Host ("=== {0}/{1} PASS, {2} FAIL ==={3}" -f $pass, $tbNames.Count, $fail, $(if ($overridesActive) { "  [SUBSET/OVERRIDE]" } else { "" }))
if ($fail -gt 0) { Remove-Item xsim.dir -Recurse -Force -ErrorAction SilentlyContinue; exit 1 }

# ---- Phase 8a: ENROLL_NEG 变体（param=0 回归锁，P2 silent-failure：原为手动一次性）----
# 独立编译（-d ENROLL_NEG 换 tb_terminal_fsm 的 DUT 参数=0）+ 跑 TEN 断言。
Write-Host "=== CI: TB ENROLL_NEG variant (param=0 idle-ignore lock) ==="
$negTbs = @("sim\tb\tb_terminal_fsm.v", "sim\tb\ro_array_sim.v")
$resN = Invoke-TimedNative -File "$vivado\xvlog.bat" -Arguments (@("-d", "PUF_MODEL_SIM", "-d", "ENROLL_NEG") + $rtl + $negTbs) -TimeoutS $CompileTimeoutS -Label "xvlog ENROLL_NEG" -WorkDir (Get-Location).Path
if ($resN.Code -ne 0) { Write-Host "ENROLL_NEG COMPILE FAILED (exit $($resN.Code))"; Remove-Item xsim.dir -Recurse -Force -ErrorAction SilentlyContinue; exit 1 }
$resN = Invoke-TimedNative -File "$vivado\xelab.bat" -Arguments @("-debug", "typical", "tb_terminal_fsm", "-s", "tb_tfs_neg_ci") -TimeoutS $ElabTimeoutS -Label "xelab ENROLL_NEG" -WorkDir (Get-Location).Path
if ($resN.Code -ne 0) { Write-Host "ENROLL_NEG ELAB FAILED (exit $($resN.Code))"; Remove-Item xsim.dir -Recurse -Force -ErrorAction SilentlyContinue; exit 1 }
$resN = Invoke-TimedNative -File "$vivado\xsim.bat" -Arguments @("tb_tfs_neg_ci", "-runall", "--onerror", "quit") -TimeoutS $SimTimeoutS -Label "xsim ENROLL_NEG" -WorkDir (Get-Location).Path
$negOut = ($resN.Lines -join " ")
if ($resN.Code -ne 0 -or $negOut -notmatch "TEN PASS" -or $negOut -notmatch "TB_TERMINAL_FSM_PASS") {
    Write-Host "  [FAIL] ENROLL_NEG variant (exit $($resN.Code))"
    $resN.Lines | Select-String "TEN|TB_TERMINAL|FAIL|ERROR" | Select-Object -First 10 | ForEach-Object { Write-Host "    | $_" }
    Remove-Item xsim.dir -Recurse -Force -ErrorAction SilentlyContinue
    exit 1
}
Write-Host "  [PASS] tb_terminal_fsm ENROLL_NEG ([TEN PASS] idle-ignore locked)"

Remove-Item xsim.dir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item *.pb -Force -ErrorAction SilentlyContinue

Write-Host "=== CI: Python (Speck self-test + A1 phase-4 unit tests) ==="
# Silent-failure review P2: a missing python must fail the gate, not
# inherit $LASTEXITCODE=0 from the last xsim run (PS 5.1 never sets it
# on CommandNotFoundException).
# -CommandType Application: a python.ps1/function shim on PATH resolves via
# bare Get-Command but runs as a script (no native exit code -> stale reads;
# ci_gate review M4 false-pass experiment).
if (-not (Get-Command python -CommandType Application -ErrorAction SilentlyContinue)) {
    Write-Host "PYTHON NOT FOUND (or not a native executable) ON PATH"; exit 1
}
# Sentinel probe: prove exit codes actually propagate before trusting them.
& python -c "import sys; sys.exit(5)" > $null 2>&1
if ($LASTEXITCODE -ne 5) {
    Write-Host "PYTHON SENTINEL FAILED (exit codes unreliable: shim?)"; exit 1
}
# NOTE: do NOT pre-assign $LASTEXITCODE here.  A/B on this very script:
# with the old "$LASTEXITCODE = 1" presets the speck self-test gate read
# a stale 1 and failed (build/reviews/a1p5/ci_second_run_python_gate_fail.log);
# with them removed the identical run is green (ci_final_run.log).  The
# exact PowerShell scoping mechanism was NOT reproduced under bare
# "powershell -File" (reviewer experiment), so treat presets here as
# harmful-in-context rather than relying on any theory.  The Get-Command
# guard above already covers the only case the presets defended against
# (command-not-found leaving a stale code); a WindowsApps stub that fails
# to launch exits 9009, which IS a fresh exit code.
& python "src\python\common\speck.py" > $null 2>&1
if ($LASTEXITCODE -ne 0) { Write-Host "PYTHON SPECK SELF-TEST FAILED"; exit 1 }
# W4-P0: "cmd /c ... 2>&1" merges stderr at the cmd level as plain text,
# so PS 5.1 never creates ErrorRecords and the evidence log stays free of
# "System.Management.Automation.RemoteException" wrapper lines (the old
# ForEach-object stringification only fixed the inner layer).  cmd /c
# propagates python's exit code to $LASTEXITCODE.
$out = & cmd.exe /c "python tests\test_a1_phase4.py 2>&1" | ForEach-Object { "$_" }
$pyCode = $LASTEXITCODE
if ($pyCode -ne 0) {
    $out | Select-Object -Last 40 | ForEach-Object { Write-Host "  $_" }
    Write-Host "PYTHON UNIT TESTS FAILED"; exit 1
}
$out | Select-Object -Last 4 | ForEach-Object { Write-Host "  $_" }
# W3 serial-loop tests (receive loop + on_confirm wiring + enroll pairing).
$outS = & cmd.exe /c "python tests\test_serial_server.py 2>&1" | ForEach-Object { "$_" }
$serialCode = $LASTEXITCODE
if ($serialCode -ne 0) {
    $outS | Select-Object -Last 40 | ForEach-Object { Write-Host "  $_" }
    Write-Host "SERIAL SERVER TESTS FAILED"; exit 1
}
$outS | Select-Object -Last 4 | ForEach-Object { Write-Host "  $_" }
# W4-P1 PUF golden-model tests (RTL<->Python cross-check anchor).
$outP = & cmd.exe /c "python tests\test_puf_model.py 2>&1" | ForEach-Object { "$_" }
$pufCode = $LASTEXITCODE
if ($pufCode -ne 0) {
    $outP | Select-Object -Last 40 | ForEach-Object { Write-Host "  $_" }
    Write-Host "PUF MODEL TESTS FAILED"; exit 1
}
$outP | Select-Object -Last 4 | ForEach-Object { Write-Host "  $_" }
# W4-P3 interop: ROPairingPUF (RTL golden model) <-> real SerialServer.
$outI = & cmd.exe /c "python tests\test_interop_rtl_model.py 2>&1" | ForEach-Object { "$_" }
$interopCode = $LASTEXITCODE
if ($interopCode -ne 0) {
    $outI | Select-Object -Last 40 | ForEach-Object { Write-Host "  $_" }
    Write-Host "INTEROP TESTS FAILED"; exit 1
}
$outI | Select-Object -Last 4 | ForEach-Object { Write-Host "  $_" }
# W4-P4 T4: DoS rate-limiting flood test.
# P1-1 fix: capture flood exit code IMMEDIATELY (ML block previously
# swallowed it -- C-agent finding)
$outF = & cmd.exe /c "python tests\test_dos_flood.py 2>&1" | ForEach-Object { "$_" }
$floodCode = $LASTEXITCODE
if ($floodCode -ne 0) {
    $outF | Select-Object -Last 20 | ForEach-Object { Write-Host "  $_" }
    Write-Host "DOS FLOOD TESTS FAILED"; exit 1
}
$outF | Select-Object -Last 3 | ForEach-Object { Write-Host "  $_" }
# W4-P5: ML attack unit tests.
$outM = & cmd.exe /c "python tests\test_ml_attack.py 2>&1" | ForEach-Object { "$_" }
$mlCode = $LASTEXITCODE
if ($mlCode -ne 0) {
    $outM | Select-Object -Last 20 | ForEach-Object { Write-Host "  $_" }
    Write-Host "ML ATTACK TESTS FAILED"; exit 1
}
$outM | Select-Object -Last 3 | ForEach-Object { Write-Host "  $_" }
# W4-P4 T6: threat PoC harness (replay/brute/inject).
$outT = & cmd.exe /c "python scripts\threat_poc.py --case all 2>&1" | ForEach-Object { "$_" }
$threatCode = $LASTEXITCODE
if ($threatCode -ne 0) {
    $outT | Select-Object -Last 20 | ForEach-Object { Write-Host "  $_" }
    Write-Host "THREAT POC FAILED"; exit 1
}
$outT | Select-Object -Last 3 | ForEach-Object { Write-Host "  $_" }
$out2 = & cmd.exe /c "python scripts\test_r2_nonlinearity.py 2>&1" | ForEach-Object { "$_" }
$canCode = $LASTEXITCODE
if ($canCode -ne 0) {
    $out2 | Select-Object -Last 40 | ForEach-Object { Write-Host "  $_" }
    Write-Host "R2 NONLINEARITY CANARY FAILED"; exit 1
}
$out2 | Select-Object -Last 3 | ForEach-Object { Write-Host "  $_" }
$out3 = & cmd.exe /c "python scripts\gen_speck_vectors.py --check 2>&1" | ForEach-Object { "$_" }
if ($LASTEXITCODE -ne 0) {
    $out3 | Select-Object -Last 10 | ForEach-Object { Write-Host "  $_" }
    Write-Host "SPECK VECTOR FRESHNESS CHECK FAILED"; exit 1
}
# One audible line on success so the evidence log proves the check ran.
$out3 | Select-Object -Last 1 | ForEach-Object { Write-Host "  $_" }
# W4-P1 review D-P2: PUF fixture freshness (.mem + tb_puf_path R1 constants).
$outP2 = & cmd.exe /c "python scripts\gen_puf_fixtures.py --check 2>&1" | ForEach-Object { "$_" }
if ($LASTEXITCODE -ne 0) {
    $outP2 | Select-Object -Last 10 | ForEach-Object { Write-Host "  $_" }
    Write-Host "PUF FIXTURE FRESHNESS CHECK FAILED"; exit 1
}
$outP2 | Select-Object -Last 1 | ForEach-Object { Write-Host "  $_" }
$out4 = & cmd.exe /c "python tools\check_contract_sync.py 2>&1" | ForEach-Object { "$_" }
if ($LASTEXITCODE -ne 0) {
    $out4 | Select-Object -Last 10 | ForEach-Object { Write-Host "  $_" }
    Write-Host "CONTRACT SYNC FAILED (docs vs protocol.py drift)"; exit 1
}
$out4 | Select-Object -Last 1 | ForEach-Object { Write-Host "  $_" }
Write-Host "  OK"
exit 0