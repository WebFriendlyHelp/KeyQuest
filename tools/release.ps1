param(
    [string]$CommitMessage = "",
    [switch]$SkipTests,
    [switch]$SkipLocalBuilds,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Label,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Action
    )

    Write-Host ""
    Write-Host "==> $Label" -ForegroundColor Cyan
    & $Action
}

function Invoke-GitOrThrow {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CommandLine
    )

    Invoke-Expression $CommandLine
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $CommandLine"
    }
}

function Test-Command {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-GitHubRepoFullName {
    $originUrl = git remote get-url origin 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $originUrl) {
        throw "Could not read origin remote URL."
    }

    $originUrl = $originUrl.Trim()
    if ($originUrl -match 'github\.com[:/](?<repo>[^/]+/[^/.]+?)(?:\.git)?$') {
        return $Matches.repo
    }

    throw "Could not determine GitHub repository name from origin URL: $originUrl"
}

function Wait-ForGitHubRelease {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoFullName,
        [Parameter(Mandatory = $true)]
        [string]$TagName,
        [int]$TimeoutSeconds = 1800,
        [int]$PollSeconds = 15
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $runId = $null
    $runUrl = $null

    while ((Get-Date) -lt $deadline) {
        $runJson = gh run list `
            --repo $RepoFullName `
            --workflow release.yml `
            --branch $TagName `
            --event push `
            --limit 10 `
            --json databaseId,headBranch,status,conclusion,url `
            2>$null

        if ($LASTEXITCODE -eq 0 -and $runJson) {
            $runs = $runJson | ConvertFrom-Json
            $matchingRun = $runs |
                Where-Object { $_.headBranch -eq $TagName } |
                Select-Object -First 1

            if ($null -ne $matchingRun) {
                $runId = $matchingRun.databaseId
                $runUrl = $matchingRun.url

                if ($matchingRun.status -eq "completed") {
                    if ($matchingRun.conclusion -ne "success") {
                        throw "GitHub Release workflow failed for $TagName. Run: $runUrl"
                    }

                    gh release view $TagName --repo $RepoFullName --json url 1>$null 2>$null
                    if ($LASTEXITCODE -eq 0) {
                        return
                    }
                }
            }
        }

        Start-Sleep -Seconds $PollSeconds
    }

    if ($runUrl) {
        throw "Timed out waiting for GitHub Release publication for $TagName. Latest workflow run: $runUrl"
    }

    throw "Timed out waiting for GitHub Release workflow to start for $TagName."
}

function Wait-ForGitHubWorkflow {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoFullName,
        [Parameter(Mandatory = $true)]
        [string]$Workflow,
        [Parameter(Mandatory = $true)]
        [string]$Branch,
        [Parameter(Mandatory = $true)]
        [string]$Event,
        [int]$TimeoutSeconds = 1800,
        [int]$PollSeconds = 15
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $runUrl = $null

    while ((Get-Date) -lt $deadline) {
        $runJson = gh run list `
            --repo $RepoFullName `
            --workflow $Workflow `
            --branch $Branch `
            --event $Event `
            --limit 10 `
            --json databaseId,headBranch,event,status,conclusion,url `
            2>$null

        if ($LASTEXITCODE -eq 0 -and $runJson) {
            $runs = $runJson | ConvertFrom-Json
            $matchingRun = $runs |
                Where-Object { $_.headBranch -eq $Branch -and $_.event -eq $Event } |
                Select-Object -First 1

            if ($null -ne $matchingRun) {
                $runUrl = $matchingRun.url

                if ($matchingRun.status -eq "completed") {
                    if ($matchingRun.conclusion -ne "success") {
                        throw "Workflow $Workflow failed for $Branch. Run: $runUrl"
                    }
                    return
                }
            }
        }

        Start-Sleep -Seconds $PollSeconds
    }

    if ($runUrl) {
        throw "Timed out waiting for workflow $Workflow on $Branch. Latest run: $runUrl"
    }

    throw "Timed out waiting for workflow $Workflow to start for $Branch."
}

function Assert-ReleaseAssetsPresent {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoFullName,
        [Parameter(Mandatory = $true)]
        [string]$TagName,
        [Parameter(Mandatory = $true)]
        [string[]]$ExpectedAssetNames
    )

    $releaseJson = gh release view $TagName --repo $RepoFullName --json assets,url 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $releaseJson) {
        throw "Could not read GitHub release metadata for $TagName."
    }

    $release = $releaseJson | ConvertFrom-Json
    $assetNames = @($release.assets | ForEach-Object { $_.name })
    $missing = @($ExpectedAssetNames | Where-Object { $_ -notin $assetNames })

    if ($missing.Count -gt 0) {
        $releaseUrl = $release.url
        $missingText = ($missing -join ", ")
        throw "GitHub release $TagName is missing expected assets: $missingText. Release: $releaseUrl"
    }
}

function Get-FileSha256 {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path $Path)) {
        throw "Expected file not found: $Path"
    }

    return (Get-FileHash -Path $Path -Algorithm SHA256).Hash
}

function Assert-FilesMatch {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,
        [Parameter(Mandatory = $true)]
        [string]$Packaged
    )

    $sourceHash = Get-FileSha256 -Path $Source
    $packagedHash = Get-FileSha256 -Path $Packaged

    if ($sourceHash -ne $packagedHash) {
        throw "Packaged file is stale: $Packaged does not match $Source"
    }
}

if (-not (Test-Command git)) {
    throw "git is required."
}
if (-not (Test-Command python)) {
    throw "python is required."
}
if (-not $DryRun -and -not (Test-Command gh)) {
    throw "gh is required to confirm that the GitHub Release workflow completed."
}

$version = python -c "from modules.version import __version__; print(__version__)" 2>$null
if (-not $version) {
    throw "Could not read modules/version.py"
}

$version = $version.Trim()
$tagName = "v$version"
$repoFullName = Get-GitHubRepoFullName

if (-not $CommitMessage) {
    $CommitMessage = "Release $tagName"
}

$currentBranch = git branch --show-current
if ($LASTEXITCODE -ne 0) {
    throw "Could not detect current git branch."
}
if ($currentBranch.Trim() -ne "main") {
    throw "Release script must be run from the main branch. Current branch: $currentBranch"
}

$statusBefore = git status --porcelain
if ($LASTEXITCODE -ne 0) {
    throw "Could not read git status."
}
if (-not $statusBefore) {
    throw "Working tree is clean. Make your release changes first, then run this script."
}

Invoke-Step "Require plain-language What's New update" {
    $statusLines = $statusBefore -split "`r?`n" | Where-Object { $_.Trim() }
    $hasWhatsNewChange = $false
    foreach ($line in $statusLines) {
        if ($line.Length -ge 4) {
            $path = $line.Substring(3).Trim()
            if ($path -eq "docs/user/WHATS_NEW.md") {
                $hasWhatsNewChange = $true
                break
            }
        }
    }

    if (-not $hasWhatsNewChange) {
        throw "Release requires a plain-language update in docs/user/WHATS_NEW.md before publishing."
    }
}

Invoke-Step "Require matching version and What's New entry" {
    python -c "from tools.dev.release_bump import validate_release_metadata; validate_release_metadata()" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Release requires modules/version.py and the top docs/user/WHATS_NEW.md version entry to match."
    }
}

Invoke-Step "Check release tag availability" {
    git rev-parse --verify --quiet "refs/tags/$tagName" | Out-Null
    if ($LASTEXITCODE -eq 0) {
        throw "Tag $tagName already exists locally. Update modules/version.py before releasing."
    }

    git ls-remote --exit-code --tags origin "refs/tags/$tagName" *> $null
    if ($LASTEXITCODE -eq 0) {
        throw "Tag $tagName already exists on origin. Update modules/version.py before releasing."
    }
}

Invoke-Step "Build Pages site" {
    python tools/dev/build_pages_site.py
}

if (-not $SkipTests) {
    Invoke-Step "Run test suite" {
        python -m pytest -q
    }
}

if (-not $SkipLocalBuilds) {
    Invoke-Step "Build local EXE" {
        cmd /c tools\build\build_exe.bat --nopause
    }

    Invoke-Step "Build local portable ZIP" {
        cmd /c tools\build\build_portable_zip.bat --nopause
    }

    Invoke-Step "Build local installer" {
        cmd /c tools\build\build_installer.bat --nopause
    }

    Invoke-Step "Verify packaged release docs in dist" {
        Assert-FilesMatch -Source "README.md" -Packaged "dist\KeyQuest\README.md"
        Assert-FilesMatch -Source "README.html" -Packaged "dist\KeyQuest\README.html"
        Assert-FilesMatch -Source "docs\user\WHATS_NEW.md" -Packaged "dist\KeyQuest\docs\WHATS_NEW.md"
        Assert-FilesMatch -Source "README.md" -Packaged "dist\KeyQuest\docs\README.md"
        Assert-FilesMatch -Source "README.html" -Packaged "dist\KeyQuest\docs\README.html"
    }
}

if ($DryRun) {
    Write-Host ""
    Write-Host "Dry run complete." -ForegroundColor Yellow
    Write-Host "Would commit with message: $CommitMessage"
    Write-Host "Would push branch: main"
    Write-Host "Would create and push tag: $tagName"
} else {
    Invoke-Step "Commit release changes" {
        Invoke-GitOrThrow "git add -A"
        Invoke-GitOrThrow "git commit -m `"$CommitMessage`""
    }

    Invoke-Step "Push main" {
        Invoke-GitOrThrow "git push origin main"
    }

    Invoke-Step "Create release tag" {
        Invoke-GitOrThrow "git tag -a $tagName -m `"KeyQuest $version`""
    }

    Invoke-Step "Push release tag" {
        Invoke-GitOrThrow "git push origin $tagName"
    }

    Invoke-Step "Wait for GitHub Release publication" {
        Wait-ForGitHubRelease -RepoFullName $repoFullName -TagName $tagName
    }

    Invoke-Step "Verify published release assets" {
        Assert-ReleaseAssetsPresent `
            -RepoFullName $repoFullName `
            -TagName $tagName `
            -ExpectedAssetNames @(
                "KeyQuest-win64.zip",
                "KeyQuest-win64.zip.sha256",
                "KeyQuestSetup.exe",
                "KeyQuestSetup.exe.sha256"
            )
    }

    Invoke-Step "Wait for updater smoke test" {
        Wait-ForGitHubWorkflow `
            -RepoFullName $repoFullName `
            -Workflow "update-smoke-test.yml" `
            -Branch $tagName `
            -Event "release"
    }
}

Write-Host ""
Write-Host "Release submitted successfully." -ForegroundColor Green
Write-Host "Version: $version"
Write-Host "Tag: $tagName"
Write-Host "GitHub Pages will update from main."
Write-Host "GitHub Release is published and visible to the updater."
