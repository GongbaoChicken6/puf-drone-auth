# build_flight.ps1 -- ARM flight-controller ELF build (OCM and DDR variants, one source tree)
# Both variants share start.S + flight_ctrl.c; only the linker script differs,
# and the stack top comes from __stack_top defined there (never hard-coded).
# After each build three positive sentinels are checked, log -> build_flight.log
#   [S1] ELF entry address == expected base
#   [S2] symbol __stack_top == expected stack top
#   [S3] the literal actually loaded into sp by _start == expected stack top
$ErrorActionPreference = "Stop"
$bin     = "D:\vivado\2026.1\gnu\aarch32\nt\gcc-arm-none-eabi\bin"
$gcc     = Join-Path $bin 'arm-none-eabi-gcc.exe'
$objdump = Join-Path $bin 'arm-none-eabi-objdump.exe'
$objcopy = Join-Path $bin 'arm-none-eabi-objcopy.exe'
$nm      = Join-Path $bin 'arm-none-eabi-nm.exe'
$readelf = Join-Path $bin 'arm-none-eabi-readelf.exe'
$size    = Join-Path $bin 'arm-none-eabi-size.exe'
foreach ($t in @($gcc,$objdump,$objcopy,$nm,$readelf,$size)) { if (-not (Test-Path $t)) { Write-Host "TOOL NOT FOUND: $t"; exit 1 } }

Set-Location $PSScriptRoot
$log = Join-Path $PSScriptRoot 'build_flight.log'
if (Test-Path $log) { Remove-Item $log -Force }
function Log([string]$s) { Write-Host $s; Add-Content -Path $log -Value $s }

$common = @('-mcpu=cortex-a9','-marm','-g','-O1','-ffreestanding','-nostdlib','-nostartfiles','-Wl,--build-id=none')

function Build-One([string]$ldName, [string]$out, [uint32]$expectBase, [uint32]$expectSp) {
    Log ""
    Log "===== BUILD $out  (linker=$ldName) ====="
    & $gcc @common -T $ldName start.S flight_ctrl.c -o $out "-Wl,-Map=$out.map"
    if ($LASTEXITCODE -ne 0) { Log "BUILD_FAIL $out"; exit 1 }
    Log "BUILD_OK $out"

    # [S1] entry address
    $eh = (& $readelf -h $out | Select-String -Pattern 'Entry point address:\s+0x([0-9a-fA-F]+)')
    if (-not $eh) { Log "[S1] entry line NOT FOUND => FAIL"; exit 1 }
    $entry = [Convert]::ToUInt32($eh.Matches[0].Groups[1].Value, 16)
    $s1 = if ($entry -eq $expectBase) { 'PASS' } else { 'FAIL' }
    Log ("[S1] ENTRY=0x{0:X8} (expect 0x{1:X8}) => {2}" -f $entry, $expectBase, $s1)
    if ($s1 -ne 'PASS') { exit 1 }

    # [S2] __stack_top symbol
    $nml = (& $nm $out | Select-String -Pattern '^([0-9a-fA-F]{8})\s+[A-Za-z]\s+__stack_top$')
    if (-not $nml) { Log "[S2] __stack_top MISSING => FAIL"; exit 1 }
    $symTop = [Convert]::ToUInt32($nml.Matches[0].Groups[1].Value, 16)
    $s2 = if ($symTop -eq $expectSp) { 'PASS' } else { 'FAIL' }
    Log ("[S2] __stack_top=0x{0:X8} (expect 0x{1:X8}) => {2}" -f $symTop, $expectSp, $s2)
    if ($s2 -ne 'PASS') { exit 1 }

    # [S3] disassemble _start, resolve the pc-relative literal, read it from raw text
    $dl = & $objdump -d $out
    $l  = $dl | Select-String -Pattern '^\s*([0-9a-fA-F]+):\s+[0-9a-fA-F]+\s+ldr\s+sp,\s*\[pc,\s*#(\d+)\]'
    if (-not $l) { Log "[S3] ldr sp,[pc,#N] NOT FOUND => FAIL"; exit 1 }
    $insnAddr = [Convert]::ToUInt32($l.Matches[0].Groups[1].Value, 16)
    $pcOff    = [Convert]::ToUInt32($l.Matches[0].Groups[2].Value, 10)
    $litAddr  = $insnAddr + 8 + $pcOff
    $raw = Join-Path $PSScriptRoot ("$out.text.bin")
    & $objcopy -O binary -j .text $out $raw
    if ($LASTEXITCODE -ne 0) { Log "[S3] objcopy FAIL"; exit 1 }
    $bytes = [IO.File]::ReadAllBytes($raw)
    $off = [int]($litAddr - $expectBase)
    if ($off -lt 0 -or ($off + 4) -gt $bytes.Length) { Log ("[S3] literal 0x{0:X8} outside .text => FAIL" -f $litAddr); exit 1 }
    $spInit = [BitConverter]::ToUInt32($bytes, $off)
    $s3 = if ($spInit -eq $expectSp) { 'PASS' } else { 'FAIL' }
    Log ("[S3] ldr sp literal @0x{0:X8} = 0x{1:X8} (expect 0x{2:X8}) => {3}" -f $litAddr, $spInit, $expectSp, $s3)
    Remove-Item $raw -Force
    if ($s3 -ne 'PASS') { exit 1 }

    Log ("SIZE $out : " + ((& $size $out | Select-Object -Last 1)))
}

# 1) OCM variant: JTAG/XSDB debug load at 0x0
Build-One 'ocm.ld' 'flight_ctrl.elf'     0x00000000 0x0000FF80
# 2) DDR variant: loaded by FSBL from BOOT.bin/SD at 0x10000000  <-- use this one in BOOT.bin
Build-One 'ddr.ld' 'flight_ctrl_ddr.elf' 0x10000000 0x1000FF80

Log ""
Log "ALL_CHECKS_PASS (ocm=flight_ctrl.elf ddr=flight_ctrl_ddr.elf)"
exit 0
