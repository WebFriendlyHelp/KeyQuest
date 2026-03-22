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

python -m pytest --version 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warning "pytest not found. The pre-push hook requires pytest to run tests before pushing a release tag. Install it with: pip install pytest"
}

python -m ruff --version 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warning "ruff not found. The pre-push hook requires ruff to lint before pushing a release tag. Install it with: pip install ruff"
}
