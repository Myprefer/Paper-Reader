@echo off
chcp 65001 >nul
echo ===================================
echo   PaperReader - Build
echo ===================================
echo.

REM === Step 1: Build frontend ===
echo [1/3] Building frontend...
cd frontend
call npx vite build
if errorlevel 1 (
    echo [FAIL] Frontend build failed!
    pause
    exit /b 1
)
cd ..
echo [OK] Frontend built
echo.

@REM REM === Step 2: Generate icon ===
@REM echo [2/4] Generating app icon...
@REM D:/ProgramData/miniconda3/envs/pytorch/python.exe scripts/generate_icon.py
@REM echo [OK] Icon generated
@REM echo.

REM === Step 3: PyInstaller ===
echo [2/3] PyInstaller packaging...
D:/ProgramData/miniconda3/envs/pytorch/python.exe -m pip install pyinstaller --quiet 2>nul
D:/ProgramData/miniconda3/envs/pytorch/python.exe -m PyInstaller build.spec --clean -y
if errorlevel 1 (
    echo [FAIL] PyInstaller failed!
    pause
    exit /b 1
)
echo [OK] PyInstaller done
echo.

REM === Step 4: Installer (optional) ===
echo [3/3] Building Windows installer...
set "ISCC="
REM Try common install paths
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files (x86)\Inno Setup 7\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 7\ISCC.exe"
if exist "C:\Program Files\Inno Setup 7\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 7\ISCC.exe"
if exist "D:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=D:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "D:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=D:\Program Files\Inno Setup 6\ISCC.exe"
if exist "D:\Program Files (x86)\Inno Setup 7\ISCC.exe" set "ISCC=D:\Program Files (x86)\Inno Setup 7\ISCC.exe"
if exist "D:\Program Files\Inno Setup 7\ISCC.exe" set "ISCC=D:\Program Files\Inno Setup 7\ISCC.exe"

if defined ISCC (
    "%ISCC%" installer.iss
    if errorlevel 1 (
        echo [WARN] Installer build failed, but PyInstaller output is usable
    ) else (
        echo [OK] Installer built
    )
) else (
    echo [WARN] Inno Setup not found, skipping installer
    echo        Install Inno Setup then run: ISCC.exe installer.iss
    echo        Download: https://jrsoftware.org/isdl.php
)
echo.

echo ===================================
echo   Build complete!
echo.
echo   Portable:   dist\PaperReader\PaperReader.exe
echo               (run directly)
echo.
if defined ISCC (
    echo   Installer:  installer_output\PaperReader_Setup_1.1.0.exe
    echo               (install to system)
    echo.
)
echo   User data:  %%USERPROFILE%%\Documents\PaperReader\
echo ===================================
pause
