"""
Nachbildung des Splines, den Creo aus einer IBL-Sektion baut.

In M0 wurde durch Messung geklaert, welche Kurve Creo erzeugt: einen
interpolierenden kubischen Spline mit not-a-knot-Randbedingung, parametrisiert
ueber die kumulierte Sehnenlaenge. Nachgewiesen an der Splinesektion der
Pruefkurve - Creo mass 210.184 mm, diese Nachbildung liefert 210.1857 mm,
also 1.7 Mikrometer Abweichung auf 210 mm.

Das ist mehr als eine Randnotiz. Weil sich die Kurve vorhersagen laesst, muss
die Punktzahl pro Profilkurve nicht geschaetzt werden - sie folgt aus einer
Toleranzvorgabe. Weniger Punkte sind in Creo strikt besser: schnellere
Regeneration, geringeres Risiko welliger Splines.
"""

from __future__ import annotations

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.spatial import cKDTree

# Absolute Modellgenauigkeit der Creo-Vorlage laut config.pro.
CREO_GENAUIGKEIT_MM = 0.010


def creo_spline(punkte: np.ndarray) -> tuple[CubicSpline, np.ndarray]:
    """Baut den Spline so, wie Creo ihn aus einer IBL-Sektion baut.

    Gibt den Spline und die Parameterwerte der Stuetzpunkte zurueck.
    """
    p = np.asarray(punkte, dtype=float)
    if p.ndim != 2 or len(p) < 2:
        raise ValueError(f"Erwartet mindestens zwei Punkte als Nx2- oder Nx3-Feld, "
                         f"bekommen {p.shape}.")
    d = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    if not np.all(np.diff(d) > 0):
        raise ValueError("Aufeinanderfolgende Punkte sind identisch - der Spline "
                         "waere nicht eindeutig.")
    return CubicSpline(d, p, bc_type="not-a-knot", axis=0), d


def abtasten(punkte: np.ndarray, n: int = 20001) -> np.ndarray:
    """Tastet den Creo-Spline durch die Punkte fein ab."""
    cs, d = creo_spline(punkte)
    return cs(np.linspace(d[0], d[-1], n))


def bogenlaenge(punkte: np.ndarray, n: int = 200001) -> float:
    """Bogenlaenge des Creo-Splines. Zum Vergleich mit Creos Messwerkzeug."""
    s = abtasten(punkte, n)
    return float(np.sum(np.linalg.norm(np.diff(s, axis=0), axis=1)))


def abweichung_zur_kontur(stuetzpunkte: np.ndarray, referenz: np.ndarray,
                          n: int = 20001) -> float:
    """Groesster Abstand zwischen der wahren Kontur und dem Creo-Spline.

    referenz ist die feinaufgeloeste Sollkontur, stuetzpunkte die Auswahl, die
    in die IBL geschrieben wuerde.

    Gemessen wird Punkt-zu-STRECKE, nicht Punkt-zu-Punkt. Der Unterschied ist
    entscheidend: Bei Punkt-zu-Punkt kann der gemessene Abstand nie kleiner
    werden als der halbe Abstand zweier Abtastpunkte. Dieser Boden lag bei
    400 mm Sehne genau in der Groessenordnung der Toleranz und liess die
    Punktzahlsuche scheitern, obwohl der Spline laengst genau genug war.
    """
    s = abtasten(stuetzpunkte, n)
    r = np.asarray(referenz, dtype=float)

    # naechster Abtastpunkt, dann die beiden angrenzenden Strecken pruefen
    _, idx = cKDTree(s).query(r)
    bester = np.full(len(r), np.inf)
    for versatz in (-1, 0):
        i = np.clip(idx + versatz, 0, len(s) - 2)
        a, b = s[i], s[i + 1]
        ab = b - a
        laenge2 = np.sum(ab * ab, axis=1)
        laenge2 = np.where(laenge2 > 0, laenge2, 1.0)
        t = np.clip(np.sum((r - a) * ab, axis=1) / laenge2, 0.0, 1.0)
        fuss = a + t[:, None] * ab
        bester = np.minimum(bester, np.linalg.norm(r - fuss, axis=1))
    return float(bester.max())


def punktzahl_fuer_toleranz(kontur_fn, toleranz_mm: float = CREO_GENAUIGKEIT_MM / 2,
                            n_min: int = 12, n_max: int = 400,
                            schritt: int = 2) -> int | None:
    """Kleinste Punktzahl, deren Creo-Spline die Kontur innerhalb `toleranz_mm` trifft.

    `kontur_fn(n)` muss n Punkte auf der Sollkontur liefern, kosinusverteilt.
    Gibt None zurueck, wenn selbst n_max nicht reicht - das ist dann ein
    Hinweis auf eine Kontur mit einem Knick, nicht auf zu wenige Punkte.
    """
    referenz = kontur_fn(4001)
    for n in range(n_min, n_max + 1, schritt):
        if abweichung_zur_kontur(kontur_fn(n), referenz) < toleranz_mm:
            return n
    return None
