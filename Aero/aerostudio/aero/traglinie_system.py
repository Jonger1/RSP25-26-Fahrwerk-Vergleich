"""Gekoppelte 3D-Traglinienrechnung fuer segmentierte Fluegelsysteme.

Der Solver arbeitet direkt mit Spannweitenintervallen. Zwischen zwei Elementen
mit einer echten y-Luecke existiert kein gebundener Wirbel; die aktiven
Segmente werden trotzdem in EINEM linearen Gleichungssystem geloest und
koppeln deshalb ueber ihre Fernfeld-/Nachlaufinduktion.

Das ist die erste echte 3D-Ebene des Aero-Tools. Sie ist bewusst inviscid:
Profilpolaren, Slot-Grenzschicht, Endplatten, Raeder und Karosserieinteraktion
werden nicht erfunden, sondern spaeter als separate Kalibrierbausteine
angekoppelt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import traglinie
from ..geometrie.fluegel_system import FluegelElement, FluegelSystem
from .profilpolare import DICHTE


@dataclass
class SystemStreifen:
    elementname: str
    gruppe: str
    baugruppe: str
    y: float
    breite: float
    sehne: float
    winkel: float
    hoehe: float
    x_viertel: float


@dataclass
class SystemKraefte:
    abtrieb: float
    widerstand: float
    widerstand_induziert: float
    widerstand_profil: float
    flaeche: float
    geschwindigkeit: float
    cl: float
    cd: float
    streifen: list[SystemStreifen] = field(default_factory=list)
    alpha_induziert: np.ndarray = field(default_factory=lambda: np.array([]))
    cl_lokal: np.ndarray = field(default_factory=lambda: np.array([]))
    konvergiert: bool = True
    schritte: int = 1

    @property
    def wirkungsgrad(self) -> float:
        return abs(self.abtrieb) / max(self.widerstand, 1e-12)


def streifen_aus_elementen(elemente: list[FluegelElement],
                           panels_je_element: int = 12) -> list[SystemStreifen]:
    """Panelisiert jedes Spannweitenintervall separat.

    Eine reale y-Luecke erzeugt keine Panels und damit keinen gebundenen Wirbel.
    Ueberlappende Baugruppen bleiben dagegen eigenstaendige Wirbelreihen.
    """
    if panels_je_element < 2:
        raise ValueError("Mindestens zwei Panels je Element sind erforderlich.")
    streifen: list[SystemStreifen] = []
    for e in elemente:
        ys = np.linspace(e.spannweite.y_von, e.spannweite.y_bis,
                         panels_je_element + 1)
        for a, b in zip(ys[:-1], ys[1:]):
            streifen.append(SystemStreifen(
                elementname=e.name,
                gruppe=e.gruppe,
                baugruppe=e.baugruppe,
                y=float((a + b) / 2.0),
                breite=float(b - a),
                sehne=float(e.sehne_mm),
                winkel=float(e.winkel_grad),
                hoehe=float(e.z_mm),
                x_viertel=float(e.x_mm + 0.25 * e.sehne_mm),
            ))
    return streifen


def streifen_aus_system(system: FluegelSystem,
                        panels_je_element: int = 12) -> list[SystemStreifen]:
    """Direkter Adapter vom zentralen Baugruppenmodell zum 3D-Solver."""
    return streifen_aus_elementen(system.elemente, panels_je_element)


def _hufeisen_koordinaten(s: SystemStreifen) -> tuple[np.ndarray, np.ndarray]:
    a = np.array([s.x_viertel, s.y - s.breite / 2.0, s.hoehe]) / 1000.0
    b = np.array([s.x_viertel, s.y + s.breite / 2.0, s.hoehe]) / 1000.0
    return a, b


def einflussmatrix(kontroll: np.ndarray, streifen: list[SystemStreifen],
                   mit_boden: bool = False) -> np.ndarray:
    """Vertikale Induktion aller segmentierten Hufeisenwirbel."""
    n = len(streifen)
    matrix = np.zeros((n, n), dtype=float)
    spiegel = np.array([1.0, 1.0, -1.0])
    for j, s in enumerate(streifen):
        a, b = _hufeisen_koordinaten(s)
        v = traglinie._hufeisen(kontroll, a, b)
        if mit_boden:
            v -= traglinie._hufeisen(kontroll, a * spiegel, b * spiegel)
        matrix[:, j] = v[:, 2]
    return matrix


def nachlaufmatrix(tragpunkte: np.ndarray, streifen: list[SystemStreifen],
                   mit_boden: bool = False) -> np.ndarray:
    """Induktion der Nachlaufschrauben an den Traglinienpunkten."""
    n = len(streifen)
    matrix = np.zeros((n, n), dtype=float)
    spiegel = np.array([1.0, 1.0, -1.0])
    for j, s in enumerate(streifen):
        a, b = _hufeisen_koordinaten(s)
        v = traglinie._hufeisen(tragpunkte, a, b, nur_nachlauf=True)
        if mit_boden:
            v -= traglinie._hufeisen(tragpunkte, a * spiegel, b * spiegel,
                                     nur_nachlauf=True)
        matrix[:, j] = v[:, 2]
    return matrix


def rechne(streifen: list[SystemStreifen], geschwindigkeit: float = 15.0,
           mit_boden: bool = False) -> SystemKraefte:
    """Loest Zirkulation aller aktiven Spannweitenpanels gemeinsam.

    Das Gleichungssystem entspricht der Hufeisenwirbel-/Weissinger-Idee der
    bestehenden Einzel-Fluegelrechnung. Anders als dort wird hier aber nicht
    vorausgesetzt, dass der Fluegel ueber y durchgaengig ist.
    """
    if not streifen:
        raise ValueError("Das Fluegelsystem enthaelt keine aktiven Streifen.")
    V = float(geschwindigkeit)
    if V <= 0.0:
        raise ValueError("Geschwindigkeit muss positiv sein.")

    y = np.array([s.y for s in streifen]) / 1000.0
    breite = np.array([s.breite for s in streifen]) / 1000.0
    sehne = np.array([s.sehne for s in streifen]) / 1000.0
    winkel = np.array([s.winkel for s in streifen])
    hoehe = np.array([s.hoehe for s in streifen]) / 1000.0
    x4 = np.array([s.x_viertel for s in streifen]) / 1000.0

    # Kontrollpunkt auf 3/4-Sehne, gebundener Wirbel auf 1/4-Sehne.
    kontroll = np.column_stack([x4 + 0.5 * sehne, y, hoehe])
    tragpunkte = np.column_stack([x4, y, hoehe])

    A = einflussmatrix(kontroll, streifen, mit_boden)
    A_w = nachlaufmatrix(tragpunkte, streifen, mit_boden)

    # Randbedingung: Strömung folgt der lokalen Sehne.
    rhs = -V * np.tan(np.radians(winkel))

    # LGS statt Iteration: Dadurch werden starke Kopplungen zwischen
    # benachbarten und getrennten Segmenten gemeinsam aufgelöst.
    gamma = np.linalg.lstsq(A, rhs, rcond=None)[0]
    w = A_w @ gamma
    alpha_ind = np.degrees(np.arctan2(w, V))
    cl_lokal = 2.0 * gamma / (V * sehne)

    q = 0.5 * DICHTE * V * V
    flaeche_i = sehne * breite
    flaeche = float(np.sum(flaeche_i))
    lift = float(q * np.sum(cl_lokal * flaeche_i))

    d_ind = float(-DICHTE * np.sum(gamma * w * breite))
    d_ind = abs(d_ind)

    return SystemKraefte(
        abtrieb=-lift,
        widerstand=d_ind,
        widerstand_induziert=d_ind,
        widerstand_profil=0.0,
        flaeche=flaeche,
        geschwindigkeit=V,
        cl=float(lift / max(q * flaeche, 1e-12)),
        cd=float(d_ind / max(q * flaeche, 1e-12)),
        streifen=streifen,
        alpha_induziert=alpha_ind,
        cl_lokal=cl_lokal,
        konvergiert=True,
        schritte=1,
    )


def system_rechne(system: FluegelSystem, geschwindigkeit: float = 15.0,
                  panels_je_element: int = 12, mit_boden: bool = False) -> SystemKraefte:
    """Kompletter Einstiegspunkt fuer die Fahrzeug-Aero-Ebene."""
    streifen = streifen_aus_system(system, panels_je_element)
    return rechne(streifen, geschwindigkeit, mit_boden)
