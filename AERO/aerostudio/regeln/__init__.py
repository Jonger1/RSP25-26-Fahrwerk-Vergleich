"""Regelwerk als Daten, nicht als Code.

Es gilt genau ein Regelstand: FS Rules 2027 v1.0. Das Original liegt im
Repo unter AERO/FS_Rules_2027_v1.0.pdf, die Werte daraus in
rules_2027.yaml (mit Seitenangaben und Wortlaut). Wer eine Grenze nachsehen
will, schaut dort - nicht in alten Staenden, die gibt es nur noch in der
Git-Historie.

Kommt ein neuer Regelstand, wird er als eigene YAML-Datei angelegt und
`AKTUELL` umgestellt.
"""

from .pruefung import (AKTUELL, ORIGINAL, Bezugsgeometrie, Fahrzustand,
                       Regelbefund, Regelsatz, alle_staende, lade,
                       pruefe_fluegel)

__all__ = ["AKTUELL", "ORIGINAL", "Bezugsgeometrie", "Fahrzustand",
           "Regelbefund", "Regelsatz", "alle_staende", "lade",
           "pruefe_fluegel"]
