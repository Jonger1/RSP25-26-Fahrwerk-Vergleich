"""
Das ganze Auto: Frontfluegel, Heckfluegel und Unterboden zusammen.

Jedes Teil fuer sich hat einen Abtrieb. Was das Auto faehrt, ist die SUMME -
und vor allem, wo sie angreift. Die Aerobalance ist der Anteil des Abtriebs,
der auf der Vorderachse landet. Passt sie nicht zur Gewichtsverteilung, wird
das Auto mit steigender Geschwindigkeit zunehmend unter- oder uebersteuernd,
und kein Setup am Fahrwerk gleicht das ueber den ganzen Geschwindigkeits-
bereich aus.

**Die Rechnung.** Jedes Teil liefert Abtrieb F, Widerstand D, den Angriffs-
punkt x des Abtriebs (ab Vorderachse, nach hinten positiv) und die Hoehe z,
in der der Widerstand angreift. Mit dem Radstand L:

    Last vorne = Summe F (L - x) / L  -  Summe D z / L

Der zweite Term ist das Nickmoment des Widerstands: Er greift ueber dem
Boden an und entlastet die Vorderachse - beim hohen Heckfluegel spuerbar.

**Fahrzeuglage.** Rake und Nicken gelten fuer ALLE Teile gemeinsam. Hier
wirken sie deshalb auch auf die Fluegel: Positiver Rake (hinten hoeher)
senkt einen Frontfluegel vor der Vorderachse ab, hebt den Heckfluegel an und
stellt beide um denselben Winkel steiler an. Die Ansicht *Fluegel* rechnet
dagegen in Konstruktionslage ohne Rake.

**Nickwanderung.** Beim Bremsen taucht die Nase ab, beim Beschleunigen hebt
sie sich. Der Frontfluegel kommt dabei naeher an den Boden, der Unterboden
kippt - die Balance wandert. Wie weit, rechnet `wanderung` ueber einige
Nickwinkel. Ein Paket, dessen Balance beim Bremsen stark nach vorne wandert,
macht das Auto am Kurveneingang nervoes.

**Was fehlt:** Raeder, Karosserie, Fahrer, Seitenkaesten - und jede
Wechselwirkung zwischen den Teilen, vor allem der Nachlauf des Frontfluegels
auf dem Unterboden und der Abwind des Heckfluegels auf dem Diffusor. Die
Teile werden einzeln gerechnet und addiert.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np


@dataclass
class Beitrag:
    """Was ein Teil zum Auto beitraegt. Kraefte in N, Lagen in mm."""

    name: str
    art: str                    # "fluegel" oder "unterboden"
    abtrieb: float
    widerstand: float
    x: float                    # Angriffspunkt des Abtriebs ab Vorderachse
    z: float                    # Hoehe des Widerstandsangriffs ueber Grund
    hinweis: str = ""

    def last_vorne(self, radstand: float) -> float:
        return (self.abtrieb * (radstand - self.x)
                - self.widerstand * self.z) / radstand


@dataclass
class Zustand:
    """Eine Fahrzeuglage zusaetzlich zu Rake und Konstruktionslage.

    `nick_grad` positiv heisst hinten hoeher - dieselbe Richtung wie der
    Rake, also Bremsen. Gedreht wird um die Mitte des Radstands; der
    Schwerpunkt liegt nicht genau dort, fuer die Frage, wohin die Balance
    wandert, macht das wenig.
    """

    name: str = "Konstruktionslage"
    nick_grad: float = 0.0
    hub: float = 0.0


# Die Vorgabe fuer die Nickwanderung. Ein halbes Grad entspricht bei 1535 mm
# Radstand etwa 7 mm Weg an jeder Achse - der Bereich, in dem ein FS-Auto
# beim Bremsen und Beschleunigen tatsaechlich nickt.
NICKZUSTAENDE = [
    Zustand("Beschleunigen, Nase 0,5° höher", -0.5),
    Zustand("Nase 0,25° höher", -0.25),
    Zustand("Konstruktionslage", 0.0),
    Zustand("Nase 0,25° tiefer", 0.25),
    Zustand("Bremsen, Nase 0,5° tiefer", 0.5),
]


class Lage:
    """Rake und Zustand in einem - mit derselben Schnittstelle wie
    `spec.modell.Fahrzeuglage`, damit `unterboden.rechne` sie nimmt."""

    def __init__(self, fahrzeuglage=None, zustand: Zustand | None = None,
                 radstand: float = 1535.0):
        self.basis = fahrzeuglage
        self.zustand = zustand or Zustand()
        self.radstand = float(radstand)

    @property
    def rake_grad(self) -> float:
        """Die gesamte Neigung: Rake plus Nicken."""
        eigen = self.basis.rake_grad if self.basis is not None else 0.0
        return float(eigen) + self.zustand.nick_grad

    def hoehe(self, x, z):
        h = self.basis.hoehe(x, z) if self.basis is not None else z
        mitte = self.radstand / 2.0
        return (h + (np.asarray(x, dtype=float) - mitte)
                * math.tan(math.radians(self.zustand.nick_grad))
                + self.zustand.hub)

    def versatz(self, x: float) -> float:
        """Um wie viel die Lage einen Punkt bei x anhebt."""
        return float(self.hoehe(float(x), 0.0))


@dataclass
class Bilanz:
    beitraege: list[Beitrag]
    radstand: float
    geschwindigkeit: float
    zustand: Zustand = field(default_factory=Zustand)
    hinweise: list[str] = field(default_factory=list)

    @property
    def abtrieb(self) -> float:
        return float(sum(b.abtrieb for b in self.beitraege))

    @property
    def widerstand(self) -> float:
        return float(sum(b.widerstand for b in self.beitraege
                         if math.isfinite(b.widerstand)))

    @property
    def wirkungsgrad(self) -> float:
        return self.abtrieb / max(self.widerstand, 1e-9)

    @property
    def druckpunkt_x(self) -> float:
        """Wo der Gesamtabtrieb angreift, ohne das Widerstandsmoment."""
        if abs(self.abtrieb) < 1e-9:
            return float("nan")
        return float(sum(b.abtrieb * b.x for b in self.beitraege) / self.abtrieb)

    @property
    def last_vorne(self) -> float:
        return float(sum(b.last_vorne(self.radstand) for b in self.beitraege))

    @property
    def last_hinten(self) -> float:
        return self.abtrieb - self.last_vorne

    @property
    def balance_vorne(self) -> float:
        """Anteil der aerodynamischen Achslast auf der Vorderachse, 0..1."""
        if abs(self.abtrieb) < 1e-9:
            return float("nan")
        return self.last_vorne / self.abtrieb


# ------------------------------------------------------------- Beitraege

def angriffspunkt(kraefte, rueckfall: float) -> float:
    """Abtriebsgewichteter Viertelpunkt ueber die Streifen der Traglinie.

    Bei gepfeilten oder nach hinten versetzten Aussenschnitten wandert der
    Angriffspunkt mit - das kaeme mit der Wurzelsehne allein nicht heraus.
    """
    fest = getattr(kraefte, "x_angriff", None)
    if fest is not None and math.isfinite(fest):
        return float(fest)          # schon ausgewertet, etwa aus einem Kennfeld
    streifen = getattr(kraefte, "streifen", None) or []
    last = np.asarray(getattr(kraefte, "auftrieb_lokal", []), dtype=float)
    if not streifen or len(last) != len(streifen):
        return float(rueckfall)
    gewicht = np.abs(last) * np.array([s.breite for s in streifen])
    if gewicht.sum() <= 1e-12:
        return float(rueckfall)
    x = np.array([s.x_viertel for s in streifen], dtype=float)
    return float((gewicht * x).sum() / gewicht.sum())


def fluegelbeitrag(name: str, element, lage: Lage, geschwindigkeit: float,
                   rechnen: Callable) -> Beitrag:
    """Ein Fluegel in der gegebenen Fahrzeuglage.

    `rechnen(element, geschwindigkeit)` liefert Kraefte wie
    `traglinie.Fluegelkraefte`. Es kommt von aussen, weil der Weg zum
    Schnittstapel (Lage des tiefsten Punkts, Kaskade, Endplatte) in der
    Oberflaeche liegt und hier nicht ein zweites Mal entstehen soll.
    """
    x_ref = float(element.pos_x) + 0.25 * float(element.sehne)
    z_neu = float(element.pos_z) + lage.versatz(x_ref)
    if element.spannweite is None:
        return Beitrag(name, "fluegel", 0.0, 0.0, x_ref, z_neu,
                       "Ohne Sektionstabelle gibt es keine Spannweite - nicht "
                       "mitgerechnet.")
    if z_neu <= 0.0:
        return Beitrag(name, "fluegel", 0.0, float("nan"), x_ref, z_neu,
                       f"Setzt in dieser Lage auf ({z_neu:.0f} mm).")

    # Hinten hoeher dreht die Nase nach unten - Anstellwinkel negativ ist
    # Nase nach unten.
    gedreht = element.model_copy(update={
        "pos_z": z_neu,
        "anstellwinkel": float(element.anstellwinkel) - lage.rake_grad})
    kraefte = rechnen(gedreht, geschwindigkeit)
    return Beitrag(name, "fluegel", float(kraefte.abtrieb),
                   float(kraefte.widerstand), angriffspunkt(kraefte, x_ref),
                   z_neu)


def unterbodenbeitrag(ub, lage: Lage, geschwindigkeit: float) -> Beitrag:
    from . import unterboden

    try:
        e = unterboden.rechne(ub, lage, geschwindigkeit)
    except ValueError as fehler:
        return Beitrag("Unterboden", "unterboden", 0.0, float("nan"),
                       float(ub.x_start) + ub.laenge / 2, 0.0, str(fehler))
    return Beitrag("Unterboden", "unterboden", e.abtrieb, e.widerstand,
                   e.druckpunkt_x, e.kehle_hoehe,
                   "; ".join(e.hinweise))


def bilanz(fluegel: list[tuple[str, object]], unterboden, fahrzeuglage,
           rechnen: Callable, geschwindigkeit: float = 20.0,
           radstand: float = 1535.0,
           zustand: Zustand | None = None) -> Bilanz:
    """Alle Teile in einer Fahrzeuglage, addiert."""
    zustand = zustand or Zustand()
    lage = Lage(fahrzeuglage, zustand, radstand)
    beitraege = [fluegelbeitrag(n, e, lage, geschwindigkeit, rechnen)
                 for n, e in fluegel]
    if unterboden is not None:
        beitraege.append(unterbodenbeitrag(unterboden, lage, geschwindigkeit))

    hinweise = []
    if not beitraege:
        hinweise.append("Weder Flügel noch Unterboden - nichts zu rechnen.")
    arten = {b.art for b in beitraege if b.abtrieb}
    if beitraege and "unterboden" not in arten:
        hinweise.append("Ohne Unterboden: Die Balance hängt allein an den "
                        "Flügeln und ist entsprechend extrem.")
    vorne = [b for b in beitraege if b.art == "fluegel" and b.x < 0 and b.abtrieb]
    hinten = [b for b in beitraege if b.art == "fluegel" and b.x > radstand / 2
              and b.abtrieb]
    if beitraege and not vorne:
        hinweise.append("Kein Flügel vor der Vorderachse gerechnet.")
    if beitraege and not hinten:
        hinweise.append("Kein Flügel hinter der Fahrzeugmitte gerechnet.")
    return Bilanz(beitraege, float(radstand), float(geschwindigkeit),
                  zustand, hinweise)


def wanderung(fluegel, unterboden, fahrzeuglage, rechnen,
              geschwindigkeit: float = 20.0, radstand: float = 1535.0,
              zustaende: list[Zustand] | None = None) -> list[Bilanz]:
    """Die Bilanz ueber mehrere Nickzustaende - wohin die Balance wandert."""
    return [bilanz(fluegel, unterboden, fahrzeuglage, rechnen,
                   geschwindigkeit, radstand, z)
            for z in (zustaende or NICKZUSTAENDE)]


def empfindlichkeit(reihe: list[Bilanz]) -> float:
    """Wanderung der Balance in Prozentpunkten je Grad Nicken (Ausgleichs-
    gerade). Positiv: Beim Bremsen wandert sie nach vorne."""
    punkte = [(b.zustand.nick_grad, 100.0 * b.balance_vorne) for b in reihe
              if math.isfinite(b.balance_vorne)]
    if len(punkte) < 2 or len({p[0] for p in punkte}) < 2:
        return float("nan")
    x, y = np.array(punkte).T
    return float(np.polyfit(x, y, 1)[0])


def zielbalance_aus_datei(pfad=None) -> float | None:
    """Die statische Achslast vorn aus vehicle_ref.yaml, in Prozent.

    None, solange dort nichts eingetragen ist - dann gibt es keine Vorgabe,
    und das Werkzeug fragt nach einer.
    """
    import yaml
    from ..regeln.pruefung import VEHICLE_REF

    try:
        d = yaml.safe_load(open(pfad or VEHICLE_REF, encoding="utf-8")) or {}
        wert = (d.get("fahrdynamik") or {}).get("achslast_vorne_prozent")
        return None if wert is None else float(wert)
    except (OSError, TypeError, ValueError):
        return None
