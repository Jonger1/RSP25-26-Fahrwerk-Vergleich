"""
Versuchsplanung (DoE) und Pareto-Front - Optimierungslaeufe statt Handiterationen (M8).

**Der Ablauf.** Ein Parameterraum wird ueber Pfade ins Spec beschrieben
("unterboden.diffusor_winkel" von 6 bis 18 Grad). Daraus zieht eine
Latin-Hypercube-Stichprobe n Varianten, jede wird ausgewertet, und am Ende
bleibt die Pareto-Front: die Varianten, bei denen man kein Ziel verbessern
kann, ohne ein anderes zu verschlechtern.

**Warum Latin Hypercube und nicht Optuna.** Der Meilensteinplan nennt Optuna.
Fuer ein Modell, das eine Variante in Millisekunden rechnet, bringt eine
adaptive Suche wenig: Tausend gleichmaessig verteilte Varianten kosten
Sekunden und zeigen den GANZEN Raum, statt nur die Umgebung des Optimums -
und genau diese Uebersicht will man, solange das Modell noch nicht
kalibriert ist. Eine adaptive Suche lohnt sich, sobald jede Auswertung
Minuten kostet, also mit CFD in der Schleife. Dann ist sie hier
einzuhaengen; `scipy.stats.qmc` braucht keine zusaetzliche Abhaengigkeit.

**Der Zustand bleibt das Spec.** Eine Variante ist kein eigenes Objekt,
sondern ein Satz von Aenderungen an einem Basis-Spec. Die Ergebnisdatei
speichert den Basis-Hash und je Variante nur die Parameterwerte - wer eine
Variante uebernehmen will, wendet sie auf das Basis-Spec an und bekommt ein
gewoehnliches Spec. Keine zweite Wahrheit.

**Der Lauf gehoert auf die Kommandozeile** (`python -m aerostudio.aero.doe`),
nicht in die Oberflaeche. Die zeigt die Ergebnisdatei an.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np
import yaml


@dataclass
class Parameter:
    """Eine Stellgroesse: Pfad ins Spec und ihr Bereich."""

    pfad: str               # etwa "unterboden.diffusor_winkel" oder "lage.rake_grad"
    von: float
    bis: float
    name: str = ""

    def __post_init__(self):
        if not self.bis > self.von:
            raise ValueError(f"Parameter {self.pfad}: 'bis' ({self.bis}) muss "
                             f"groesser sein als 'von' ({self.von}).")
        if not self.name:
            self.name = self.pfad.rsplit(".", 1)[-1]


@dataclass
class Ziel:
    """Eine Zielgroesse und ihre Richtung."""

    name: str
    maximieren: bool = True
    einheit: str = ""


# Die drei Ziele aus dem Meilensteinplan: Abtrieb gegen Widerstand gegen
# Breite des Arbeitsbereichs.
UNTERBODEN_ZIELE = [
    Ziel("abtrieb", True, "N"),
    Ziel("widerstand", False, "N"),
    Ziel("stabilitaet", True, ""),
]

# Ein sinnvoller Startraum fuer den Unterboden. Die Grenzen sind so gewaehlt,
# dass jede Variante baubar ist - wer sie weiter zieht, bekommt Varianten,
# die aufsetzen oder T 2.2.1 reissen, und die werden dann verworfen.
UNTERBODEN_RAUM = [
    Parameter("unterboden.einlass_hoehe", 80.0, 160.0),
    Parameter("unterboden.kehle_hoehe_vorne", 40.0, 80.0),
    Parameter("unterboden.kehle_hoehe_hinten", 35.0, 75.0),
    Parameter("unterboden.diffusor_winkel", 4.0, 20.0),
    Parameter("unterboden.diffusor_laenge", 250.0, 600.0),
    Parameter("lage.rake_grad", 0.0, 1.5),
]


# ------------------------------------------------------------ Varianten

def setze(daten: dict, pfad: str, wert: float) -> None:
    """Schreibt einen Wert an einen Pfad in einem Spec-Abbild."""
    teile = pfad.split(".")
    knoten = daten
    for teil in teile[:-1]:
        if teil.isdigit():
            knoten = knoten[int(teil)]
        else:
            if knoten.get(teil) is None:
                raise KeyError(f"Pfad {pfad}: '{teil}' fehlt im Spec. Ist der "
                               f"Unterboden angelegt?")
            knoten = knoten[teil]
    knoten[teile[-1]] = float(wert)


def variante(basis, werte: dict[str, float]):
    """Wendet Parameterwerte auf ein Basis-Spec an - ergibt ein neues Spec.

    Ueber das Abbild und zurueck durch die Validierung: Ein Wert ausserhalb
    der Grenzen des Datenmodells faellt hier auf und nicht erst in der
    Rechnung.
    """
    from ..spec.projekt import AeroSpec

    daten = basis.model_dump(mode="json")
    for pfad, wert in werte.items():
        setze(daten, pfad, wert)
    return AeroSpec.model_validate(daten)


def stichprobe(raum: list[Parameter], n: int, seed: int = 0) -> list[dict[str, float]]:
    """Latin-Hypercube-Stichprobe ueber den Raum.

    Latin Hypercube statt Zufall: Jede Stellgroesse wird ueber ihren ganzen
    Bereich gleichmaessig abgedeckt, auch bei wenigen Varianten. Bei reinem
    Zufall klumpen fuenfzig Punkte in sechs Dimensionen sichtbar.

    Der `seed` macht den Lauf wiederholbar - dieselbe Stichprobe fuer
    denselben Aufruf, sonst liesse sich kein Ergebnis nachrechnen.
    """
    from scipy.stats import qmc

    if n < 1:
        raise ValueError("Ein DoE braucht mindestens eine Variante.")
    muster = qmc.LatinHypercube(d=len(raum), seed=seed).random(n)
    von = np.array([p.von for p in raum])
    bis = np.array([p.bis for p in raum])
    werte = qmc.scale(muster, von, bis)
    return [{p.pfad: float(zeile[i]) for i, p in enumerate(raum)}
            for zeile in werte]


# -------------------------------------------------------------- Auswertung

def unterboden_bewerten(spec, geschwindigkeit: float = 20.0,
                        regelsatz=None) -> dict:
    """Die Zielfunktion fuer den Unterboden.

    Liefert die drei Ziele und ob die Variante gueltig ist. Ungueltig heisst:
    reisst T 2.2.1 oder setzt im Hub auf. Solche Varianten werden gefuehrt,
    aber nicht in die Pareto-Front genommen - man soll sehen, wo die
    Grenze verlaeuft, und sie nicht fuer eine Loesung halten.
    """
    from . import unterboden as ub

    if spec.unterboden is None:
        raise ValueError("Im Spec ist kein Unterboden angelegt.")

    try:
        e = ub.rechne(spec.unterboden, spec.lage, geschwindigkeit)
    except ValueError as fehler:
        return {"gueltig": False, "grund": str(fehler), "abtrieb": 0.0,
                "widerstand": float("nan"), "stabilitaet": 0.0}

    k = ub.kennlinie(spec.unterboden, spec.lage, geschwindigkeit)
    befunde = ub.pruefe(spec.unterboden, spec.lage, regelsatz)
    verletzt = [b for b in befunde if not b.ok]

    return {
        "gueltig": not verletzt,
        "grund": "; ".join(f"{b.regel} {b.text}" for b in verletzt),
        "abtrieb": e.abtrieb,
        "widerstand": e.widerstand,
        "stabilitaet": k.stabilitaet,
        "druckpunkt_x": e.druckpunkt_x,
        "diffusor_wirksam": e.diffusor_winkel_wirksam,
        "abgeloest": bool(e.abgeloest),
    }


def pareto(ergebnisse: list[dict], ziele: list[Ziel]) -> list[int]:
    """Die Indizes der nicht dominierten, gueltigen Varianten.

    Eine Variante ist dominiert, wenn eine andere in keinem Ziel schlechter
    und in mindestens einem besser ist. Quadratisch in n - bei ein paar
    tausend Varianten sind das Millisekunden, und eine schnellere Form lohnt
    den Code nicht.
    """
    def endlich(wert) -> bool:
        # None steht in geladenen Dateien fuer NaN (siehe _sauber).
        try:
            return math.isfinite(float(wert))
        except (TypeError, ValueError):
            return False

    kandidaten = [i for i, e in enumerate(ergebnisse)
                  if e.get("gueltig") and all(endlich(e.get(z.name))
                                              for z in ziele)]
    if not kandidaten:
        return []

    # Alles auf "groesser ist besser" drehen.
    punkte = np.array([[float(ergebnisse[i][z.name]) * (1.0 if z.maximieren else -1.0)
                        for z in ziele] for i in kandidaten])

    front = []
    for a in range(len(kandidaten)):
        besser_gleich = np.all(punkte >= punkte[a], axis=1)
        echt_besser = np.any(punkte > punkte[a], axis=1)
        if not np.any(besser_gleich & echt_besser):
            front.append(kandidaten[a])
    return front


@dataclass
class Lauf:
    """Ein abgeschlossener DoE-Lauf, so wie er in die Ergebnisdatei geht."""

    basis_hash: str
    raum: list[Parameter]
    ziele: list[Ziel]
    varianten: list[dict[str, float]]
    ergebnisse: list[dict]
    front: list[int]
    geschwindigkeit: float
    seed: int
    zeitpunkt: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))

    @property
    def gueltige(self) -> int:
        return sum(1 for e in self.ergebnisse if e.get("gueltig"))

    def speichern(self, pfad: str | Path) -> Path:
        pfad = Path(pfad)
        pfad.parent.mkdir(parents=True, exist_ok=True)
        daten = {
            "meta": {"basis_hash": self.basis_hash, "zeitpunkt": self.zeitpunkt,
                     "geschwindigkeit": self.geschwindigkeit, "seed": self.seed,
                     "varianten": len(self.varianten), "gueltig": self.gueltige},
            "raum": [{"pfad": p.pfad, "von": p.von, "bis": p.bis, "name": p.name}
                     for p in self.raum],
            "ziele": [{"name": z.name, "maximieren": z.maximieren,
                       "einheit": z.einheit} for z in self.ziele],
            "front": list(self.front),
            "varianten": [{"werte": v, "ergebnis": _sauber(e)}
                          for v, e in zip(self.varianten, self.ergebnisse)],
        }
        pfad.write_text(yaml.safe_dump(daten, allow_unicode=True,
                                       sort_keys=False), encoding="utf-8")
        return pfad

    @staticmethod
    def laden(pfad: str | Path) -> "Lauf":
        d = yaml.safe_load(Path(pfad).read_text(encoding="utf-8"))
        return Lauf(
            basis_hash=d["meta"]["basis_hash"],
            raum=[Parameter(**p) for p in d["raum"]],
            ziele=[Ziel(**z) for z in d["ziele"]],
            varianten=[v["werte"] for v in d["varianten"]],
            ergebnisse=[v["ergebnis"] for v in d["varianten"]],
            front=list(d["front"]),
            geschwindigkeit=float(d["meta"]["geschwindigkeit"]),
            seed=int(d["meta"]["seed"]),
            zeitpunkt=str(d["meta"]["zeitpunkt"]))


def _sauber(ergebnis: dict) -> dict:
    """YAML kennt kein NaN - ungueltige Werte werden zu None."""
    aus = {}
    for k, v in ergebnis.items():
        if isinstance(v, float) and not math.isfinite(v):
            aus[k] = None
        elif isinstance(v, (np.floating, np.integer)):
            aus[k] = float(v)
        elif isinstance(v, np.bool_):
            aus[k] = bool(v)
        else:
            aus[k] = v
    return aus


def laufen(basis, raum: list[Parameter] | None = None, n: int = 60, *,
           seed: int = 0, geschwindigkeit: float = 20.0,
           bewerten: Callable | None = None, ziele: list[Ziel] | None = None,
           regelsatz=None, fortschritt: Callable[[int, int], None] | None = None) -> Lauf:
    """Fuehrt einen DoE-Lauf durch - ohne Handeingriff, das ist M8.

    Eine Variante, die sich nicht aufbauen laesst (Wert ausserhalb des
    Datenmodells), bricht den Lauf NICHT ab. Sie wird als ungueltig gefuehrt,
    mit Grund. Ein Lauf ueber Nacht, der an Variante 37 von 500 stehenbleibt,
    ist der teuerste Fehler, den ein DoE machen kann.
    """
    raum = raum or UNTERBODEN_RAUM
    ziele = ziele or UNTERBODEN_ZIELE
    bewerten = bewerten or unterboden_bewerten

    varianten = stichprobe(raum, n, seed)
    ergebnisse = []
    for i, werte in enumerate(varianten):
        try:
            spec = variante(basis, werte)
            ergebnisse.append(bewerten(spec, geschwindigkeit=geschwindigkeit,
                                       regelsatz=regelsatz))
        except Exception as fehler:            # bewusst breit, siehe Docstring
            ergebnisse.append({"gueltig": False, "grund": str(fehler)})
        if fortschritt is not None:
            fortschritt(i + 1, len(varianten))

    return Lauf(basis_hash=basis.hash(), raum=raum, ziele=ziele,
                varianten=varianten, ergebnisse=ergebnisse,
                front=pareto(ergebnisse, ziele),
                geschwindigkeit=float(geschwindigkeit), seed=int(seed))


# ----------------------------------------------------------- Kommandozeile

def main(argv: list[str] | None = None) -> int:
    import argparse

    from ..regeln import lade
    from ..spec.projekt import AeroSpec
    from ..spec.modell import Unterboden

    teil = argparse.ArgumentParser(
        prog="python -m aerostudio.aero.doe",
        description="DoE ueber den Unterboden: Stichprobe, Auswertung, "
                    "Pareto-Front. Schreibt eine Ergebnisdatei, die der "
                    "Reiter Unterboden anzeigt.")
    teil.add_argument("--spec", required=True, help="Basis-Spec (YAML)")
    teil.add_argument("--n", type=int, default=60, help="Zahl der Varianten")
    teil.add_argument("--seed", type=int, default=0)
    teil.add_argument("--tempo", type=float, default=20.0, help="m/s")
    teil.add_argument("--aus", default="export/doe_unterboden.yaml",
                      help="Ergebnisdatei")
    teil.add_argument("--regelstand", default="2026")
    arg = teil.parse_args(argv)

    basis = AeroSpec.laden(arg.spec)
    if basis.unterboden is None:
        print("  Im Spec ist kein Unterboden angelegt - es wird mit den "
              "Vorgabewerten gerechnet.")
        basis.unterboden = Unterboden()

    def melden(i, n):
        if i == n or i % max(1, n // 10) == 0:
            print(f"  {i:>5} / {n}")

    lauf = laufen(basis, n=arg.n, seed=arg.seed, geschwindigkeit=arg.tempo,
                  regelsatz=lade(arg.regelstand), fortschritt=melden)
    ziel = lauf.speichern(arg.aus)

    print()
    print(f"  {len(lauf.varianten)} Varianten, {lauf.gueltige} gueltig, "
          f"{len(lauf.front)} auf der Pareto-Front.")
    if lauf.front:
        beste = max(lauf.front, key=lambda i: lauf.ergebnisse[i]["abtrieb"])
        e = lauf.ergebnisse[beste]
        print(f"  Hoechster Abtrieb auf der Front: {e['abtrieb']:.1f} N bei "
              f"{e['widerstand']:.1f} N Widerstand, Stabilitaet "
              f"{e['stabilitaet']:.2f}.")
    print(f"  Geschrieben: {ziel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
