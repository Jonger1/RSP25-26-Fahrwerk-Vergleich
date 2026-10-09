"""
DRS - der verstellbare Flap (M8, Aufgabe 5).

Ein Flap mit `drs_winkel` hat zwei Zustaende: zu (Kurve, `winkel`) und offen
(Gerade, `drs_winkel`). Offen heisst flacher angestellt: weniger Abtrieb,
deutlich weniger Widerstand. Das Reglement verbietet ein bewegliches
Aerosystem nicht (Konzept 4.1); Monash setzt es seit Jahren ein.

Was hier entsteht, ist immer ein GEWOEHNLICHES Spec im jeweiligen Zustand.
Alle Rechnungen - Kraefte, Regelpruefung, Balance, Export - laufen darauf
unveraendert. Es gibt keinen DRS-Sonderweg durch das Werkzeug.

**Grenze:** Der offene Flap wird wie jeder Flap ueber Spalt und Ueberlappung
angeordnet, also so, als saesse er fuer den neuen Winkel neu justiert. Ein
echtes DRS dreht um ein festes Scharnier - Spalt und Ueberlappung aendern
sich dabei. Fuer die Kraefte ist das zweitrangig, fuer die Kinematik und
die Kollisionspruefung nicht: Die gehoeren an das Scharnier in Creo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


def hat_drs(element) -> bool:
    return any(k.drs_winkel is not None for k in element.kaskade)


def element_offen(element):
    """Das Element mit offenem DRS. Ohne DRS unveraendert zurueck."""
    if not hat_drs(element):
        return element
    stufen = []
    for k in element.kaskade:
        if k.drs_winkel is None:
            stufen.append(k)
            continue
        delta = k.drs_winkel - k.winkel
        # Ein verwundener Flap dreht als Ganzes - der Winkel aussen wandert
        # um denselben Betrag mit.
        aussen = None if k.winkel_aussen is None else k.winkel_aussen + delta
        stufen.append(k.model_copy(update={"winkel": k.drs_winkel,
                                           "winkel_aussen": aussen}))
    return element.model_copy(update={"kaskade": stufen})


def offen(spec):
    """Das ganze Spec mit offenem DRS - ein gewoehnliches Spec."""
    return spec.model_copy(update={
        "elemente": [element_offen(e) for e in spec.elemente]})


@dataclass
class Vergleich:
    name: str
    zu_abtrieb: float
    zu_widerstand: float
    auf_abtrieb: float
    auf_widerstand: float

    @property
    def abtrieb_verlust(self) -> float:
        """Anteil des Abtriebs, der beim Oeffnen verloren geht, 0..1."""
        return 1.0 - self.auf_abtrieb / self.zu_abtrieb if self.zu_abtrieb else 0.0

    @property
    def widerstand_gewinn(self) -> float:
        """Anteil des Widerstands, der beim Oeffnen wegfaellt, 0..1."""
        return (1.0 - self.auf_widerstand / self.zu_widerstand
                if self.zu_widerstand else 0.0)


def vergleich(element, rechnen: Callable, geschwindigkeit: float = 20.0,
              name: str = "") -> Vergleich:
    zu = rechnen(element, geschwindigkeit)
    auf = rechnen(element_offen(element), geschwindigkeit)
    return Vergleich(name or element.name or element.id,
                     float(zu.abtrieb), float(zu.widerstand),
                     float(auf.abtrieb), float(auf.widerstand))
