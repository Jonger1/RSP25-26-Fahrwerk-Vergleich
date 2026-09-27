@echo off
setlocal
rem ---------------------------------------------------------------
rem  Aero Studio - Kaskaden-Editor
rem ---------------------------------------------------------------
cd /d "%~dp0"
title Aero Studio - Kaskaden-Editor

set "VENV=%~dp0.venv"
set "VPY=%VENV%\Scripts\python.exe"

if not exist "%VPY%" (
    echo.
    echo   [FEHLER] Die Aero-Studio-Umgebung .venv wurde noch nicht angelegt.
    echo   Bitte einmal "Aero Studio.bat" starten.
    echo.
    pause
    exit /b 1
)

"%VPY%" -m aerostudio.ui.kaskade_editor

echo.
echo   Kaskaden-Editor wurde beendet.
pause
