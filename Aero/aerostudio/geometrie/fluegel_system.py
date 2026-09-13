"""Allgemeines Datenmodell fuer segmentierte Fluegelsysteme.

Die bisherige Kaskadenrechnung ist zweidimensional: Ein Querschnitt besteht aus
mehreren Profilen hintereinander. Ein realer Formula-Student-Fluegel ist dagegen
3D und muss nicht ueber die komplette Fahrzeugbreite durchlaufen.

Dieses Modul trennt deshalb die beiden Ebenen:

* ``FluegelElement`` beschreibt ein Profilsegment mit Spannweitenbereich.
* ``FluegelSystem`` verwaltet bis zu sechs Elemente und ihre Gruppen.
* Eine Gruppe ist ein lokaler 2D-Kaskadenquerschnitt, z. B. Frontfluegel links,
  Frontfluegel rechts, Bullwing oder Heckfluegel.

Die eigentliche 3D-Traglinien-/CFD-Kopplung bleibt bewusst spaeteren Modulen
vorbehalten. Das Modell erzeugt deshalb noch keine erfundenen 3D-Kraefte.
"""

from __future__ import annotations

from dataclasses import dataclass, field


MAX_ELEMENTE = 6


@dataclass(frozen=True)
class Spannweitenbereich:
    """Spannweitenintervall in mm, bezogen auf die Fahrzeugmitte."""

    y_von: float
    y_bis: float

    def __post_init__(self) -> None:
        if self.y_bis <= self.y_von:
            raise ValueError("y_bis muss groesser als y_von sein.")

    @property
    def mitte(self) -> float:
        return 0.5 * (self.y_von + self.y_bis)

    @property
    def breite(self) -> float:
        return self.y_bis - self.y_von

    def enthaelt(self, y: float) -> bool:
        return self.y_von <= y <= self.y_bis


@dataclass(frozen=True)
class FluegelElement:
    """Ein reales Profil-/Fluegelelement innerhalb eines Spannweitenbandes."""

    name: str
    gruppe: str
    profil: str
    sehne_mm: float
    winkel_grad: float
    spannweite: Spannweitenbereich
    x_mm: float = 0.0
    z_mm: float = 0.0
    vorheriger_elementname: str | None = None

    def __post_init__(self) -> None:
        if self.sehne_mm <= 0:
            raise ValueError("Die Sehne muss positiv sein.")
        if not self.name.strip():
            raise ValueError("Ein Fluegelelement braucht einen Namen.")
        if not self.gruppe.strip():
            raise ValueError("Ein Fluegelelement braucht eine Gruppe.")


@dataclass
class FluegelSystem:
    """Verwaltet eine segmentierte 3D-Fluegelarchitektur.

    Sechs Elemente sind absichtlich das UI-Limit des aktuellen Editors. Das
    Datenmodell kennt keine aerodynamische Sonderbehandlung fuer Front-/Heck-
    fluegel; damit koennen spaeter dieselben Bausteine fuer alle Baugruppen
    verwendet werden.
    """

    elemente: list[FluegelElement] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.validiere()

    def validiere(self) -> None:
        if len(self.elemente) > MAX_ELEMENTE:
            raise ValueError(f"Maximal {MAX_ELEMENTE} Fluegelelemente erlaubt.")

        namen = [e.name for e in self.elemente]
        if len(set(namen)) != len(namen):
            raise ValueError("Fluegelelementnamen muessen eindeutig sein.")

    def gruppen(self) -> list[str]:
        return list(dict.fromkeys(e.gruppe for e in self.elemente))

    def elemente_der_gruppe(self, gruppe: str) -> list[FluegelElement]:
        return [e for e in self.elemente if e.gruppe == gruppe]

    def elemente_bei_y(self, y: float) -> list[FluegelElement]:
        return [e for e in self.elemente if e.spannweite.enthaelt(y)]

    def huelle(self) -> dict[str, float]:
        if not self.elemente:
            return {"y_min": 0.0, "y_max": 0.0, "breite": 0.0}
        y_min = min(e.spannweite.y_von for e in self.elemente)
        y_max = max(e.spannweite.y_bis for e in self.elemente)
        return {"y_min": y_min, "y_max": y_max, "breite": y_max - y_min}
