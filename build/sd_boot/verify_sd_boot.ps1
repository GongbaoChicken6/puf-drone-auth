# verify_sd_boot.ps1 -- offline acceptance check for the SD-boot deliverables (2026-11-19)
# Every check is a positive sentinel: on success it prints "xxx=PASS".
# Run:  powershell -ExecutionPolicy Bypass -File .\verify_sd_boot.ps1
# Log:  .\verify_report_20261119.txt
$ErrorActionPreference = 'Stop'
$here   = $PSScriptRoot
$bootgen = 'D:\vivado\2026.1\Vitis\bin\bootgen.bat'
$report = Join-Path $here 'verify_report_20261119.txt'
if (Test-Path $report) { Remove-Item $report -Force }
$script:fails = 0
function Say([string]$s) { Write-Host $s; Add-Content -Path $report -Value $s }
function Check([string]$name, [bool]$ok, [string]$detail) {
    if ($ok) { Say ("{0}=PASS  {1}" -f $name, $detail) }
    else     { Say ("{0}=FAIL  {1}" -f $name, $detail); $script:fails++ }
}
function Sha([string]$p) { if (-not (Test-Path $p)) { return 'MISSING' }; (Get-FileHash $p -Algorithm SHA256).Hash }

Say ("verify time: " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
Say ("dir: " + $here)

# ---- expected hashes (frozen at delivery; any rebuild must update them deliberately) ----
$expFsbl = 'B893A313997A92E97BD8BB108332A3F068D0442B0EA967093E40D940C57B478E'
$expBit  = '504B042D85E028E6F7101A98A00CA5EF8C0DA9C857277DFE1B1F0C1ECE421958'
$expElf  = '36810A5A4A0D3A1C1FA65E566F46FA9413E56AEB2DF1337DAD23E7FD95497D36'
$expFinal= 'A9441C80E43D6E11206F480755E81480D16F022DFC765A72F0D560CB835DDB0C'
$expStage1='3053A6EE752666D28CACAB2BB9C3B2D50C37DF43EF8A896985FD822DC47C39DC'
$expBoardB='F5A1473A36BB7716AF09C8AFD425071CD2DD3052E331E3893DE0C86429026991'

# ---- C1..C3 inputs ----
Check 'C1_FSBL'  ((Sha (Join-Path $here 'fsbl_zc706.elf')) -eq $expFsbl) 'fsbl_zc706.elf sha256'
Check 'C2_BIT_V4' ((Sha (Join-Path $here 'w3_top_zc706_v4.bit')) -eq $expBit) 'v4 ARM bitstream sha256'
Check 'C3_FC_ELF' ((Sha (Join-Path $here 'flight_ctrl_ddr.elf')) -eq $expElf) 'flight controller DDR ELF sha256'

# ---- C4 final image ----
$finalPath = Join-Path $here 'BOOT_SD_FINAL_V4_FC.bin'
Check 'C4_FINAL_SHA' ((Sha $finalPath) -eq $expFinal) 'BOOT_SD_FINAL_V4_FC.bin sha256'
Check 'C4_FINAL_LEN' ((Test-Path $finalPath) -and ((Get-Item $finalPath).Length -eq 13410976)) 'size==13410976'

# ---- C5 partition table ----
$rd = (& $bootgen -read $finalPath -arch zynq | Out-String)
Check 'C5_IMG_COUNT' ($rd -match 'total_images \(0x04\) : 0x00000003') 'boot image holds 3 partitions'
Check 'C5_NAME_FSBL' ($rd -match 'IMAGE HEADER \(fsbl_zc706\.elf\)') 'partition 1 = fsbl'
Check 'C5_NAME_BIT'  ($rd -match 'IMAGE HEADER \(w3_top_zc706_v4\.bit\)') 'partition 2 = v4 bit'
Check 'C5_NAME_ELF'  ($rd -match 'IMAGE HEADER \(flight_ctrl_ddr\.elf\)') 'partition 3 = fc elf'
$blocks  = $rd -split 'PARTITION HEADER TABLE'
$fcBlock = ($blocks | Where-Object { $_ -match 'flight_ctrl_ddr\.elf\.0' } | Out-String)
Check 'C5_ELF_LOAD' ($fcBlock -match 'load_addr \(0x0c\) : 0x10000000') 'fc elf load addr 0x10000000'

# ---- C6 app payload inside the image ----
$img = [IO.File]::ReadAllBytes($finalPath)
$appOff = 0x332700 * 4
$spInImage = [BitConverter]::ToUInt32($img, $appOff + 0x28)
Check 'C6_ELF_SP' ($spInImage -eq 0x1000FF80) ('sp literal in image = 0x{0:X8}' -f $spInImage)
$needle = [Text.Encoding]::ASCII.GetBytes('PUF Drone Flight Controller')
$found = $false
for ($i = $appOff; $i -le $img.Length - $needle.Length; $i++) {
    $ok = $true
    for ($j = 0; $j -lt $needle.Length; $j++) { if ($img[$i + $j] -ne $needle[$j]) { $ok = $false; break } }
    if ($ok) { $found = $true; break }
}
Check 'C6_ELF_BANNER' $found 'fc banner string present in app partition'

# ---- C7 stage1 image (bit only) ----
$stage1 = Join-Path $here 'BOOT_SD_STAGE1_V4.bin'
Check 'C7_STAGE1_SHA' ((Sha $stage1) -eq $expStage1) 'BOOT_SD_STAGE1_V4.bin sha256'
$s1 = [IO.File]::ReadAllBytes($stage1)
$found1 = $false
for ($i = 0; $i -le $s1.Length - $needle.Length; $i++) {
    $ok = $true
    for ($j = 0; $j -lt $needle.Length; $j++) { if ($s1[$i + $j] -ne $needle[$j]) { $ok = $false; break } }
    if ($ok) { $found1 = $true; break }
}
Check 'C7_STAGE1_NO_ELF' (-not $found1) 'stage1 must NOT contain the fc banner (bit-only image)'

# ---- C8 toolchain reproduces the SD-verified teacher image ----
$ref  = Join-Path $here 'REF_BOOT_verified.bin'
$rep2 = Join-Path $here 'REPRO2_BOOT.bin'
if ((Test-Path $ref) -and (Test-Path $rep2)) {
    $a = [IO.File]::ReadAllBytes($ref); $b = [IO.File]::ReadAllBytes($rep2)
    $diff = @()
    $n = [Math]::Min($a.Length, $b.Length)
    for ($i = 0; $i -lt $n; $i++) { if ($a[$i] -ne $b[$i]) { $diff += $i } }
    $want = @(0xAA71, 0xAA73, 0xAA74, 0xAA77)
    $sameSet = ($diff.Count -eq 4)
    if ($sameSet) { foreach ($k in 0..3) { if ($diff[$k] -ne $want[$k]) { $sameSet = $false } } }
    Check 'C8_REPRO_VERIFIED' ($a.Length -eq $b.Length -and $sameSet) ('diff vs teacher image = {0} bytes (expect 4: FSBL __TIME__ only)' -f $diff.Count)
} else {
    Check 'C8_REPRO_VERIFIED' $false 'REF_BOOT_verified.bin / REPRO2_BOOT.bin missing'
}

# ---- C9 board B image ----
$boardB = Join-Path $here 'BOOT_SD_BOARDB_SEED2.bin'
Check 'C9_BOARDB_SHA' ((Sha $boardB) -eq $expBoardB) 'BOOT_SD_BOARDB_SEED2.bin sha256'
$rdB = (& $bootgen -read $boardB -arch zynq | Out-String)
Check 'C9_BOARDB_2PART' ($rdB -match 'total_images \(0x04\) : 0x00000002') 'board B image holds 2 partitions'

Say ''
if ($script:fails -eq 0) { Say 'ALL_CHECKS_PASS' ; exit 0 } else { Say ("FAILED_CHECKS=" + $script:fails); exit 1 }
