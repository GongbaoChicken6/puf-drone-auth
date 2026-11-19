# QSPI program_flash retry matrix (2026-11-15 lead)
# Usage: powershell -File build/tcl/qspi_retry_matrix.ps1 -BoardSN 210251A04F2C -BootBin D:/puf-drone-auth/build/BOOT_B_v3.bin
# Stops at first success sentinel: "Flash Operation Successful"
param(
  [Parameter(Mandatory=$true)][string]$BoardSN,
  [Parameter(Mandatory=$true)][string]$BootBin
)
$ErrorActionPreference = 'Continue'
$pf = 'D:/vivado/2026.1/Vitis/bin/program_flash.bat'
$fsbl = 'D:/puf-drone-auth/build/vitis_qspi3_192337/zc706_qspi/zynq_fsbl/build/fsbl.elf'
$logdir = 'D:/puf-drone-auth/build/logs'
$types = @(
  @{t='qspi-x4-dual_stacked'; d='128'},
  @{t='qspi-x4-single';       d='128'},
  @{t='qspi-x8-dual_parallel';d='128'},
  @{t='qspi-x4-dual_stacked'; d='256'}
)
$i = 0
foreach ($ty in $types) {
  $i++
  $log = Join-Path $logdir ('pf_retry_' + $i + '_' + $ty.t + '_' + $ty.d + '.log')
  Write-Output ('=== ATTEMPT ' + $i + ' : ' + $ty.t + ' density ' + $ty.d + ' -> ' + $log)
  & $pf -f $BootBin -fsbl $fsbl -flash_type $ty.t -flash_density $ty.d -offset 0 -verify -url tcp:localhost:3121 2>&1 | Tee-Object -FilePath $log
  if (Select-String -Path $log -Pattern 'Flash Operation Successful|Programming Successful|successfully' -Quiet) {
    Write-Output ('PF_SUCCESS_ATTEMPT=' + $i + ' TYPE=' + $ty.t)
    break
  }
  Write-Output ('PF_FAIL_ATTEMPT=' + $i)
}
Write-Output 'MATRIX_DONE'
