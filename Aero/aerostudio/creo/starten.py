"""
Creo mit einer Datei starten.

Creo Parametric nimmt eine Datei als Befehlszeilenargument entgegen - die
eigene Hilfe nennt die Reihenfolge:

    parametric.exe [.pha] [.psf] [Pfad zur CAD-Objektdatei] ...

Der mitgelieferte parametric.bat reicht alles nach der .psf durch, ist also
der bequemste Einstieg.

Was damit NICHT geht: einer bereits laufenden Creo-Sitzung sagen, sie moege
eine Datei oeffnen. Dafuer braeuchte es eine Toolkit-Anwendung, und die laedt
die Student Edition nicht (siehe creo/plugin/README.md). Deshalb prueft dieses
Modul, ob Creo schon laeuft, und startet dann bewusst KEINE zweite Sitzung -
die belegt schnell zwei Gigabyte und bringt niemandem etwas.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

PROFIL = Path(__file__).resolve().parent / "profiles" / "creo8.yaml"


@dataclass
class Startergebnis:
    """Was beim Startversuch herauskam - fuer eine verstaendliche Rueckmeldung."""

    gestartet: bool
    meldung: str
    hinweis: str = ""


def loadpoint() -> Path | None:
    """Installationsordner von Creo aus dem Versionsprofil."""
    try:
        daten = yaml.safe_load(PROFIL.read_text(encoding="utf-8"))
        pfad = Path(str(daten["creo"]["loadpoint"]))
        return pfad if pfad.is_dir() else None
    except Exception:
        return None


def starter() -> Path | None:
    """Pfad zu parametric.bat, oder None."""
    wurzel = loadpoint()
    if wurzel is None:
        return None
    bat = wurzel / "Parametric" / "bin" / "parametric.bat"
    return bat if bat.is_file() else None


def laeuft() -> bool:
    """Laeuft schon eine Creo-Sitzung?

    Geprueft wird xtop.exe - das ist der eigentliche Creo-Prozess.
    parametric.exe ist nur der Starter und bleibt als Huelle stehen.
    """
    try:
        ausgabe = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq xtop.exe"],
            capture_output=True, text=True, timeout=10).stdout
        return "xtop.exe" in ausgabe
    except Exception:
        return False


def oeffne(datei: str | Path, trotz_laufender_sitzung: bool = False) -> Startergebnis:
    """Startet Creo und laesst es die Datei oeffnen."""
    datei = Path(datei)
    if not datei.is_file():
        return Startergebnis(False, f"Die Datei gibt es nicht: {datei}",
                             "Erst schreiben lassen, dann öffnen.")

    bat = starter()
    if bat is None:
        return Startergebnis(
            False, "Creo wurde nicht gefunden.",
            f"Erwartet unter dem Pfad aus {PROFIL.name}. Liegt Creo woanders, "
            f"dort den Eintrag creo.loadpoint anpassen.")

    if laeuft() and not trotz_laufender_sitzung:
        return Startergebnis(
            False, "Creo läuft bereits.",
            "Eine zweite Sitzung würde noch einmal rund zwei Gigabyte belegen "
            "und bringt nichts. Im offenen Creo genügen drei Klicks: "
            "Modell → Daten abrufen → Importieren, dann Importtyp Kurve. "
            "Der Pfad steht oben.")

    try:
        # Losgeloest starten, sonst haengt die Oberflaeche an Creos Lebensdauer.
        subprocess.Popen([str(bat), str(datei)], cwd=str(datei.parent),
                         creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    except Exception as fehler:
        return Startergebnis(False, f"Der Start ist fehlgeschlagen: {fehler}")

    return Startergebnis(
        True, "Creo wird gestartet.",
        "Das dauert eine Weile. Die Kurve erscheint als neues Teil, benannt "
        "nach der Datei.")
