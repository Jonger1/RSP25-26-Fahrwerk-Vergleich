"""Parametrischer Sweep fuer MehrElement-Kaskaden.

Der Sweep ist bewusst kein Black-Box-Optimierer. Er erzeugt einen
reproduzierbaren Designraum und kennzeichnet Kombinationen ausserhalb der
Kaskaden-Modellgrenzen. So laesst sich spaeter CFD direkt gegen denselben
Designraum vergleichen.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product


@dataclass(frozen=True)
class SweepErgebnis:
    gap: float
    overlap: float
    winkel_relativ: float
    cl: float
    cd: float
    reserve: float
    abgerissen: bool
    modellgueltig: bool

    @property
    def gueltig(self) -> bool:
        return self.modellgueltig and not self.abgerissen


def raster(start: float, ende: float, schritt: float) -> tuple[float, ...]:
    """Erzeugt ein inklusives Raster mit robuster Gleitkomma-Behandlung."""
    start = float(start)
    ende = float(ende)
    schritt = float(schritt)
    if schritt <= 0.0:
        raise ValueError("Schrittweite muss > 0 sein.")
    if ende < start:
        raise ValueError("Rasterende muss >= Rasterstart sein.")
    werte = []
    i = 0
    while True:
        wert = start + i * schritt
        if wert > ende + 1e-12:
            break
        werte.append(round(wert, 10))
        i += 1
        if i > 10000:
            raise ValueError("Raster zu gross.")
    if not werte or abs(werte[-1] - ende) > 1e-10:
        werte.append(round(ende, 10))
    return tuple(werte)


def sweep(*,
          gaeps: list[float] | tuple[float, ...],
          overlaps: list[float] | tuple[float, ...],
          winkel: list[float] | tuple[float, ...],
          rechner,
          modellgrenze: tuple[float, float] | None = None,
          min_reserve: float | None = None,
          ) -> list[SweepErgebnis]:
    """Rechnet jede Parameterkombination genau einmal.

    ``rechner(gap, overlap, winkel)`` muss ein Objekt mit ``cl``, ``cd`` und
    optional ``knappste_reserve`` sowie ``abgerissen``/``abgeriss`` liefern.
    Die Funktion bleibt damit unabhaengig von der konkreten UI und kann in
    Tests oder spaeter fuer CFD-/Messdatenadapter wiederverwendet werden.
    """
    ergebnisse: list[SweepErgebnis] = []
    for gap, overlap, winkel_relativ in product(gaeps, overlaps, winkel):
        b = rechner(float(gap), float(overlap), float(winkel_relativ))
        cl = float(b.cl)
        cd = float(b.cd)
        reserve = float(getattr(b, "knappste_reserve", getattr(b, "reserve", 0.0)))
        abgerissen = bool(getattr(b, "abgerissen", False))

        modellgueltig = True
        if modellgrenze is not None:
            unten, oben = modellgrenze
            modellgueltig = float(unten) <= cl <= float(oben)
        if min_reserve is not None:
            modellgueltig = modellgueltig and reserve >= float(min_reserve)

        ergebnisse.append(SweepErgebnis(
            gap=float(gap), overlap=float(overlap),
            winkel_relativ=float(winkel_relativ), cl=cl, cd=cd,
            reserve=reserve, abgerissen=abgerissen,
            modellgueltig=modellgueltig))
    return ergebnisse


def sortiere_nach_effizienz(ergebnisse: list[SweepErgebnis]) -> list[SweepErgebnis]:
    """Sortiert gueltige Punkte nach |CL|/CD, ungueltige ans Ende."""
    def schluessel(e: SweepErgebnis):
        if not e.gueltig or e.cd <= 0.0:
            return (1, 0.0)
        return (0, -(abs(e.cl) / e.cd))
    return sorted(ergebnisse, key=schluessel)
