"""
Das ganze Aeropaket optimieren: Fluegel, Unterboden und Rake gemeinsam.

Der DoE aus `doe.py` variiert den Unterboden allein. Hier wird das GANZE
Auto variiert - die Anstellwinkel von Front- und Heckfluegel, der Unterboden
und der Rake - und nach dem bewertet, was am Ende faehrt:

* **Abtrieb** in Konstruktionslage, moeglichst viel,
* **Balancefehler**: Abstand der Balance zur Zielbalance in Prozentpunkten,
  moeglichst klein,
* **Nickwanderung**: wie weit die Balance je Grad Nicken wandert (Betrag),
  moeglichst klein.

Den Widerstand fuehrt die Ergebnisdatei mit, er ist aber kein Ziel: Mit
vier Zielen wuerde die Front so breit, dass sie nichts mehr aussondert.
(Bis zum 28.09. war er zudem nicht glatt - behoben in traglinie.rechne.)

**Das Paket.** Front- und Heckfluegel stehen meist in getrennten Specs. Ein
Paket ist EIN AeroSpec mit allen Fluegeln als Elementen, dem Unterboden und
der Fahrzeuglage. Damit ist eine Variante wieder "Basis plus Werte", genau
wie im Unterboden-DoE, und `doe.laufen` traegt den Lauf unveraendert.

**Kennfelder statt Traglinie je Variante.** Eine Variante mit Nickwanderung
braucht fuenf Lagen je Fluegel. Mit der echten Rechnung waeren das rund
acht Sekunden, zweihundert Varianten also eine halbe Stunde. Stattdessen
bekommt jeder Fluegel vorab ein Kennfeld: Abtrieb, Widerstand und
Angriffspunkt ueber Anstellwinkel und Hoehe, einmal mit der echten Rechnung
gefuellt und dann linear interpoliert. Das kostet einmal etwa eine Minute,
danach rechnet jede Variante in Millisekunden. Voraussetzung: Der DoE
aendert am Fluegel NUR Anstellwinkel und (ueber Rake und Nicken) Hoehe -
alles andere ist im Kennfeld eingefroren.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Callable

import numpy as np

from . import doe, gesamt

PAKET_ZIELE = [
    doe.Ziel("abtrieb", True, "N"),
    doe.Ziel("balancefehler", False, "%-Pkt."),
    doe.Ziel("wanderung", False, "%/°"),
]

# Wie weit die Anstellwinkel um den Ausgangsentwurf variiert werden.
WINKEL_SPIELRAUM = 3.0
# Mit Groesse: Sehne und Halbspannweite als Faktor auf den Ausgangsentwurf.
SEHNE_FAKTOR = (0.8, 1.25)
SPANNWEITE_FAKTOR = (0.8, 1.2)
RAKE_BEREICH = (0.0, 1.5)
NICK_MAX = 0.5                  # wie gesamt.NICKZUSTAENDE

# Stuetzstellen je Kennfeldachse - ohne und mit Groesse. Mit Groesse wird
# das Feld vierdimensional; 5 x 3 x 3 x 3 = 135 echte Rechnungen je Fluegel
# statt 7 x 4 = 28, also einige Minuten statt einer.
STUFEN = {"winkel": 7, "hoehe": 4}
STUFEN_GROESSE = {"winkel": 5, "hoehe": 3, "sehne": 3, "halbspannweite": 3}


# ------------------------------------------------------------------ Paket

def bauen(editor, weitere=()):
    """Ein Paket-Spec aus dem Spec im Editor und weiteren Specs.

    Fluegel aus allen, Unterboden und Lage aus dem Editor; hat der keinen
    Unterboden, der erste aus den weiteren. Doppelte Element-ids bekommen
    eine Nummer angehaengt, damit die Kennfelder sie auseinanderhalten.
    """
    paket = editor.model_copy(deep=True)
    vergeben = {e.id for e in paket.elemente}
    for anderes in weitere:
        for element in anderes.elemente:
            neu = element.model_copy(deep=True)
            kennung, n = neu.id, 2
            while kennung in vergeben:
                kennung, n = f"{neu.id}_{n}", n + 1
            neu.id = kennung
            vergeben.add(kennung)
            paket.elemente.append(neu)
        if paket.unterboden is None and anderes.unterboden is not None:
            paket.unterboden = anderes.unterboden.model_copy(deep=True)
    return paket


def fluegel_des_pakets(paket) -> list[tuple[str, object]]:
    return [(e.name or e.id, e) for e in paket.elemente]


def halbspannweite(element) -> float:
    return float(max(st.y for st in element.spannweite.stuetzstellen))


def breitengrenze(element, bezug=None) -> float:
    """Die Halbspannweite, bis zu der T 8.2.2 einen Fluegel in seiner
    Einbauhoehe zulaesst (FS Rules 2027 v1.0). Ohne Endplattendicke - die
    genaue Pruefung macht danach der Pruefer an der Front."""
    from ..regeln import Bezugsgeometrie

    bezug = bezug or Bezugsgeometrie.aus_datei()
    z = float(element.pos_z)
    if z >= 700.0:
        return bezug.rad_aussen_hinten
    if float(element.pos_x) < bezug.vorderreifen_vorderkante_x or \
            z < bezug.reifenoberkante_z:
        return bezug.rad_aussen
    return bezug.rad_innen_hinten - 150.0


def raum(paket, winkel: float = WINKEL_SPIELRAUM,
         groesse: bool = False, bezug=None) -> list[doe.Parameter]:
    """Der Vorgaberaum: jeder Fluegel mit Spannweite um seinen Winkel - mit
    `groesse` auch Sehne und Halbspannweite -, der Unterboden wie im
    Unterboden-DoE (ohne Einlass und Laenge), der Rake.

    Mit Winkeln allein ist eine Zielbalance oft nicht erreichbar: Beim
    Beispielpaket liefert der Frontfluegel ein Vielfaches des Heckfluegels,
    und +-3 Grad verschieben daran wenig. Die Groesse ist der Hebel.
    """
    teile = []
    for i, e in enumerate(paket.elemente):
        if e.spannweite is None:
            continue
        name = e.name or e.id
        a = float(e.anstellwinkel)
        teile.append(doe.Parameter(f"elemente.{i}.anstellwinkel",
                                   a - winkel, a + winkel,
                                   name=f"Anstellwinkel {name} [°]"))
        if groesse:
            c, h = float(e.sehne), halbspannweite(e)
            teile.append(doe.Parameter(f"elemente.{i}.sehne",
                                       c * SEHNE_FAKTOR[0], c * SEHNE_FAKTOR[1],
                                       name=f"Sehne {name} [mm]"))
            # Nach oben bis an die Breitengrenze, die fuer die Einbauhoehe
            # des Fluegels gilt - nicht nur +20 %. Ein schmaler Heckfluegel
            # (Beispiel: 280 mm halb) darf oberhalb 700 mm bis zur
            # Hinterrad-Aussenkante; mit +20 % blieb die Zielbalance
            # unerreichbar, obwohl das Reglement den Platz hergibt.
            oben = max(h * SPANNWEITE_FAKTOR[1], breitengrenze(e, bezug))
            teile.append(doe.Parameter(f"elemente.{i}.halbspannweite",
                                       h * SPANNWEITE_FAKTOR[0], oben,
                                       name=f"Halbspannweite {name} [mm]"))
    if paket.unterboden is not None:
        namen = {"unterboden.kehle_hoehe_vorne": "Kehle vorne [mm]",
                 "unterboden.kehle_hoehe_hinten": "Kehle hinten [mm]",
                 "unterboden.diffusor_winkel": "Diffusorwinkel [°]"}
        teile += [doe.Parameter(p.pfad, p.von, p.bis, namen[p.pfad])
                  for p in doe.UNTERBODEN_RAUM if p.pfad in namen]
    teile.append(doe.Parameter("lage.rake_grad", *RAKE_BEREICH, name="Rake [°]"))
    return teile


# --------------------------------------------------------------- Kennfeld

def _achswert(element, name: str) -> float:
    if name == "winkel":
        return float(element.anstellwinkel)
    if name == "hoehe":
        return float(element.pos_z)
    if name == "sehne":
        return float(element.sehne)
    if name == "halbspannweite":
        return halbspannweite(element)
    raise KeyError(name)


def _mit(element, werte: dict[str, float]):
    """Das Element mit gesetzten Achswerten."""
    neu = {}
    if "winkel" in werte:
        neu["anstellwinkel"] = float(werte["winkel"])
    if "hoehe" in werte:
        neu["pos_z"] = float(werte["hoehe"])
    if "sehne" in werte:
        neu["sehne"] = float(werte["sehne"])
    if "halbspannweite" in werte:
        neu["spannweite"] = element.spannweite.skaliert(float(werte["halbspannweite"]))
    return element.model_copy(update=neu)


@dataclass
class Kennfeld:
    """Kraefte eines Fluegels ueber mehrere Achsen, bei einer Geschwindigkeit.

    Immer Anstellwinkel und Hoehe des tiefsten Punkts; mit Groesse dazu
    Sehne und Halbspannweite. Zwischen den Stuetzstellen linear.
    """

    achsen: dict[str, np.ndarray]
    abtrieb: np.ndarray          # Form wie die Achsen, in deren Reihenfolge
    widerstand: np.ndarray
    x: np.ndarray
    geschwindigkeit: float

    # Rueckwaerts lesbar wie das alte zweiachsige Feld.
    @property
    def winkel(self) -> np.ndarray:
        return self.achsen["winkel"]

    @property
    def hoehe(self) -> np.ndarray:
        return self.achsen["hoehe"]

    def _punkt(self, element=None, *werte) -> list[float]:
        if element is not None and not isinstance(element, (int, float, np.floating)):
            return [_achswert(element, n) for n in self.achsen]
        return [float(w) for w in ((element,) + werte)]

    def enthaelt(self, element=None, *werte) -> bool:
        punkt = self._punkt(element, *werte)
        return all(a[0] - 1e-9 <= w <= a[-1] + 1e-9
                   for w, a in zip(punkt, self.achsen.values()))

    def __call__(self, element=None, *werte) -> SimpleNamespace:
        """Linear, am Rand festgehalten. Ausserhalb wird nicht
        extrapoliert - wer dort landet, hat das Kennfeld zu klein gewaehlt,
        und `enthaelt` sagt es. Aufrufbar mit einem Element oder mit den
        Achswerten in Achsreihenfolge."""
        from scipy.interpolate import RegularGridInterpolator

        punkt = [float(np.clip(w, a[0], a[-1]))
                 for w, a in zip(self._punkt(element, *werte),
                                 self.achsen.values())]
        gitter = tuple(self.achsen.values())

        def lies(feld):
            return float(RegularGridInterpolator(gitter, feld)(punkt)[0])

        return SimpleNamespace(abtrieb=lies(self.abtrieb),
                               widerstand=lies(self.widerstand),
                               x_angriff=lies(self.x), streifen=[],
                               auftrieb_lokal=[])


def kennfeld(element, rechnen: Callable, geschwindigkeit: float,
             winkel: tuple[float, float], hoehe: tuple[float, float],
             stufen_winkel: int = 7, stufen_hoehe: int = 4,
             fortschritt: Callable[[int, int], None] | None = None,
             sehne: tuple[float, float] | None = None,
             spannweite: tuple[float, float] | None = None,
             stufen_sehne: int = 3, stufen_spannweite: int = 3) -> Kennfeld:
    """Fuellt das Kennfeld mit der echten Rechnung."""
    import itertools

    achsen = {"winkel": np.linspace(winkel[0], winkel[1], stufen_winkel),
              "hoehe": np.linspace(max(hoehe[0], 1.0),
                                   max(hoehe[1], hoehe[0] + 1.0), stufen_hoehe)}
    if sehne is not None:
        achsen["sehne"] = np.linspace(sehne[0], sehne[1], stufen_sehne)
    if spannweite is not None:
        achsen["halbspannweite"] = np.linspace(spannweite[0], spannweite[1],
                                               stufen_spannweite)
    form = tuple(len(a) for a in achsen.values())
    abtrieb, widerstand, x = np.zeros(form), np.zeros(form), np.zeros(form)
    gesamt_n = int(np.prod(form))
    for k, index in enumerate(itertools.product(*(range(n) for n in form)), 1):
        werte = {name: float(achse[i]) for (name, achse), i
                 in zip(achsen.items(), index)}
        e = _mit(element, werte)
        r = rechnen(e, geschwindigkeit)
        abtrieb[index] = float(r.abtrieb)
        widerstand[index] = float(r.widerstand)
        x[index] = gesamt.angriffspunkt(r, float(e.pos_x) + 0.25 * float(e.sehne))
        if fortschritt is not None:
            fortschritt(k, gesamt_n)
    return Kennfeld(achsen, abtrieb, widerstand, x, float(geschwindigkeit))


def kennfeldbereich(element, parameter: list[doe.Parameter], index: int,
                    fahrzeuglage, radstand: float) -> dict[str, tuple]:
    """Welche Achswerte der Fluegel im Lauf ueberhaupt sieht.

    Winkel aus dem DoE-Bereich, dem Rakebereich und dem Nicken; Hoehe nur
    ueber Rake und Nicken; Sehne und Halbspannweite, falls der DoE sie
    variiert. Die Hoehe wird am Viertelpunkt der groessten Sehne bewertet -
    eine laengere Sehne schiebt ihn nach hinten.
    """
    def bereich(name, vorgabe):
        p = next((q for q in parameter if q.pfad == f"elemente.{index}.{name}"), None)
        return (p.von, p.bis) if p else None

    a_lo, a_hi = bereich("anstellwinkel", None) or (element.anstellwinkel,) * 2
    rake = next((p for p in parameter if p.pfad == "lage.rake_grad"), None)
    r_lo, r_hi = ((rake.von, rake.bis) if rake
                  else (fahrzeuglage.rake_grad,) * 2)
    drehpunkt = fahrzeuglage.drehpunkt_x
    sehne = bereich("sehne", None)

    hoehen, winkel = [], []
    for c in ((sehne[0], sehne[1]) if sehne else (float(element.sehne),)):
        x_ref = float(element.pos_x) + 0.25 * float(c)
        for r in (r_lo, r_hi):
            for n in (-NICK_MAX, NICK_MAX):
                lage = gesamt.Lage(type(fahrzeuglage)(rake_grad=r, drehpunkt_x=drehpunkt),
                                   gesamt.Zustand("", n), radstand)
                hoehen.append(float(element.pos_z) + lage.versatz(x_ref))
                winkel += [a_lo - lage.rake_grad, a_hi - lage.rake_grad]
    rand = 0.25
    aus = {"winkel": (min(winkel) - rand, max(winkel) + rand),
           "hoehe": (min(hoehen) - 2.0, max(hoehen) + 2.0)}
    if sehne:
        aus["sehne"] = sehne
    spann = bereich("halbspannweite", None)
    if spann:
        aus["spannweite"] = spann
    return aus


# --------------------------------------------------------------- Bewertung

class Bewertung:
    """Die Zielfunktion fuer das Paket, mit einem Kennfeld je Fluegel.

    Aufrufbar wie `doe.unterboden_bewerten`, damit `doe.laufen` sie nimmt.
    """

    def __init__(self, kennfelder: dict[str, Kennfeld], ziel: float,
                 radstand: float = 1535.0, nicken: bool = True):
        self.kennfelder = kennfelder
        self.ziel = float(ziel)
        self.radstand = float(radstand)
        self.nicken = nicken
        self.ausserhalb = 0

    def rechnen(self, element, geschwindigkeit):
        feld = self.kennfelder[element.id]
        if not feld.enthaelt(element):
            self.ausserhalb += 1
        return feld(element)

    def __call__(self, spec, geschwindigkeit: float = 20.0,
                 regelsatz=None) -> dict:
        from . import unterboden as ub

        fluegel = [(n, e) for n, e in fluegel_des_pakets(spec)
                   if e.id in self.kennfelder]
        zustaende = gesamt.NICKZUSTAENDE if self.nicken else [gesamt.Zustand()]
        reihe = gesamt.wanderung(fluegel, spec.unterboden, spec.lage,
                                 self.rechnen, geschwindigkeit, self.radstand,
                                 zustaende)
        mitte = next(b for b in reihe if b.zustand.nick_grad == 0.0)

        gruende = [f"{b.name}: {b.hinweis}" for bil in reihe
                   for b in bil.beitraege
                   if b.hinweis.startswith("Setzt") or "setzt auf" in b.hinweis]
        if spec.unterboden is not None:
            gruende += [f"{b.regel} {b.text}" for b in
                        ub.pruefe(spec.unterboden, spec.lage, regelsatz)
                        if not b.ok]

        balance = 100.0 * mitte.balance_vorne
        wandern = gesamt.empfindlichkeit(reihe) if self.nicken else 0.0
        return {
            "gueltig": not gruende and math.isfinite(balance),
            "grund": "; ".join(dict.fromkeys(gruende)),
            "abtrieb": mitte.abtrieb,
            "balance": balance,
            "balancefehler": abs(balance - self.ziel),
            "wanderung": abs(wandern) if math.isfinite(wandern) else float("nan"),
            "widerstand": mitte.widerstand,
        }


def kennfelder(paket, parameter, rechnen, geschwindigkeit: float,
               radstand: float,
               fortschritt: Callable[[str, int, int], None] | None = None,
               **stufen) -> dict[str, Kennfeld]:
    felder = {}
    for i, e in enumerate(paket.elemente):
        if e.spannweite is None:
            continue
        bereiche = kennfeldbereich(e, parameter, i, paket.lage, radstand)
        if "sehne" in bereiche or "spannweite" in bereiche:
            vorgabe = {"stufen_winkel": STUFEN_GROESSE["winkel"],
                       "stufen_hoehe": STUFEN_GROESSE["hoehe"],
                       "stufen_sehne": STUFEN_GROESSE["sehne"],
                       "stufen_spannweite": STUFEN_GROESSE["halbspannweite"]}
            vorgabe.update(stufen)
        else:
            vorgabe = dict(stufen)
        melden = (lambda k, n, name=e.name or e.id: fortschritt(name, k, n)) \
            if fortschritt else None
        felder[e.id] = kennfeld(e, rechnen, geschwindigkeit, fortschritt=melden,
                                **bereiche, **vorgabe)
    return felder


def regeln_auf_der_front(lauf, paket, pruefen: Callable,
                         ziele=None) -> int:
    """Prueft die Varianten der Front gegen das Reglement, bis die Front
    nur noch aus geprueften, regelkonformen Varianten besteht.

    Jede Variante zu pruefen kostet gut eine halbe Sekunde fuer beide
    Fluegel - bei 200 Varianten Minuten. Geprueft wird deshalb nur, was auf
    der Front landet: Faellt eine durch, kommt sie raus, die Front wird neu
    bestimmt, und die Nachruecker werden geprueft. Die Front am Ende ist
    damit vollstaendig geprueft; Varianten abseits der Front nicht - das
    steht in ihrem Ergebnis (`regeln`).

    `pruefen(element, lage)` liefert die Verstoesse eines Fluegels als
    Texte. Geprueft wird in der Fahrzeuglage der Variante, also mit Rake.
    Gibt die Zahl der geprueften Varianten zurueck.
    """
    ziele = ziele or lauf.ziele
    for e in lauf.ergebnisse:
        e.setdefault("regeln", "ungeprüft")
    geprueft = 0
    while True:
        offen = [i for i in lauf.front if lauf.ergebnisse[i]["regeln"] == "ungeprüft"]
        if not offen:
            break
        for i in offen:
            spec = doe.variante(paket, lauf.varianten[i])
            lage = gesamt.Lage(spec.lage, gesamt.Zustand(), 0.0)
            verstoesse = []
            for name, element in fluegel_des_pakets(spec):
                if element.spannweite is None:
                    continue
                verstoesse += [f"{name}: {v}" for v in pruefen(element, lage)]
            geprueft += 1
            if verstoesse:
                lauf.ergebnisse[i]["gueltig"] = False
                lauf.ergebnisse[i]["regeln"] = "verletzt"
                grund = lauf.ergebnisse[i].get("grund") or ""
                lauf.ergebnisse[i]["grund"] = "; ".join(
                    t for t in [grund, *verstoesse] if t)
            else:
                lauf.ergebnisse[i]["regeln"] = "geprüft"
        lauf.front = doe.pareto(lauf.ergebnisse, ziele)
    return geprueft


def laufen(paket, rechnen: Callable, ziel: float, n: int = 200, *,
           parameter: list[doe.Parameter] | None = None, seed: int = 0,
           geschwindigkeit: float = 20.0, radstand: float = 1535.0,
           regelsatz=None, felder: dict[str, Kennfeld] | None = None,
           fortschritt=None, groesse: bool = False,
           pruefen: Callable | None = None,
           **stufen) -> tuple[doe.Lauf, Bewertung]:
    """Kennfelder fuellen, dann den DoE ueber das Paket.

    `pruefen` (siehe `regeln_auf_der_front`) prueft die Front gegen das
    Reglement. Ohne wird nur Aufsetzen und T 2.2.1 am Unterboden geprueft.
    """
    parameter = parameter or raum(paket, groesse=groesse)
    if felder is None:
        felder = kennfelder(paket, parameter, rechnen, geschwindigkeit,
                            radstand, fortschritt, **stufen)
    bewertung = Bewertung(felder, ziel, radstand)
    lauf = doe.laufen(paket, parameter, n, seed=seed,
                      geschwindigkeit=geschwindigkeit, bewerten=bewertung,
                      ziele=PAKET_ZIELE, regelsatz=regelsatz)
    lauf.zusatz["zielbalance"] = float(ziel)
    if pruefen is not None:
        lauf.zusatz["regeln_geprueft"] = regeln_auf_der_front(lauf, paket, pruefen)
    return lauf, bewertung


# ----------------------------------------------------------- Kommandozeile

def main(argv: list[str] | None = None) -> int:
    import argparse

    from ..regeln import AKTUELL, Bezugsgeometrie, lade
    from ..spec.projekt import AeroSpec

    teil = argparse.ArgumentParser(
        prog="python -m aerostudio.aero.paket",
        description="DoE ueber das ganze Aeropaket: Fluegelwinkel, "
                    "Unterboden, Rake. Ziele: Abtrieb, Balancefehler, "
                    "Nickwanderung.")
    teil.add_argument("--spec", required=True, help="Haupt-Spec (YAML)")
    teil.add_argument("--dazu", nargs="*", default=[],
                      help="weitere Specs, etwa der Heckfluegel")
    teil.add_argument("--ziel", type=float, default=None,
                      help="Zielbalance vorn in Prozent. Ohne Angabe die "
                           "Achslast aus vehicle_ref.yaml")
    teil.add_argument("--n", type=int, default=200)
    teil.add_argument("--seed", type=int, default=0)
    teil.add_argument("--tempo", type=float, default=20.0)
    teil.add_argument("--aus", default="export/doe_paket.yaml")
    teil.add_argument("--regelstand", default=AKTUELL)
    teil.add_argument("--groesse", action="store_true",
                      help="auch Sehne und Halbspannweite variieren")
    arg = teil.parse_args(argv)
    if arg.ziel is None:
        arg.ziel = gesamt.zielbalance_aus_datei()
        if arg.ziel is None:
            teil.error("--ziel fehlt, und vehicle_ref.yaml nennt keine "
                       "fahrdynamik.achslast_vorne_prozent.")

    from ..ui.app import _fluegelkraefte, _regelverstoesse

    paket = bauen(AeroSpec.laden(arg.spec),
                  [AeroSpec.laden(p) for p in arg.dazu])
    radstand = Bezugsgeometrie.aus_datei().radstand

    def melden(name, k, n):
        if k == n or k % max(1, n // 4) == 0:
            print(f"  Kennfeld {name}: {k:>3} / {n}", flush=True)

    lauf, bewertung = laufen(paket, _fluegelkraefte, arg.ziel, arg.n,
                             seed=arg.seed, geschwindigkeit=arg.tempo,
                             radstand=radstand,
                             regelsatz=lade(arg.regelstand), fortschritt=melden,
                             groesse=arg.groesse, pruefen=_regelverstoesse)
    ziel = lauf.speichern(arg.aus)
    print()
    print(f"  {len(lauf.varianten)} Varianten, {lauf.gueltige} gueltig, "
          f"{len(lauf.front)} auf der Pareto-Front "
          f"({lauf.zusatz.get('regeln_geprueft', 0)} gegen das Reglement geprueft).")
    print(f"  Geschrieben: {ziel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
