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


def geschlossener_spline(punkte: np.ndarray) -> tuple[CubicSpline, np.ndarray]:
    """Der Spline, den Creo aus einer GESCHLOSSENEN IBL-Sektion baut.

    Unterschied zum offenen Fall: Statt der not-a-knot-Randbedingung wird die
    Kurve periodisch geschlossen. Sie ist damit an der Naht genauso glatt wie
    ueberall sonst - was der Grund ist, warum eine geschlossene Kurve an einer
    scharfen Hinterkante mehr Punkte braucht als zwei offene Haelften: Der
    Knick muss durch dichte Stuetzpunkte erzwungen werden, statt einfach die
    Grenze zwischen zwei Kurven zu sein.

    Erwartet den Umlauf OHNE doppelten Endpunkt; geschlossen wird hier.
    """
    p = np.asarray(punkte, dtype=float)
    if p.ndim != 2 or len(p) < 3:
        raise ValueError(f"Erwartet mindestens drei Punkte als Nx2- oder Nx3-Feld, "
                         f"bekommen {p.shape}.")
    if np.allclose(p[0], p[-1]):
        p = p[:-1]
    umlauf = np.vstack([p, p[:1]])
    d = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(umlauf, axis=0), axis=1))]
    if not np.all(np.diff(d) > 0):
        raise ValueError("Aufeinanderfolgende Punkte sind identisch - der Spline "
                         "waere nicht eindeutig.")
    return CubicSpline(d, umlauf, bc_type="periodic", axis=0), d


def abtasten(punkte: np.ndarray, n: int = 20001,
             geschlossen: bool = False) -> np.ndarray:
    """Tastet den Creo-Spline durch die Punkte fein ab."""
    cs, d = geschlossener_spline(punkte) if geschlossen else creo_spline(punkte)
    return cs(np.linspace(d[0], d[-1], n))


def bogenlaenge(punkte: np.ndarray, n: int = 200001) -> float:
    """Bogenlaenge des Creo-Splines. Zum Vergleich mit Creos Messwerkzeug."""
    s = abtasten(punkte, n)
    return float(np.sum(np.linalg.norm(np.diff(s, axis=0), axis=1)))


def abweichung_zur_kontur(stuetzpunkte: np.ndarray, referenz: np.ndarray,
                          n: int = 20001, geschlossen: bool = False) -> float:
    """Groesster Abstand zwischen der wahren Kontur und dem Creo-Spline.

    referenz ist die feinaufgeloeste Sollkontur, stuetzpunkte die Auswahl, die
    in die IBL geschrieben wuerde.

    Gemessen wird Punkt-zu-STRECKE, nicht Punkt-zu-Punkt. Der Unterschied ist
    entscheidend: Bei Punkt-zu-Punkt kann der gemessene Abstand nie kleiner
    werden als der halbe Abstand zweier Abtastpunkte. Dieser Boden lag bei
    400 mm Sehne genau in der Groessenordnung der Toleranz und liess die
    Punktzahlsuche scheitern, obwohl der Spline laengst genau genug war.
    """
    s = abtasten(stuetzpunkte, n, geschlossen=geschlossen)
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


def entdoppeln(punkte: np.ndarray,
               mindestabstand: float = CREO_GENAUIGKEIT_MM,
               geschlossen: bool = False) -> np.ndarray:
    """Entfernt Punkte, die naeher beieinander liegen als Creo aufloesen kann.

    Warum das noetig ist: Die Kosinusverteilung draengt die Punkte an Nase und
    Hinterkante zusammen. Bei hohen Punktzahlen - und die geschlossene Kurve
    braucht hohe Punktzahlen - unterschreitet der Abstand dort die absolute
    Modellgenauigkeit der Creo-Vorlage von 0,01 mm. Creo haelt zwei solche
    Punkte fuer denselben Punkt; der Spline wird entweder abgelehnt oder er
    entartet an genau der Stelle, auf die es ankommt.

    Gemessen fuer das FX 63-137 bei 250 mm Sehne: kleinster Punktabstand
    0,0070 mm - also deutlich darunter.

    Der erste Punkt bleibt immer stehen, und bei `geschlossen` wird auch der
    Abstand vom letzten zurueck zum ersten geprueft. Was hier wegfaellt, kann
    die Kurve nicht veraendern: Es liegt naeher am Nachbarn als Creo
    ueberhaupt unterscheiden kann.
    """
    p = np.asarray(punkte, dtype=float)
    if len(p) < 3:
        return p

    behalten = [0]
    for i in range(1, len(p)):
        if np.linalg.norm(p[i] - p[behalten[-1]]) >= mindestabstand:
            behalten.append(i)

    if geschlossen:
        # Der Rueckweg zum ersten Punkt zaehlt mit - sonst entsteht genau dort
        # das Nullsegment, das vermieden werden soll.
        while (len(behalten) > 3
               and np.linalg.norm(p[behalten[-1]] - p[0]) < mindestabstand):
            behalten.pop()
    elif behalten[-1] != len(p) - 1:
        # Bei einer offenen Kurve darf der Endpunkt nicht verlorengehen - er
        # ist die Nahtstelle zur Nachbarkurve.
        behalten[-1] = len(p) - 1

    return p[behalten]


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


def punktzahl_fuer_umlauf(umlauf_fn, toleranz_mm: float = CREO_GENAUIGKEIT_MM / 2,
                          n_min: int = 20, n_max: int = 400,
                          schritt: int = 4) -> int | None:
    """Dasselbe fuer den geschlossenen Umlauf.

    `umlauf_fn(n)` liefert den vollstaendigen Profilumlauf mit n Punkten je
    Seite. Gemessen wird gegen einen sehr fein aufgeloesten Umlauf.

    Die Schrittweite ist groesser als bei der offenen Suche, weil jeder
    Versuch den doppelten Umfang abtastet. Der Startwert liegt hoeher, weil
    eine geschlossene Kurve unter etwa zwanzig Punkten je Seite an der
    Hinterkante ohnehin ausbeult.
    """
    referenz = umlauf_fn(2001)
    for n in range(n_min, n_max + 1, schritt):
        if abweichung_zur_kontur(umlauf_fn(n), referenz,
                                 geschlossen=True) < toleranz_mm:
            return n
    return None
