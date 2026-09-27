@echo off
setlocal
cd /d "%~dp0"
title Aero Studio - 3D Aero-System
set "VENV=%~dp0.venv"
set "VPY=%VENV%\Scripts\python.exe"
if not exist "%VPY%" (
    echo.
    echo [FEHLER] Aero-Studio-.venv fehlt.
    echo Bitte zuerst "Aero Studio.bat" starten.
    pause
    exit /b 1
)
"%VPY%" -m aerostudio.ui.system_aero
echo.
echo 3D-Aero-System wurde beendet.
pause
