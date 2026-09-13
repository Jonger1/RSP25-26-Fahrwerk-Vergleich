"""
Vom 2D-Profil zum 3D-Flügel.

Ein Flügel ist ein Stapel identisch aufgebauter Profilschnitte entlang der
Spannweite. "Identisch aufgebaut" heißt: gleiche Punktzahl, gleiche Reihenfolge,
gleicher Startpunkt. Das ist keine Förmlichkeit, sondern die Bedingung dafür,
dass Creo daraus einen sauberen Boundary Blend baut - bei ungleich strukturierten
Schnitten verdreht sich die Fläche.

Was andere Formula-Student-Teams machen, und woher das kommt:

* Der Frontflügel ist spannweitig SEGMENTIERT, nicht gleichmäßig verjüngt. Eine
  schwedische Arbeit zum FS-Frontflügel (Jönköping 2024) beschreibt vier
  Elemente im mittleren Bereich und drei im äußeren, und begründet das mit den
  Geometriegrenzen des Reglements: außen ist schlicht weniger Höhe erlaubt.
* Innen wird der Flügel NEGATIV angestellt, um die Luft nach außen um das Rad
  herumzuleiten. Dieselbe Arbeit misst dafür −10 Grad als bestes Ergebnis und
  weist den Erfolg über den gesunkenen Widerstand der Vorderräder nach.
* Außen am Rad sitzt die längste Sehne und der größte Anstellwinkel - so
  beschreibt es eMotorsports Cologne für ihren Frontflügel.

Diese drei Punkte sind der Grund, warum hier Sehne, Verwindung, Höhe und
Längsversatz einzeln über die Spannweite verteilbar sind statt über einen
einzigen Verjüngungsfaktor.

ACHTUNG bei der Übertragung des zweiten Punktes - hier ist schon einmal ein
Fehler passiert:

Die −10 Grad gelten für ein eigenes ELEMENT eines segmentierten Flügels, nicht
für die Verwindung einer durchgehenden Fläche. Als Verwindung eingetragen
ergaben sie 24 Grad je Meter; der Berandungsverbund in Creo schnürte in der
Mitte sichtbar ein, und die Wurzel stand zwei Grad jenseits des Abrisses. Ein
segmentierter Flügel hat dort eine KANTE zwischen zwei Bauteilen - eine
durchgehende Haut muss den Unterschied über die Spannweite verteilen und
verdreht sich dabei.

Die Vorgabe in spec.modell.Spannweite ist deshalb maßvoll gehalten, und
geometrie.verwindung warnt, sobald die Rate zu groß wird oder ein Schnitt an
den Abriss kommt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import PchipInterpolator

from .profil import Profil


@dataclass
class Schnitt:
    """Ein Profilschnitt an einer Spannweitenposition, in Millimetern."""

    y: float
    sehne: float
    anstellwinkel: float
    punkte: np.ndarray          # Nx3 im Werkzeug-Koordinatensystem

    @property
    def hoehe_min(self) -> float:
        return float(self.punkte[:, 2].min())

    @property
    def hoehe_max(self) -> float:
        return float(self.punkte[:, 2].max())


def _verlauf(stellen: list[float], werte: list[float]) -> callable:
    """Formerhaltender Verlauf über die Spannweite.

    PCHIP und nicht der gewöhnliche kubische Spline: Der überschwingt zwischen
    Stützstellen und erfindet dabei Sehnen oder Winkel, die niemand eingegeben
    hat. Bei einer Verjüngung von innen nach außen fällt das sofort auf - der
    Flügel würde zwischen zwei Stationen dicker als an beiden.
    """
    if len(stellen) == 1:
        wert = float(werte[0])
        return lambda y: np.full_like(np.asarray(y, dtype=float), wert)
    ordnung = np.argsort(stellen)
    return PchipInterpolator(np.asarray(stellen, dtype=float)[ordnung],
                             np.asarray(werte, dtype=float)[ordnung],
                             extrapolate=True)


def schnitte(profil: Profil, spannweite, grundsehne: float,
             grundwinkel: float, punkte_je_seite: int,
             lage: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> list[Schnitt]:
    """Baut den Schnittstapel eines Flügels.

    grundsehne und grundwinkel sind die Werte an der Wurzel; die Verteilungen
    wirken multiplikativ beziehungsweise additiv darauf.

    `lage` verschiebt den fertigen Stapel ins Fahrzeug-Koordinatensystem. Ohne
    diese Verschiebung ließe sich keine Regel prüfen - das Reglement nennt
    ausschließlich absolute Lagen am Fahrzeug, nie relative.
    """
    stellen = [s.y for s in spannweite.stuetzstellen]
    f_sehne = _verlauf(stellen, [s.sehne for s in spannweite.stuetzstellen])
    f_twist = _verlauf(stellen, [s.verwindung for s in spannweite.stuetzstellen])
    f_z = _verlauf(stellen, [s.z for s in spannweite.stuetzstellen])
    f_x = _verlauf(stellen, [s.x for s in spannweite.stuetzstellen])

    fein = profil.repanelisiert(punkte_je_seite)
    ergebnis: list[Schnitt] = []

    for y in np.linspace(min(stellen), max(stellen), spannweite.schnitte):
        sehne = grundsehne * float(f_sehne(y))
        winkel = grundwinkel + float(f_twist(y))
        eben = fein.angestellt(winkel, sehne)

        punkte = np.column_stack([
            eben[:, 0] + float(f_x(y)) + lage[0],
            np.full(len(eben), float(y) + lage[1]),
            eben[:, 1] + float(f_z(y)) + lage[2],
        ])
        ergebnis.append(Schnitt(float(y), sehne, winkel, punkte))

    return ergebnis


def als_sektionen(stapel: list[Schnitt]) -> list[np.ndarray]:
    """Zerlegt den Stapel in IBL-Sektionen: je Schnitt Ober- und Unterseite.

    Getrennt, weil ein durchgehender Spline über die Nase in Creo fast immer
    eine Beule erzeugt. Alle Sektionen haben dieselbe Punktzahl und laufen in
    derselben Richtung - sonst verdreht der Boundary Blend die Fläche.
    """
    sektionen: list[np.ndarray] = []
    for schnitt in stapel:
        nase = len(schnitt.punkte) // 2
        sektionen.append(schnitt.punkte[:nase + 1])
        sektionen.append(schnitt.punkte[nase:])
    return sektionen


def als_umlaeufe(stapel: list[Schnitt]) -> list[np.ndarray]:
    """Ein geschlossener Umlauf je Schnitt - die Form für einen Volumenkörper.

    Anders als `als_sektionen` liefert das eine geschlossene Kurve pro Schnitt
    statt zweier Hälften. Genau die braucht Creo, um zwischen den Schnitten
    einen Verbund (Boundary Blend oder Zug) als VOLUMEN zu bilden: Offene
    Hälften ergeben Flächen, die man hinterher einzeln vernähen muss.

    Der doppelte Punkt an der Hinterkante bleibt hier stehen; entfernt wird er
    erst beim Schreiben, wo auch der Kopf auf "closed" gesetzt wird.
    """
    return [schnitt.punkte.copy() for schnitt in stapel]


def huellwerte(stapel: list[Schnitt]) -> dict[str, float]:
    """Abmessungen des fertigen Flügels - die Größen, die das Reglement nennt."""
    alle = np.vstack([s.punkte for s in stapel])
    return {
        "spannweite": float(alle[:, 1].max() - alle[:, 1].min()),
        "y_min": float(alle[:, 1].min()),
        "y_max": float(alle[:, 1].max()),
        "x_min": float(alle[:, 0].min()),
        "x_max": float(alle[:, 0].max()),
        "z_min": float(alle[:, 2].min()),
        "z_max": float(alle[:, 2].max()),
        "flaeche": _flaeche(stapel),
    }


def _flaeche(stapel: list[Schnitt]) -> float:
    """Grundrissfläche in mm², aus den Sehnen über die Spannweite integriert."""
    if len(stapel) < 2:
        return 0.0
    y = np.array([s.y for s in stapel])
    c = np.array([s.sehne for s in stapel])
    return float(np.trapezoid(c, y)) if hasattr(np, "trapezoid") else float(np.trapz(c, y))
