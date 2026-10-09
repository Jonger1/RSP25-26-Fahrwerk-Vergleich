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

**Feinsuche (räumlich):** Mit `feinsuche` werden die besten Kombinationen der
Vorauswahl noch einmal RÄUMLICH gerechnet (aero/kaskade3d.py), jeweils in
mehreren Varianten: Flaps über die ganze Breite, der letzte Flap nach außen
verdreht, innen entlastet und außen steiler, der letzte Flap nur auf der
äußeren Hälfte. Das sind die Muster, mit denen Formula-Student-Teams innen
Luft in den Unterboden leiten und außen vor dem Reifen den meisten Abtrieb
holen. Jede Variante wird mit Endplatten und Kanalwirkung am Boden gerechnet,
auf Durchdringung der Flächen und gegen das Reglement geprüft. Gewonnen hat
die stärkste Variante, die anliegt, sich nicht schneidet und regelkonform ist.

**Grenzen — bitte mitlesen:** Alles aus kaskade.py gilt hier. Das Modell
unterschätzt gut abgestimmte Spalte, weil es die Grenzschicht über den Spalt
hinweg nicht rechnet. Für den VERGLEICH von Kombinationen untereinander ist
das weniger schlimm als für den Absolutwert — der Fehler wirkt auf alle
Kandidaten in dieselbe Richtung. Der Vorschlag ist ein Startpunkt für CFD.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

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
    # Die Zeilen fuer die Kaskadentabelle - mit Teilfluegel-Angaben.
    stufen: list[dict] = field(default_factory=list)
    variante: str = "Flaps über die ganze Spannweite"
    raeumlich: bool = False            # aus der Feinsuche?
    abgerissen_raeumlich: bool = False
    durchdringungsfrei: bool | None = None
    regelkonform: bool | None = None
    hinweise: list[str] = field(default_factory=list)

    @property
    def wirkungsgrad(self) -> float:
        return abs(self.abtrieb) / max(self.widerstand, 1e-9)

    @property
    def brauchbar(self) -> bool:
        if self.raeumlich:
            return not self.abgerissen_raeumlich
        return not self.beiwert.abgerissen

    @property
    def empfehlbar(self) -> bool:
        """Anliegend, durchdringungsfrei und regelkonform - soweit geprueft."""
        return (self.brauchbar and self.durchdringungsfrei is not False
                and self.regelkonform is not False)

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
    vorauswahl: list[Bauart] = field(default_factory=list)
    feinsuche: bool = False

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
                     lage, endplatte_mm: float = 0.0,
                     cache: dict | None = None) -> tuple[float, float]:
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

    # Fuer dasselbe Hauptprofil ist die Traglinie jedes Mal dieselbe - sie
    # haengt nicht an den Flaps. Einmal rechnen statt je Kandidat.
    schluessel = (profil.name, len(profil.punkte), round(sehne, 3),
                  round(winkel, 3), round(geschwindigkeit, 3),
                  round(endplatte_mm, 3))
    if cache is not None and schluessel in cache:
        einzeln, cl_2d = cache[schluessel]
    else:
        # lage[2] ist die Hoehe des tiefsten Punkts - erst messen, dann setzen.
        stapel = schnitte(profil, spannweite, sehne, winkel, 24,
                          lage=(lage[0], lage[1], 0.0))
        tief = min(s.hoehe_min for s in stapel)
        stapel = [replace(s, punkte=s.punkte + np.array([0.0, 0.0, lage[2] - tief]))
                  for s in stapel]
        einzeln = traglinie_rechne(stapel, profil, geschwindigkeit,
                                   panels_je_seite=10,
                                   endplatte_mm=endplatte_mm)
        # Zweidimensionaler Beiwert desselben Profils bei demselben Winkel.
        from .profilpolare import polare, reynolds
        cl_2d = polare(profil, reynolds(geschwindigkeit, sehne)).cl_bei(winkel)
        if cache is not None:
            cache[schluessel] = (einzeln, cl_2d)
    if abs(einzeln.cl) < 1e-9:
        return 0.0, 0.0
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
          anzahl_alternativen: int = 5, endplatte_mm: float = 0.0,
          feinsuche: int = 0, innenbereich_mm: float = 0.0,
          mit_boden: bool = True,
          regelpruefung: bool = True) -> Generatorergebnis:
    """Rechnet die Kombinationen durch und sucht den groessten Abtrieb.

    Zwei Stufen. Die VORAUSWAHL rechnet jede Kombination im Schnitt und
    rechnet grob auf den Fluegel um - schnell genug fuer hunderte Kandidaten.
    Mit `feinsuche` > 0 werden die besten so vielen Kombinationen danach
    raeumlich in Varianten gerechnet (siehe Modul-Docstring).

    `lage[2]` ist die Hoehe des TIEFSTEN Punkts ueber Boden. Jede Variante
    wird darauf gesetzt - jedes Profil und jeder Flap hat einen anderen.

    `innenbereich_mm` haelt innen, ab der Wurzel des Hauptelements, einen
    Streifen frei von Flaps - den Einlauf zum Unterboden. Den Gewinn am
    Unterboden kennt das Werkzeug nicht; es ist deshalb eine VORGABE, kein
    Suchergebnis. Gilt nur in der Feinsuche.
    """
    haupt = haupt or hauptprofile()
    flaps = flaps or flapprofile()

    kandidaten: list[Bauart] = []
    verworfen = 0
    cache: dict = {}

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
                    geschwindigkeit, lage, endplatte_mm, cache)

                kandidaten.append(Bauart(
                    hauptprofil=hauptdatei, flapprofil=flapdatei,
                    elemente=anzahl, flapwinkel=tuple(winkelfolge),
                    beiwert=beiwert, abtrieb=abtrieb, widerstand=widerstand,
                    gesamtsehne=beiwert.gesamtsehne, lage=lagen,
                    stufen=_zeilen(flapdatei, winkelfolge, spalt,
                                   ueberlappung)))

    kandidaten.sort(key=lambda b: -b.abtrieb)
    geprueft = len(kandidaten) + verworfen
    begruendung = _begruenden(kandidaten, verworfen, geprueft)

    if feinsuche and kandidaten:
        raeumlich = _feinsuche(kandidaten, int(feinsuche), spannweite, sehne,
                               grundwinkel, geschwindigkeit, lage,
                               endplatte_mm, innenbereich_mm, mit_boden,
                               regelpruefung)
        if raeumlich:
            return Generatorergebnis(
                bester=raeumlich[0],
                alternativen=raeumlich[1:1 + 2 * anzahl_alternativen],
                geprueft=geprueft + len(raeumlich), verworfen_abriss=verworfen,
                begruendung=_begruenden_raeumlich(raeumlich, innenbereich_mm,
                                                  endplatte_mm) + begruendung,
                vorauswahl=kandidaten[:10], feinsuche=True)

    return Generatorergebnis(
        bester=kandidaten[0] if kandidaten else None,
        alternativen=_streuen(kandidaten[1:], anzahl_alternativen),
        geprueft=geprueft, verworfen_abriss=verworfen,
        begruendung=begruendung, vorauswahl=kandidaten[:10])


def _zeilen(flapdatei: str, winkelfolge, spalt: float,
            ueberlappung: float) -> list[dict]:
    """Die Flaps einer Kombination als Zeilen der Kaskadentabelle.

    Dieselbe Verjuengung, mit der gerechnet wird - jedes weitere Element
    kuerzer.
    """
    if flapdatei == "-":
        return []
    return [{"profil": flapdatei, "sehne": round(0.35 - 0.07 * i, 3),
             "winkel": float(w), "spalt": spalt, "ueberlappung": ueberlappung}
            for i, w in enumerate(winkelfolge)]


def _begrenzt(winkel: float) -> float:
    return float(min(max(winkel, -60.0), 60.0))


def _varianten(zeilen: list[dict], innen: float, aussen: float,
               innenbereich_mm: float = 0.0) -> list[tuple[str, list[dict]]]:
    """Die raeumlichen Varianten einer Kombination.

    Die Muster stammen aus dem, was im Formula Student gebaut wird: innen vor
    dem Unterboden weniger Last und Luft fuer den Kanal, aussen vor dem Reifen
    die steilsten Flaps.
    """
    beginn = None
    if innenbereich_mm and innenbereich_mm > 0.0 \
            and innen + innenbereich_mm < aussen - 50.0:
        beginn = round(innen + float(innenbereich_mm), 1)
    if not zeilen:
        return [("Einzelnes Element", [])]

    def kopie():
        return [dict(z, y_von=beginn, y_bis=None, winkel_aussen=None)
                for z in zeilen]

    varianten = []
    v = kopie()
    varianten.append(("Flaps über die ganze Spannweite" if beginn is None else
                      f"Flaps ab y = {beginn:.0f} mm, innen Einlauf zum "
                      f"Unterboden", v))

    v = kopie()
    v[-1]["winkel_aussen"] = _begrenzt(v[-1]["winkel"] - 6.0)
    varianten.append(("Letzter Flap nach außen 6° steiler", v))

    v = kopie()
    grund = v[0]["winkel"]
    v[0]["winkel"] = _begrenzt(grund + 6.0)
    v[0]["winkel_aussen"] = _begrenzt(grund - 4.0)
    varianten.append(("Erster Flap innen 6° flacher, außen 4° steiler", v))

    von = beginn if beginn is not None else innen
    v = kopie()
    v[-1]["y_von"] = round(von + 0.5 * (aussen - von), 1)
    v[-1]["winkel"] = _begrenzt(v[-1]["winkel"] - 4.0)
    varianten.append(("Letzter Flap nur auf der äußeren Hälfte, 4° steiler", v))
    return varianten


def _feinsuche(kandidaten: list[Bauart], anzahl: int, spannweite,
               sehne: float, grundwinkel: float, geschwindigkeit: float, lage,
               endplatte_mm: float, innenbereich_mm: float, mit_boden: bool,
               regelpruefung: bool) -> list[Bauart]:
    """Rechnet die besten Kombinationen raeumlich, in Varianten."""
    from ..geometrie import spannweite as spw_geo
    from . import kaskade3d

    stellen = [st.y for st in spannweite.stuetzstellen]
    innen, aussen = float(min(stellen)), float(max(stellen))

    auswahl: list[Bauart] = []
    for b in kandidaten:
        if all((b.hauptprofil, b.flapprofil, b.elemente)
               != (g.hauptprofil, g.flapprofil, g.elemente) for g in auswahl):
            auswahl.append(b)
        if len(auswahl) >= anzahl:
            break

    ergebnisse: list[Bauart] = []
    for b in auswahl:
        hauptprofil = _lade(b.hauptprofil)
        for name, zeilen in _varianten(b.stufen, innen, aussen, innenbereich_mm):
            vorgaben = [geo.Kaskadenvorgabe(
                _lade(z["profil"]), sehne_faktor=z["sehne"],
                winkel_relativ=z["winkel"], spalt=z["spalt"],
                ueberlappung=z["ueberlappung"], name=f"Flap {i}",
                y_von=z.get("y_von"), y_bis=z.get("y_bis"),
                winkel_aussen=z.get("winkel_aussen"))
                for i, z in enumerate(zeilen, start=1)]
            try:
                # Erst bei Hoehe null bauen und den tiefsten Punkt messen: Er
                # haengt an Profil, Flaps und Verdrehung, also an der Variante.
                stapel = spw_geo.kaskadenschnitte(hauptprofil, spannweite,
                                                  sehne, grundwinkel, vorgaben,
                                                  25, lage=(lage[0], lage[1], 0.0))
                tief = min(sc.hoehe_min for st in stapel for sc in st)
                eigene_lage = (lage[0], lage[1], lage[2] - tief)
                stapel = [[replace(sc, punkte=sc.punkte
                                   + np.array([0.0, 0.0, lage[2] - tief]))
                           for sc in st] for st in stapel]
                r = kaskade3d.rechne(hauptprofil, spannweite, sehne,
                                     grundwinkel, vorgaben, geschwindigkeit,
                                     lage=eigene_lage,
                                     endplatte_mm=endplatte_mm,
                                     mit_boden=mit_boden, stuetzen=3,
                                     punkte=40)
            except Exception:
                continue
            raum = spw_geo.pruefe_kaskade_raeumlich(stapel, vorgaben, spannweite)
            konform, regeltexte = (_regelpruefung(stapel) if regelpruefung
                                   else (None, []))
            ergebnisse.append(replace(
                b, abtrieb=r.abtrieb, widerstand=r.widerstand,
                flapwinkel=tuple(z["winkel"] for z in zeilen),
                stufen=zeilen, variante=name, raeumlich=True,
                abgerissen_raeumlich=not r.brauchbar,
                durchdringungsfrei=raum.durchdringungsfrei,
                regelkonform=konform,
                hinweise=list(r.hinweise)
                + [x.text for x in raum.befunde if x.stufe != "ok"]
                + regeltexte))

    ergebnisse.sort(key=lambda e: (not e.empfehlbar, -e.abtrieb))
    return ergebnisse


def _regelpruefung(stapel_je_element) -> tuple[bool, list[str]]:
    """Haelt die ganze Kaskade das Reglement ein? Nur harte Verstoesse zaehlen."""
    from ..regeln import Bezugsgeometrie, Fahrzustand, alle_staende, pruefe_fluegel

    alle = [s for st in stapel_je_element for s in st]
    bezug = Bezugsgeometrie.aus_datei()
    vorne = max(0.0, -min(float(s.punkte[:, 0].min()) for s in alle))
    zustand = Fahrzustand.bremsend(vorne)
    verstoesse = []
    for satz in alle_staende():
        for befund in pruefe_fluegel(alle, satz, bezug, zustand):
            if not befund.ok and befund.blockiert:
                verstoesse.append(f"{satz.version}: {befund.regel} "
                                  f"{befund.pruefung}")
    return not verstoesse, verstoesse


def _begruenden_raeumlich(ergebnisse: list[Bauart], innenbereich_mm: float,
                          endplatte_mm: float) -> list[str]:
    bester = ergebnisse[0]
    texte = [f"Räumlich gerechnet: {len(ergebnisse)} Varianten aus den besten "
             f"Kombinationen der Vorauswahl — mit Teilflügeln und verdrehten "
             f"Flaps, Endplatten {endplatte_mm:.0f} mm und Kanalwirkung am "
             f"Boden, dazu Durchdringungs- und Regelprüfung."]
    if not bester.empfehlbar:
        texte.append("Keine Variante ist zugleich anliegend, "
                     "durchdringungsfrei und regelkonform. Die stärkste steht "
                     "trotzdem oben, mit ihren Befunden.")
    gleiche = [e for e in ergebnisse
               if (e.hauptprofil, e.flapprofil, e.elemente)
               == (bester.hauptprofil, bester.flapprofil, bester.elemente)]
    grund = next((e for e in gleiche if e.variante.startswith("Flaps")), None)
    if grund is not None and grund is not bester:
        texte.append(f"„{bester.variante}“ bringt {bester.abtrieb - grund.abtrieb:+.0f} N "
                     f"gegenüber denselben Flaps ohne Verdrehung "
                     f"({grund.abtrieb:.0f} N).")
    if innenbereich_mm and innenbereich_mm > 0:
        texte.append(f"Innen bleiben {innenbereich_mm:.0f} mm ohne Flaps als "
                     f"Einlauf zum Unterboden. Den Gewinn am Unterboden rechnet "
                     f"das Werkzeug nicht — nur, was der Flügel dafür abgibt.")
    return texte


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
