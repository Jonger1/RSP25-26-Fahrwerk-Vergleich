@echo off
rem ---------------------------------------------------------------------
rem  Aero Studio starten
rem
rem  Doppelklick genuegt. Das Fenster bleibt offen, weil dort die Meldungen
rem  des Programms landen - bei einem Fehler steht die Ursache darin.
rem  Zum Beenden: dieses Fenster schliessen oder Strg+C druecken.
rem ---------------------------------------------------------------------

title Aero Studio
cd /d "%~dp0"

echo.
echo   Aero Studio wird gestartet...
echo.

rem Python suchen: erst der Starter py, dann python im PATH.
where py >nul 2>&1
if %errorlevel%==0 (
    set "PYTHON=py -3"
) else (
    where python >nul 2>&1
    if %errorlevel%==0 (
        set "PYTHON=python"
    ) else (
        echo   [FEHLER] Python wurde nicht gefunden.
        echo.
        echo   Aero Studio braucht Python 3.10 oder neuer.
        echo   Herunterladen: https://www.python.org/downloads/
        echo   Beim Installieren unbedingt "Add Python to PATH" ankreuzen.
        echo.
        pause
        exit /b 1
    )
)

rem Fehlende Pakete melden, statt mit einem Stapel roter Zeilen abzustuerzen.
%PYTHON% -c "import dash, plotly, numpy, scipy, pydantic, yaml, ezdxf" 2>nul
if %errorlevel% neq 0 (
    echo   Es fehlen noch Pakete. Sie werden jetzt einmalig installiert...
    echo.
    %PYTHON% -m pip install --quiet dash plotly numpy scipy pydantic pyyaml ezdxf shapely
    if %errorlevel% neq 0 (
        echo.
        echo   [FEHLER] Die Installation ist fehlgeschlagen.
        echo   Besteht eine Internetverbindung? Sonst bitte melden.
        echo.
        pause
        exit /b 1
    )
    echo   Fertig.
    echo.
)

echo   Der Browser oeffnet sich gleich von selbst.
echo   Falls nicht: http://127.0.0.1:8051
echo.

%PYTHON% -m aerostudio.ui.app

echo.
echo   Aero Studio wurde beendet.
pause
