"""
IBL-Export fuer Creo - Schreiben importierbarer Bezugskurven.

Zwei Aufgaben:

1. Das IBL-Format schreiben, wie Creo es erwartet (Kopf "open"/"arclength",
   je Segment "begin section" und "begin curve", dann die Punkte).

2. Vom Werkzeug-Koordinatensystem in das der Creo-Vorlage umrechnen.

Zu 2., weil es die zentrale Entwurfsentscheidung ist:

Das Werkzeug rechnet durchgehend mit **z nach oben**, weil das Reglement ueber
Hoehen ueber Grund argumentiert - T 8.2 sagt "lower than 500 mm from the
ground". Mit z = 0 auf der Bodenebene wird jede Regelpruefung ein Vergleich
statt einer Koordinatentransformation.

Die Creo-Vorlage hat dagegen **Y nach oben**. Der Unterschied wird hier beim
Schreiben aufgeloest, nicht in Creo. Damit muss niemand von Hand ein gedrehtes
Koordinatensystem anlegen - eine erzeugte .ibl laesst sich direkt auf das
Standard-Koordinatensystem importieren und sitzt richtig.

Die Abbildung selbst steht als Daten im Versionsprofil (creo8.yaml), nicht
hier im Code. Eine andere Creo-Vorlage bekommt ein anderes Profil, nicht
einen anderen Exporter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

# Abbildung Werkzeug -> Creo-Vorlage, Standardfall.
# Gelesen als: die X-Achse in Creo ist unsere +x, die Y-Achse unsere +z,
# die Z-Achse unsere -y. Das ist eine echte Drehung (Determinante +1),
# also keine Spiegelung - das wird in `frame_matrix` geprueft.
STANDARD_FRAME = {"creo_x": "+x", "creo_y": "+z", "creo_z": "-y"}

_ACHSE = {"x": 0, "y": 1, "z": 2}


def frame_matrix(frame: dict[str, str] | None = None) -> np.ndarray:
    """Baut die 3x3-Matrix aus einer Achsabbildung wie STANDARD_FRAME.

    Wirft einen Fehler, wenn die Abbildung keine Drehung ist. Eine Spiegelung
    wuerde ein Profil seitenverkehrt nach Creo bringen, und zwar ohne dass es
    an der Geometrie auffaellt - deshalb wird hier hart geprueft.
    """
    frame = frame or STANDARD_FRAME
    M = np.zeros((3, 3))
    for i, schluessel in enumerate(("creo_x", "creo_y", "creo_z")):
        token = frame[schluessel].strip().lower()
        vorzeichen = -1.0 if token.startswith("-") else 1.0
        M[i, _ACHSE[token[-1]]] = vorzeichen

    det = float(np.linalg.det(M))
    if not np.isclose(det, 1.0):
        raise ValueError(
            f"Achsabbildung {frame} ist keine Drehung (Determinante {det:+.0f}). "
            "Bei -1 waere die Geometrie in Creo gespiegelt."
        )
    return M


def to_creo(punkte: np.ndarray, frame: dict[str, str] | None = None) -> np.ndarray:
    """Rechnet Punkte vom Werkzeug- ins Creo-Koordinatensystem um."""
    p = np.asarray(punkte, dtype=float)
    if p.ndim != 2 or p.shape[1] != 3:
        raise ValueError(f"Erwartet ein Nx3-Feld, bekommen: {p.shape}")
    return p @ frame_matrix(frame).T


def write_ibl(
    pfad: str | Path,
    sektionen: Sequence[np.ndarray],
    *,
    frame: dict[str, str] | None = None,
    kommentare: Iterable[str] | None = None,
    nachkommastellen: int = 6,
    punktnummern: bool = True,
) -> Path:
    """Schreibt Sektionen als .ibl-Datei.

    sektionen        Liste von Nx3-Feldern im Werkzeug-Koordinatensystem, in mm.
                     Zwei Punkte ergeben in Creo eine Gerade, mehr als zwei
                     einen Spline.
    frame            Achsabbildung; None nimmt STANDARD_FRAME.
    kommentare       Zeilen, die als "! ..." vor den Kopf geschrieben werden.
                     Ob Creo das akzeptiert, ist ein offener M0-Befund - im
                     Zweifel weglassen.
    punktnummern     Die fuehrende Nummer je Punkt ist laut PTC optional.
    """
    pfad = Path(pfad)
    zeilen: list[str] = []

    if kommentare:
        zeilen += [f"! {k}" for k in kommentare]

    zeilen += ["open", "arclength", ""]

    for nr, sektion in enumerate(sektionen, start=1):
        p = to_creo(sektion, frame)
        if len(p) < 2:
            raise ValueError(f"Sektion {nr} hat weniger als zwei Punkte.")
        zeilen.append(f"begin section ! {nr}")
        zeilen.append("        begin curve")
        for i, (x, y, z) in enumerate(p, start=1):
            werte = f"{x:12.{nachkommastellen}f}{y:14.{nachkommastellen}f}{z:14.{nachkommastellen}f}"
            zeilen.append(f"{i:5d}{werte}" if punktnummern else f"     {werte}")
        zeilen.append("")

    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text("\n".join(zeilen).rstrip() + "\n", encoding="ascii")
    return pfad
