@echo off
REM KeyQuest - Clean Executable Build Script
REM Removes all temp files and old builds before creating fresh executable
setlocal
pushd "%~dp0\..\.."

set "NO_PAUSE="
if /I "%~1"=="--nopause" set "NO_PAUSE=1"

echo ========================================
echo KeyQuest Executable Builder
echo ========================================
echo.

REM Step 1: Clean old builds and temp files
echo [1/4] Cleaning old builds and temporary files...
if exist "build" (
    echo   Removing build/ folder...
    rmdir /s /q "build"
)
if exist "dist" (
    echo   Removing dist/ folder...
    rmdir /s /q "dist"
)
if exist "__pycache__" (
    echo   Removing __pycache__...
    rmdir /s /q "__pycache__"
)
if exist "modules\__pycache__" (
    echo   Removing modules/__pycache__...
    rmdir /s /q "modules\__pycache__"
)
if exist "games\__pycache__" (
    echo   Removing games/__pycache__...
    rmdir /s /q "games\__pycache__"
)
echo   Cleanup complete!
echo.

REM Step 2: Build executable
echo [2/4] Building executable with PyInstaller...
py -3.11 -m PyInstaller tools\build\KeyQuest-RootFolders.spec
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Build failed!
    pause
    exit /b 1
)
echo   Build complete!
echo.

REM Step 3: Verify build
echo [3/4] Verifying build...
if not exist "dist\KeyQuest\KeyQuest.exe" (
    echo ERROR: KeyQuest.exe not found in dist\KeyQuest\
    pause
    exit /b 1
)
echo   KeyQuest.exe found: dist\KeyQuest\KeyQuest.exe
echo.

REM Step 3b: Authenticode-sign KeyQuest.exe as Web Friendly Help LLC (Azure
REM Artifact Signing). Signs where the Azure CLI is signed in with the signer
REM role: Casey's machine, or the release job after azure/login. Anywhere else
REM it says NOT SIGNED; the release workflow then fails its signature check.
py -3.11 tools\build\codesign.py --can-sign
if errorlevel 1 (
    echo   NOT SIGNED: this machine cannot sign.
) else (
    py -3.11 tools\build\codesign.py "dist\KeyQuest\KeyQuest.exe"
    if errorlevel 1 (
        echo ERROR: signing KeyQuest.exe failed!
        exit /b 1
    )
)
echo.

REM Step 4: Display results
echo [4/4] Build summary:
echo   Output location: dist\KeyQuest\
echo   Executable: KeyQuest.exe
echo   Ready to distribute!
echo.

echo ========================================
echo Build Complete Successfully!
echo ========================================
echo.
echo Next steps:
echo   1. Test: dist\KeyQuest\KeyQuest.exe
echo   2. Zip dist\KeyQuest folder to distribute
echo.

if not defined NO_PAUSE pause
popd
