Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "env_bootstrap.ps1")

function Get-CommandVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [string[]]$Args = @("--version")
    )

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        return [pscustomobject]@{
            Name = $Name
            Found = $false
            Detail = "missing"
        }
    }

    try {
        $output = & $Name @Args 2>&1 | Select-Object -First 1
        $detail = if ($null -eq $output -or [string]::IsNullOrWhiteSpace("$output")) {
            $command.Source
        } else {
            "$output"
        }
    } catch {
        $detail = "found at $($command.Source), but version check failed: $($_.Exception.Message)"
    }

    [pscustomobject]@{
        Name = $Name
        Found = $true
        Detail = $detail
    }
}

function Write-Section {
    param([string]$Title)
    Write-Output ""
    Write-Output "[$Title]"
}

function Get-ProcessPathDetail {
    $candidates = @(
        { [Environment]::ProcessPath },
        { (Get-Process -Id $PID -ErrorAction Stop).Path },
        { [Diagnostics.Process]::GetCurrentProcess().MainModule.FileName }
    )

    foreach ($candidate in $candidates) {
        try {
            $value = & $candidate
            if (-not [string]::IsNullOrWhiteSpace($value)) {
                return $value
            }
        } catch {
        }
    }

    return "unavailable"
}

$utf8Output = $false
if ($null -ne [Console]::OutputEncoding) {
    $utf8Output = [Console]::OutputEncoding.WebName -match "utf-8"
}

$utf8Input = $false
if ($null -ne [Console]::InputEncoding) {
    $utf8Input = [Console]::InputEncoding.WebName -match "utf-8"
}

$utf8Pipeline = $false
if ($null -ne $OutputEncoding) {
    $utf8Pipeline = $OutputEncoding.WebName -match "utf-8"
}

$pathEntries = @($env:PATH -split ";" | Where-Object { $_ })

Write-Output "KeyQuest Codex diagnostics"
Write-Output "Timestamp: $(Get-Date -Format s)"

Write-Section "Host"
Write-Output "PowerShell version: $($PSVersionTable.PSVersion)"
Write-Output "PowerShell edition: $($PSVersionTable.PSEdition)"
Write-Output "Process path: $(Get-ProcessPathDetail)"
Write-Output "Current directory: $((Get-Location).Path)"
Write-Output "UTF-8 input encoding: $utf8Input"
Write-Output "UTF-8 output encoding: $utf8Output"
Write-Output "UTF-8 pipeline encoding: $utf8Pipeline"
Write-Output "Input encoding: $([Console]::InputEncoding.WebName)"
Write-Output "Output encoding: $([Console]::OutputEncoding.WebName)"
Write-Output "Pipeline encoding: $($OutputEncoding.WebName)"

Write-Section "Environment"
foreach ($name in @(
    "SystemRoot",
    "windir",
    "ComSpec",
    "USERPROFILE",
    "LOCALAPPDATA",
    "HOME",
    "ProgramFiles",
    "ProgramFiles(x86)",
    "CommonProgramFiles",
    "PROCESSOR_ARCHITECTURE",
    "PATHEXT"
)) {
    Write-Output ("{0}={1}" -f $name, [Environment]::GetEnvironmentVariable($name))
}

Write-Section "Path"
Write-Output "PATH entries: $($pathEntries.Count)"
foreach ($entry in $pathEntries) {
    Write-Output $entry
}

Write-Section "Commands"
$checks = @(
    (Get-CommandVersion -Name "git"),
    (Get-CommandVersion -Name "gh"),
    (Get-CommandVersion -Name "py" -Args @("-3.11", "--version")),
    (Get-CommandVersion -Name "codex"),
    (Get-CommandVersion -Name "rg")
)

foreach ($check in $checks) {
    Write-Output ("{0}: found={1}; {2}" -f $check.Name, $check.Found, $check.Detail)
}

Write-Section "Repo markers"
foreach ($marker in @(".git", "pyproject.toml", "keyquest.pyw", "docs/dev/HANDOFF.md", "AGENTS.md")) {
    Write-Output ("{0}: {1}" -f $marker, (Test-Path (Join-Path (Get-Location) $marker)))
}
