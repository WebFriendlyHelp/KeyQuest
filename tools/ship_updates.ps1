param(
    [ValidateSet("auto", "patch", "minor", "major")]
    [string]$Bump = "auto",
    [string]$CommitMessage = "",
    [switch]$SkipTests,
    [switch]$SkipLocalBuilds,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git is required."
}
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "py launcher is required."
}

$status = git status --porcelain
if ($LASTEXITCODE -ne 0) {
    throw "Could not read git status."
}
if (-not $status) {
    throw "Working tree is clean. Make your release changes first."
}

if ($Bump -eq "auto") {
    $Bump = (py -3.11 tools/dev/release_bump.py --suggest).Trim()
    if (-not $Bump) {
        throw "Could not determine automatic version bump."
    }
}

$oldVersion = (py -3.11 -c "from modules.version import __version__; print(__version__)").Trim()
if (-not $oldVersion) {
    throw "Could not read current version."
}

$newVersion = (py -3.11 tools/dev/release_bump.py --apply $Bump).Trim()
if (-not $newVersion) {
    throw "Could not apply version bump."
}

Write-Host ""
Write-Host "Selected bump: $Bump" -ForegroundColor Cyan
Write-Host "Version: $oldVersion -> $newVersion" -ForegroundColor Cyan

if (-not $CommitMessage) {
    $CommitMessage = "Release v$newVersion"
}

$releaseArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", "tools/release.ps1",
    "-CommitMessage", $CommitMessage
)

if ($SkipTests) {
    $releaseArgs += "-SkipTests"
}
if ($SkipLocalBuilds) {
    $releaseArgs += "-SkipLocalBuilds"
}
if ($DryRun) {
    $releaseArgs += "-DryRun"
}

& powershell @releaseArgs
if ($LASTEXITCODE -ne 0) {
    throw "Release failed after bumping to $newVersion."
}
