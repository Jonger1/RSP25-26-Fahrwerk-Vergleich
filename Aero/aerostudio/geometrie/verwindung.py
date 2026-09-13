"""
Prüfung der Verwindungsverteilung.

Zwei Dinge lassen sich an einer Spannweitenverteilung erkennen, bevor
irgendetwas gerechnet oder exportiert wird — und beide sind beim ersten
Entwurf des Frontflügels schiefgegangen:

1. **Zu schnelle Verwindung.** Eine durchgehende Fläche, die sich über die
   Spannweite stark verdreht, wird eingeschnürt. Im CAD sieht man das als
   spitze Stelle, und der Verbund wird schwer zu vernähen. Gemessen an der
   ersten Vorgabe: 24 Grad je Meter — die Fläche schnürte sichtbar ein.

2. **Ein Schnitt jenseits des Abrisses.** Steht die Wurzel schon geometrisch
   über dem Abrisswinkel des Profils, hilft keine Rechnung mehr. Dieselbe
   Vorgabe stellte die Wurzel auf −14 Grad, bei einem Abriss des E423 bei
   −12 Grad.

Beides fällt in der Abtriebsrechnung erst hinterher auf und ist dort schwer
zuzuordnen. Hier steht es beim Eintippen.

Die Grenzwerte sind Erfahrungswerte, keine Naturkonstanten — sie stehen
deshalb als benannte Konstanten hier oben und nicht verstreut im Code.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Ab hier wird eine durchgehende Fläche sichtbar eingeschnürt. Zum Vergleich:
# Die Schränkung eines Segelflugzeugs liegt bei 2 bis 5 Grad über die ganze
# Halbspannweite, also weit unter 10 Grad je Meter.
RATE_HINWEIS = 10.0      # Grad je Meter
RATE_WARNUNG = 18.0

# So nah darf ein Schnitt dem Abriss kommen, bevor gewarnt wird. Nicken und
# Federn bewegen den wirksamen Winkel am Fahrzeug um mehrere Grad.
ABRISS_RESERVE = 3.0     # Grad


@dataclass
class Verwindungsbefund:
    """Ein Hinweis zur Verteilung. `stufe` ist "hinweis" oder "warnung"."""

    text: str
    stufe: str = "hinweis"
    ort: str = ""

    def __str__(self) -> str:
        marke = "!" if self.stufe == "warnung" else "-"
        return f"  {marke} {self.text}" + (f"  ({self.ort})" if self.ort else "")


def verwindungsrate(spannweite) -> list[tuple[float, float, float]]:
    """Verwindungsrate je Abschnitt, in Grad pro Meter.

    Gibt Tripel (y von, y bis, Rate) zurück. Die Rate ist vorzeichenbehaftet;
    für die Beurteilung zählt der Betrag.
    """
    stellen = sorted(spannweite.stuetzstellen, key=lambda s: s.y)
    raten = []
    for a, b in zip(stellen[:-1], stellen[1:]):
        breite = b.y - a.y
        if breite <= 1e-9:
            continue
        raten.append((a.y, b.y, (b.verwindung - a.verwindung) / breite * 1000.0))
    return raten


def pruefe(spannweite, grundwinkel: float,
           abrisswinkel: float | None = None) -> list[Verwindungsbefund]:
    """Beurteilt eine Verteilung.

    `abrisswinkel` ist der Winkel, bei dem das Profil abreisst — negativ für
    ein Abtriebsprofil. Ohne Angabe wird nur die Verwindungsrate geprüft; das
    ist der Fall, wenn NeuralFoil nicht zur Verfügung steht.
    """
    befunde: list[Verwindungsbefund] = []

    for von, bis, rate in verwindungsrate(spannweite):
        betrag = abs(rate)
        if betrag >= RATE_WARNUNG:
            befunde.append(Verwindungsbefund(
                f"Die Verwindung ändert sich mit {betrag:.0f}° je Meter. Eine "
                f"durchgehende Fläche wird dabei sichtbar eingeschnürt — im "
                f"CAD erscheint dort eine spitze Stelle. Unter {RATE_HINWEIS:.0f}° "
                f"je Meter bleibt sie glatt; wer mehr Unterschied braucht, "
                f"baut den inneren Bereich als eigenes Element.",
                stufe="warnung", ort=f"y {von:.0f} bis {bis:.0f} mm"))
        elif betrag >= RATE_HINWEIS:
            befunde.append(Verwindungsbefund(
                f"Verwindung {betrag:.0f}° je Meter — das ist viel für eine "
                f"durchgehende Fläche. Im CAD prüfen, ob der Verbund dort "
                f"glatt bleibt.",
                ort=f"y {von:.0f} bis {bis:.0f} mm"))

    if abrisswinkel is None:
        return befunde

    for st in sorted(spannweite.stuetzstellen, key=lambda s: s.y):
        gesamt = grundwinkel + st.verwindung
        # Abtriebsprofil: Abriss bei negativem Winkel, "darüber hinaus" heisst
        # noch negativer.
        jenseits = (gesamt < abrisswinkel if abrisswinkel < 0
                    else gesamt > abrisswinkel)
        reserve = abs(gesamt - abrisswinkel)
        if jenseits:
            befunde.append(Verwindungsbefund(
                f"Dieser Schnitt steht bei {gesamt:+.1f}° und damit "
                f"{reserve:.1f}° JENSEITS des Abrisses ({abrisswinkel:+.1f}°). "
                f"Dort entsteht kein Abtrieb mehr, sondern Widerstand.",
                stufe="warnung", ort=f"y {st.y:.0f} mm"))
        elif reserve < ABRISS_RESERVE:
            befunde.append(Verwindungsbefund(
                f"Nur {reserve:.1f}° Reserve bis zum Abriss ({abrisswinkel:+.1f}°). "
                f"Nicken und Federn bewegen den wirksamen Winkel am Fahrzeug "
                f"um mehrere Grad — in der ersten Bremszone reisst das ab.",
                stufe="warnung", ort=f"y {st.y:.0f} mm"))
    return befunde


def lastverteilung(kraefte) -> Verwindungsbefund | None:
    """Warnt, wenn die Last sehr ungleich über die Spannweite liegt.

    Ein Flügel, dessen Wurzel den ganzen Abtrieb trägt, hat zwei Probleme: Die
    Wurzel steht nahe am Abriss, und der induzierte Widerstand ist höher als
    nötig — der ist bei elliptischer Verteilung am kleinsten.

    Gemessen an der ersten Vorgabe: örtlicher Beiwert von −2,03 innen auf
    −0,32 außen, also Faktor sechs. Die höchste Last lag dabei dort, wo die
    Sehne am kürzesten war.
    """
    if len(getattr(kraefte, "cl_lokal", [])) < 4:
        return None
    rechts = [i for i, s in enumerate(kraefte.streifen) if s.y > 0]
    if len(rechts) < 4:
        return None

    cl = np.abs(kraefte.cl_lokal[rechts])
    # Die aeussersten Streifen sind durch die Traglinientheorie ohnehin
    # entlastet - verglichen wird deshalb ohne sie.
    innen, aussen = cl[0], cl[max(len(cl) - 2, 0)]
    if aussen < 1e-6:
        return None
    verhaeltnis = innen / aussen
    if verhaeltnis < 3.0:
        return None
    return Verwindungsbefund(
        f"Die Last liegt stark innen: örtlicher Beiwert {innen:.2f} an der "
        f"Wurzel gegen {aussen:.2f} weiter außen, Faktor {verhaeltnis:.1f}. "
        f"Das kostet induzierten Widerstand und bringt die Wurzel früh an den "
        f"Abriss. Weniger Verwindung oder außen mehr Sehne verteilt es "
        f"gleichmäßiger.",
        stufe="hinweis")
