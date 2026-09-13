"""Gekoppelte 3D-Traglinienrechnung fuer segmentierte Fluegelsysteme.

Der Solver arbeitet direkt mit Spannweitenintervallen. Zwischen zwei Elementen
mit einer echten y-Luecke existiert kein gebundener Wirbel; die Tip-Wirbel der
aktiven Segmente werden trotzdem gemeinsam geloest und koppeln damit ueber den
gesamten betrachteten Spannweitenraum.

Bewusste Modellgrenzen:
- Profilpolaren werden als lokale Sektionen angenaehert.
- Endplatten sind noch kein eigener Wirbelabschluss; ihre Wirkung bleibt einem
  spaeteren kalibrierten Modell vorbehalten.
- Interaktion mit Boden, Raedern und Karosserie ist nur ueber die bestehende
  Spiegelungsoption abbildbar.
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
    konvergiert: bool = False
    schritte: int = 0

    @property
    def wirkungsgrad(self) -> float:
        return abs(self.abtrieb) / max(self.widerstand, 1e-12)


def _viertelpunkt(element) -> np.ndarray:
    p = element.punkte
    hinten = p[0]
    nase = p[int(np.argmax(np.linalg.norm(p - hinten, axis=1)))]
    return nase + 0.25 * (hinten - nase)


def streifen_aus_system(system_streifen: list[tuple[FluegelElement, object]],
                         panels_je_element: int = 12) -> list[SystemStreifen]:
    """Erzeugt Rechenstreifen aus 3D-Elementen.

    Jedes Spannweitenintervall wird unabhaengig panelisiert. Ueberlappungen in
    y werden absichtlich zugelassen: verschiedene Baugruppen koennen an
    derselben y-Position liegen, etwa Bullwing und Frontfluegel.
    """
    if panels_je_element < 2:
        raise ValueError("Mindestens zwei Panels je Element sind erforderlich.")
    out: list[SystemStreifen] = []
    for meta, geos in system_streifen:
        if geos is None or len(geos) == 0:
            continue
        ys = np.linspace(meta.spannweite.y_von, meta.spannweite.y_bis,
                         panels_je_element + 1)
        # Der lokale 2D-Querschnitt liefert keine echte Spannweitenverteilung;
        # wir bilden deshalb die Elementwerte am jeweiligen Streifenmittelpunkt
        # direkt aus Sehne/Winkel ab.
        p = geos[0]
        flaeche = geos
        del flaeche
        # Geometrie des lokalen Elements steckt im ersten Punktarray; fuer die
        # angenaeherte 3D-Linie genuegt Viertelpunkt und lokale Sehne.
        for a, b in zip(ys[:-1], ys[1:]):
            ym = 0.5 * (a + b)
            # Falls die 2D-Kaskade mehrere Elemente enthaelt, meta verweist auf
            # genau das zu betrachtende 3D-Segment.
            out.append(SystemStreifen(
                elementname=meta.name,
                gruppe=meta.gruppe,
                baugruppe=meta.baugruppe,
                y=float(ym),
                breite=float(b - a),
                sehne=float(meta.sehne_mm),
                winkel=float(meta.winkel_grad),
                hoehe=float(meta.z_mm),
                x_viertel=float(meta.x_mm + 0.25 * meta.sehne_mm),
            ))
    return out


def _system_kanten(streifen: list[SystemStreifen]) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """Erzeugt getrennte gebundene Wirbelfaeden fuer jedes aktive Segment."""
    kanten = []
    segmente = []
    cursor = 0
    for s in streifen:
        kanten.append([s.x_viertel, s.y - s.breite / 2, s.hoehe])
        kanten.append([s.x_viertel, s.y + s.breite / 2, s.hoehe])
        segmente.append((cursor, cursor + 1))
        cursor += 2
    return np.asarray(kanten, dtype=float), segmente


def _einflussmatrix_system(kontroll: np.ndarray, streifen: list[SystemStreifen],
                           mit_boden: bool = False) -> np.ndarray:
    """Einflussmatrix fuer alle segmentierten Hufeisenwirbel.

    Im Gegensatz zur alten Flaechenrechnung werden die einzelnen Wirbel nicht
    ueber einen durchgehenden Fluegelrand verbunden. Dadurch bleiben reale
    Spannweitenluecken Luecken im Modell.
    """
    n = len(streifen)
    A = np.zeros((n, n), dtype=float)
    for j, s in enumerate(streifen):
        a = np.array([s.x_viertel, s.y - s.breite / 2, s.hoehe], dtype=float)
        b = np.array([s.x_viertel, s.y + s.breite / 2, s.hoehe], dtype=float)
        v = traglinie._hufeisen(kontroll, a, b)
        if mit_boden:
            spiegel = np.array([1.0, 1.0, -1.0])
            v -= traglinie._hufeisen(kontroll, a * spiegel, b * spiegel)
        A[:, j] = v[:, 2]
    return A


def _nachlaufmatrix_system(tragpunkte: np.ndarray, streifen: list[SystemStreifen],
                           mit_boden: bool = False) -> np.ndarray:
    n = len(streifen)
    A = np.zeros((n, n), dtype=float)
    for j, s in enumerate(streifen):
        a = np.array([s.x_viertel, s.y - s.breite / 2, s.hoehe], dtype=float)
        b = np.array([s.x_viertel, s.y + s.breite / 2, s.hoehe], dtype=float)
        v = traglinie._hufeisen(tragpunkte, a, b, nur_nachlauf=True)
        if mit_boden:
            spiegel = np.array([1.0, 1.0, -1.0])
            v -= traglinie._hufeisen(tragpunkte, a * spiegel, b * spiegel, nur_nachlauf=True)
        A[:, j] = v[:, 2]
    return A


def rechne(streifen: list[SystemStreifen], geschwindigkeit: float = 15.0,
           mit_boden: bool = False, schritte_max: int = 40,
           daempfung: float = 0.35, genauigkeit: float = 1e-5) -> SystemKraefte:
    """Loest die Zirkulation aller aktiven Spannweitenpanels gemeinsam."""
    if not streifen:
        raise ValueError("Das Fluegelsystem enthaelt keine aktiven Streifen.")
    V = float(geschwindigkeit)
    y = np.array([s.y for s in streifen]) / 1000.0
    breite = np.array([s.breite for s in streifen]) / 1000.0
    sehne = np.array([s.sehne for s in streifen]) / 1000.0
    winkel = np.array([s.winkel for s in streifen])
    hoehe = np.array([s.hoehe for s in streifen]) / 1000.0
    x4 = np.array([s.x_viertel for s in streifen]) / 1000.0

    kontroll = np.column_stack([x4 + 0.5 * sehne, y, hoehe])
    tragpunkte = np.column_stack([x4, y, hoehe])
    A = _einflussmatrix_system(kontroll, streifen, mit_boden)
    A_w = _nachlaufmatrix_system(tragpunkte, streifen, mit_boden)

    korrektur = np.zeros(len(streifen))
    gamma = np.zeros(len(streifen))
    alpha_ind = np.zeros(len(streifen))
    cl_lokal = np.zeros(len(streifen))
    kraft_alt = None
    konvergiert = False

    # Das 3D-Grundmodell arbeitet zunaechst reibungsfrei. Profilverluste und
    # Abrissgrenzen werden spaeter gruppenweise ueber Polaren eingekoppelt.
    for schritt in range(1, schritte_max + 1):
        rhs = -V * np.tan(np.radians(winkel + korrektur))
        gamma = np.linalg.lstsq(A, rhs, rcond=None)[0]
        alpha_ind = np.degrees(np.arctan2(A_w @ gamma, V))
        alpha_eff = winkel + alpha_ind
        cl_lokal = 2.0 * gamma / (V * sehne)
        kraft = float(np.sum(cl_lokal * sehne * breite))
        if kraft_alt is not None and abs(kraft - kraft_alt) <= genauigkeit * max(abs(kraft), 1e-9):
            konvergiert = True
            break
        kraft_alt = kraft
        # Keine erfundene Viskositaetskorrektur: Korrektur nur aus der lokalen
        # geometrischen/induzieren Kopplung im 3D-Grundmodell.
        korrektur += daempfung * alpha_ind * 0.05

    q = 0.5 * DICHTE * V * V
    dA = sehne * breite
    area = float(np.sum(dA))
    lift = float(q * np.sum(cl_lokal * dA))
    wind = float(-DICHTE * np.sum(gamma * (A_w @ gamma) * breite))
    wind = abs(wind)
    cd_ind = wind / max(q * area, 1e-12)

    return SystemKraefte(
        abtrieb=-lift,
        widerstand=wind,
        widerstand_induziert=wind,
        widerstand_profil=0.0,
        flaeche=area,
        geschwindigkeit=V,
        cl=lift / max(q * area, 1e-12),
        cd=cd_ind,
        streifen=streifen,
        alpha_induziert=alpha_ind,
        cl_lokal=cl_lokal,
        konvergiert=konvergiert,
        schritte=schritt,
    )


def system_rechne(system_streifen, geschwindigkeit=15.0, **kwargs):
    return rechne(system_streifen, geschwindigkeit=geschwindigkeit, **kwargs)
