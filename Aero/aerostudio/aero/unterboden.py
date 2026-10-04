"""
Unterboden und Diffusor als Kanal - der groesste aerodynamische Hebel (M8).

**Warum ein Kanalmodell und nicht das Panelverfahren.** Zwischen Unterboden
und Strasse stroemt die Luft durch einen flachen Kanal, dessen Hoehe klein ist
gegen seine Laenge. Dort bestimmt die QUERSCHNITTSFLAECHE die Geschwindigkeit,
und die Geschwindigkeit den Unterdruck - Kontinuitaet und Bernoulli. Das
Panelverfahren mit Bodenspiegelung waere hier das falsche Werkzeug: Es kennt
keine Reibung, und ohne Reibung waechst der Sog im engen Kanal ohne Grenze
(derselbe Befund wie beim Frontfluegel in aero/boden.py).

**Das Modell in drei Zeilen.** Die Stroemung tritt vorne aus der freien
Anstroemung ein, verliert dabei einen Teil ihres Totaldrucks (K_EINLASS),
wird in der Kehle am schnellsten und gewinnt im Diffusor Druck zurueck - aber
nur den Anteil eta des idealen Rueckgewinns. Am Diffusorende muss der Druck
dem Basisdruck hinter dem Auto entsprechen. Daraus folgt geschlossen:

    (u_Kehle / U)^2 = (1 - cp_Basis) / (1 + K_Einlass - eta * (1 - (A_Kehle/A_Ende)^2))

Das ist die ganze Physik. Alles andere ist Buchhaltung ueber die Laenge.

**Was das Modell kann:** die richtige RICHTUNG jeder Parameteraenderung
liefern, und das schnell - ein paar Millisekunden je Variante, also tausend
Varianten in einem DoE-Lauf in Sekunden. Kehle tiefer, mehr Abtrieb;
Diffusor steiler, mehr Abtrieb bis zur Abloesegrenze, dann weniger; Rake
wirkt wie ein steilerer Diffusor.

**Was es nicht kann, und das gehoert in jeden Report:**

* Seitliches Nachstroemen. Schleifschuerzen sind nach T 2.2.2 verboten, also
  ist der Kanal seitlich offen. Das steckt pauschal in `abdichtung`, und
  dieser Faktor ist geraten. Er ist der erste Wert, der mit CFD abzugleichen
  ist.
* Die Diffusorabloesung selbst. Sie steckt als Abfall von eta ueber einem
  kritischen Winkel drin - die Grenze stammt aus der Literatur zu
  Bodeneffekt-Diffusoren, nicht aus einer Rechnung.
* Das Zusammenwachsen der Grenzschichten bei sehr kleiner Bodenfreiheit.
  Unterhalb von etwa 20 mm bricht der Abtrieb in Wirklichkeit ein; hier
  waechst er weiter. T 2.2.1 verbietet solche Hoehen ohnehin - die
  Bodenfreiheitspruefung faengt es ab.
* Raeder, Seitenkaesten, Nachlauf des Frontfluegels. Nichts davon ist drin.

Der Vergleich zweier Entwuerfe untereinander traegt. Die absoluten Newton
tragen erst nach dem Abgleich.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

# Totaldruckverlust beim Eintritt in den Kanal, als Anteil des Staudrucks in
# der Kehle. Fuer eine gut verrundete Einlasskante liegen typische Werte um
# 0,05 bis 0,15; gewaehlt ist die Mitte.
K_EINLASS = 0.10

# Wirkungsgrad des Diffusors bei anliegender Stroemung: welcher Anteil des
# idealen Druckrueckgewinns tatsaechlich erreicht wird.
ETA_DIFFUSOR = 0.80

# Ab welchem wirksamen Winkel der Diffusor abzuloesen beginnt, und bei
# welchem er praktisch nichts mehr zurueckgewinnt. In der Literatur zu
# Bodeneffekt-Diffusoren (u. a. Cooper et al. 1998, Ruhrmann und Zhang 2003)
# liegt das Abtriebsmaximum typisch zwischen etwa 10 und 17 Grad; darueber
# loest die Stroemung im Diffusor ab. Die Werte hier sind eine Lesart davon,
# keine Rechnung.
WINKEL_KRITISCH = 15.0
WINKEL_ABGELOEST = 25.0
ETA_ABGELOEST = 0.25

# Druck am Diffusorende gegen die freie Anstroemung - der Nachlauf hinter dem
# Auto liegt leicht im Unterdruck.
CP_BASIS = -0.10

# Reibungsbeiwert der Unterbodenflaeche, turbulent, glatt.
CF_BODEN = 0.004

DICHTE = 1.2    # kg/m^3


@dataclass
class Unterbodenergebnis:
    """Was die Rechnung liefert. Kraefte in N, Laengen in mm."""

    x: np.ndarray               # Stationen entlang des Bodens
    hoehe: np.ndarray           # Hoehe ueber Grund an jeder Station
    cp: np.ndarray              # Druckbeiwert an jeder Station
    abtrieb: float
    widerstand: float
    druckpunkt_x: float         # wo der Abtrieb angreift - fuer die Balance
    kehle_x: float
    kehle_hoehe: float
    diffusor_winkel_wirksam: float   # samt Rake
    eta: float                  # tatsaechlicher Diffusorwirkungsgrad
    geschwindigkeit: float      # m/s
    hinweise: list[str] = field(default_factory=list)

    @property
    def cp_min(self) -> float:
        return float(self.cp.min())

    @property
    def wirkungsgrad(self) -> float:
        return self.abtrieb / max(self.widerstand, 1e-9)

    @property
    def abgeloest(self) -> bool:
        return self.diffusor_winkel_wirksam > WINKEL_KRITISCH


def eta(winkel_grad: float) -> float:
    """Diffusorwirkungsgrad ueber dem wirksamen Winkel.

    Bis zum kritischen Winkel konstant, dann linear fallend bis auf den Rest,
    den ein abgeloester Diffusor noch leistet. Linear ist gewaehlt, nicht
    gemessen - es ist die einfachste Form, die das Maximum an der richtigen
    Stelle hat.
    """
    w = abs(float(winkel_grad))
    if w <= WINKEL_KRITISCH:
        return ETA_DIFFUSOR
    if w >= WINKEL_ABGELOEST:
        return ETA_ABGELOEST
    anteil = (w - WINKEL_KRITISCH) / (WINKEL_ABGELOEST - WINKEL_KRITISCH)
    return ETA_DIFFUSOR + anteil * (ETA_ABGELOEST - ETA_DIFFUSOR)


def hoehenverlauf(ub, lage=None, hub: float = 0.0,
                  n: int = 400) -> tuple[np.ndarray, np.ndarray]:
    """Hoehe ueber Grund entlang des Bodens, mit Rake und Hub.

    `hub` hebt (positiv) oder senkt (negativ) das ganze Fahrzeug - so wird
    der Federweg abgefahren, ohne die Konstruktion anzufassen.
    """
    x0 = float(ub.x_start)
    x1 = x0 + ub.einlass_laenge
    x2 = x1 + ub.kehle_laenge
    x3 = x2 + ub.diffusor_laenge
    # Die Knickstellen gehoeren ins Raster. Bei einem stueckweise linearen
    # Boden liegt die tiefste Stelle immer an einem Knick; ein gleichmaessiges
    # Raster trifft ihn nur zufaellig und ueberschaetzt dann die
    # Bodenfreiheit - bei T 2.2.1 die falsche Richtung.
    #
    # Auf den Nanometer gerundet, bevor vereinigt wird: Liegt ein Knick
    # zufaellig auf einem Rasterpunkt, ergaeben linspace und Knickliste zwei
    # Werte im Abstand 1e-13, und np.gradient lieferte dort eine riesige
    # Steigung - der Diffusor galt dann als abgeloest (Review 29.09.).
    x = np.union1d(np.round(np.linspace(x0, x3, n), 6),
                   np.round([x0, x1, x2, x3], 6))

    h = np.empty_like(x)
    m = x <= x1
    h[m] = np.interp(x[m], [x0, x1], [ub.einlass_hoehe, ub.kehle_hoehe_vorne])
    m = (x > x1) & (x <= x2)
    h[m] = np.interp(x[m], [x1, x2], [ub.kehle_hoehe_vorne, ub.kehle_hoehe_hinten])
    m = x > x2
    h[m] = ub.kehle_hoehe_hinten + (x[m] - x2) * math.tan(
        math.radians(ub.diffusor_winkel))

    if lage is not None:
        h = np.asarray(lage.hoehe(x, h), dtype=float)
    return x, h + float(hub)


def rechne(ub, lage=None, geschwindigkeit: float = 20.0,
           hub: float = 0.0) -> Unterbodenergebnis:
    """Abtrieb, Widerstand und Druckverlauf des Unterbodens."""
    x, h = hoehenverlauf(ub, lage, hub)
    hinweise: list[str] = []

    if h.min() <= 0.0:
        raise ValueError(
            f"Der Unterboden setzt auf: tiefster Punkt {h.min():.1f} mm bei "
            f"x = {x[int(np.argmin(h))]:.0f} mm. Rake, Hub oder Kehlenhoehe "
            f"passen so nicht zusammen.")

    b = float(ub.breite)
    flaeche = b * h                                  # mm^2

    # Die Kehle ist die engste Stelle VOR dem Diffusor. Im Diffusor waechst
    # die Flaeche ohnehin - aber mit Rake kann auch ein flacher Diffusor
    # vorne tiefer liegen als die Kehle. Dann ist dort die Kehle.
    diffusor_start = float(ub.x_start + ub.einlass_laenge + ub.kehle_laenge)
    vorne = x <= diffusor_start + 1e-9
    i_t = int(np.argmin(np.where(vorne, flaeche, np.inf)))
    a_t, a_e = float(flaeche[i_t]), float(flaeche[-1])

    # Wirksamer Diffusorwinkel: die STEILSTE oertliche Aufweitung hinter der
    # Kehle, samt Rake. Abloesen tut die Stroemung dort, wo sie am staerksten
    # verzoegert wird, und das ist eine oertliche Groesse.
    #
    # Der erste Anlauf mass den Winkel als Sekante von der Kehle bis zum Ende.
    # Mit Rake wandert die engste Stelle aber an den KEHLENANFANG, und die
    # Sekante lief dann ueber die ganze flache Kehle - 0,5 Grad Rake machten
    # den Diffusor scheinbar flacher (10 auf 3,8 Grad) statt steiler.
    steigung = np.gradient(h, x)
    hinten = np.arange(len(x)) > i_t
    groesste = float(steigung[hinten].max()) if hinten.any() else 0.0
    winkel = math.degrees(math.atan(max(groesste, 0.0)))
    wirkung = eta(winkel)
    if winkel > WINKEL_KRITISCH:
        hinweise.append(
            f"Wirksamer Diffusorwinkel {winkel:.1f} Grad liegt ueber "
            f"{WINKEL_KRITISCH:.0f} Grad - die Stroemung loest im Diffusor "
            f"ab, der Druckrueckgewinn sinkt auf {wirkung:.0%}.")

    r = a_t / max(a_e, 1e-9)
    nenner = 1.0 + K_EINLASS - wirkung * (1.0 - r * r)
    if nenner < 0.05:
        # Physikalisch hiesse das: mehr Rueckgewinn als Verlust, der Kanal
        # saugt unbegrenzt. Das Modell ist dort nicht mehr gueltig.
        nenner = 0.05
        hinweise.append("Flaechenverhaeltnis ausserhalb des Gueltigkeits"
                        "bereichs - der Diffusor ist zu gross fuer die Kehle.")
    k2 = (1.0 - CP_BASIS) / nenner                   # (u_Kehle/U)^2

    geschw_rel = np.sqrt(k2) * a_t / flaeche          # u/U an jeder Station
    cp = np.empty_like(x)
    vor = np.arange(len(x)) <= i_t
    cp[vor] = 1.0 - (1.0 + K_EINLASS) * geschw_rel[vor] ** 2
    cp_t = 1.0 - (1.0 + K_EINLASS) * k2
    cp[~vor] = cp_t + wirkung * k2 * (1.0 - (a_t / flaeche[~vor]) ** 2)

    q = 0.5 * DICHTE * geschwindigkeit ** 2          # Pa
    b_m = b / 1000.0
    x_m = x / 1000.0
    integral = float(np.trapezoid(cp, x_m)) if hasattr(np, "trapezoid") \
        else float(np.trapz(cp, x_m))

    abtrieb = -ub.abdichtung * q * b_m * integral

    # Druckpunkt: wo der Abtrieb angreift. Fuer die Aerobalance die Zahl,
    # die zaehlt - ein Unterboden, der seinen Abtrieb hinter die Hinterachse
    # legt, macht das Auto untersteuern.
    moment = float(np.trapezoid(cp * x_m, x_m)) if hasattr(np, "trapezoid") \
        else float(np.trapz(cp * x_m, x_m))
    druckpunkt = 1000.0 * moment / integral if abs(integral) > 1e-12 else float("nan")

    # Widerstand: der verlorene Totaldruck mal den Volumenstrom, plus Reibung.
    verlust = K_EINLASS + (1.0 - wirkung) * (1.0 - r * r)
    a_t_m2 = a_t / 1e6
    widerstand_verlust = q * a_t_m2 * k2 ** 1.5 * verlust
    widerstand_reibung = CF_BODEN * q * b_m * float(
        np.trapezoid(geschw_rel ** 2, x_m) if hasattr(np, "trapezoid")
        else np.trapz(geschw_rel ** 2, x_m))

    return Unterbodenergebnis(
        x=x, hoehe=h, cp=cp, abtrieb=float(abtrieb),
        widerstand=float(widerstand_verlust + widerstand_reibung),
        druckpunkt_x=float(druckpunkt), kehle_x=float(x[i_t]),
        kehle_hoehe=float(h[i_t]), diffusor_winkel_wirksam=float(winkel),
        eta=float(wirkung), geschwindigkeit=float(geschwindigkeit),
        hinweise=hinweise)


@dataclass
class Hoehenkennlinie:
    """Abtrieb ueber dem Hub - wie empfindlich der Boden auf Federwege ist."""

    hub: np.ndarray
    abtrieb: np.ndarray

    @property
    def stabilitaet(self) -> float:
        """Kleinster durch groessten Abtrieb im Bereich, 1 = voellig stabil.

        Das dritte Ziel des DoE neben Abtrieb und Widerstand: Ein Boden, der
        bei 10 mm Einfedern die Haelfte seines Abtriebs verliert, macht das
        Auto unfahrbar, auch wenn er in Konstruktionslage glaenzt.
        """
        groesster = float(self.abtrieb.max())
        if groesster <= 0.0:
            return 0.0
        return max(0.0, float(self.abtrieb.min()) / groesster)


def kennlinie(ub, lage=None, geschwindigkeit: float = 20.0,
              hub_bereich: float = 15.0, stufen: int = 7) -> Hoehenkennlinie:
    """Rechnet den Boden ueber den Hub von -bereich bis +bereich.

    Stufen, bei denen der Boden aufsetzen wuerde, werden mit Abtrieb 0
    gefuehrt statt ausgelassen: Aufsetzen ist der schlechteste Fall und soll
    die Stabilitaet auch so bewerten.
    """
    hub = np.linspace(-hub_bereich, hub_bereich, stufen)
    werte = []
    for dz in hub:
        try:
            werte.append(rechne(ub, lage, geschwindigkeit, float(dz)).abtrieb)
        except ValueError:
            werte.append(0.0)
    return Hoehenkennlinie(hub=hub, abtrieb=np.asarray(werte, dtype=float))


@dataclass
class Bodenbefund:
    regel: str
    text: str
    ok: bool
    ist: float
    grenze: float


def pruefe(ub, lage=None, regelsatz=None,
           einfedern: float | None = None) -> list[Bodenbefund]:
    """T 2.2.1 und das Aufsetzen im tiefsten Fahrzustand.

    T 2.2.1 verlangt 30 mm STATISCHE Bodenfreiheit mit Fahrer - geprueft in
    Konstruktionslage samt Rake. Zusaetzlich darf im tiefsten Fahrzustand
    nichts aufsetzen; das ist keine Zahl aus dem Reglement, sondern die
    Bedingung dafuer, dass die Rechnung ueberhaupt gilt.
    """
    if einfedern is None:
        # Derselbe Fahrzustand wie bei der Fluegelpruefung - nicht eine
        # eigene Zahl, die auseinanderlaufen kann.
        from ..regeln import Fahrzustand
        einfedern = Fahrzustand().tief
    grenze = 30.0
    if regelsatz is not None:
        try:
            grenze = float((regelsatz["uebernommen_aus_2026"] or {})
                           .get("t2_2_1_bodenfreiheit_min", 30.0))
        except (KeyError, TypeError):
            pass

    _x, h = hoehenverlauf(ub, lage)
    tiefster = float(h.min())
    return [
        Bodenbefund("T 2.2.1", f"Statische Bodenfreiheit (min {grenze:.0f} mm)",
                    tiefster >= grenze - 1e-9, tiefster, grenze),
        Bodenbefund("—", f"Kein Aufsetzen bei {einfedern:.0f} mm Einfedern",
                    tiefster - einfedern > 0.0, tiefster - einfedern, 0.0),
    ]
