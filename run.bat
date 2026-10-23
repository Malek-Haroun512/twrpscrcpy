@echo off
rem Start twrpscrcpy on Windows (requires Python, PySide6, numpy, adb in PATH).
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
    python -m twrpscrcpy %*
) else (
    py -3 -m twrpscrcpy %*
)
