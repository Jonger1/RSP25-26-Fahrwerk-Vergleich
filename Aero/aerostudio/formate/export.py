"""
Vom Element zur IBL-Datei.

Bewusst als eigenes Modul und nicht im Dash-Callback: Dieselbe Strecke wird
spaeter von der Kommandozeile, vom DoE-Lauf und vom Reportgenerator gebraucht.
Was nur im Callback stuende, koennte keiner von ihnen benutzen - und liesse
sich auch nicht testen, weil Dash ausserhalb einer echten Anfrage keinen
Kontext hat.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..geometrie.profil import Profil
from .ibl import write_ibl


@dataclass
class Exportplan:
    """Was geschrieben wuerde, bevor es geschrieben wird.

    Erlaubt der Oberflaeche, Punktzahl und Vorschau zu zeigen, ohne dass eine
    Datei entsteht - und dem Anwender, das Ergebnis zu pruefen, bevor er es
    ins CAD laesst.
    """

    sektionen: list[np.ndarray]
    punktzahl: int
    toleranz_mm: float           # tatsaechlich erreichte Toleranz
    toleranz_gefordert: float    # was verlangt war

    @property
    def punkte_gesamt(self) -> int:
        return sum(len(s) for s in self.sektionen)

    @property
    def gelockert(self) -> bool:
        """Musste die Toleranz aufgeweicht werden, damit es ueberhaupt geht?"""
        return self.toleranz_mm > self.toleranz_gefordert * 1.001


def plane_element(profil: Profil, sehne_mm: float, anstellwinkel: float,
                  toleranz_mm: float = 0.005) -> Exportplan:
    """Bereitet die Sektionen fuer ein Fluegelelement vor.

    Ober- und Unterseite werden GETRENNT exportiert, mit einem Knick an Nase
    und Hinterkante. Ein durchgehender Spline ueber die Nase erzeugt in Creo
    fast immer eine Beule, weil die Kruemmung dort springt.

    Die Punktzahl wird gerechnet, nicht geschaetzt - auf Basis des in M0
    vermessenen Creo-Splines.
    """
    # Reicht die geforderte Toleranz nicht, wird sie schrittweise gelockert
    # statt den Export scheitern zu lassen. Eine etwas groebere Kurve ist immer
    # noch besser als gar keine - und der Plan sagt hinterher, womit gerechnet
    # wurde, sodass niemand eine Genauigkeit annimmt, die es nicht gab.
    gefordert = float(toleranz_mm)
    # Kurze Leiter statt fortgesetztem Verdoppeln: Bei einer sehr kleinen
    # Vorgabe braeuchte das Verdoppeln zwei Dutzend Anlaeufe, und jeder davon
    # sucht die Punktzahl von Neuem. Sieben Stufen decken denselben Bereich ab.
    leiter = [gefordert, gefordert * 2, gefordert * 5,
              0.005, 0.010, 0.020, 0.050]
    leiter = sorted({round(t, 6) for t in leiter if t >= gefordert})

    n, versuch = None, gefordert
    for versuch in leiter:
        n = profil.punktzahl(sehne_mm, versuch)
        if n is not None:
            break

    if n is None:
        raise ValueError(
            f"Selbst mit {versuch:.4f} mm Toleranz laesst sich die Kontur nicht "
            f"treffen. Das deutet auf einen Knick im Profil hin, nicht auf zu "
            f"wenige Punkte - bitte die Quelldatei pruefen.")

    punkte = profil.repanelisiert(n).angestellt(anstellwinkel, sehne_mm)
    nase = len(punkte) // 2
    oben, unten = punkte[:nase + 1], punkte[nase:]

    return Exportplan(sektionen=[_in_spannweitenebene(oben),
                                 _in_spannweitenebene(unten)],
                      punktzahl=n, toleranz_mm=versuch,
                      toleranz_gefordert=gefordert)


def schreibe(plan: Exportplan, ziel: str | Path,
             kommentare: list[str] | None = None) -> Path:
    """Schreibt den Plan als IBL-Datei."""
    return write_ibl(ziel, plan.sektionen, kommentare=kommentare)


def vorschau(plan: Exportplan, zeilen: int = 40) -> str:
    """Erzeugt den Dateitext, ohne eine Datei anzulegen."""
    import tempfile

    with tempfile.TemporaryDirectory() as ordner:
        pfad = write_ibl(Path(ordner) / "vorschau.ibl", plan.sektionen)
        text = pfad.read_text(encoding="ascii").splitlines()
    if len(text) > zeilen:
        text = text[:zeilen] + [f"... ({len(text) - zeilen} weitere Zeilen)"]
    return "\n".join(text)


def _in_spannweitenebene(punkte: np.ndarray) -> np.ndarray:
    """Legt 2D-Profilpunkte in die Ebene y = 0 des Werkzeug-Koordinatensystems.

    Die Spannweitenverteilung kommt erst in M4 dazu; bis dahin liegt jedes
    Element in einer einzigen Schnittebene.
    """
    return np.column_stack([punkte[:, 0], np.zeros(len(punkte)), punkte[:, 1]])
