Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repoRoot

$hooksPath = ".githooks"

git config core.hooksPath $hooksPath
if ($LASTEXITCODE -ne 0) {
    throw "Could not set git hooks path to $hooksPath."
}

Write-Host "Configured git hooks path: $hooksPath" -ForegroundColor Green

py -3.11 -m pytest --version 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warning "pytest for Python 3.11 not found. The pre-push hook requires py -3.11 -m pytest before pushing a release tag."
}

py -3.11 -m ruff --version 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warning "ruff for Python 3.11 not found. The pre-push hook requires py -3.11 -m ruff before pushing a release tag."
}
