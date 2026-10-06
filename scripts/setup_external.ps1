# setup_external.ps1 -- Clone external reference repos
# Usage: .\scripts\setup_external.ps1
# Run once after cloning the main repo

$repos = @(
    @{ Name = "fpga_puf";       Url = "https://github.com/stnolting/fpga_puf.git" },
    @{ Name = "PUF-lab";        Url = "https://github.com/eriksargent/PUF-lab.git" },
    @{ Name = "c_library_v2";   Url = "https://github.com/mavlink/c_library_v2.git" },
    @{ Name = "puf-esp32-auth"; Url = "https://github.com/xtncl/esp32-sram-puf-authentication.git" }
)

$extDir = Join-Path $PSScriptRoot "..\external"
New-Item -ItemType Directory -Force $extDir | Out-Null

foreach ($repo in $repos) {
    $dest = Join-Path $extDir $repo.Name
    if (Test-Path $dest) {
        Write-Host "  [SKIP] $($repo.Name)"
    } else {
        Write-Host "  [CLONE] $($repo.Name)"
        git clone --depth 1 $repo.Url $dest
    }
}
Write-Host "External repos ready."
