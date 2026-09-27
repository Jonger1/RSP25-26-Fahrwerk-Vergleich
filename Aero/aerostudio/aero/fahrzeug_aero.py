"""Quasi-3D-Integrationsschicht fuer mehrere Aero-Baugruppen.

Die lokalen Kaskaden-/2D-Modelle liefern Beiwerte; dieses Modul integriert
sie ueber reale Spannweitenbereiche in Kraefte und Momente. Es behauptet noch
keine gegenseitige 3D-Induktion zwischen Frontfluegel, Bullwing, Sidepod und
Heckfluegel. Diese Kopplung kommt spaeter in die zentrale Traglinienrechnung.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AeroLast:
    """Lasten einer einzelnen lokal gerechneten Baugruppe."""

    name: str
    gruppe: str
    cl: float
    cd: float
    flaeche_m2: float
    geschwindigkeit_ms: float
    x_mm: float = 0.0
    z_mm: float = 0.0

    @property
    def q_pa(self) -> float:
        # Standardluftdichte bewusst lokal gehalten, solange keine
        # Fahrzeug-/Umgebungsdatenquelle angeschlossen ist.
        rho = 1.225
        return 0.5 * rho * self.geschwindigkeit_ms**2

    @property
    def abtrieb_n(self) -> float:
        return -self.cl * self.q_pa * self.flaeche_m2

    @property
    def widerstand_n(self) -> float:
        return self.cd * self.q_pa * self.flaeche_m2


@dataclass
class FahrzeugAeroErgebnis:
    lasten: list[AeroLast] = field(default_factory=list)

    @property
    def abtrieb_n(self) -> float:
        return sum(l.abtrieb_n for l in self.lasten)

    @property
    def widerstand_n(self) -> float:
        return sum(l.widerstand_n for l in self.lasten)

    @property
    def x_moment_nm(self) -> float:
        # Moment um y: M_y = -F_z * x; fuer Abtrieb ist F_z < 0.
        return sum(-l.abtrieb_n * (l.x_mm / 1000.0) for l in self.lasten)

    @property
    def aero_balance_front(self) -> float:
        front = sum(l.abtrieb_n for l in self.lasten if l.x_mm < 0.0)
        total = self.abtrieb_n
        return front / total if abs(total) > 1e-9 else 0.0


def last_aus_beiwert(name: str, gruppe: str, cl: float, cd: float,
                     flaeche_m2: float, geschwindigkeit_ms: float,
                     x_mm: float = 0.0, z_mm: float = 0.0) -> AeroLast:
    """Erzeugt eine Last aus lokalen 2D-/Kaskadenbeiwerten."""
    if flaeche_m2 <= 0.0:
        raise ValueError("flaeche_m2 muss positiv sein.")
    if geschwindigkeit_ms <= 0.0:
        raise ValueError("geschwindigkeit_ms muss positiv sein.")
    return AeroLast(name, gruppe, cl, cd, flaeche_m2,
                    geschwindigkeit_ms, x_mm, z_mm)
