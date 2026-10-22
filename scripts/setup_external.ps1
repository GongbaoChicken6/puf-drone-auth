# setup_external.ps1 -- Clone the four external reference repos at the commits
# recorded in the repository index (gitlink entries).
# Usage: .\scripts\setup_external.ps1
# Run once after cloning the main repo. If you cloned with
#   git clone --recurse-submodules <url>
# the four repos are already present and this script will skip them.

$ErrorActionPreference = "Stop"

# Pinned commits MUST stay in sync with: git ls-tree HEAD external/
$repos = @(
    @{ Name = "fpga_puf";       Url = "https://github.com/stnolting/fpga_puf.git";                 Commit = "d1d50c0e10c30fcd7e2338910fdfa8686927b6e9" },
    @{ Name = "PUF-lab";        Url = "https://github.com/eriksargent/PUF-lab.git";                Commit = "4a1f8aa7d84d4e081a1e02ad64d56542eef2f7ac" },
    @{ Name = "c_library_v2";   Url = "https://github.com/mavlink/c_library_v2.git";               Commit = "56f6435ee725ed15d2e6d2a4c97ab6b41886ffc9" },
    @{ Name = "puf-esp32-auth"; Url = "https://github.com/xtncl/esp32-sram-puf-authentication.git"; Commit = "9ff36f6417c583bc51d7b913ae73f2e92422653a" }
)

$extDir = Join-Path $PSScriptRoot "..\external"
New-Item -ItemType Directory -Force $extDir | Out-Null

$failed = @()
foreach ($repo in $repos) {
    $dest = Join-Path $extDir $repo.Name
    # An *empty* directory is what git leaves behind for an uninitialised
    # submodule: it does NOT mean the repo is present. Require a real .git.
    if (Test-Path (Join-Path $dest ".git")) {
        Write-Host "  [SKIP] $($repo.Name) already present"
        continue
    }
    if (Test-Path $dest) {
        # remove the leftover empty directory so git clone can create it
        Remove-Item $dest -Recurse -Force
    }
    Write-Host "  [CLONE] $($repo.Name)"
    git clone --quiet $repo.Url $dest
    if ($LASTEXITCODE -ne 0) { $failed += $repo.Name; continue }
    git -C $dest checkout --quiet $repo.Commit
    if ($LASTEXITCODE -ne 0) { $failed += ("$($repo.Name) (checkout $($repo.Commit))") }
}

if ($failed.Count -gt 0) {
    Write-Error "External repos FAILED: $($failed -join ', ')"
    exit 1
}
Write-Host "External repos ready (4 pinned checkouts)."
exit 0
