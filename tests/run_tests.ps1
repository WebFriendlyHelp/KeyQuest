$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$logsDir = Join-Path $PSScriptRoot "logs"
$logPath = Join-Path $logsDir "pytest.log"

New-Item -ItemType Directory -Force $logsDir | Out-Null

Push-Location $repoRoot
try {
  python -m pytest -q 2>&1 | Tee-Object -FilePath $logPath
  exit $LASTEXITCODE
} finally {
  Pop-Location
}
