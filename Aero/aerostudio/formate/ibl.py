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

def standard_frame() -> dict[str, str]:
    """Die Achsabbildung aus dem Versionsprofil.

    Bis M0 stand sie zusaetzlich hier im Code. Das war genau die doppelte
    Wahrheit, die die Versionsstrategie verhindern soll: Eine neue
    Creo-Vorlage haette zwei Aenderungen an verschiedenen Orten gekostet.
    Jetzt kommt sie aus creo8.yaml; fehlt die Datei, greift die dort
    hinterlegte Vorgabe, und das Profil sagt es ueber `maengel`.
    """
    from ..creo.profil import profil
    return profil().frame


def kommentare_erlaubt() -> bool:
    """Darf in den Kopf einer .ibl ein "!"-Kommentar? Befund aus dem Profil."""
    from ..creo.profil import profil
    return profil().kommentare_erlaubt


_ACHSE = {"x": 0, "y": 1, "z": 2}


def frame_matrix(frame: dict[str, str] | None = None) -> np.ndarray:
    """Baut die 3x3-Matrix aus einer Achsabbildung wie `standard_frame()`.

    Wirft einen Fehler, wenn die Abbildung keine Drehung ist. Eine Spiegelung
    wuerde ein Profil seitenverkehrt nach Creo bringen, und zwar ohne dass es
    an der Geometrie auffaellt - deshalb wird hier hart geprueft.
    """
    frame = frame or standard_frame()
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
    kommentarort: str = "vor_kopf",
    nachkommastellen: int = 6,
    punktnummern: bool = True,
    geschlossen: bool = False,
) -> Path:
    """Schreibt Sektionen als .ibl-Datei.

    sektionen        Liste von Nx3-Feldern im Werkzeug-Koordinatensystem, in mm.
                     Zwei Punkte ergeben in Creo eine Gerade, mehr als zwei
                     einen Spline.
    frame            Achsabbildung; None nimmt die aus dem Versionsprofil.
    kommentare       Zeilen, die als "! ..." vor den Kopf geschrieben werden.
                     Ob Creo das annimmt, steht als Befund im Versionsprofil
                     (befunde.ibl_kommentarzeilen_erlaubt). Steht dort `false`,
                     werden sie stillschweigend weggelassen - der Aufrufer
                     muss das nicht wissen, und ein negativer Befund aus Creo
                     kostet dann keine Codeaenderung, sondern eine Zeile YAML.
    kommentarort     Wo die Kommentare landen. "vor_kopf" (Vorgabe) schreibt
                     sie ueber "open", "nach_kopf" darunter, "zwischen" vor
                     jede Sektion. Das ist keine Spielerei, sondern der
                     M0-Kommentartest: Ein einzelner Fehlschlag mit einer
                     einzigen Variante sagt nicht, WELCHE Stelle Creo stoert.
                     Fuer den Betrieb bleibt es bei "vor_kopf".
    punktnummern     Die fuehrende Nummer je Punkt ist laut PTC optional.
    geschlossen      Schreibt "closed" statt "open" in den Kopf. Creo
                     verbindet dann den letzten Punkt jeder Sektion wieder
                     mit dem ersten und liefert EINE geschlossene Kurve statt
                     zweier offener Haelften. Nur so laesst sich aus der
                     importierten Kurve unmittelbar eine Skizze und daraus
                     ein Extrudieren machen - zwei getrennte Kurven, die sich
                     nur beruehren, sind dafuer keine geschlossene Kontur.
                     Der letzte Punkt darf dann NICHT der erste sein, sonst
                     entsteht ein Segment der Laenge null.
    """
    if kommentarort not in {"vor_kopf", "nach_kopf", "zwischen"}:
        raise ValueError(f"Unbekannter Kommentarort: {kommentarort!r}")

    pfad = Path(pfad)
    zeilen: list[str] = []

    texte = [f"! {k}" for k in kommentare] if (
        kommentare and kommentare_erlaubt()) else []

    if kommentarort == "vor_kopf":
        zeilen += texte

    zeilen += ["closed" if geschlossen else "open", "arclength", ""]

    if kommentarort == "nach_kopf" and texte:
        zeilen += texte + [""]

    for nr, sektion in enumerate(sektionen, start=1):
        p = to_creo(sektion, frame)
        if len(p) < 2:
            raise ValueError(f"Sektion {nr} hat weniger als zwei Punkte.")
        if geschlossen and np.allclose(p[0], p[-1]):
            # Der Doppelpunkt waere ein Segment der Laenge null. Creo schliesst
            # bei "closed" selbst - der letzte Punkt muss also weg.
            p = p[:-1]
        if geschlossen and len(p) < 3:
            raise ValueError(f"Sektion {nr} hat fuer eine geschlossene Kurve "
                             f"zu wenige Punkte.")
        if kommentarort == "zwischen" and texte:
            zeilen += texte
        zeilen.append(f"begin section ! {nr}")
        zeilen.append("        begin curve")
        for i, (x, y, z) in enumerate(p, start=1):
            werte = f"{x:12.{nachkommastellen}f}{y:14.{nachkommastellen}f}{z:14.{nachkommastellen}f}"
            zeilen.append(f"{i:5d}{werte}" if punktnummern else f"     {werte}")
        zeilen.append("")

    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text("\n".join(zeilen).rstrip() + "\n", encoding="ascii")
    return pfad
