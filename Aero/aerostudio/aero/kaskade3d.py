"""
Abtrieb einer räumlichen Kaskade — auch mit Teilflügeln.

Bisher wurde der 2D-Beiwert der Kaskade mit dem Verlust des HAUPTPROFILS
allein auf den endlichen Flügel umgerechnet. Das geht nicht mehr, sobald ein
Flap nur über einen Teil der Spannweite läuft: Innen arbeitet dann ein
anderer Querschnitt als außen, und genau diese Verteilung verändert den
Abwind über die ganze Spannweite.

**Verfahren:**

1. Die Spannweite zerfällt an den Enden der Teilflaps in Bereiche, in denen
   dieselben Elemente existieren.
2. In jedem Bereich wird an einigen Stellen die Kaskade tatsächlich gebaut
   und mit aero/kaskade.py bei mehreren Anströmwinkeln gerechnet. Daraus
   entsteht eine KASKADENPOLARE: Beiwert über dem Winkel des Hauptelements,
   bezogen auf die Gesamtsehne, mit Abriss aus dem Saugspitzenkriterium.
3. Die Traglinie (traglinie.py) rechnet mit diesen Polaren - jeder Streifen
   bekommt die Polare der nächsten Stelle im selben Bereich, dazu die
   Gesamtsehne als Sehne. So wirkt der induzierte Winkel auf die ganze
   Kaskade, und Endplatten und Boden gehen wie beim einfachen Flügel ein.
4. Die Kanalwirkung am Boden (aero/boden.py) wird je Stelle aus der Kaskade
   gerechnet und auf deren Polare gelegt.

Ein Abgleichfaktor aus CFD oder Messung wirkt zuletzt auf alle Beiwerte.
Die Grenzen aus kaskade.py und boden.py gelten hier unverändert.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from ..geometrie import kaskade as geo
from ..geometrie.spannweite import Schnitt, _verlauf
from . import boden, traglinie
from . import kaskade as aero_kaskade
from .profilpolare import Polare, reynolds

# Anströmwinkel relativ zum eingestellten Winkel, für die Kaskadenpolare. Der
# induzierte Winkel nimmt einem Abtriebsflügel einige Grad weg; beide
# Richtungen müssen abgedeckt sein, sonst klemmt die Polare am Rand.
VERSAETZE = (-6.0, -3.0, 0.0, 3.0, 6.0)


@dataclass
class Stuetzwert:
    """Die Kaskade an einer Stelle der Spannweite."""

    y: float
    namen: list[str]
    sehne: float                # Hauptelement, mm
    gesamtsehne: float          # mm
    winkel: float               # Hauptelement, Grad
    polare: Polare
    abgerissen: bool            # 2D, beim eingestellten Winkel
    bodenwirkung: boden.Bodenwirkung | None
    x_viertel: float            # je mm Hauptsehne, ab Nase des Hauptelements
    z_viertel: float
    bereich: int


@dataclass
class Kaskadenabtrieb:
    kraefte: traglinie.Fluegelkraefte
    stuetzwerte: list[Stuetzwert] = field(default_factory=list)
    abgleich: float = 1.0
    endplatte_mm: float = 0.0
    hinweise: list[str] = field(default_factory=list)

    @property
    def abtrieb(self) -> float:
        return self.kraefte.abtrieb

    @property
    def widerstand(self) -> float:
        return self.kraefte.widerstand

    @property
    def wirkungsgrad(self) -> float:
        return self.kraefte.wirkungsgrad

    @property
    def brauchbar(self) -> bool:
        return (self.kraefte.abgerissen <= 0.05
                and not any(s.abgerissen for s in self.stuetzwerte))


def kaskadenpolare(elemente: list[geo.Elementlage],
                   geschwindigkeit: float = 15.0,
                   versaetze=VERSAETZE) -> tuple[Polare, bool]:
    """Beiwert der Kaskade über dem Winkel des Hauptelements.

    Gedreht wird die Anströmung, nicht die Geometrie - die Elemente stehen
    zueinander fest. Ein Anströmwinkel +d entspricht einem um d weniger
    steilen Hauptelement.

    Jenseits des steilsten Winkels, bei dem die Kaskade noch anliegt, fällt
    der Beiwert leicht ab. So findet die Traglinie dort den Abriss, statt
    auf einer reibungsfrei immer weiter wachsenden Kurve zu landen.
    """
    werte = []
    abgerissen_null = False
    for d in versaetze:
        b = aero_kaskade.rechne(elemente, geschwindigkeit, anstellwinkel=d)
        werte.append((elemente[0].winkel + d, b.cl, b.cd, b.vertrauen,
                      b.abgerissen))
        if abs(d) < 1e-9:
            abgerissen_null = b.abgerissen
    werte.sort(key=lambda w: w[0])

    alpha = np.array([w[0] for w in werte])
    cl = np.array([w[1] for w in werte])
    cd = np.array([w[2] for w in werte])
    vertrauen = np.array([w[3] for w in werte])
    anliegend = ~np.array([w[4] for w in werte])

    if anliegend.any():
        grenze = int(np.argmax(anliegend))       # steilster anliegender Winkel
        for k in range(grenze - 1, -1, -1):
            cl[k] = cl[grenze] * (1.0 - 0.05 * (grenze - k))
            vertrauen[k] = min(vertrauen[k], 0.5)

    polare = Polare(alpha=alpha, cl=cl, cd=cd, cm=np.zeros_like(cl),
                    vertrauen=vertrauen,
                    reynolds=reynolds(geschwindigkeit,
                                      geo.gesamtsehne(elemente)),
                    name=" + ".join(e.name for e in elemente))
    return polare, bool(abgerissen_null)


def _skaliert(polare: Polare, faktor: float) -> Polare:
    return replace(polare, cl=polare.cl * faktor)


def rechne(haupt, spannweite, sehne: float, winkel: float, vorgaben: list,
           geschwindigkeit: float = 15.0,
           lage: tuple[float, float, float] = (0.0, 0.0, 0.0),
           endplatte_mm: float = 0.0, mit_boden: bool = True,
           abgleich: float = 1.0, stuetzen: int = 5,
           panels_je_seite: int = 16, punkte: int = 50) -> Kaskadenabtrieb:
    """Abtrieb und Widerstand der ganzen Kaskade über die Spannweite.

    `stuetzen` ist die Zahl der Stellen, an denen die Kaskade gebaut und
    gerechnet wird, verteilt nach Bereichslänge. Jeder Bereich bekommt
    mindestens eine, mit verdrehtem Flap mindestens zwei.
    """
    V = float(geschwindigkeit)
    stellen = [s.y for s in spannweite.stuetzstellen]
    innen, aussen = float(min(stellen)), float(max(stellen))
    f_sehne = _verlauf(stellen, [s.sehne for s in spannweite.stuetzstellen])
    f_twist = _verlauf(stellen, [s.verwindung for s in spannweite.stuetzstellen])
    f_z = _verlauf(stellen, [s.z for s in spannweite.stuetzstellen])
    f_x = _verlauf(stellen, [s.x for s in spannweite.stuetzstellen])

    grenzen = sorted({innen, aussen}
                     | {e for v in vorgaben for e in v.bereich(innen, aussen)})
    bereiche = [(a, b) for a, b in zip(grenzen[:-1], grenzen[1:]) if b - a > 1.0]
    verdreht = any(v.winkel_aussen is not None for v in vorgaben)

    stuetzwerte: list[Stuetzwert] = []
    for nr, (a, b) in enumerate(bereiche):
        anzahl = max(2 if verdreht else 1,
                     int(round(stuetzen * (b - a) / max(aussen - innen, 1e-9))))
        mitte = 0.5 * (a + b)
        vorhanden = [i for i, _ in geo.vorgaben_bei(vorgaben, mitte, innen, aussen)]
        for y in a + (np.arange(anzahl) + 0.5) * (b - a) / anzahl:
            y = float(y)
            kette = [replace(vorgaben[i],
                             winkel_relativ=vorgaben[i].winkel_bei(y, innen, aussen))
                     for i in vorhanden]
            c = sehne * float(f_sehne(y))
            w = winkel + float(f_twist(y))
            x0 = float(f_x(y)) + lage[0]
            z0 = float(f_z(y)) + lage[2]
            elemente = geo.platziere(haupt, c, w, kette, lage=(x0, z0),
                                     punkte=punkte)
            polare, abgerissen = kaskadenpolare(elemente, V)

            wirkung = None
            if mit_boden:
                wirkung = boden.kanalfaktor([e.punkte for e in elemente])
                polare = _skaliert(polare, wirkung.faktor)
            if abs(abgleich - 1.0) > 1e-12:
                polare = _skaliert(polare, abgleich)

            gesamt = geo.gesamtsehne(elemente)
            x_nase = float(np.vstack([e.punkte for e in elemente])[:, 0].min())
            erstes = elemente[0].punkte
            nase = erstes[int(np.argmax(np.linalg.norm(erstes - erstes[0], axis=1)))]
            z_viertel = nase[1] + 0.25 * (elemente[-1].hinterkante[1] - nase[1])
            stuetzwerte.append(Stuetzwert(
                y=y, namen=[e.name for e in elemente], sehne=c,
                gesamtsehne=gesamt, winkel=w, polare=polare,
                abgerissen=abgerissen, bodenwirkung=wirkung,
                x_viertel=(x_nase + 0.25 * gesamt - x0) / c,
                z_viertel=(z_viertel - z0) / c, bereich=nr))

    def stuetze_fuer(y: float) -> Stuetzwert:
        y = min(max(abs(y), innen), aussen)
        nr = len(bereiche) - 1
        for k, (a, b) in enumerate(bereiche):
            if y <= b:
                nr = k
                break
        kandidaten = [s for s in stuetzwerte if s.bereich == nr] or stuetzwerte
        return min(kandidaten, key=lambda s: abs(s.y - y))

    # Rechenstapel: je Stelle ein Ersatzschnitt aus Nase, Hinterkante und
    # Viertelsehne der ganzen Kaskade. Beiderseits jeder Bereichsgrenze ein
    # Schnitt, damit die Gesamtsehne dort springt und nicht verschmiert.
    ys = set(np.linspace(innen, aussen, 41).tolist())
    for g in grenzen[1:-1]:
        ys |= {g - 0.5, g + 0.5}
    ys = sorted(y for y in ys if innen - 1e-9 <= y <= aussen + 1e-9)

    stapel = []
    for y in ys:
        s = stuetze_fuer(y)
        c = sehne * float(f_sehne(y))
        w = winkel + float(f_twist(y))
        g = s.gesamtsehne / s.sehne * c
        xq = float(f_x(y)) + lage[0] + s.x_viertel * c
        zq = float(f_z(y)) + lage[2] + s.z_viertel * c
        yy = float(y) + lage[1]
        punkte = np.array([[xq + 0.75 * g, yy, zq], [xq - 0.25 * g, yy, zq],
                           [xq + 0.75 * g, yy, zq]])
        stapel.append(Schnitt(float(y), g, w, punkte))

    streifen = traglinie.streifen_aus_stapel(stapel, panels_je_seite)
    polaren = [stuetze_fuer(st.y).polare for st in streifen]
    kraefte = traglinie.rechne(stapel, polaren=polaren, geschwindigkeit=V,
                               panels_je_seite=panels_je_seite,
                               mit_boden=mit_boden, endplatte_mm=endplatte_mm)

    hinweise = []
    for s in stuetzwerte:
        if s.abgerissen:
            hinweise.append(f"Bei y = {s.y:.0f} mm reißt die Kaskade "
                            f"({', '.join(s.namen)}) schon im Schnitt ab.")
    wirkungen = [s.bodenwirkung for s in stuetzwerte if s.bodenwirkung]
    if wirkungen:
        tiefste = min(wirkungen, key=lambda w: w.hoehe_sehnen)
        hinweise.append(tiefste.text)

    return Kaskadenabtrieb(kraefte=kraefte, stuetzwerte=stuetzwerte,
                           abgleich=float(abgleich),
                           endplatte_mm=float(endplatte_mm), hinweise=hinweise)
