"""
Generator — sucht die Kombination aus Profilen und Elementen mit dem größten
Abtrieb.

Die Aufgabe, die ein Aerodynamiker sonst von Hand durchprobiert: Welches
Profil als Hauptelement, welches als Flap, wie viele Elemente, welche Winkel?
Der Raum ist zu groß zum Raten und klein genug zum Durchrechnen.

**Was gesucht wird:**

* Hauptprofil und Flapprofil aus dem Katalog — nicht jede Paarung ist
  sinnvoll, deshalb wird nach der Eignung aus `profile/katalog.yaml`
  vorsortiert.
* Die Zahl der Elemente, eins bis drei.
* Die Flapwinkel, als Raster.

**Was NICHT gesucht wird:** Spalt und Überlappung bleiben bei den Werten, die
sich im Formula Student bewährt haben (1,5 % und 2 % der Hauptsehne). Beides
zusätzlich zu rastern vervielfacht die Rechenzeit, und die Empfindlichkeit ist
gering — zwischen 1 % und 2 % Spalt liegen wenige Prozent Beiwert. Wer daran
drehen will, tut das anschließend am fertigen Entwurf.

**Die Bewertung** ist der Abtrieb am ganzen Flügel, nicht der zweidimensionale
Beiwert: Eine Kaskade mit viel Beiwert und kurzer Gesamtsehne kann weniger
liefern als eine flachere mit mehr Fläche. Gerechnet wird deshalb 2D für die
Kaskade und daraus über die Traglinie auf den endlichen Flügel.

**Grenzen — bitte mitlesen:** Alles aus kaskade.py gilt hier. Das Modell
unterschätzt gut abgestimmte Spalte, weil es die Grenzschicht über den Spalt
hinweg nicht rechnet. Für den VERGLEICH von Kombinationen untereinander ist
das weniger schlimm als für den Absolutwert — der Fehler wirkt auf alle
Kandidaten in dieselbe Richtung. Der Vorschlag ist ein Startpunkt für CFD.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..geometrie import kaskade as geo
from ..geometrie.profil import Profil, katalognotiz, katalogprofile
from . import kaskade as aero
from .traglinie import rechne as traglinie_rechne
from .profilpolare import DICHTE


@dataclass
class Bauart:
    """Eine durchgerechnete Kombination."""

    hauptprofil: str
    flapprofil: str
    elemente: int
    flapwinkel: tuple[float, ...]
    beiwert: aero.Kaskadenbeiwert
    abtrieb: float              # N, ganzer Flügel
    widerstand: float
    gesamtsehne: float
    lage: list[geo.Elementlage] = field(default_factory=list)

    @property
    def wirkungsgrad(self) -> float:
        return abs(self.abtrieb) / max(self.widerstand, 1e-9)

    @property
    def brauchbar(self) -> bool:
        return not self.beiwert.abgerissen

    def __str__(self) -> str:
        winkel = ", ".join(f"{w:+.0f}" for w in self.flapwinkel) or "-"
        zeichen = "ok " if self.brauchbar else "!  "
        return (f"  {zeichen} {self.elemente} Element(e)  "
                f"{self.hauptprofil:12s} + {self.flapprofil:12s}  "
                f"Flapwinkel {winkel:16s}  "
                f"{self.abtrieb:6.1f} N  L/D {self.wirkungsgrad:5.1f}  "
                f"Sehne {self.gesamtsehne:5.0f} mm")


@dataclass
class Generatorergebnis:
    bester: Bauart | None
    alternativen: list[Bauart] = field(default_factory=list)
    geprueft: int = 0
    verworfen_abriss: int = 0
    begruendung: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        zeilen = [f"{self.geprueft} Kombinationen gerechnet, "
                  f"{self.verworfen_abriss} davon abgerissen.", ""]
        if self.bester:
            zeilen += ["Bester Entwurf:", str(self.bester), ""]
        if self.alternativen:
            zeilen.append("Alternativen:")
            zeilen += [str(b) for b in self.alternativen]
        if self.begruendung:
            zeilen.append("")
            zeilen += [f"  {b}" for b in self.begruendung]
        return "\n".join(zeilen)


def hauptprofile() -> list[str]:
    """Profile, die sich laut Katalog als Hauptelement eignen."""
    return [d for d in katalogprofile()
            if "Hauptelement" in katalognotiz(d).get("eignung", "")]


def flapprofile() -> list[str]:
    """Profile fuer die hinteren Elemente.

    Flaps sind duenn und stark gewoelbt. Wo der Katalog nichts sagt, werden
    die duennsten Hauptelemente mitgenommen - besser als eine leere Liste.
    """
    ausdruecklich = [d for d in katalogprofile()
                     if "Flap" in katalognotiz(d).get("eignung", "")]
    return ausdruecklich or ["e58.dat"]


def _lade(datei: str) -> Profil:
    return Profil.aus_dat(f"profile/katalog/{datei}").gespiegelt()


def _dreidimensional(beiwert: aero.Kaskadenbeiwert, spannweite, sehne: float,
                     winkel: float, profil: Profil, geschwindigkeit: float,
                     lage) -> tuple[float, float]:
    """Rechnet den 2D-Beiwert der Kaskade auf den endlichen Fluegel um.

    Der Weg: Die Traglinie wird einmal fuer das HAUPTPROFIL allein gerechnet.
    Das Verhaeltnis aus ihrem dreidimensionalen und ihrem zweidimensionalen
    Beiwert ist der Verlust durch die endliche Spannweite - rund ein Drittel
    bei Streckung fuenf. Dieses Verhaeltnis wird auf die Kaskade angewendet.

    Warum nicht die Kaskade selbst durch die Traglinie schicken: Dafuer
    muesste je Streifen die ganze Panelrechnung laufen, und der Generator
    prueft hunderte Kombinationen. Der Umweg kostet Genauigkeit, aber der
    Fehler wirkt auf alle Kandidaten gleich - und verglichen wird hier.
    """
    from ..geometrie.spannweite import schnitte

    stapel = schnitte(profil, spannweite, sehne, winkel, 24, lage=lage)
    einzeln = traglinie_rechne(stapel, profil, geschwindigkeit,
                               panels_je_seite=10)
    if abs(einzeln.cl) < 1e-9:
        return 0.0, 0.0

    # Zweidimensionaler Beiwert desselben Profils bei demselben Winkel.
    from .profilpolare import polare, reynolds
    cl_2d = polare(profil, reynolds(geschwindigkeit, sehne)).cl_bei(winkel)
    if abs(cl_2d) < 1e-9:
        return 0.0, 0.0
    verlust = einzeln.cl / cl_2d

    staudruck = 0.5 * DICHTE * geschwindigkeit ** 2
    # Die Flaeche waechst mit der Gesamtsehne der Kaskade.
    flaeche = einzeln.flaeche * beiwert.gesamtsehne / max(sehne, 1e-9)
    abtrieb = -staudruck * flaeche * beiwert.cl * verlust
    widerstand = (staudruck * flaeche * beiwert.cd
                  + einzeln.widerstand_induziert
                  * (beiwert.cl * verlust / einzeln.cl) ** 2)
    return float(abtrieb), float(widerstand)


def suche(spannweite, sehne: float = 250.0, grundwinkel: float = -4.0,
          geschwindigkeit: float = 15.0,
          lage: tuple[float, float, float] = (-600.0, 0.0, 110.0),
          haupt: list[str] | None = None, flaps: list[str] | None = None,
          elementzahlen: tuple[int, ...] = (1, 2, 3),
          flapwinkel: tuple[float, ...] = (-12.0, -18.0, -24.0),
          spalt: float = 0.015, ueberlappung: float = 0.02,
          anzahl_alternativen: int = 5) -> Generatorergebnis:
    """Rechnet die Kombinationen durch und sucht den groessten Abtrieb."""
    haupt = haupt or hauptprofile()
    flaps = flaps or flapprofile()

    kandidaten: list[Bauart] = []
    verworfen = 0

    for hauptdatei in haupt:
        hauptprofil = _lade(hauptdatei)
        for anzahl in elementzahlen:
            if anzahl == 1:
                paare = [("-", ())]
            else:
                paare = [(f, w) for f in flaps
                         for w in _winkelfolgen(anzahl - 1, flapwinkel)]

            for flapdatei, winkelfolge in paare:
                vorgaben = []
                if flapdatei != "-":
                    flapprofil = _lade(flapdatei)
                    # Jedes weitere Element wird kuerzer - so bauen es alle.
                    for i, w in enumerate(winkelfolge):
                        vorgaben.append(geo.Kaskadenvorgabe(
                            flapprofil, sehne_faktor=0.35 - 0.07 * i,
                            winkel_relativ=w, spalt=spalt,
                            ueberlappung=ueberlappung,
                            name=f"Flap {i + 1}"))
                try:
                    lagen, beiwert = aero.baue_und_rechne(
                        hauptprofil, sehne, grundwinkel, vorgaben,
                        geschwindigkeit, hoehe_ueber_boden=lage[2])
                except Exception:
                    continue

                if beiwert.abgerissen:
                    verworfen += 1
                    continue

                abtrieb, widerstand = _dreidimensional(
                    beiwert, spannweite, sehne, grundwinkel, hauptprofil,
                    geschwindigkeit, lage)

                kandidaten.append(Bauart(
                    hauptprofil=hauptdatei, flapprofil=flapdatei,
                    elemente=anzahl, flapwinkel=tuple(winkelfolge),
                    beiwert=beiwert, abtrieb=abtrieb, widerstand=widerstand,
                    gesamtsehne=beiwert.gesamtsehne, lage=lagen))

    kandidaten.sort(key=lambda b: -b.abtrieb)
    geprueft = len(kandidaten) + verworfen

    return Generatorergebnis(
        bester=kandidaten[0] if kandidaten else None,
        alternativen=_streuen(kandidaten[1:], anzahl_alternativen),
        geprueft=geprueft, verworfen_abriss=verworfen,
        begruendung=_begruenden(kandidaten, verworfen, geprueft))


def _winkelfolgen(anzahl: int, auswahl: tuple[float, ...]) -> list[tuple]:
    """Winkelfolgen fuer mehrere Flaps.

    Nur MONOTON steiler werdende Folgen: Ein Flap, der flacher steht als sein
    Vorgaenger, ergibt aerodynamisch keinen Sinn - die Kaskade soll die
    Stroemung schrittweise umlenken, nicht zurueckbiegen. Das halbiert
    ausserdem den Suchraum.
    """
    if anzahl == 1:
        return [(w,) for w in auswahl]
    folgen = []
    for erste in auswahl:
        for rest in _winkelfolgen(anzahl - 1, auswahl):
            if abs(rest[0]) <= abs(erste):
                folgen.append((erste,) + rest)
    return folgen


def _streuen(kandidaten: list[Bauart], anzahl: int) -> list[Bauart]:
    """Alternativen auswaehlen, die sich wirklich unterscheiden.

    Sonst stehen fuenf Varianten desselben Profils mit zwei Grad Unterschied
    nebeneinander - formal verschieden, praktisch dieselbe Antwort.
    """
    gewaehlt: list[Bauart] = []
    for b in kandidaten:
        if all(b.hauptprofil != g.hauptprofil or b.elemente != g.elemente
               for g in gewaehlt):
            gewaehlt.append(b)
        if len(gewaehlt) >= anzahl:
            break
    return gewaehlt


def _begruenden(kandidaten, verworfen, geprueft) -> list[str]:
    if not kandidaten:
        return [f"Alle {geprueft} Kombinationen sind abgerissen. Flachere "
                f"Flapwinkel oder ein groesserer Spalt helfen."]

    bester = kandidaten[0]
    texte = [f"{geprueft} Kombinationen gerechnet, {verworfen} wegen Abriss "
             f"verworfen."]

    einzeln = [b for b in kandidaten if b.elemente == 1]
    if einzeln and bester.elemente > 1:
        gewinn = 100.0 * (bester.abtrieb / max(einzeln[0].abtrieb, 1e-9) - 1.0)
        texte.append(f"Der Sprung von einem auf {bester.elemente} Elemente "
                     f"bringt {gewinn:.0f} % mehr Abtrieb — "
                     f"{einzeln[0].abtrieb:.0f} N gegen {bester.abtrieb:.0f} N.")

    sparsam = max(kandidaten, key=lambda b: b.wirkungsgrad)
    if sparsam is not bester:
        verlust = 100.0 * (1.0 - sparsam.abtrieb / max(bester.abtrieb, 1e-9))
        texte.append(f"Wenn Widerstand zaehlt: {sparsam.hauptprofil} mit "
                     f"{sparsam.elemente} Element(en) liefert {verlust:.0f} % "
                     f"weniger Abtrieb bei Wirkungsgrad "
                     f"{sparsam.wirkungsgrad:.1f} statt "
                     f"{bester.wirkungsgrad:.1f}.")

    texte.append("Die Zahlen sind eine Abschaetzung und untereinander "
                 "vergleichbar, nicht absolut belastbar. Das Modell rechnet "
                 "die Grenzschicht ueber den Spalt hinweg nicht mit und "
                 "unterschaetzt daher gut abgestimmte Kaskaden.")
    return texte
