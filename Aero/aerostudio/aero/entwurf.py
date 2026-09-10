"""
Vom Abtriebswunsch zum Flügelvorschlag.

Die Aufgabe umgedreht: Nicht „was leistet dieser Flügel", sondern „welcher
Flügel leistet das". Eingabe ist ein Abtrieb in Newton bei einer
Geschwindigkeit, Ausgabe sind Sehne, Anstellwinkel und Spannweite.

**Wie gesucht wird, und warum so:**

Die Verwindungsverteilung aus der Sektionstabelle bleibt UNANGETASTET. Sie ist
die Entwurfsabsicht des Anwenders - der Outwash innen, die Verwindung außen -
und ein Suchverfahren, das daran dreht, liefert einen Flügel, den niemand
haben wollte. Skaliert werden nur drei Größen: Wurzelsehne, Halbspannweite und
Grundanstellwinkel.

Für Sehne und Spannweite wird ein Raster abgefahren, für den Anstellwinkel je
Rasterpunkt der Zielwert eingeschachtelt. Das ist möglich, weil der Abtrieb
über dem Anstellwinkel bis zum Abriss monoton wächst - und nur dort wird
gesucht. Ein allgemeiner Optimierer wäre hier die schlechtere Wahl: Er
bräuchte mehr Auswertungen, und niemand könnte hinterher erklären, warum
gerade diese Kombination herauskam.

**Nebenbedingungen**, die ein Vorschlag einhalten muss:

* Das Reglement, geprüft über beide Regelstände und über den
  Fahrzustands-Envelope.
* Der Abriss. Ein Flügel, dessen halbe Fläche abgerissen ist, erreicht den
  Zielwert auf dem Papier und im Fahrzeug nie.
* Die Fertigbarkeit des Profils bei der vorgeschlagenen Sehne.

Unter allem, was den Zielwert trifft, gewinnt der beste Wirkungsgrad - also
der Flügel, der den Abtrieb mit dem geringsten Widerstand erreicht. Das ist
am Rennwagen die richtige Frage, nicht der maximale Abtrieb.

**Die Zahl bleibt eine Abschätzung.** Alles aus traglinie.py gilt hier
unverändert: keine Endplatten, keine Kanalwirkung am Boden, keine Kaskade.
Der Vorschlag ist ein begründeter Startpunkt für CFD, kein Ergebnis.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..geometrie.spannweite import schnitte
from .traglinie import Fluegelkraefte, rechne

# Auflösung der Suchrechnung. Bewusst gröber als die Nachrechnung: Ein
# Vorschlag entsteht aus hunderten Auswertungen, und der Unterschied zwischen
# zehn und zwanzig Streifen liegt bei rund einem Prozent - weit unter der
# Unsicherheit des Verfahrens.
SUCH_STREIFEN = 10
SUCH_PUNKTE = 24


@dataclass
class Grenzen:
    """Der Raum, in dem gesucht werden darf. Alles in mm und Grad."""

    sehne: tuple[float, float] = (120.0, 400.0)
    halbspannweite: tuple[float, float] = (300.0, 695.0)
    anstellwinkel: tuple[float, float] = (-16.0, 0.0)

    # Höchstens so viel abgerissene Fläche. Fünf Prozent sind die Flügelspitze
    # und der äußerste Streifen - das lässt sich nicht vermeiden und stört
    # nicht. Darüber hinaus wird der Entwurf unbrauchbar.
    abriss_max: float = 0.05

    # Die Einbauhöhe wird MITGESUCHT, nicht vorgegeben. Grund: Eine längere
    # Sehne bringt bei gleicher Aufhängehöhe die Hinterkante näher an den
    # Boden - ohne Nachführen scheitert jeder größere Vorschlag an T 2.2.1,
    # obwohl er sich mit zwanzig Millimetern mehr Höhe bauen ließe.
    # Gesetzt wird so tief wie zulässig: Das bringt den meisten Bodeneffekt.
    hoehe_anpassen: bool = True
    bodenfreiheit_min: float = 30.0      # T 2.2.1
    bodenfreiheit_reserve: float = 5.0   # Sicherheit auf die Nickrechnung

    # Wie fein das Raster über Sehne und Spannweite liegt.
    stufen_sehne: int = 7
    stufen_spannweite: int = 5

    def __post_init__(self):
        for name in ("sehne", "halbspannweite", "anstellwinkel"):
            unten, oben = getattr(self, name)
            if oben <= unten:
                raise ValueError(f"Grenzen fuer {name} sind verdreht: "
                                 f"{unten} bis {oben}")


@dataclass
class Kandidat:
    """Ein durchgerechneter Flügelentwurf."""

    sehne: float
    halbspannweite: float
    anstellwinkel: float
    hoehe: float                 # Höhe der Wurzelsehne über Boden, mm
    kraefte: Fluegelkraefte
    regelkonform: bool = True
    verstoesse: list[str] = field(default_factory=list)   # harte, geltendes Recht
    hinweise: list[str] = field(default_factory=list)     # nur der 2027-Entwurf

    @property
    def abtrieb(self) -> float:
        return self.kraefte.abtrieb

    @property
    def wirkungsgrad(self) -> float:
        return self.kraefte.wirkungsgrad

    def __str__(self) -> str:
        zeichen = "ok " if self.regelkonform else "!  "
        return (f"  {zeichen} Sehne {self.sehne:6.1f} mm, Halbspannweite "
                f"{self.halbspannweite:6.1f} mm, Winkel {self.anstellwinkel:+6.2f} Grad, "
                f"Höhe {self.hoehe:5.1f} mm"
                f"  ->  {self.abtrieb:6.1f} N   L/D {self.wirkungsgrad:5.1f}")


@dataclass
class Vorschlag:
    """Das Ergebnis einer Suche."""

    ziel: float
    geschwindigkeit: float
    treffer: Kandidat | None
    alternativen: list[Kandidat] = field(default_factory=list)
    erreichbar_max: float = 0.0
    begruendung: list[str] = field(default_factory=list)

    @property
    def gefunden(self) -> bool:
        return self.treffer is not None

    def __str__(self) -> str:
        kopf = (f"Ziel {self.ziel:.0f} N bei {self.geschwindigkeit:.1f} m/s"
                f"  -  {'gefunden' if self.gefunden else 'NICHT erreichbar'}")
        zeilen = [kopf, ""]
        if self.treffer:
            zeilen.append("Vorschlag:")
            zeilen.append(str(self.treffer))
        if self.alternativen:
            zeilen.append("")
            zeilen.append("Weitere Wege zum selben Ziel:")
            zeilen += [str(k) for k in self.alternativen]
        if self.begruendung:
            zeilen.append("")
            zeilen += [f"  {b}" for b in self.begruendung]
        return "\n".join(zeilen)


# --------------------------------------------------------------- Suche

def _baue(profil, spannweite, sehne, halbspannweite, winkel, lage,
          punkte=SUCH_PUNKTE):
    """Ein Flügel mit skalierter Sehne und Spannweite, Verwindung unverändert."""
    return schnitte(profil, spannweite.skaliert(halbspannweite), sehne, winkel,
                    punkte, lage=lage)


def _hoehe_setzen(profil, spannweite, sehne, halbspannweite, winkel, lage,
                  grenzen, zustand) -> tuple[float, float, float]:
    """Setzt den Flügel so tief, wie T 2.2.1 im Fahrzustand es gerade zulässt.

    Der tiefste Punkt eines angestellten Flügels ist nicht die Wurzelsehne,
    sondern je nach Verwindung die Hinterkante irgendwo über die Spannweite.
    Deshalb wird er aus der fertigen Geometrie gemessen und nicht gerechnet.

    Abgezogen wird das Absinken beim Bremsen - dieselbe Nickrechnung, mit der
    auch der Regelprüfer arbeitet. Sonst stünde am Ende ein Vorschlag, der
    statisch passt und in der ersten Bremszone aufsetzt.
    """
    if not grenzen.hoehe_anpassen:
        return lage

    stapel = _baue(profil, spannweite, sehne, halbspannweite, winkel, lage)
    tiefster = min(float(s.punkte[:, 2].min()) for s in stapel)

    # GENAU derselbe Fahrzustand, mit dem hinterher geprueft wird. Ein erster
    # Anlauf rechnete hier mit dem Bremsfall (6,6 mm Absinken), waehrend der
    # Regelpruefer den vollen Einfederweg ansetzte (24,35 mm). Ergebnis: Jeder
    # Vorschlag war rechnerisch knapp legal und fiel in der Pruefung durch,
    # ohne dass erkennbar war, warum.
    soll = (grenzen.bodenfreiheit_min + grenzen.bodenfreiheit_reserve
            + zustand.tief)
    return (lage[0], lage[1], lage[2] + (soll - tiefster))


def _auswerten(profil, spannweite, sehne, halbspannweite, winkel, lage,
               geschwindigkeit, streifen=SUCH_STREIFEN) -> Fluegelkraefte:
    stapel = _baue(profil, spannweite, sehne, halbspannweite, winkel, lage)
    return rechne(stapel, profil, geschwindigkeit, panels_je_seite=streifen)


def _winkel_fuer_ziel(profil, spannweite, sehne, halbspannweite, lage,
                      geschwindigkeit, ziel, grenzen, zustand):
    """Sucht den Anstellwinkel, der den Zielabtrieb trifft.

    Erst ein grobes Abtasten, um den brauchbaren Bereich zu finden - also den
    Teil, in dem der Abtrieb noch wächst und der Abriss unter der Schwelle
    bleibt. Dann Intervallhalbierung darin.

    Warum nicht gleich ein Nullstellensucher über den ganzen Bereich: Jenseits
    des Abrisses fällt der Abtrieb wieder ab. Ein Sucher, der das nicht weiß,
    landet mit gleicher Wahrscheinlichkeit auf dem falschen Ast - und der
    liefert denselben Abtrieb bei viel mehr Widerstand.
    """
    unten, oben = grenzen.anstellwinkel
    raster = np.linspace(oben, unten, 9)          # von flach nach steil

    def bei(w):
        """Auswertung bei einem Winkel, mit nachgeführter Einbauhöhe."""
        eigene_lage = _hoehe_setzen(profil, spannweite, sehne, halbspannweite,
                                    float(w), lage, grenzen, zustand)
        return eigene_lage, _auswerten(profil, spannweite, sehne, halbspannweite,
                                       float(w), eigene_lage, geschwindigkeit)

    brauchbar = []
    for w in raster:
        eigene_lage, k = bei(w)
        if k.abgerissen > grenzen.abriss_max:
            break                                  # ab hier wird es nur schlimmer
        brauchbar.append((float(w), k, eigene_lage))

    if len(brauchbar) < 2:
        return None

    winkel = np.array([w for w, _, _ in brauchbar])
    kraft = np.array([k.abtrieb for _, k, _ in brauchbar])

    if kraft[-1] < ziel:
        return None                                # nicht erreichbar
    if kraft[0] > ziel + 0.05:
        # Schon der flachste zulaessige Winkel liefert mehr als gewuenscht.
        # Das ist KEINE Loesung fuer dieses Ziel - dieser Zuschnitt ist
        # schlicht zu gross. Frueher wurde er trotzdem zurueckgegeben und
        # erschien dann als "weiterer Weg zum selben Ziel" mit 69 statt
        # 60 Newton.
        return None

    # Intervall einschachteln, in dem der Zielwert liegt.
    i = int(np.argmax(kraft >= ziel))
    a, b = winkel[i - 1], winkel[i]
    for _ in range(18):
        m = 0.5 * (a + b)
        eigene_lage, k = bei(m)
        if abs(k.abtrieb - ziel) < 0.05 or abs(b - a) < 0.01:
            if k.abgerissen > grenzen.abriss_max:
                return None
            return (m, k, eigene_lage)
        if k.abtrieb < ziel:
            a = m
        else:
            b = m
    return None


def suche(ziel_abtrieb: float, profil, spannweite,
          geschwindigkeit: float = 15.0,
          lage: tuple[float, float, float] = (-600.0, 0.0, 90.0),
          grenzen: Grenzen | None = None,
          regelsaetze=None, bezug=None, zustand=None,
          anzahl_alternativen: int = 4) -> Vorschlag:
    """Sucht Flügel, die den Zielabtrieb erreichen.

    `spannweite` liefert die Verwindungsverteilung - die bleibt erhalten,
    skaliert wird nur ihre Ausdehnung.
    """
    grenzen = grenzen or Grenzen()
    ziel = float(ziel_abtrieb)

    # EIN Fahrzustand fuer die ganze Suche - Hoehensuche und Regelpruefung
    # muessen denselben benutzen, sonst widersprechen sie sich.
    if zustand is None:
        from ..regeln import Fahrzustand
        zustand = Fahrzustand()

    sehnen = np.linspace(*grenzen.sehne, grenzen.stufen_sehne)
    weiten = np.linspace(*grenzen.halbspannweite, grenzen.stufen_spannweite)

    kandidaten: list[Kandidat] = []
    bestes_maximum = 0.0
    bester_maximalfall = None

    for weite in weiten:
        for sehne in sehnen:
            gefunden = _winkel_fuer_ziel(profil, spannweite, float(sehne),
                                         float(weite), lage, geschwindigkeit,
                                         ziel, grenzen, zustand)
            if gefunden is None:
                # Merken, wieviel dieser Zuschnitt überhaupt hergibt - daraus
                # entsteht die Auskunft, wenn nichts passt.
                grenzfall = _grenzleistung(profil, spannweite, float(sehne),
                                           float(weite), lage, geschwindigkeit,
                                           grenzen, zustand)
                if grenzfall and grenzfall.abtrieb > bestes_maximum:
                    bestes_maximum = grenzfall.abtrieb
                    bester_maximalfall = (float(sehne), float(weite), grenzfall)
                continue

            winkel, kraefte, eigene_lage = gefunden
            kandidaten.append(Kandidat(sehne=float(sehne),
                                       halbspannweite=float(weite),
                                       anstellwinkel=winkel,
                                       hoehe=float(eigene_lage[2]),
                                       kraefte=kraefte))

    _regeln_pruefen(kandidaten, profil, spannweite, lage, regelsaetze, bezug,
                    zustand)

    # Regelkonforme zuerst, darin der beste Wirkungsgrad.
    kandidaten.sort(key=lambda k: (not k.regelkonform, -k.wirkungsgrad))

    begruendung = _begruenden(kandidaten, ziel, bestes_maximum,
                              bester_maximalfall, grenzen)

    return Vorschlag(
        ziel=ziel, geschwindigkeit=float(geschwindigkeit),
        treffer=kandidaten[0] if kandidaten else None,
        alternativen=_streuen(kandidaten[1:], anzahl_alternativen),
        erreichbar_max=bestes_maximum if not kandidaten else
        max(k.abtrieb for k in kandidaten),
        begruendung=begruendung)


def _grenzleistung(profil, spannweite, sehne, weite, lage, geschwindigkeit,
                   grenzen, zustand) -> Fluegelkraefte | None:
    """Was dieser Zuschnitt maximal hergibt, ohne abzureissen."""
    bester = None
    for w in np.linspace(grenzen.anstellwinkel[1], grenzen.anstellwinkel[0], 9):
        eigene_lage = _hoehe_setzen(profil, spannweite, sehne, weite, float(w),
                                    lage, grenzen, zustand)
        k = _auswerten(profil, spannweite, sehne, weite, float(w), eigene_lage,
                       geschwindigkeit)
        if k.abgerissen > grenzen.abriss_max:
            break
        if bester is None or k.abtrieb > bester.abtrieb:
            bester = k
    return bester


def _regeln_pruefen(kandidaten, profil, spannweite, lage, regelsaetze, bezug,
                    zustand) -> None:
    """Hängt jedem Kandidaten an, ob er das Reglement einhält."""
    if regelsaetze is None:
        from ..regeln import alle_staende
        regelsaetze = alle_staende()
    if bezug is None:
        from ..regeln import Bezugsgeometrie
        bezug = Bezugsgeometrie.aus_datei()

    from ..regeln import pruefe_fluegel

    for k in kandidaten:
        stapel = _baue(profil, spannweite, k.sehne, k.halbspannweite,
                       k.anstellwinkel, (lage[0], lage[1], k.hoehe), punkte=20)
        verstoesse, hinweise = [], []
        for satz in regelsaetze:
            for befund in pruefe_fluegel(stapel, satz, bezug, zustand):
                if befund.ok:
                    continue
                text = f"{satz.version}: {befund.regel} {befund.pruefung}"
                # Was nur im 2027-Entwurf steht, blockiert keinen Entwurf -
                # sonst faende die Suche nichts mehr, sobald eine noch nicht
                # verabschiedete Regel greift. Es wird getrennt gemeldet.
                (verstoesse if befund.blockiert else hinweise).append(text)
        k.verstoesse, k.hinweise = verstoesse, hinweise
        k.regelkonform = not verstoesse


def _streuen(kandidaten: list[Kandidat], anzahl: int) -> list[Kandidat]:
    """Wählt Alternativen aus, die sich WIRKLICH unterscheiden.

    Ohne das kämen vier Vorschläge mit fünf Millimetern Sehnenunterschied
    heraus - formal verschieden, praktisch derselbe Flügel. Ausgewählt wird
    deshalb über die Sehne gestreut.
    """
    if len(kandidaten) <= anzahl:
        return kandidaten
    gewaehlt: list[Kandidat] = []
    for k in kandidaten:
        if all(abs(k.sehne - g.sehne) > 15.0 or
               abs(k.halbspannweite - g.halbspannweite) > 40.0
               for g in gewaehlt):
            gewaehlt.append(k)
        if len(gewaehlt) >= anzahl:
            break
    return gewaehlt


def _begruenden(kandidaten, ziel, maximum, maximalfall, grenzen) -> list[str]:
    """Sagt in Klartext, was die Suche ergeben hat."""
    if not kandidaten:
        texte = [f"Kein Flügel im vorgegebenen Rahmen erreicht {ziel:.0f} N."]
        if maximalfall:
            sehne, weite, k = maximalfall
            texte.append(
                f"Das Beste im Rahmen sind {maximum:.0f} N — mit {sehne:.0f} mm "
                f"Sehne und {weite:.0f} mm Halbspannweite.")
            texte.append(
                "Mehr geht nur über einen zweiten Flügel oder eine Kaskade, "
                "über ein stärker gewölbtes Profil, oder indem die Grenzen für "
                "Sehne und Spannweite angehoben werden — soweit das Reglement "
                "das zulässt.")
        else:
            texte.append("In diesem Rahmen reisst die Strömung ab, bevor der "
                         "Zielwert erreicht wird. Ein gutmütigeres Profil oder "
                         "weniger Verwindung innen hilft.")
        return texte

    regelkonform = [k for k in kandidaten if k.regelkonform]
    texte = [f"{len(kandidaten)} Kombinationen treffen {ziel:.0f} N, "
             f"{len(regelkonform)} davon regelkonform."]

    if not regelkonform:
        texte.append("KEINE davon hält das Reglement ein — der Vorschlag oben "
                     "ist der beste unzulässige. Die Verstöße stehen dabei.")
        return texte

    bester = regelkonform[0]
    texte.append(f"Gewählt wurde der beste Wirkungsgrad: {bester.wirkungsgrad:.1f} "
                 f"Newton Abtrieb je Newton Widerstand.")
    texte.append(f"Die Einbauhöhe von {bester.hoehe:.0f} mm ist mitgesucht: so "
                 f"tief, wie T 2.2.1 im Bremsfall gerade zulässt — das bringt "
                 f"den meisten Bodeneffekt.")

    if bester.hinweise:
        ohne_hinweis = [k for k in regelkonform if not k.hinweise]
        texte.append(f"Nach geltendem Reglement zulässig, aber der 2027-Entwurf "
                     f"stört sich daran: {bester.hinweise[0]}.")
        if ohne_hinweis:
            alt = ohne_hinweis[0]
            texte.append(f"Auch nach dem Entwurf zulässig wäre {alt.sehne:.0f} mm "
                         f"Sehne bei {alt.halbspannweite:.0f} mm Halbspannweite "
                         f"und {alt.anstellwinkel:+.1f} Grad — Wirkungsgrad "
                         f"{alt.wirkungsgrad:.1f} statt {bester.wirkungsgrad:.1f}.")
        else:
            texte.append("Keine der gefundenen Kombinationen besteht auch den "
                         "2027-Entwurf.")

    # Der Hinweis, der am häufigsten gebraucht wird: flacher und größer
    # schlägt steiler und kleiner. Nur zeigen, wenn der Unterschied auch
    # zählt - sonst steht dort "kostet 0 % mehr Widerstand", und das ist
    # keine Aussage, sondern Rauschen.
    teurer = min(regelkonform, key=lambda k: k.wirkungsgrad)
    aufschlag = 100.0 * (bester.wirkungsgrad / max(teurer.wirkungsgrad, 1e-9) - 1.0)
    if aufschlag >= 5.0:
        texte.append(
            f"Zum Vergleich: {teurer.sehne:.0f} mm Sehne bei "
            f"{teurer.halbspannweite:.0f} mm Halbspannweite und "
            f"{teurer.anstellwinkel:+.1f} Grad bringt denselben Abtrieb, "
            f"kostet aber {aufschlag:.0f} % mehr Widerstand. Spannweite ist "
            f"billiger als Anstellwinkel — der induzierte Widerstand fällt "
            f"mit der Streckung.")
    return texte
