$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "env_bootstrap.ps1")

$repoRoot = Split-Path -Parent $PSScriptRoot
$testsDir = Join-Path $repoRoot "tests"
$logsDir = Join-Path $testsDir "logs"
$logPath = Join-Path $logsDir "quality_checks.log"

New-Item -ItemType Directory -Force $logsDir | Out-Null

function Run-Step([string]$name, [scriptblock]$command, [switch]$QuietOnSuccess) {
  "=== $name ===" | Out-File -FilePath $logPath -Append -Encoding utf8
  $prevErrorActionPreference = $ErrorActionPreference
  $prevNativeErrorSetting = $null
  if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -Scope Global -ErrorAction SilentlyContinue) {
    $prevNativeErrorSetting = $PSNativeCommandUseErrorActionPreference
    $PSNativeCommandUseErrorActionPreference = $false
  }
  $ErrorActionPreference = "Continue"

  $output = @(& $command *>&1)
  $exitCode = $LASTEXITCODE
  $output | Out-File -FilePath $logPath -Append -Encoding utf8

  $ErrorActionPreference = $prevErrorActionPreference
  if ($null -ne $prevNativeErrorSetting) {
    $PSNativeCommandUseErrorActionPreference = $prevNativeErrorSetting
  }

  if ($exitCode -ne 0) {
    $output | Out-Host
    throw "$name failed with exit code $exitCode"
  }
  if (-not $QuietOnSuccess) {
    $output | Out-Host
  }
  "" | Out-File -FilePath $logPath -Append -Encoding utf8
}

Push-Location $repoRoot
try {
  "=== Quality checks: $(Get-Date -Format o) ===" | Out-File -FilePath $logPath -Append -Encoding utf8

  Run-Step "Syntax check (compileall)" { py -3.11 -m compileall -q keyquest.pyw modules games ui 2>&1 }

  Run-Step "Lint (ruff: undefined names + syntax)" {
    if (-not (Get-Command ruff -ErrorAction SilentlyContinue)) { py -3.11 -m pip install ruff 2>&1 }
    ruff check --select F821,F822,F823,E9 keyquest.pyw modules games ui tests 2>&1
  }

  Run-Step "Unit tests (pytest)" { py -3.11 -m pytest -q 2>&1 } -QuietOnSuccess

  Run-Step "Release metadata" { py -3.11 tools/dev/release_bump.py --validate 2>&1 }

  Run-Step "Contrast audit" {
    $prevPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = $repoRoot
    try {
      py -3.11 tools/quality/check_contrast.py 2>&1
    } finally {
      $env:PYTHONPATH = $prevPythonPath
    }
  }

  Run-Step "Clean caches" { powershell -ExecutionPolicy Bypass -File tools/clean_caches.ps1 2>&1 }

  Write-Host "All checks passed. Log: $logPath"
} finally {
  Pop-Location
}
