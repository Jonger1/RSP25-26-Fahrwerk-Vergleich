@echo off
setlocal
cd /d "%~dp0"
title Aero Studio - Kaskaden-Sweep
set "VENV=%~dp0.venv"
set "VPY=%VENV%\Scripts\python.exe"
if not exist "%VPY%" (
    echo [FEHLER] .venv fehlt. Bitte zuerst "Aero Studio.bat" starten.
    pause
    exit /b 1
)
"%VPY%" -m aerostudio.ui.kaskade_sweep
echo.
echo Kaskaden-Sweep wurde beendet.
pause
