Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Set-EnvIfMissing {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $currentValue = [Environment]::GetEnvironmentVariable($Name)
    if (-not [string]::IsNullOrWhiteSpace($currentValue)) {
        return
    }

    [Environment]::SetEnvironmentVariable($Name, $Value)
}

function Add-PathIfExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PathEntry
    )

    if (-not (Test-Path $PathEntry)) {
        return
    }

    $current = @($env:PATH -split ';' | Where-Object { $_ })
    if ($current -contains $PathEntry) {
        return
    }

    $env:PATH = if ([string]::IsNullOrWhiteSpace($env:PATH)) {
        $PathEntry
    } else {
        "$PathEntry;$env:PATH"
    }
}

function Add-FirstExistingPath {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Candidates
    )

    foreach ($candidate in $Candidates) {
        $resolved = Get-Item -Path $candidate -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty FullName -First 1
        if ([string]::IsNullOrWhiteSpace($resolved)) {
            continue
        }

        Add-PathIfExists -PathEntry $resolved
        return
    }
}

function Set-EnvIfInvalid {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [scriptblock]$IsInvalid,
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $currentValue = [Environment]::GetEnvironmentVariable($Name)
    if (-not (& $IsInvalid $currentValue)) {
        return
    }

    [Environment]::SetEnvironmentVariable($Name, $Value)
}

function Set-Utf8ConsoleEncoding {
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)

    try {
        [Console]::InputEncoding = $utf8NoBom
    } catch {
    }

    try {
        [Console]::OutputEncoding = $utf8NoBom
    } catch {
    }

    $global:OutputEncoding = $utf8NoBom
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$defaultUserProfile = "C:\Users\csm12"

Set-EnvIfMissing -Name "SystemRoot" -Value "C:\Windows"
Set-EnvIfMissing -Name "windir" -Value "C:\Windows"
Set-EnvIfMissing -Name "ComSpec" -Value "C:\Windows\System32\cmd.exe"
Set-EnvIfMissing -Name "USERPROFILE" -Value $defaultUserProfile
Set-EnvIfMissing -Name "LOCALAPPDATA" -Value (Join-Path $env:USERPROFILE "AppData\Local")
Set-EnvIfMissing -Name "HOME" -Value $env:USERPROFILE
Set-EnvIfMissing -Name "ProgramFiles" -Value "C:\Program Files"
Set-EnvIfMissing -Name "ProgramFiles(x86)" -Value "C:\Program Files (x86)"
Set-EnvIfMissing -Name "CommonProgramFiles" -Value "C:\Program Files\Common Files"
Set-EnvIfMissing -Name "PROCESSOR_ARCHITECTURE" -Value "AMD64"
Set-EnvIfInvalid -Name "PATHEXT" -IsInvalid {
    param($CurrentValue)
    [string]::IsNullOrWhiteSpace($CurrentValue) -or
    $CurrentValue -notmatch '(^|;)\.EXE($|;)' -or
    $CurrentValue -notmatch '(^|;)\.CMD($|;)'
} -Value ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.CPL"

Add-PathIfExists -PathEntry "C:\Windows\system32"
Add-PathIfExists -PathEntry "C:\Windows"
Add-PathIfExists -PathEntry "C:\Program Files\Git\cmd"
Add-PathIfExists -PathEntry "C:\Program Files\GitHub CLI"
Add-PathIfExists -PathEntry (Join-Path $env:LOCALAPPDATA "Programs\Python\Launcher")
Add-PathIfExists -PathEntry (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311")
Add-PathIfExists -PathEntry (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\Scripts")
Add-FirstExistingPath -Candidates @(
    (Join-Path $env:LOCALAPPDATA "OpenAI\Codex\bin"),
    (Join-Path $env:LOCALAPPDATA "dyad\app-*\resources\@vscode\ripgrep\bin")
)

Set-Utf8ConsoleEncoding
