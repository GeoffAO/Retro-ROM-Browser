@echo off
setlocal enabledelayedexpansion
REM ─────────────────────────────────────────────────────────────────────────────
REM  RetroBat ROM Browser — Launcher
REM  Checks Python and dependencies, installs missing ones, then starts the app.
REM ─────────────────────────────────────────────────────────────────────────────

echo.
echo ============================================================
echo   RetroBat ROM Browser
echo ============================================================
echo.

REM ── Check Python is installed ─────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not on PATH.
    echo.
    echo   Please install Python 3.12 from:
    echo   https://www.python.org/downloads/release/python-3120/
    echo.
    echo   During install, tick "Add Python to PATH".
    echo   Then run this file again.
    echo.
    pause
    exit /b 1
)

REM ── Check Python version is 3.10-3.12 ────────────────────────────────────────
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
for /f "tokens=1,2 delims=." %%a in ("!PYVER!") do (
    set PYMAJ=%%a
    set PYMIN=%%b
)
if !PYMAJ! NEQ 3 goto :bad_version
if !PYMIN! LSS 10 goto :bad_version
if !PYMIN! GTR 12 goto :bad_version
echo Python !PYVER! ... OK
goto :version_ok

:bad_version
echo ERROR: Python 3.10, 3.11, or 3.12 is required.
echo        You have Python !PYVER!.
echo.
echo   PyQt6 does not yet support Python 3.13 or 3.14.
echo   Please install Python 3.12 from:
echo   https://www.python.org/downloads/release/python-3120/
echo.
pause
exit /b 1

:version_ok

REM ── Check each required package, install if missing ───────────────────────────
echo Checking dependencies...
echo.
set MISSING=0

python -c "import PyQt6" >nul 2>&1
if errorlevel 1 (echo   PyQt6  ... missing - will install & set MISSING=1) else echo   PyQt6  ... OK

python -c "import PIL" >nul 2>&1
if errorlevel 1 (echo   Pillow ... missing - will install & set MISSING=1) else echo   Pillow ... OK

python -c "import lxml" >nul 2>&1
if errorlevel 1 (echo   lxml   ... missing - will install & set MISSING=1) else echo   lxml   ... OK

if !MISSING!==1 (
    echo.
    echo Installing missing packages ^(one-time, requires internet^)...
    python -m pip install PyQt6 Pillow lxml --no-warn-script-location
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to install packages.
        echo        Check your internet connection and try again.
        echo        Or install manually:  pip install PyQt6 Pillow lxml
        echo.
        pause
        exit /b 1
    )
    echo Packages installed OK.
)

REM ── Launch ────────────────────────────────────────────────────────────────────
echo.
echo Starting...
cd /d "%~dp0"
start "" pythonw main.py
echo.
echo TIP: Double-click "Create Shortcut.vbs" to add a desktop icon you can pin to the taskbar.
endlocal
