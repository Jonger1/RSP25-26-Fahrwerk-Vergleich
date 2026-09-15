"""
Aerodynamik einer Kaskade — mehrere Elemente hintereinander.

Das Problem: NeuralFoil kennt nur das einzelne Profil, das Panelverfahren
kennt keine Reibung. Gebraucht wird beides zusammen, denn eine Kaskade lebt
von zwei Dingen gleichzeitig — der gegenseitigen Beeinflussung der Elemente
(reibungsfrei gut erfassbar) und dem Anliegen der Strömung (ohne Reibung
nicht beschreibbar).

**Wie beides verbunden wird — der wichtigste Absatz hier:**

Für die KRAFT wird je Element ein Wirkungsgrad bestimmt: das Verhältnis aus
zähem und reibungsfreiem Beiwert, gemessen am Element ALLEIN bei seinem
eigenen Winkel. Für die Katalogprofile liegt er bei 0,85 bis 0,87 — die
Reibung kostet also rund ein Siebtel. Dieser Wirkungsgrad wird auf den
reibungsfreien Beiwert IM VERBUND angewendet:

    cl_zaeh = cl_reibungsfrei_im_Verbund × (cl_zaeh_allein / cl_reibungsfrei_allein)

Für den ABRISS wird ein zweiter Weg gegangen, über die Saugspitze. Für jedes
Profil wird einmal bestimmt, welchen kleinsten Druckbeiwert es bei seinem
Abrisswinkel erreicht — das ist die Saugspitze, die seine Grenzschicht gerade
noch verträgt. Im Verbund wird dagegen verglichen.

**Warum nicht über einen wirksamen Anstellwinkel**, was naheliegend wäre: Ein
erster Anlauf rechnete die Beiwertdifferenz in einen Zusatzwinkel um und
fragte NeuralFoil danach. Das Ergebnis war unbrauchbar — dem Hauptelement
wurden bei drei Flaps −30 Grad wirksamer Winkel zugeschrieben und Abriss
gemeldet. Der Fehler ist grundsätzlich: Ein Flap hebt die Zirkulation des
Hauptelements, OHNE dessen Saugspitze entsprechend zu erhöhen. Er entlastet
den Druckanstieg an dessen Hinterkante — das ist der eigentliche Zweck einer
Kaskade. Diesen Gewinn in einen Anstellwinkel zu übersetzen unterstellt
gerade das Gegenteil.

**Was dieses Modell unterschätzt:** Der Spalt tut mehr, als die Zirkulation zu
erhöhen. Er bläst frische, schnelle Luft in die Grenzschicht des folgenden
Elements und hält sie dadurch anliegend, weit über den Winkel hinaus, bei dem
das Profil allein abreissen würde. Diese Wirkung steckt hier nicht drin — sie
lässt sich ohne Grenzschichtrechnung über den Spalt hinweg nicht erfassen.

Die Richtung des Fehlers ist damit bekannt: Bei gut gesetztem Spalt liefert
dieses Modell eher ZU WENIG. Der reibungsfreie Wert wird deshalb mit
ausgewiesen; er ist die Obergrenze.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from ..geometrie import kaskade as geo
from . import panel
from .profilpolare import polare, reynolds

# Auftriebsanstieg der ebenen Platte, je Grad - rechnet eine Beiwertdifferenz
# in einen Winkel um.
CL_ALPHA_GRAD = 2.0 * np.pi * np.pi / 180.0


@dataclass
class Elementbeiwert:
    """Was ein einzelnes Element in der Kaskade beiträgt."""

    name: str
    winkel: float
    cl_allein: float            # reibungsfrei, ohne Nachbarn
    cl_verbund: float           # reibungsfrei, im Verbund
    cl_zaeh: float              # mit Reibung, im Verbund
    cd_zaeh: float
    wirkungsgrad: float         # zäh je reibungsfrei, allein gemessen
    saugspitze: float           # kleinster cp im Verbund
    saugspitze_grenze: float    # was das Profil beim Abriss erreicht
    vertrauen: float

    @property
    def gewinn(self) -> float:
        """Um wieviel die Nachbarn den Beiwert anheben."""
        if abs(self.cl_allein) < 1e-9:
            return 1.0
        return self.cl_verbund / self.cl_allein

    @property
    def abgerissen(self) -> bool:
        """Saugspitze über dem, was die Grenzschicht des Profils verträgt."""
        return self.saugspitze < self.saugspitze_grenze

    @property
    def reserve(self) -> float:
        """Wieviel Saugspitze noch übrig ist, als Anteil der Grenze."""
        if abs(self.saugspitze_grenze) < 1e-9:
            return 1.0
        return 1.0 - self.saugspitze / self.saugspitze_grenze


@dataclass
class Kaskadenbeiwert:
    """Ergebnis einer Kaskadenrechnung, bezogen auf die Gesamtsehne."""

    cl: float                   # zäh, negativ = Abtrieb
    cd: float
    cl_reibungsfrei: float      # die Obergrenze, siehe Modul-Docstring
    gesamtsehne: float
    elemente: list[Elementbeiwert] = field(default_factory=list)
    reynolds: float = 0.0
    bodennah: bool = False

    @property
    def vertrauen(self) -> float:
        return min((e.vertrauen for e in self.elemente), default=1.0)

    @property
    def abgerissen(self) -> bool:
        return any(e.abgerissen for e in self.elemente)

    @property
    def knappste_reserve(self) -> float:
        """Das Element, das der Ablösung am nächsten ist."""
        return min((e.reserve for e in self.elemente), default=1.0)

    @property
    def spanne(self) -> tuple[float, float]:
        """Der Bereich, in dem der wahre Wert liegen dürfte.

        Untere Grenze ist die zähe Rechnung, obere die reibungsfreie. Der
        Spalt hält die Strömung länger anliegend, als das Modell weiss - die
        Wahrheit liegt dazwischen und näher an der zähen Rechnung, solange
        der Spalt nicht sorgfältig abgestimmt ist.
        """
        return (self.cl, self.cl_reibungsfrei)

    def __str__(self) -> str:
        return (f"cl {self.cl:+.3f} (reibungsfrei {self.cl_reibungsfrei:+.3f}), "
                f"cd {self.cd:.4f}, Gesamtsehne {self.gesamtsehne:.1f} mm, "
                f"{len(self.elemente)} Elemente")


def rechne(elemente: list[geo.Elementlage], geschwindigkeit: float = 15.0,
           mit_boden: bool = False, bodenhoehe: float = 0.0,
           anstellwinkel: float = 0.0) -> Kaskadenbeiwert:
    """Rechnet die Beiwerte einer angeordneten Kaskade.

    `anstellwinkel` dreht die ANSTRÖMUNG, also das ganze Paket auf einmal -
    die Elemente stehen zueinander fest. Ihre eigenen Winkel stecken schon in
    der Geometrie.

    Die 2D-Bodenspiegelung ist bewusst nur ein Diagnosewerkzeug. Dicht über
    dem Boden kennt eine reibungsfreie Panelrechnung keine Grenzschicht und
    keinen Abriss im Kanal; ihr Abtrieb wächst dann unphysikalisch ins
    Unbegrenzte. Für die Anzeige und die Entwurfssuche wird sie deshalb nicht
    aktiviert. Der Bodeneffekt bleibt ein CFD-/Mess-Abgleichpunkt.
    """
    sehne_gesamt = geo.gesamtsehne(elemente)
    koerper = [panel.Koerper(punkte=e.punkte, name=e.name) for e in elemente]

    verbund = panel.loese(koerper, alpha_grad=anstellwinkel,
                          mit_boden=mit_boden, bodenhoehe=bodenhoehe,
                          bezugssehne=sehne_gesamt)

    beitraege: list[Elementbeiwert] = []
    cl_zaeh_gesamt = 0.0
    cd_zaeh_gesamt = 0.0

    for i, element in enumerate(elemente):
        # Dasselbe Element ALLEIN, an derselben Stelle und beim selben Winkel.
        # An derselben Stelle, weil der Boden sonst anders wirkt.
        allein = panel.loese([koerper[i]], alpha_grad=anstellwinkel,
                             mit_boden=mit_boden, bodenhoehe=bodenhoehe,
                             bezugssehne=element.sehne)

        cl_verbund = (verbund.cl_je_koerper[i] * sehne_gesamt
                      / max(element.sehne, 1e-9))
        cl_allein = allein.cl_gesamt
        winkel = element.winkel + anstellwinkel

        pol = polare(element.profil, reynolds(geschwindigkeit, element.sehne))
        cl_zaeh_allein = float(pol.cl_bei(winkel))
        cd_zaeh_allein = float(pol.cd_bei(winkel))

        # Wirkungsgrad: was die Reibung von der reibungsfreien Rechnung
        # uebriglaesst. Bei den Katalogprofilen 0.85 bis 0.87. Auf eins
        # begrenzt - mehr als reibungsfrei geht nicht.
        if abs(cl_allein) > 1e-6:
            wirkungsgrad = min(abs(cl_zaeh_allein / cl_allein), 1.0)
        else:
            wirkungsgrad = 0.86
        cl_zaeh = cl_verbund * wirkungsgrad
        # Widerstand beim WIRKSAMEN Winkel, nicht beim geometrischen: Ein Flap
        # bei -26 Grad waere allein laengst abgerissen und haette einen
        # riesigen Widerstand. Im Verbund traegt er viel weniger, weil das
        # Element davor die Stroemung schon umlenkt. Abgelesen wird deshalb
        # dort, wo das Element allein den Beiwert haette, den es im Verbund
        # tatsaechlich traegt.
        cd_zaeh = _cd_beim_beiwert(pol, cl_zaeh, cd_zaeh_allein)

        beitraege.append(Elementbeiwert(
            name=element.name, winkel=winkel,
            cl_allein=cl_allein, cl_verbund=cl_verbund, cl_zaeh=cl_zaeh,
            cd_zaeh=cd_zaeh, wirkungsgrad=wirkungsgrad,
            saugspitze=float(verbund.cp[i].min()),
            saugspitze_grenze=_saugspitze_beim_abriss(element.profil,
                                                      pol.abriss_winkel),
            vertrauen=float(pol.vertrauen_bei(winkel))))

        # Auf die Gesamtsehne umrechnen, damit sich die Beitraege addieren.
        anteil = element.sehne / sehne_gesamt
        cl_zaeh_gesamt += cl_zaeh * anteil
        cd_zaeh_gesamt += cd_zaeh * anteil

    return Kaskadenbeiwert(
        cl=cl_zaeh_gesamt, cd=cd_zaeh_gesamt,
        cl_reibungsfrei=verbund.cl_gesamt, gesamtsehne=sehne_gesamt,
        elemente=beitraege,
        reynolds=reynolds(geschwindigkeit, sehne_gesamt),
        bodennah=verbund.bodennah)


def _cd_beim_beiwert(pol, cl_ziel: float, rueckfall: float) -> float:
    """Profilwiderstand bei dem Winkel, bei dem das Profil `cl_ziel` traegt.

    Gesucht wird nur auf dem anliegenden Ast der Polare - zwischen Abriss und
    der anderen Seite. Traegt das Element mehr, als es allein je koennte,
    bleibt es beim Widerstand am Abriss.
    """
    grenze = pol.abriss_winkel
    maske = pol.alpha >= grenze if grenze < 0 else pol.alpha <= grenze
    if int(maske.sum()) < 2:
        return rueckfall
    cl = pol.cl[maske]
    alpha = pol.alpha[maske]
    ordnung = np.argsort(cl)
    alpha_wirksam = float(np.interp(cl_ziel, cl[ordnung], alpha[ordnung]))
    return float(pol.cd_bei(alpha_wirksam))


@lru_cache(maxsize=64)
def _saugspitze_beim_abriss_roh(punkte_bytes, form, abrisswinkel) -> float:
    p = np.frombuffer(punkte_bytes, dtype=float).reshape(form)
    loesung = panel.loese([panel.Koerper(punkte=p)], alpha_grad=abrisswinkel,
                          bezugssehne=1.0)
    return float(loesung.cp[0].min())


def _saugspitze_beim_abriss(profil, abrisswinkel: float) -> float:
    """Welchen kleinsten Druckbeiwert erreicht dieses Profil beim Abriss?

    Das ist die Saugspitze, die seine Grenzschicht gerade noch vertraegt -
    reibungsfrei gerechnet, damit sie mit der Kaskadenrechnung vergleichbar
    ist. Ein Profil, dessen Saugspitze im Verbund darunter liegt, ist
    gefaehrdet.

    Gepuffert, weil dieselbe Zahl in jeder Iteration der Suche gebraucht wird
    und nur von Profil und Abrisswinkel abhaengt.
    """
    punkte = profil.repanelisiert(100).punkte
    return _saugspitze_beim_abriss_roh(punkte.tobytes(), punkte.shape,
                                       round(float(abrisswinkel), 2))


def baue_und_rechne(haupt, sehne: float, winkel: float,
                    flaps: list[geo.Kaskadenvorgabe] | None = None,
                    geschwindigkeit: float = 15.0,
                    hoehe_ueber_boden: float | None = None,
                    punkte: int = 100) -> tuple[list[geo.Elementlage],
                                                Kaskadenbeiwert]:
    """Anordnen und rechnen in einem Schritt.

    `hoehe_ueber_boden` setzt die Nase des Hauptelements auf diese Höhe. Die
    bodennahe Panel-Spiegelung wird absichtlich nicht eingeschaltet: Sie ist
    ohne Grenzschichtmodell kein belastbarer Abtriebswert.
    """
    lage = (0.0, hoehe_ueber_boden if hoehe_ueber_boden is not None else 0.0)
    elemente = geo.platziere(haupt, sehne, winkel, flaps, lage=lage,
                             punkte=punkte)
    beiwert = rechne(elemente, geschwindigkeit, mit_boden=False)
    return elemente, beiwert
