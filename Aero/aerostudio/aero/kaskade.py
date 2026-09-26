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

**Das Abrisskriterium, Stand 24.09.2026.** Es hat zwei Korrekturen bekommen,
nachdem der alte Stand jede dreielementige Kaskade verworfen hatte — 68 von
80 Kombinationen fielen durch, während reale FS-Frontflügel durchweg
dreielementig sind.

*Erstens, die Nasensingularität.* Der kleinste Druckbeiwert lag durchweg bei
x/c = 0,002, also an der Nase, und wuchs mit jedem Flap: −2,8 bei einem
Element, −9,8 bei zweien, −23,0 bei dreien. Beim Einzelprofil ändert ein
Ausschluss des ersten Sehnenprozents nichts, im Verbund halbiert er den Wert
— das ist der Beweis, dass es keine Saugspitze war, sondern eine numerische
Spitze: Das Panelverfahren löst den Nasenradius mit hundert Panels nicht auf,
und je höher die Zirkulation, desto stärker entgleist es dort. Ausgewertet
wird deshalb ab `NASENAUSSCHLUSS`.

*Zweitens, die falsche Größe.* Verglichen wurde die absolute Saugspitze. Eine
Grenzschicht löst aber nicht an einer tiefen Spitze ab, sondern an dem
DRUCKANSTIEG dahinter — das ist A. M. O. Smiths Argument (High-Lift
Aerodynamics, 1975). Ein Flap bei −26 Grad hat eine sehr tiefe Saugspitze und
liegt trotzdem an, weil der Rückgewinn dahinter klein bleibt. Verglichen wird
jetzt `rueckgewinn` gegen den Wert, den dasselbe Profil allein an seinem
Abrisswinkel erreicht.

**Was weiterhin fehlt, und ein Negativbefund dazu.** Der Spalt bläst frische,
schnelle Luft in die Grenzschicht des folgenden Elements und hält sie
anliegend, weit über den Winkel hinaus, bei dem das Profil allein abreissen
würde. Diese Wirkung steckt hier nicht drin.

Der Versuch, wenigstens den Dumping-Effekt zu erfassen — das Element entlässt
seine Grenzschicht in die beschleunigte Strömung des Spalts statt auf
Umgebungsdruck —, ist gescheitert: Der Druck am Ende der Saugseite des
Hauptelements ändert sich kaum, ob null, ein oder zwei Flaps dahinter sitzen
(cp = 0,26 / 0,68 / 0,64 bei 95 % Sehne). In dieser reibungsfreien Rechnung
zeigt sich der Effekt nicht. Das ist festgehalten statt weggelassen, weil es
die erste Stelle ist, an der jemand mit CFD nachsehen sollte.

**Die Folge, ehrlich benannt:** Das Modell ist nach beiden Korrekturen
physikalisch stimmiger, aber immer noch ZU STRENG. Bei drei Elementen fällt
das Hauptelement durch, sobald die Flaps üblich groß sind. Der Vergleich
zweier Entwürfe untereinander trägt; die absolute Aussage "reisst ab" trägt
nicht. `GRENZSCHICHTRESERVE` ist der Ort, an dem eine Kalibrierung an
gemessenen oder gerechneten Daten einzutragen wäre — sie steht auf 1,0, also
unkalibriert, und bleibt dort, bis jemand solche Daten hat.
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
    rueckgewinn: float          # cp_Hinterkante - cp_min, im Verbund
    rueckgewinn_grenze: float   # derselbe Wert am Einzelprofil beim Abriss
    vertrauen: float

    @property
    def gewinn(self) -> float:
        """Um wieviel die Nachbarn den Beiwert anheben."""
        if abs(self.cl_allein) < 1e-9:
            return 1.0
        return self.cl_verbund / self.cl_allein

    @property
    def abgerissen(self) -> bool:
        """Muss die Grenzschicht mehr Druckanstieg überstehen als sie kann?

        **Nicht** mehr über die absolute Saugspitze. Das war das Kriterium bis
        zum 24.09., und es war zu streng: Von 80 durchgerechneten
        Kombinationen fielen 68 durch, keine einzige dreielementige überlebte
        — während reale FS-Frontflügel durchweg dreielementig sind.

        Der Fehler war grundsätzlich, nicht eine Frage der Kalibrierung. Eine
        Grenzschicht reißt nicht an einer tiefen Saugspitze ab, sondern an
        dem DRUCKANSTIEG dahinter. Und genau den verkürzt ein Spalt: Das
        Element bläst seine Hinterkante in die beschleunigte Strömung des
        folgenden Schlitzes, statt auf Umgebungsdruck zurückgewinnen zu
        müssen. Das ist A. M. O. Smiths Dumping-Effekt, einer der fünf
        Gründe, warum Mehrelementflügel überhaupt funktionieren.

        Ein Flap bei −26 Grad hat deshalb eine sehr tiefe Saugspitze und
        trotzdem anliegende Strömung: Er dumpt in einen ebenso tiefen
        Hinterkantendruck, der Rückgewinn dazwischen bleibt klein.
        """
        return self.rueckgewinn > self.rueckgewinn_grenze * GRENZSCHICHTRESERVE

    @property
    def reserve(self) -> float:
        """Wieviel Druckanstieg die Grenzschicht noch verträgt, als Anteil."""
        grenze = self.rueckgewinn_grenze * GRENZSCHICHTRESERVE
        if abs(grenze) < 1e-9:
            return 1.0
        return 1.0 - self.rueckgewinn / grenze


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

        grenze_spitze, grenze_rueckgewinn = _grenzen_beim_abriss(
            element.profil, pol.abriss_winkel)

        beitraege.append(Elementbeiwert(
            name=element.name, winkel=winkel,
            cl_allein=cl_allein, cl_verbund=cl_verbund, cl_zaeh=cl_zaeh,
            cd_zaeh=cd_zaeh, wirkungsgrad=wirkungsgrad,
            saugspitze=saugspitze(verbund.cp[i], koerper[i].punkte),
            saugspitze_grenze=grenze_spitze,
            rueckgewinn=rueckgewinn(verbund.cp[i], koerper[i].punkte),
            rueckgewinn_grenze=grenze_rueckgewinn,
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


# Das erste Sehnenprozent bleibt bei der Auswertung aussen vor.
#
# BEFUND vom 24.09.2026, und der Grund, warum keine dreielementige Kaskade
# ueberlebte: Der kleinste Druckbeiwert lag durchweg bei x/c = 0,002, also
# unmittelbar an der Nase - und er wuchs mit der Zirkulation, also mit jedem
# zusaetzlichen Flap:
#
#     Ausschluss    1 Element   2 Elemente   3 Elemente
#            0 %       -2,82       -9,81       -23,03
#            2 %       -2,82       -6,59       -10,77
#            5 %       -2,82       -5,79        -8,87
#
# Beim Einzelprofil aendert der Ausschluss NICHTS. Das ist der Beweis, dass
# es sich nicht um eine Saugspitze handelt, sondern um eine numerische
# Spitze: Das Panelverfahren loest den Nasenradius mit hundert Panels nicht
# auf, und je hoeher die Zirkulation, desto staerker entgleist es dort.
#
# Physikalisch ist die Nase ohnehin der falsche Ort, um nach Abloesung zu
# suchen. Dort ist die Grenzschicht duenn und stark beschleunigt; was es dort
# wirklich gibt, ist eine kurze laminare Abloeseblase, die wieder anlegt -
# und die eine reibungsfreie Rechnung grundsaetzlich nicht abbildet.
# Abgeloest wird stromab, im Druckanstieg.
#
# Zwei Prozent, weil die Reihe oben dort flach zu werden beginnt. Der Wert
# ist gewaehlt und nicht hergeleitet; deshalb steht die Empfindlichkeit hier
# und ein Test haelt sie fest.
NASENAUSSCHLUSS = 0.02


def _x_relativ(punkte: np.ndarray) -> np.ndarray:
    """Panelmittelpunkte als Sehnenanteil, 0 an der Nase, 1 an der Hinterkante."""
    mitte = 0.5 * (punkte[:-1] + punkte[1:])
    x = mitte[:, 0]
    spanne = float(np.ptp(punkte[:, 0]))
    return (x - float(punkte[:, 0].min())) / max(spanne, 1e-12)


# Wo die Saugseite ausgewertet wird - kurz VOR der Hinterkante.
#
# BEFUND vom 24.09.2026: An der Hinterkante selbst zwingt die
# Kutta-Bedingung den Druck auf Staupunktniveau, cp ~ +0,5. Gemessen am
# Hauptelement, unabhaengig von der Zahl der Flaps dahinter:
#
#     1 Element   cp an der Hinterkante  +0,49
#     2 Elemente                         +0,54
#     3 Elemente                         +0,44
#
# Wer dort auswertet, sieht vom Dumping-Effekt NICHTS - und der ist der
# Hauptgrund, warum ein Mehrelementfluegel mehr vertraegt als ein
# Einzelprofil. Gemeint ist der Druck dort, wo die Grenzschicht das Element
# tatsaechlich verlaesst und in den Spalt entlassen wird, also kurz vor der
# Hinterkante auf der SAUGSEITE.
ABLESESTELLE = 0.95

# Kalibrierfaktor auf den zulaessigen Druckanstieg. 1.0 heisst unkalibriert.
#
# Was dieser Faktor NICHT ist: eine Stellschraube, an der gedreht wird, bis
# ein Entwurf gruen meldet. Er steht auf 1.0 und bleibt dort, bis jemand
# gemessene oder mit CFD gerechnete Daten hat.
#
# Wozu er da ist: Das Kriterium unten ist nach zwei Korrekturen (Nasen-
# singularitaet, Druckanstieg statt Saugspitze) physikalisch stimmig, aber
# nachweislich immer noch ZU STRENG. Stand 24.09.2026 faellt bei drei
# Elementen das Hauptelement durch, sobald die Flaps ueblich gross sind:
#
#     Flapsehne   Spalt 1,5 %   Spalt 6 %
#       0,35 c       -0,64        -0,49      (Reserve des Hauptelements)
#       0,28 c       -0,38        -0,23
#       0,22 c       -0,14         0,00
#
# Reale FS-Frontfluegel sind dreielementig mit Flapsehnen um 0,3 c und
# Spalten um 2 %. Das Modell sagt fuer sie Abriss voraus, die Autos fahren
# trotzdem. Die Luecke ist also belegt, ihre Groesse nicht - dafuer braucht
# es Daten, nicht noch eine Annahme.
#
# Ein FUNDIERTER Verdacht, wohin die Luecke gehoert, steht bei ABLESESTELLE:
# Der Dumping-Effekt, der das Hauptelement entlasten muesste, zeigt sich in
# dieser reibungsfreien Rechnung nicht. Wer das Modell kalibriert, sollte
# dort zuerst nachsehen.
GRENZSCHICHTRESERVE = 1.0


def _saugseite(cp: np.ndarray, x_rel: np.ndarray) -> np.ndarray:
    """Maske der Panels auf der Seite, auf der die Saugspitze liegt.

    Welche der beiden Seiten das ist, haengt am Vorzeichen des Auftriebs und
    damit an Profil und Anstellwinkel - bei einem Abtriebsfluegel ist es die
    untere. Deshalb wird sie gesucht und nicht angenommen: Die Panelfolge
    laeuft ab Hinterkante ueber eine Seite zur Nase und ueber die andere
    zurueck, also trennt der Index der Nase die beiden Haelften.
    """
    nase = int(np.argmin(x_rel))
    maske = np.zeros(len(cp), dtype=bool)

    # Die Spitze AUSSERHALB der Nase suchen, mit demselben Ausschluss wie
    # `saugspitze`. Der rohe argmin landet sonst genau in der numerischen
    # Spitze an der Nase - und die liegt je nach Vernetzung mal auf der
    # einen, mal auf der anderen Seite. Bei einer dreielementigen Kaskade
    # traf sie die DRUCKseite, und der Rueckgewinn mischte anschliessend
    # beide Flaechen. Das ist genau die Groesse, auf der das ganze
    # Abrisskriterium ruht.
    frei = x_rel >= NASENAUSSCHLUSS
    if not frei.any():
        frei = np.ones(len(cp), dtype=bool)
    spitze = int(np.argmin(np.where(frei, cp, np.inf)))

    if spitze <= nase:
        maske[:nase + 1] = True
    else:
        maske[nase:] = True
    return maske


def rueckgewinn(cp: np.ndarray, punkte: np.ndarray | None = None) -> float:
    """Der Druckanstieg, den die Grenzschicht der Saugseite ueberstehen muss.

    Von der Saugspitze bis zur Ablesestelle kurz vor der Hinterkante. Das ist
    die Groesse, an der eine Grenzschicht wirklich abloest - nicht die
    Saugspitze allein. Eine tiefe Spitze ist unproblematisch, solange die
    Stroemung danach nicht weit zurueckgewinnen muss, und genau das ist der
    Dumping-Effekt: Das Element entlaesst seine Grenzschicht in die
    beschleunigte Stroemung des folgenden Spalts statt auf Umgebungsdruck.

    Ohne `punkte` wird schlicht gegen den Mittelwert der Randpanels
    gerechnet. Das ist die alte, grobe Form - nur fuer Vergleichsrechnungen.
    """
    cp = np.asarray(cp, dtype=float)
    if punkte is None:
        return 0.5 * (float(cp[0]) + float(cp[-1])) - float(cp.min())

    x_rel = _x_relativ(punkte)
    saug = _saugseite(cp, x_rel)
    hinten = saug & (x_rel >= ABLESESTELLE)
    if not hinten.any():
        hinten = saug & (x_rel >= x_rel[saug].max() - 0.05)
    cp_ablese = float(cp[hinten].mean()) if hinten.any() else float(cp[-1])
    return cp_ablese - saugspitze(cp, punkte)


def saugspitze(cp: np.ndarray, punkte: np.ndarray | None = None) -> float:
    """Der kleinste Druckbeiwert ausserhalb der Nasensingularitaet."""
    cp = np.asarray(cp, dtype=float)
    if punkte is None:
        return float(cp.min())
    maske = _x_relativ(punkte) >= NASENAUSSCHLUSS
    return float(cp[maske].min()) if maske.any() else float(cp.min())


@lru_cache(maxsize=64)
def _beim_abriss_roh(punkte_bytes, form, abrisswinkel) -> tuple[float, float]:
    """Saugspitze UND Rueckgewinn des Einzelprofils an seinem Abrisswinkel.

    Mit demselben Nasenausschluss wie im Verbund - sonst waere der Vergleich
    zwischen beiden Aepfel gegen Birnen.
    """
    p = np.frombuffer(punkte_bytes, dtype=float).reshape(form)
    loesung = panel.loese([panel.Koerper(punkte=p)], alpha_grad=abrisswinkel,
                          bezugssehne=1.0)
    return (saugspitze(loesung.cp[0], p), rueckgewinn(loesung.cp[0], p))


def _saugspitze_beim_abriss_roh(punkte_bytes, form, abrisswinkel) -> float:
    return _beim_abriss_roh(punkte_bytes, form, abrisswinkel)[0]


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
    return _beim_abriss_roh(punkte.tobytes(), punkte.shape,
                            round(float(abrisswinkel), 2))[0]


def _grenzen_beim_abriss(profil, abrisswinkel: float) -> tuple[float, float]:
    """Saugspitze und zulaessiger Rueckgewinn des Profils, beides beim Abriss.

    Der Rueckgewinn ist das eigentliche Kriterium; die Saugspitze wird
    weiterhin mitgefuehrt, weil sie in der Anzeige steht und beim Vergleich
    zweier Entwuerfe anschaulicher ist.

    Gepuffert, weil dieselben Zahlen in jeder Iteration der Suche gebraucht
    werden und nur von Profil und Abrisswinkel abhaengen.
    """
    punkte = profil.repanelisiert(100).punkte
    return _beim_abriss_roh(punkte.tobytes(), punkte.shape,
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
