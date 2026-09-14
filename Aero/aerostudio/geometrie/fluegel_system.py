"""Allgemeines Datenmodell fuer segmentierte Fluegelsysteme.

Die Kaskadenrechnung bleibt lokal zweidimensional. Dieses Modul beschreibt die
3D-Architektur davor: Elemente duerfen getrennte Spannweitenbereiche haben und
werden einer wiederverwendbaren Aero-Baugruppe zugeordnet.
"""

from __future__ import annotations

from dataclasses import dataclass, field


MAX_ELEMENTE = 6
BAUGRUPPEN = (
    "Frontfluegel",
    "Seitenkasten",
    "Bullwing",
    "Heckfluegel",
    "Beamwing",
    "Sonstige",
)


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
    baugruppe: str = "Frontfluegel"
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
        if self.baugruppe not in BAUGRUPPEN:
            raise ValueError(f"Unbekannte Baugruppe: {self.baugruppe}")


@dataclass
class FluegelSystem:
    """Verwaltet eine segmentierte Aero-Architektur mit bis zu sechs Elementen."""

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

    def baugruppen(self) -> list[str]:
        return list(dict.fromkeys(e.baugruppe for e in self.elemente))

    def elemente_der_gruppe(self, gruppe: str) -> list[FluegelElement]:
        return [e for e in self.elemente if e.gruppe == gruppe]

    def elemente_der_baugruppe(self, baugruppe: str) -> list[FluegelElement]:
        return [e for e in self.elemente if e.baugruppe == baugruppe]

    def elemente_bei_y(self, y: float) -> list[FluegelElement]:
        return [e for e in self.elemente if e.spannweite.enthaelt(y)]

    def huelle(self) -> dict[str, float]:
        if not self.elemente:
            return {"y_min": 0.0, "y_max": 0.0, "breite": 0.0}
        y_min = min(e.spannweite.y_von for e in self.elemente)
        y_max = max(e.spannweite.y_bis for e in self.elemente)
        return {"y_min": y_min, "y_max": y_max, "breite": y_max - y_min}
