@echo off
REM RetroBat ROM Browser — Developer build script (requires Python 3.10-3.12)
echo.
python -m pip install PyQt6 Pillow lxml pyinstaller --quiet --no-warn-script-location
if errorlevel 1 ( echo ERROR: pip install failed & pause & exit /b 1 )
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist
python -m PyInstaller retrobat_browser.spec --noconfirm
if errorlevel 1 ( echo ERROR: PyInstaller failed & pause & exit /b 1 )
echo.
echo Done. Output: dist\RetroBat ROM Browser\RetroBat ROM Browser.exe
pause
