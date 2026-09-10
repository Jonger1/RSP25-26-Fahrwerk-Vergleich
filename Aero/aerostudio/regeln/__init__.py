"""Regelwerk als Daten, nicht als Code.

Beide Regelstaende liegen als YAML daneben und werden zur Laufzeit gelesen.
Das ist Absicht: Wenn im November der endgueltige 2027er-Text erscheint,
aendert sich eine Datei und keine Zeile Python.
"""

from .pruefung import (Bezugsgeometrie, Fahrzustand, Regelbefund, Regelsatz,
                       alle_staende, lade, pruefe_fluegel)

__all__ = ["Bezugsgeometrie", "Fahrzustand", "Regelbefund", "Regelsatz",
           "alle_staende", "lade", "pruefe_fluegel"]
