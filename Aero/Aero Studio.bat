@echo off
setlocal EnableDelayedExpansion
rem ---------------------------------------------------------------------
rem  Aero Studio starten
rem
rem  Doppelklick genuegt. Beim ersten Mal dauert es ein paar Minuten, weil
rem  eine eigene Python-Umgebung im Ordner .venv angelegt wird. Danach
rem  startet es in Sekunden.
rem
rem  Warum eine eigene Umgebung: Auf dem Rechner liegen mehrere
rem  Python-Versionen. Ohne feste Umgebung erwischt der Starter mal die eine,
rem  mal die andere - und installiert jedes Mal alles neu. Mit .venv ist immer
rem  dieselbe da, und das System-Python bleibt unberuehrt.
rem
rem  Das Fenster bleibt offen, weil dort die Meldungen landen.
rem  Zum Beenden: Fenster schliessen oder Strg+C.
rem ---------------------------------------------------------------------

title Aero Studio
cd /d "%~dp0"

echo.
echo   Aero Studio
echo.

set "VENV=%~dp0.venv"
set "VPY=%VENV%\Scripts\python.exe"

rem ---- Umgebung vorhanden? Dann direkt starten. ------------------------
if exist "%VPY%" goto starten

rem ---- Sonst: passenden Python suchen und Umgebung anlegen -------------
echo   Erster Start - die Arbeitsumgebung wird eingerichtet.
echo   Das dauert ein paar Minuten und passiert nur dieses eine Mal.
echo.

set "BASIS="
rem Bewusst von 3.12 abwaerts: Fuer die neuesten Python-Versionen gibt es
rem nicht immer fertige Pakete, dann muesste alles muehsam uebersetzt werden.
for %%V in (3.12 3.11 3.10 3.13) do (
    if not defined BASIS (
        py -%%V -c "import sys" >nul 2>&1
        if !errorlevel!==0 set "BASIS=py -%%V"
    )
)
if not defined BASIS (
    py -3 -c "import sys" >nul 2>&1
    if !errorlevel!==0 set "BASIS=py -3"
)
if not defined BASIS (
    python -c "import sys" >nul 2>&1
    if !errorlevel!==0 set "BASIS=python"
)

if not defined BASIS (
    echo   [FEHLER] Python wurde nicht gefunden.
    echo.
    echo   Aero Studio braucht Python 3.10 oder neuer.
    echo   Herunterladen: https://www.python.org/downloads/
    echo   Beim Installieren unbedingt "Add Python to PATH" ankreuzen.
    echo.
    pause
    exit /b 1
)

for /f "delims=" %%A in ('%BASIS% -c "import sys;print(sys.version.split()[0])"') do set "VER=%%A"
echo   Verwendet wird Python %VER%.
echo.

%BASIS% -m venv "%VENV%"
if %errorlevel% neq 0 (
    echo.
    echo   [FEHLER] Die Umgebung liess sich nicht anlegen.
    pause
    exit /b 1
)

echo   Pakete werden geladen...
"%VPY%" -m pip install --upgrade --quiet pip
"%VPY%" -m pip install --quiet --no-warn-script-location ^
    dash plotly numpy scipy pydantic pyyaml ezdxf shapely neuralfoil
if %errorlevel% neq 0 (
    echo.
    echo   [FEHLER] Die Pakete liessen sich nicht installieren.
    echo   Besteht eine Internetverbindung?
    echo.
    echo   Der Ordner .venv kann gefahrlos geloescht werden - beim naechsten
    echo   Start wird er neu angelegt.
    echo.
    pause
    exit /b 1
)
echo   Fertig.
echo.

:starten
echo   Der Browser oeffnet sich gleich von selbst.
echo   Falls nicht: http://127.0.0.1:8051
echo.
"%VPY%" -m aerostudio.ui.app

echo.
echo   Aero Studio wurde beendet.
pause
