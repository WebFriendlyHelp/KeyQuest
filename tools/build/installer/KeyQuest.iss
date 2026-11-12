; KeyQuest Inno Setup script
; Build with:
;   tools\build\build_installer.bat

#define MyAppName "KeyQuest"
#define MyAppPublisher "Web Friendly Help"
#define MyAppURL "https://webfriendlyhelp.com"
#define MyAppExeName "KeyQuest.exe"

#ifndef MyAppVersion
  #define MyAppVersion "1.0"
#endif

#ifndef MyAppVersionNumeric
  #define MyAppVersionNumeric "1.0.0.0"
#endif

[Setup]
AppId={{8EE865FD-6D3E-46F9-A36B-4A2A383B8C25}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName}
VersionInfoVersion={#MyAppVersionNumeric}
VersionInfoProductVersion={#MyAppVersionNumeric}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
ShowLanguageDialog=no
DisableWelcomePage=yes
DisableDirPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\..\dist\installer
OutputBaseFilename=KeyQuestSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
; Authenticode, when build_installer.bat passes /DSign and the "wfh" sign tool.
#ifdef Sign
SignTool=wfh
SignedUninstaller=yes
#endif
ArchitecturesAllowed=x86compatible or x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; Sentences\ is the user's folder. Overwriting it here (as this line once did)
; replaced every edited sentence file whenever the installer was run by hand,
; for example after the updater's third fallback. The shipped set goes to
; Sentences only on a first install; otherwise it is staged in
; _sentences_incoming and modules\sentence_merge.py decides per file at the
; next start. The leading backslash in Excludes anchors the pattern at the top
; of the tree, so defaults\Sentences is still installed.
Source: "..\..\..\dist\KeyQuest\*"; DestDir: "{app}"; Excludes: "\Sentences\*"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\..\..\dist\KeyQuest\Sentences\*"; DestDir: "{app}\Sentences"; Flags: recursesubdirs createallsubdirs ignoreversion; Check: IsFirstSentencesInstall
Source: "..\..\..\dist\KeyQuest\Sentences\*"; DestDir: "{app}\_sentences_incoming"; Flags: recursesubdirs createallsubdirs ignoreversion; Check: not IsFirstSentencesInstall
Source: "..\..\..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion

[UninstallDelete]
; Uninstall removes everything KeyQuest wrote, not just what Setup copied
; (Casey, 2026-11-11: "uninstall should remove everything"). Inno runs these
; only from the uninstaller. Updates never run it: the in-app updater and a
; by-hand KeyQuestSetup.exe both install over the top, so progress stays.
; Each entry names something KeyQuest owns; {app} itself is not deleted
; wholesale, because /DIR= can point Setup at a folder that holds other files.
; tests\test_uninstall_removes_everything.py checks this list against the code.
; Left on purpose (1.28.1 review): %TEMP%\gen_py, pywin32's cache shared by
; every frozen Python 3.11 program; and the Downloads folder, where KeyQuest
; puts problem reports and re-downloaded updates for the learner to keep.
; {%TEMP} is Inno's TEMP for this user. Python's tempfile prefers TMPDIR when
; it is set, so on such a machine the two TEMP entries miss; both are
; KeyQuest-named, so a miss never deletes anything else.
; No dirifempty for {app}: these run before unins000.exe leaves the folder,
; so it could never be empty here. Setup created {app}, and the uninstaller
; undoes that last; the VM checklist confirms the folder is gone.
Type: files; Name: "{app}\progress*"
Type: files; Name: "{app}\sentence_prefs.json"
Type: files; Name: "{app}\keyquest_error.log"
Type: files; Name: "{app}\keyquest_speech.log*"
Type: files; Name: "{app}\pending_update.json"
Type: files; Name: "{app}\.keyquest-installed"
Type: filesandordirs; Name: "{app}\Sentences"
Type: filesandordirs; Name: "{app}\_sentences_incoming"
Type: filesandordirs; Name: "{app}\Backups"
Type: filesandordirs; Name: "{app}\updates"
Type: filesandordirs; Name: "{%TEMP}\KeyQuestUpdater"
Type: files; Name: "{%TEMP}\keyquest_update.sha256"
; comtypes' cache for KeyQuest.exe on the pyttsx3 fallback (<exe>-<python>).
; The 311 is the Python the release is built with; change it with Python.
Type: filesandordirs; Name: "{%TEMP}\comtypes_cache\KeyQuest-311"

[Run]
Filename: "cmd.exe"; Parameters: "/c type nul > ""{app}\.keyquest-installed"""; Flags: runhidden

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Code]
var
  HadSentences: Boolean;

{ Decided once, just before any file is copied. A per-file DirExists check
  would turn false as soon as the first sentence file was installed. }
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    HadSentences := DirExists(ExpandConstant('{app}\Sentences'));
end;

function IsFirstSentencesInstall: Boolean;
begin
  Result := not HadSentences;
end;

{ Uninstall refuses while KeyQuest is open. A running copy keeps its exe
  locked and saves progress.json again after [UninstallDelete] removed it,
  leaving a half-removed folder (1.28.1 review, finding 2). KeyQuest holds
  this mutex while it runs (modules\single_instance.py, RUNNING_MUTEX_NAME).
  Not AppMutex: Setup checks that too, and the in-app updater runs Setup
  silently while the old copy is handing over. Setup itself needs nothing
  here, because CloseApplications (default yes) closes KeyQuest through
  Restart Manager before replacing its files. SuppressibleMsgBox answers
  Cancel under /SUPPRESSMSGBOXES, so a scripted uninstall stops instead of
  half-removing. }
function InitializeUninstall(): Boolean;
begin
  Result := True;
  while CheckForMutexes('KeyQuest.AppRunning') do
  begin
    if SuppressibleMsgBox('KeyQuest is still open, so it cannot be uninstalled yet.' + #13#10#13#10 +
      'Close KeyQuest, then choose Retry. If more than one copy of KeyQuest is open, close them all.' + #13#10#13#10 +
      'Choose Cancel to stop, and KeyQuest stays installed.',
      mbError, MB_RETRYCANCEL, IDCANCEL) = IDCANCEL then
    begin
      Result := False;
      Exit;
    end;
  end;
end;
