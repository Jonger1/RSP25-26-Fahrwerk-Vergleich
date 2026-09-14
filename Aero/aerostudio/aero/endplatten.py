"""Endplatten-Modell fuer die Fluegelrechnung.

Endplatten werden nicht als pauschaler, frei erfundener Abtriebsaufschlag
behandelt. Das Modul beschreibt zunaechst die Geometrie und stellt eine
kalibrierbare Umrechnung auf eine aequivalente Spannweite bereit.

Wichtig: ``effizienz`` ist standardmaessig 0.0. Erst eigene CFD-/Messdaten
sollten einen positiven Kalibrierwert setzen. So wird eine Endplatte nicht
versehentlich als validierte Physik verkauft.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Endplatte:
    """Parameter einer Endplatte.

    ``hoehe`` und ``laenge`` in mm. ``effizienz`` beschreibt, welcher Anteil
    der geometrisch moeglichen Spannweitenwirkung in einer spaeteren
    Kalibrierung angesetzt werden darf; 0 bedeutet bewusst: neutral.
    """

    hoehe: float = 0.0
    laenge: float = 0.0
    dicke: float = 2.0
    spalt_boden: float | None = None
    wirkungsgrad: float = 0.0

    def __post_init__(self) -> None:
        if self.hoehe < 0 or self.laenge < 0 or self.dicke <= 0:
            raise ValueError("Endplattenabmessungen muessen positiv bzw. nichtnegativ sein.")
        if self.spalt_boden is not None and self.spalt_boden < 0:
            raise ValueError("Bodenspalt kann nicht negativ sein.")
        if not 0.0 <= self.wirkungsgrad <= 1.0:
            raise ValueError("Wirkungsgrad muss zwischen 0 und 1 liegen.")

    @property
    def aktiv(self) -> bool:
        return self.hoehe > 0.0 and self.laenge > 0.0

    def aequivalente_halbspannweite(self, halbspannweite: float) -> float:
        """Kalibrierte aequivalente Halbspannweite.

        Die Funktion ist absichtlich konservativ: Ohne Kalibrierung liefert
        sie exakt die reale Halbspannweite zurueck. Eine spaetere Kalibrierung
        kann dann ueber ``wirkungsgrad`` die Wirkung der Endplatte einblenden.
        ``hoehe`` allein wird nicht in eine Abtriebszahl umgedeutet.
        """
        if not self.aktiv or self.wirkungsgrad == 0.0:
            return float(halbspannweite)
        zusatz = self.wirkungsgrad * self.hoehe
        return float(halbspannweite + zusatz)

    def hinweis(self) -> str:
        if not self.aktiv:
            return "Keine Endplatte aktiviert; Rechnung bleibt unveraendert."
        if self.wirkungsgrad == 0.0:
            return ("Endplatte geometrisch definiert, aber aerodynamisch neutral. "
                    "Wirkungsgrad erst mit CFD oder Messdaten kalibrieren.")
        return (f"Kalibrierte aequivalente Halbspannweite: "
                f"+{self.wirkungsgrad * self.hoehe:.1f} mm.")
