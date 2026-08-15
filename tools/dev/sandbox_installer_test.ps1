# Install KeyQuest in Windows Sandbox, upgrade over it, and prove the user's
# own sentence files survive.
#
# STATUS 2026-08-15: DOES NOT CURRENTLY WORK, and the reason is not in this
# script. Nothing inside the sandbox ever runs. Four ways were tried on
# Windows 11 26200: LogonCommand twice (once plain, once via cmd with a
# delay), a script mapped onto the sandbox account's per-user Startup folder,
# and one mapped onto the machine-wide Startup folder under ProgramData. Every
# run booted to a desktop and sat there, results folder empty, for five to ten
# minutes. Mapped folders themselves are fine: the container refuses to start
# if a HostFolder is missing, and it started every time.
#
# This matches microsoft/Windows-Sandbox issue 125, "LogonCommand never
# executes (no process spawned) while MappedFolders works normally", opened
# 2026-07-27 and closed 2026-07-29. Since Windows 11 24H2 the in-box sandbox
# hands off to a Store-delivered Windows Sandbox app, which is where the
# broken command handling lives; the same app is behind the widespread
# 0x800705B4 launch timeout.
#
# That diagnostic has now been run, and it settles it. One boot with all three
# mechanisms armed at once, each writing its own marker into a writable mapped
# folder: logon command, machine-wide Startup, and per-user Startup. **No
# marker of any kind appeared.** Nothing auto-executes inside Windows Sandbox
# on this machine, so the fault is not in this script and there is nothing here
# left to fix. Re-run this tool after a Windows Sandbox app update and see
# whether the markers show up; until then, installer testing has to happen
# somewhere else.
#
# WHY THIS EXISTS. Installing on the dev machine repoints the owner's real
# uninstall registry entry at whatever folder the test used, which is why
# v1.24.0 through v1.27.1 were all checksum-verified and deliberately never
# installed. The Sentences restore path has destroyed user data before
# (`/XN` versus `/XO`, fixed 2026-08-08), and the in-app updater runs the
# installer SILENTLY OVER A LIVE INSTALL, which is the worst possible moment
# for a regression. A disposable VM is the only honest place to test that.
#
# Requires Windows Sandbox (Containers-DisposableClientVM) and, on first run,
# the GitHub CLI to fetch the installers.
#
#   powershell -ExecutionPolicy Bypass -File tools/dev/sandbox_installer_test.ps1
#   powershell -ExecutionPolicy Bypass -File tools/dev/sandbox_installer_test.ps1 -From v1.27.0 -To v1.27.1
[CmdletBinding()]
param(
  [string]$From = "v1.27.0",
  [string]$To = "v1.27.1",
  [string]$Repo = "csm120/KeyQuest",
  [switch]$KeepPayload
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command WindowsSandbox.exe -ErrorAction SilentlyContinue)) {
  throw ("Windows Sandbox is not available. Enable it with: Enable-WindowsOptionalFeature " +
         "-Online -FeatureName Containers-DisposableClientVM, then REBOOT. It does not " +
         "work until the machine has been restarted.")
}

# Public, not %TEMP%. The sandbox runs as WDAGUtilityAccount and maps host
# folders as that account; a folder under another user's private AppData tree
# is not reliably readable from inside, and the failure is silent, which cost
# a first attempt that sat there for six minutes doing nothing at all.
$work = Join-Path $env:PUBLIC "KeyQuestSandboxTest"
$payload = Join-Path $work "payload"
$results = Join-Path $work "results"
$startup = Join-Path $work "startup"
New-Item -ItemType Directory -Force -Path $payload, $results, $startup | Out-Null
Get-ChildItem $results -File -ErrorAction SilentlyContinue | Remove-Item -Force

function Get-Installer($tag, $name) {
  $target = Join-Path $payload $name
  if (Test-Path $target) { Write-Host "have $name"; return }
  if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "gh is needed to download $tag, or drop $name into $payload yourself."
  }
  Write-Host "downloading $tag"
  gh release download $tag --repo $Repo --pattern "KeyQuestSetup.exe" --output $target --clobber
  if (-not (Test-Path $target)) { throw "could not download the installer for $tag" }
}

Get-Installer $From "KeyQuestSetup_from.exe"
Get-Installer $To "KeyQuestSetup_to.exe"

# The in-sandbox script. Written out here so the whole test is one file in the
# repo rather than a script plus a loose payload nobody can find later.
$inner = @'
$ErrorActionPreference = "Continue"
$desktop = "C:\Users\WDAGUtilityAccount\Desktop"
$payload = Join-Path $desktop "payload"
$results = Join-Path $desktop "results"
$log = Join-Path $results "sandbox-test.log"
function Say($text) { Add-Content -Path $log -Value ("[{0:HH:mm:ss}] {1}" -f (Get-Date), $text) }

Set-Content -Path $log -Value "KeyQuest installer test in Windows Sandbox"
$install = "$env:LOCALAPPDATA\Programs\KeyQuest"

function Read-InstalledVersion {
  $vf = Join-Path $install "modules\version.py"
  if (-not (Test-Path $vf)) { return "(no version.py)" }
  $m = Select-String -Path $vf -Pattern '__version__\s*=\s*"([^"]+)"'
  if ($m) { return $m.Matches[0].Groups[1].Value } else { return "(unreadable)" }
}

Say "installing the FROM build"
$p = Start-Process -FilePath (Join-Path $payload "KeyQuestSetup_from.exe") `
  -ArgumentList "/CURRENTUSER", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait -PassThru
Say "exit code: $($p.ExitCode)"
Say "install folder exists: $(Test-Path $install)"
Say "version after fresh install: $(Read-InstalledVersion)"

$sentences = Join-Path $install "Sentences"
Say "Sentences folder exists: $(Test-Path $sentences)"
New-Item -ItemType Directory -Force -Path $sentences | Out-Null
Say "shipped sentence files: $(@(Get-ChildItem $sentences -File).Count)"

# The two cases an upgrade has to preserve: a file only the user has, and a
# shipped file the user has edited.
$userFile = Join-Path $sentences "My Own Practice Sentences.txt"
Set-Content -Path $userFile -Encoding UTF8 -Value "sentences a user typed themselves`nDO NOT LOSE THIS LINE"
$userHash = (Get-FileHash $userFile -Algorithm SHA256).Hash
Say "seeded user file, sha256 $userHash"
$shipped = Get-ChildItem $sentences -File | Where-Object { $_.Name -ne "My Own Practice Sentences.txt" } | Select-Object -First 1
if ($shipped) { Add-Content -Path $shipped.FullName -Value "USER ADDED LINE"; Say "edited shipped file: $($shipped.Name)" }

Say "upgrading over the live install, the way the in-app updater does"
$p2 = Start-Process -FilePath (Join-Path $payload "KeyQuestSetup_to.exe") `
  -ArgumentList "/CURRENTUSER", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=$install" -Wait -PassThru
Say "exit code: $($p2.ExitCode)"
Say "version after upgrade: $(Read-InstalledVersion)"

if (Test-Path $userFile) {
  $after = (Get-FileHash $userFile -Algorithm SHA256).Hash
  Say "USER FILE SURVIVED: $($after -eq $userHash)"
} else {
  Say "USER FILE LOST: the upgrade deleted it"
}
if ($shipped) {
  if (Test-Path $shipped.FullName) {
    Say "edit to shipped file kept: $(((Get-Content $shipped.FullName -Raw) -match 'USER ADDED LINE'))"
  } else {
    Say "shipped file gone entirely: $($shipped.Name)"
  }
}
Say "sentence files after upgrade: $(@(Get-ChildItem $sentences -File -ErrorAction SilentlyContinue).Count)"

$entry = Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
                          "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*" -ErrorAction SilentlyContinue |
         Where-Object { $_.DisplayName -like "*KeyQuest*" }
if ($entry) {
  Say "uninstall entry: $($entry.DisplayName) version $($entry.DisplayVersion)"
  Say "uninstall string: $($entry.UninstallString)"
} else {
  Say "NO uninstall registry entry found"
}
Say "DONE"
'@
Set-Content -Path (Join-Path $payload "run_test.ps1") -Value $inner -Encoding UTF8

# LogonCommand is NOT used, and that is not a style choice.
#
# Windows Sandbox has a bug where LogonCommand never executes at all, no
# process is spawned, while MappedFolders in the same file works perfectly:
# microsoft/Windows-Sandbox issue 125, opened 2026-07-27, closed 2026-07-29.
# It cost two silent five-minute boots here before the cause was found, with a
# VM sitting at an empty desktop doing nothing. The workaround from that issue
# is to map a folder onto a Startup directory and let the ordinary Windows
# logon mechanism run the script.
#
# It is mapped onto the MACHINE-WIDE Startup folder under ProgramData, not the
# per-user one under the sandbox account's AppData. The per-user path was tried
# first and never fired, which fits: that profile is created during logon, so a
# folder mapped onto it is competing with profile creation. ProgramData exists
# before anybody logs on.
$launcher = @"
@echo off
powershell.exe -ExecutionPolicy Bypass -File C:\Users\WDAGUtilityAccount\Desktop\payload\run_test.ps1 > C:\Users\WDAGUtilityAccount\Desktop\results\console.txt 2>&1
"@
Set-Content -Path (Join-Path $startup "run_keyquest_test.cmd") -Value $launcher -Encoding ASCII

$wsb = Join-Path $work "keyquest-installer-test.wsb"
@"
<Configuration>
  <VGpu>Disable</VGpu>
  <Networking>Disable</Networking>
  <MappedFolders>
    <MappedFolder>
      <HostFolder>$payload</HostFolder>
      <SandboxFolder>C:\Users\WDAGUtilityAccount\Desktop\payload</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>$results</HostFolder>
      <SandboxFolder>C:\Users\WDAGUtilityAccount\Desktop\results</SandboxFolder>
      <ReadOnly>false</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>$startup</HostFolder>
      <SandboxFolder>C:\ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
  </MappedFolders>
</Configuration>
"@ | Set-Content -Path $wsb -Encoding UTF8

Write-Host "starting Windows Sandbox; a VM window will open and run the test by itself"
Start-Process -FilePath "WindowsSandbox.exe" -ArgumentList $wsb

$logFile = Join-Path $results "sandbox-test.log"
$deadline = (Get-Date).AddMinutes(10)
while ((Get-Date) -lt $deadline) {
  Start-Sleep -Seconds 5
  if (Test-Path $logFile) {
    $text = Get-Content $logFile -Raw
    if ($text -match "DONE") { break }
  }
}

if (Test-Path $logFile) {
  Write-Host "--- result ($logFile)"
  Get-Content $logFile
  $text = Get-Content $logFile -Raw
  if ($text -notmatch "DONE") { Write-Host "TEST DID NOT FINISH within 10 minutes" }
  if ($text -match "USER FILE LOST" -or $text -match "USER FILE SURVIVED: False") {
    Write-Host "FAILED: user data did not survive the upgrade"
    exit 1
  }
} else {
  Write-Host "no result file; the sandbox may still be starting, or the logon command did not run"
  exit 2
}

Write-Host "Close the sandbox window when you are done; everything in it is discarded."
if (-not $KeepPayload) { Write-Host "Installers kept at $payload for the next run." }
