"""
Skelett für Creo — Achsen statt Flächen.

Die Idee: Nicht die fertigen Flügel nach Creo bringen, sondern die LINIEN, um
die sie sich drehen. Jedes Element bekommt eine Achse auf seiner Viertelsehne,
quer zur Fahrtrichtung. In Creo hängt der Flügel dann an dieser Achse, und
der Anstellwinkel wird zu einem Maß, das sich ändern lässt, ohne dass
irgendetwas neu importiert werden muss.

Warum die Viertelsehne: Dort liegt bei einem Profil bei niedriger
Geschwindigkeit näherungsweise der Neutralpunkt — das Moment ändert sich beim
Verstellen des Anstellwinkels am wenigsten. Wer die Achse an die Nase legt,
bekommt beim Verstellen ein springendes Moment und eine wandernde Hinterkante.

Was die Datei enthält:

* **Je Element eine Drehachse**, als Strecke von der Wurzel bis zur Spitze.
  Zwei Punkte ergeben in Creo eine Gerade, keinen Spline.
* **Die Querlinie** — die Bezugslinie quer zum Fahrzeug, auf der alle Achsen
  ihren Anfang haben. Sie ist fest und dient als gemeinsamer Bezug, damit die
  Elemente zueinander nicht verrutschen.
* **Die Bezugslinien des Reglements**: Bodenebene, Vorderachse,
  Reifenvorderkante und die Höhengrenzen aus T 8.2.1. Damit steht das
  Reglement im CAD und nicht nur im Kopf des Aerodynamikers.

Alles in einer Datei, jede Linie eine eigene Sektion. In Creo entsteht daraus
ein einziges Kurvenfeature mit mehreren geraden Kurven darin.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .ibl import write_ibl


@dataclass
class Achse:
    """Eine Drehachse für ein Element."""

    name: str
    x: float                    # Längslage der Viertelsehne, mm
    z: float                    # Höhe über Boden, mm
    y_von: float                # Anfang der Achse, mm ab Fahrzeugmitte
    y_bis: float
    winkel: float = 0.0         # nur informativ, für den Kommentarkopf
    sehne: float = 0.0

    def punkte(self) -> np.ndarray:
        return np.array([[self.x, self.y_von, self.z],
                         [self.x, self.y_bis, self.z]], dtype=float)


@dataclass
class Skelettplan:
    """Was geschrieben würde."""

    achsen: list[Achse] = field(default_factory=list)
    bezugslinien: list[tuple[str, np.ndarray]] = field(default_factory=list)

    @property
    def sektionen(self) -> list[np.ndarray]:
        return ([a.punkte() for a in self.achsen]
                + [p for _, p in self.bezugslinien])

    @property
    def beschriftung(self) -> list[str]:
        zeilen = ["Aero Studio - Skelett", "",
                  "Reihenfolge der Sektionen in dieser Datei:"]
        for i, a in enumerate(self.achsen, start=1):
            zeilen.append(f"  {i:2d}  Drehachse {a.name}: x {a.x:.1f}, "
                          f"z {a.z:.1f}, Sehne {a.sehne:.1f} mm, "
                          f"Winkel {a.winkel:+.1f} Grad")
        for i, (name, _) in enumerate(self.bezugslinien,
                                      start=len(self.achsen) + 1):
            zeilen.append(f"  {i:2d}  {name}")
        return zeilen


def viertelsehne(profil, sehne: float, winkel: float,
                 nase_x: float, nase_z: float) -> tuple[float, float]:
    """Lage der Viertelsehne aus Nasenposition, Sehne und Winkel.

    Gerechnet aus der fertigen Geometrie und nicht über cos/sin von Hand: So
    bleibt es konsistent mit dem, was der Export schreibt, auch wenn sich die
    Drehkonvention einmal ändert.
    """
    punkte = profil.repanelisiert(60).angestellt(winkel, sehne)
    hinten = punkte[0]
    nase = punkte[int(np.argmax(np.linalg.norm(punkte - hinten, axis=1)))]
    viertel = nase + 0.25 * (hinten - nase)
    return (float(viertel[0] - nase[0] + nase_x),
            float(viertel[1] - nase[1] + nase_z))


def plane_skelett(achsen: list[Achse], bezug=None,
                  mit_regelgrenzen: bool = True,
                  querlinie_y: tuple[float, float] | None = None) -> Skelettplan:
    """Baut den Skelettplan.

    `querlinie_y` legt fest, wie weit die Querlinie reicht. Ohne Angabe deckt
    sie die weiteste Achse ab.
    """
    plan = Skelettplan(achsen=list(achsen))

    if achsen:
        von = querlinie_y[0] if querlinie_y else min(a.y_von for a in achsen)
        bis = querlinie_y[1] if querlinie_y else max(a.y_bis for a in achsen)
        # Die Querlinie liegt auf der Hoehe der ERSTEN Achse und an deren
        # Laengslage. Sie ist der gemeinsame Bezug, an dem die uebrigen
        # Elemente ausgerichtet werden - deshalb fest und nicht gemittelt.
        fuehrend = achsen[0]
        plan.bezugslinien.append((
            f"Querlinie (fester Bezug, auf Hoehe von {fuehrend.name})",
            np.array([[fuehrend.x, von, fuehrend.z],
                      [fuehrend.x, bis, fuehrend.z]])))

    if not mit_regelgrenzen or bezug is None:
        return plan

    breite = max((a.y_bis for a in achsen), default=700.0)
    x_vorn = min((a.x for a in achsen), default=-600.0) - 100.0
    x_hint = max((a.x for a in achsen), default=-300.0) + 100.0

    plan.bezugslinien += [
        ("Bodenebene z = 0",
         np.array([[x_vorn, 0.0, 0.0], [x_hint, 0.0, 0.0]])),
        ("Vorderachse x = 0",
         np.array([[0.0, -breite, 0.0], [0.0, breite, 0.0]])),
        (f"Vorderkante Vorderreifen x = {bezug.vorderreifen_vorderkante_x:.1f}",
         np.array([[bezug.vorderreifen_vorderkante_x, -breite, 0.0],
                   [bezug.vorderreifen_vorderkante_x, breite, 0.0]])),
        (f"T 8.2.1 Hoehengrenze 2027: {350.0:.0f} mm vor der Reifenvorderkante",
         np.array([[x_vorn, breite, 350.0],
                   [bezug.vorderreifen_vorderkante_x, breite, 350.0]])),
        (f"T 8.2.2 Breitengrenze |y| = {bezug.rad_aussen_vorne:.1f}",
         np.array([[x_vorn, bezug.rad_aussen_vorne, 0.0],
                   [x_hint, bezug.rad_aussen_vorne, 0.0]])),
        ("T 2.2.1 Bodenfreiheit 30 mm",
         np.array([[x_vorn, 0.0, 30.0], [x_hint, 0.0, 30.0]])),
    ]
    return plan


def schreibe(plan: Skelettplan, ziel: str | Path) -> Path:
    """Schreibt das Skelett als IBL.

    Immer OFFEN - eine Achse ist eine Gerade, kein Umlauf. Der geschlossene
    Kopf wuerde Creo veranlassen, die beiden Endpunkte zu verbinden, und aus
    jeder Achse eine entartete Schleife machen.
    """
    return write_ibl(ziel, plan.sektionen, kommentare=plan.beschriftung,
                     geschlossen=False)


def aus_element(element, profil, name: str = "") -> Achse:
    """Macht aus einem Spec-Element die passende Drehachse."""
    x, z = viertelsehne(profil, element.sehne, element.anstellwinkel,
                        element.pos_x, element.pos_z)
    weite = (max(s.y for s in element.spannweite.stuetzstellen)
             if element.spannweite is not None else 600.0)
    return Achse(name=name or element.anzeigename, x=x, z=z,
                 y_von=element.pos_y, y_bis=element.pos_y + weite,
                 winkel=element.anstellwinkel, sehne=element.sehne)
