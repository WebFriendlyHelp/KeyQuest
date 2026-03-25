param(
    [switch]$StrictPortable
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not $env:USERPROFILE) {
    $env:USERPROFILE = [Environment]::GetFolderPath("UserProfile")
}
if (-not $env:HOME) {
    $env:HOME = $env:USERPROFILE
}
if (-not $env:HOMEDRIVE) {
    $env:HOMEDRIVE = [System.IO.Path]::GetPathRoot($env:USERPROFILE).TrimEnd("\")
}
if (-not $env:HOMEPATH) {
    $env:HOMEPATH = $env:USERPROFILE.Substring($env:HOMEDRIVE.Length)
}
if (-not $env:LOCALAPPDATA) {
    $env:LOCALAPPDATA = Join-Path $env:USERPROFILE "AppData\Local"
}

if ($StrictPortable) {
    py -3.11 tests\run_local_updater_integration.py --strict-portable
} else {
    py -3.11 tests\run_local_updater_integration.py
}
exit $LASTEXITCODE
