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
RAKE_BEREICH = (0.0, 1.5)
NICK_MAX = 0.5                  # wie gesamt.NICKZUSTAENDE


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


def raum(paket, winkel: float = WINKEL_SPIELRAUM) -> list[doe.Parameter]:
    """Der Vorgaberaum: jeder Fluegel mit Spannweite um seinen Winkel, der
    Unterboden wie im Unterboden-DoE (ohne Einlass und Laenge), der Rake."""
    teile = []
    for i, e in enumerate(paket.elemente):
        if e.spannweite is None:
            continue
        a = float(e.anstellwinkel)
        teile.append(doe.Parameter(f"elemente.{i}.anstellwinkel",
                                   a - winkel, a + winkel,
                                   name=f"Anstellwinkel {e.name or e.id} [°]"))
    if paket.unterboden is not None:
        namen = {"unterboden.kehle_hoehe_vorne": "Kehle vorne [mm]",
                 "unterboden.kehle_hoehe_hinten": "Kehle hinten [mm]",
                 "unterboden.diffusor_winkel": "Diffusorwinkel [°]"}
        teile += [doe.Parameter(p.pfad, p.von, p.bis, namen[p.pfad])
                  for p in doe.UNTERBODEN_RAUM if p.pfad in namen]
    teile.append(doe.Parameter("lage.rake_grad", *RAKE_BEREICH, name="Rake [°]"))
    return teile


# --------------------------------------------------------------- Kennfeld

@dataclass
class Kennfeld:
    """Kraefte eines Fluegels ueber Anstellwinkel und Hoehe des tiefsten
    Punkts, bei einer Geschwindigkeit."""

    winkel: np.ndarray
    hoehe: np.ndarray
    abtrieb: np.ndarray          # [winkel, hoehe]
    widerstand: np.ndarray
    x: np.ndarray
    geschwindigkeit: float

    def enthaelt(self, winkel: float, hoehe: float) -> bool:
        return (self.winkel[0] - 1e-9 <= winkel <= self.winkel[-1] + 1e-9
                and self.hoehe[0] - 1e-9 <= hoehe <= self.hoehe[-1] + 1e-9)

    def __call__(self, winkel: float, hoehe: float) -> SimpleNamespace:
        """Bilinear, am Rand festgehalten. Ausserhalb wird nicht
        extrapoliert - wer dort landet, hat das Kennfeld zu klein gewaehlt,
        und `enthaelt` sagt es."""
        w = float(np.clip(winkel, self.winkel[0], self.winkel[-1]))
        h = float(np.clip(hoehe, self.hoehe[0], self.hoehe[-1]))

        def lies(feld):
            zeile = np.array([np.interp(h, self.hoehe, feld[i])
                              for i in range(len(self.winkel))])
            return float(np.interp(w, self.winkel, zeile))

        return SimpleNamespace(abtrieb=lies(self.abtrieb),
                               widerstand=lies(self.widerstand),
                               x_angriff=lies(self.x), streifen=[],
                               auftrieb_lokal=[])


def kennfeld(element, rechnen: Callable, geschwindigkeit: float,
             winkel: tuple[float, float], hoehe: tuple[float, float],
             stufen_winkel: int = 7, stufen_hoehe: int = 4,
             fortschritt: Callable[[int, int], None] | None = None) -> Kennfeld:
    """Fuellt das Kennfeld mit der echten Rechnung."""
    ww = np.linspace(winkel[0], winkel[1], stufen_winkel)
    hh = np.linspace(max(hoehe[0], 1.0), max(hoehe[1], hoehe[0] + 1.0),
                     stufen_hoehe)
    form = (len(ww), len(hh))
    abtrieb, widerstand, x = np.zeros(form), np.zeros(form), np.zeros(form)
    x_ref = float(element.pos_x) + 0.25 * float(element.sehne)
    gesamt_n, k = form[0] * form[1], 0
    for i, a in enumerate(ww):
        for j, z in enumerate(hh):
            e = element.model_copy(update={"anstellwinkel": float(a),
                                           "pos_z": float(z)})
            r = rechnen(e, geschwindigkeit)
            abtrieb[i, j] = float(r.abtrieb)
            widerstand[i, j] = float(r.widerstand)
            x[i, j] = gesamt.angriffspunkt(r, x_ref)
            k += 1
            if fortschritt is not None:
                fortschritt(k, gesamt_n)
    return Kennfeld(ww, hh, abtrieb, widerstand, x, float(geschwindigkeit))


def kennfeldbereich(element, parameter: list[doe.Parameter], index: int,
                    fahrzeuglage, radstand: float) -> tuple[tuple, tuple]:
    """Welche Winkel und Hoehen der Fluegel im Lauf ueberhaupt sieht.

    Aus dem Winkelbereich des DoE, dem Rakebereich und dem Nicken. Die
    Hoehe aendert sich nur ueber Rake und Nicken - der DoE setzt sie nicht.
    """
    pfad = f"elemente.{index}.anstellwinkel"
    eigen = next((p for p in parameter if p.pfad == pfad), None)
    a_lo, a_hi = ((eigen.von, eigen.bis) if eigen
                  else (element.anstellwinkel, element.anstellwinkel))
    rake = next((p for p in parameter if p.pfad == "lage.rake_grad"), None)
    r_lo, r_hi = ((rake.von, rake.bis) if rake
                  else (fahrzeuglage.rake_grad,) * 2)
    drehpunkt = fahrzeuglage.drehpunkt_x

    x_ref = float(element.pos_x) + 0.25 * float(element.sehne)
    hoehen, winkel = [], []
    for r in (r_lo, r_hi):
        for n in (-NICK_MAX, NICK_MAX):
            lage = gesamt.Lage(type(fahrzeuglage)(rake_grad=r, drehpunkt_x=drehpunkt),
                               gesamt.Zustand("", n), radstand)
            hoehen.append(float(element.pos_z) + lage.versatz(x_ref))
            winkel += [a_lo - lage.rake_grad, a_hi - lage.rake_grad]
    rand = 0.25
    return ((min(winkel) - rand, max(winkel) + rand),
            (min(hoehen) - 2.0, max(hoehen) + 2.0))


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
        if not feld.enthaelt(element.anstellwinkel, element.pos_z):
            self.ausserhalb += 1
        return feld(element.anstellwinkel, element.pos_z)

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
        winkel, hoehe = kennfeldbereich(e, parameter, i, paket.lage, radstand)
        melden = (lambda k, n, name=e.name or e.id: fortschritt(name, k, n)) \
            if fortschritt else None
        felder[e.id] = kennfeld(e, rechnen, geschwindigkeit, winkel, hoehe,
                                fortschritt=melden, **stufen)
    return felder


def laufen(paket, rechnen: Callable, ziel: float, n: int = 200, *,
           parameter: list[doe.Parameter] | None = None, seed: int = 0,
           geschwindigkeit: float = 20.0, radstand: float = 1535.0,
           regelsatz=None, felder: dict[str, Kennfeld] | None = None,
           fortschritt=None, **stufen) -> tuple[doe.Lauf, Bewertung]:
    """Kennfelder fuellen, dann den DoE ueber das Paket."""
    parameter = parameter or raum(paket)
    if felder is None:
        felder = kennfelder(paket, parameter, rechnen, geschwindigkeit,
                            radstand, fortschritt, **stufen)
    bewertung = Bewertung(felder, ziel, radstand)
    lauf = doe.laufen(paket, parameter, n, seed=seed,
                      geschwindigkeit=geschwindigkeit, bewerten=bewertung,
                      ziele=PAKET_ZIELE, regelsatz=regelsatz)
    return lauf, bewertung


# ----------------------------------------------------------- Kommandozeile

def main(argv: list[str] | None = None) -> int:
    import argparse

    from ..regeln import Bezugsgeometrie, lade
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
    teil.add_argument("--regelstand", default="2026")
    arg = teil.parse_args(argv)
    if arg.ziel is None:
        arg.ziel = gesamt.zielbalance_aus_datei()
        if arg.ziel is None:
            teil.error("--ziel fehlt, und vehicle_ref.yaml nennt keine "
                       "fahrdynamik.achslast_vorne_prozent.")

    from ..ui.app import _fluegelkraefte

    paket = bauen(AeroSpec.laden(arg.spec),
                  [AeroSpec.laden(p) for p in arg.dazu])
    radstand = Bezugsgeometrie.aus_datei().radstand

    def melden(name, k, n):
        if k == n or k % max(1, n // 4) == 0:
            print(f"  Kennfeld {name}: {k:>3} / {n}", flush=True)

    lauf, bewertung = laufen(paket, _fluegelkraefte, arg.ziel, arg.n,
                             seed=arg.seed, geschwindigkeit=arg.tempo,
                             radstand=radstand,
                             regelsatz=lade(arg.regelstand), fortschritt=melden)
    ziel = lauf.speichern(arg.aus)
    print()
    print(f"  {len(lauf.varianten)} Varianten, {lauf.gueltige} gueltig, "
          f"{len(lauf.front)} auf der Pareto-Front.")
    print(f"  Geschrieben: {ziel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
