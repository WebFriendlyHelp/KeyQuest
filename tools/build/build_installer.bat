@echo off
setlocal EnableExtensions

REM Build a Windows installer for KeyQuest using Inno Setup 6
REM Usage:
REM   tools\build\build_installer.bat
REM   tools\build\build_installer.bat --nopause

set "NO_PAUSE=0"
if /I "%~1"=="--nopause" set "NO_PAUSE=1"

pushd "%~dp0\..\.."

echo ========================================
echo KeyQuest Installer Builder
echo ========================================
echo.

if not exist "dist\KeyQuest\KeyQuest.exe" (
    echo ERROR: dist\KeyQuest\KeyQuest.exe not found.
    echo Build the executable first:
    echo   tools\build\build_exe.bat
    goto :fail
)

set "ISCC_PATH="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"

if not defined ISCC_PATH (
    echo ERROR: Inno Setup compiler not found.
    echo Install Inno Setup 6 from:
    echo   https://jrsoftware.org/isdl.php
    goto :fail
)

set "APP_VERSION="
for /f "usebackq delims=" %%A in (`python -c "from modules.version import __version__; print(__version__)" 2^>nul`) do (
    set "APP_VERSION=%%A"
)
if "%APP_VERSION%"=="" (
    for /f "tokens=2 delims==" %%A in ('findstr /R /C:"__version__ *= *\".*\"" modules\version.py') do (
        set "APP_VERSION=%%~A"
    )
)
REM Cleaned OUTSIDE the block: inside it %APP_VERSION% was expanded when the
REM block was parsed, before the findstr loop set it, which left " =" behind.
if defined APP_VERSION set "APP_VERSION=%APP_VERSION:"=%"
if defined APP_VERSION set "APP_VERSION=%APP_VERSION: =%"
if "%APP_VERSION%"=="" (
    echo ERROR: Could not read the version from modules\version.py.
    echo Refusing to build an installer with a made-up version number.
    goto :fail
)

set "APP_VERSION_NUMERIC="
for /f "usebackq delims=" %%A in (`python -c "from modules.version import __version__; raw = ''.join(ch if (ch.isdigit() or ch=='.') else ' ' for ch in __version__); parts = [p for p in raw.split() if p]; joined = '.'.join('.'.join(parts).split('.')); nums = [p for p in joined.split('.') if p.isdigit()][:4]; nums += ['0'] * (4 - len(nums)); print('.'.join(nums[:4]) if nums else '1.0.0.0')" 2^>nul`) do (
    set "APP_VERSION_NUMERIC=%%A"
)
REM Without python, fall back to the version read above; Inno Setup rejects
REM it loudly if it is not numeric, instead of stamping 1.0.0.0 silently.
if "%APP_VERSION_NUMERIC%"=="" set "APP_VERSION_NUMERIC=%APP_VERSION%"

echo Building installer version %APP_VERSION% ...
"%ISCC_PATH%" /DMyAppVersion=%APP_VERSION% /DMyAppVersionNumeric=%APP_VERSION_NUMERIC% tools\build\installer\KeyQuest.iss
if errorlevel 1 goto :fail

echo.
echo Installer build complete:
echo   dist\installer\KeyQuestSetup.exe
goto :done

:fail
echo.
echo Installer build failed.
if "%NO_PAUSE%"=="0" pause
popd
exit /b 1

:done
if "%NO_PAUSE%"=="0" pause
popd
exit /b 0
