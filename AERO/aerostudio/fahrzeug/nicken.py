"""
Nickwinkel und Bodenabstandsaenderung beim Bremsen.

Der Nickwinkel steht in keinem Kinematikexport, ist aber fuer den Frontfluegel
die wichtigste Groesse ueberhaupt: Er bestimmt, wie weit der Fluegel beim
Bremsen an den Boden kommt. Das Reglement verlangt in T 8.2.4 die Einhaltung
aller Grenzen "with any suspension setup" - also auch in dieser Lage.

Gerechnet wird aus Groessen, die entweder gemessen sind oder in den
RSP-Exporten stehen:

  Laengslastverschiebung   dF = m * a * h_sp / Radstand
  Anteil, den die Feder sieht   (1 - AntiDive) * dF
  Einfederung              z = Federanteil / Radrate
  Nickwinkel               atan((z_vorne + z_hinten) / Radstand)

Anti-Dive ist der entscheidende Zwischenschritt: Der Anteil der
Lastverschiebung, den die Radaufhaengungsgeometrie ueber die Lenker abstuetzt,
erreicht die Feder gar nicht. Bei 59 % Anti-Dive vorne federt das Auto also
nur mit 41 % der Last ein. Wer das weglaesst, rechnet den Nickwinkel um mehr
als das Doppelte zu gross.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

G = 9.80665  # m/s2


@dataclass
class Fahrzeug:
    """Die Eingangsgroessen. Alle bewusst als Parameter, weil sie sich von
    Saison zu Saison aendern."""

    masse_leer: float = 220.0          # kg, ohne Fahrer
    masse_fahrer: float = 75.0         # kg
    schwerpunkthoehe: float = 0.310    # m ueber Boden
    radstand: float = 1.535            # m

    radrate_vorne: float = 64884.5     # N/m, aus Dynamic Wheelrate Spring Front
    radrate_hinten: float = 68827.5    # N/m
    antidive_vorne: float = 0.59012    # Anteil, aus Dynamic Anti Dive Front
    antilift_hinten: float = 0.55318   # Anteil, aus Dynamic Anti Dive Rear

    @property
    def masse(self) -> float:
        return self.masse_leer + self.masse_fahrer


@dataclass
class Nickzustand:
    verzoegerung_g: float
    lastverschiebung: float     # N, gesamt von hinten nach vorne
    einfederung_vorne: float    # mm, positiv = einfedern
    ausfederung_hinten: float   # mm, positiv = ausfedern
    nickwinkel: float           # Grad, positiv = Nase runter

    def __str__(self) -> str:
        return (f"{self.verzoegerung_g:.1f} g   "
                f"Lastverschiebung {self.lastverschiebung:7.1f} N   "
                f"vorne {self.einfederung_vorne:5.2f} mm ein, "
                f"hinten {self.ausfederung_hinten:5.2f} mm aus   "
                f"Nickwinkel {self.nickwinkel:.3f} Grad")


def nicken(fz: Fahrzeug, verzoegerung_g: float = 2.0) -> Nickzustand:
    """Rechnet den Nickzustand fuer eine gegebene Verzoegerung."""
    dF = fz.masse * verzoegerung_g * G * fz.schwerpunkthoehe / fz.radstand

    # Je Rad, und nur der Anteil, den die Feder ueberhaupt sieht.
    feder_vorne = (1.0 - fz.antidive_vorne) * dF / 2.0
    feder_hinten = (1.0 - fz.antilift_hinten) * dF / 2.0

    z_vorne = feder_vorne / fz.radrate_vorne      # m
    z_hinten = feder_hinten / fz.radrate_hinten   # m

    winkel = math.degrees(math.atan((z_vorne + z_hinten) / fz.radstand))

    return Nickzustand(verzoegerung_g, dF, z_vorne * 1000.0, z_hinten * 1000.0, winkel)


def bodenabstand_aenderung(zustand: Nickzustand, abstand_vor_vorderachse_mm: float) -> float:
    """Wie weit ein Punkt vor der Vorderachse beim Bremsen absinkt, in mm.

    Setzt sich aus zwei Anteilen zusammen: die Vorderachse federt selbst ein,
    und zusaetzlich kippt das Auto um sie herum nach vorne. Der zweite Anteil
    waechst linear mit dem Abstand - deshalb ist ein weit vorstehender
    Frontfluegel doppelt betroffen.

    ACHTUNG Einheiten: Abstand in MILLIMETERN hineingeben, Ergebnis in
    Millimetern. Das ganze Modul rechnet intern in Metern und Newton, nur
    diese Funktion arbeitet in Millimetern - weil Bodenabstaende im Reglement
    und in Creo in Millimetern stehen.
    """
    return zustand.einfederung_vorne + abstand_vor_vorderachse_mm * math.tan(
        math.radians(zustand.nickwinkel))


def _hauptteil() -> None:
    print("Nickwinkel beim Bremsen - RSP26/27\n")

    print("Eingang aus den Kinematikexporten:")
    fz = Fahrzeug()
    print(f"  Radrate vorne    {fz.radrate_vorne:9.1f} N/m")
    print(f"  Radrate hinten   {fz.radrate_hinten:9.1f} N/m")
    print(f"  Anti-Dive vorne  {fz.antidive_vorne*100:9.2f} %")
    print(f"  Anti-Lift hinten {fz.antilift_hinten*100:9.2f} %")
    print(f"\nEingang vom Team:")
    print(f"  Masse            {fz.masse_leer:.0f} kg leer + {fz.masse_fahrer:.0f} kg Fahrer")
    print(f"  Schwerpunkt      {fz.schwerpunkthoehe*1000:.0f} mm ueber Boden")
    print(f"  Radstand         {fz.radstand*1000:.0f} mm")

    print("\nNickzustand:")
    for a in (0.5, 1.0, 1.5, 2.0):
        print("  ", nicken(fz, a))

    print("\nStreuung durch das Fahrergewicht bei 2 g:")
    for mf in (70.0, 80.0):
        z = nicken(Fahrzeug(masse_fahrer=mf), 2.0)
        print(f"   Fahrer {mf:.0f} kg -> Nickwinkel {z.nickwinkel:.3f} Grad, "
              f"vorne {z.einfederung_vorne:.2f} mm ein")

    print("\nStreuung durch die Schwerpunkthoehe bei 2 g:")
    for h in (0.28, 0.31, 0.34):
        z = nicken(Fahrzeug(schwerpunkthoehe=h), 2.0)
        print(f"   Schwerpunkt {h*1000:.0f} mm -> Nickwinkel {z.nickwinkel:.3f} Grad")

    print("\nAbsinken eines Frontfluegelpunkts bei 2 g, je nach Abstand"
          " vor der Vorderachse:")
    z = nicken(Fahrzeug(), 2.0)
    for d_mm in (0.0, 300.0, 500.0, 700.0, 900.0):
        s = bodenabstand_aenderung(z, d_mm)
        print(f"   {d_mm:4.0f} mm vor der Achse -> {s:5.2f} mm tiefer"
              f"   (von 40 mm bleiben {40 - s:5.2f} mm)")


if __name__ == "__main__":
    _hauptteil()
