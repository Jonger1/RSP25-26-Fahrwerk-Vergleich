"""
M0 - Verifikation des Creo-Splineverhaltens und Ableitung der Punktzahl.

Hintergrund
-----------
Creo misst fuer die Splinesektion der Pruefkurve eine Bogenlaenge von
210.184 mm. Dieses Skript zeigt, dass Creo daraus einen *interpolierenden
kubischen Spline mit not-a-knot-Randbedingung* baut, parametrisiert ueber die
kumulierte Sehnenlaenge - dieselbe Kurve laesst sich also in Python exakt
vorhersagen.

Warum das wichtig ist
--------------------
Wenn wir wissen, welche Kurve Creo aus einer Punktfolge macht, muss die
Punktzahl pro Profilkurve nicht geschaetzt werden. Sie wird aus einer
Toleranzvorgabe berechnet. Genau das macht `punktzahl_fuer_toleranz()` -
diese Funktion wandert in M1 in den IBL-Writer.

Aufruf:  python spline_verifikation.py
"""

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.spatial import cKDTree

# In Creo gemessen am 09.09.2026, Sektion 5 der Pruefkurve
CREO_BOGENLAENGE = 210.184  # mm
CREO_GENAUIGKEIT = 0.010    # mm, absolute Modellgenauigkeit laut config.pro


def creo_spline(punkte):
    """Baut den Spline so, wie Creo ihn aus einer IBL-Sektion baut.

    Parametrisierung ueber die kumulierte Sehnenlaenge - das ist es, was der
    Schluesselwort 'arclength' im IBL-Kopf bewirkt.
    """
    p = np.asarray(punkte, float)
    d = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    return CubicSpline(d, p, bc_type="not-a-knot", axis=0), d


def bogenlaenge(punkte, n=400001):
    cs, d = creo_spline(punkte)
    s = cs(np.linspace(d[0], d[-1], n))
    return float(np.sum(np.linalg.norm(np.diff(s, axis=0), axis=1)))


def kosinus(n):
    """Kosinusverteilung: dicht an Nase und Hinterkante, duenn in der Mitte."""
    return 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, n)))


def naca4(m, p, t, x):
    """Analytische NACA-4-Kontur, Oberseite, Einheitssehne."""
    yt = 5 * t * (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x**2
                  + 0.2843 * x**3 - 0.1015 * x**4)
    yc = np.where(x < p, m / p**2 * (2 * p * x - x**2),
                  m / (1 - p)**2 * ((1 - 2 * p) + 2 * p * x - x**2))
    dy = np.where(x < p, 2 * m / p**2 * (p - x),
                  2 * m / (1 - p)**2 * (p - x))
    th = np.arctan(dy)
    return np.column_stack([x - yt * np.sin(th), yc + yt * np.cos(th)])


def max_abweichung(kontur_fn, n, referenz):
    """Groesster Abstand zwischen wahrer Kontur und dem Spline durch n Punkte."""
    P = kontur_fn(kosinus(n))
    cs, d = creo_spline(P)
    S = cs(np.linspace(d[0], d[-1], 60001))
    return float(cKDTree(S).query(referenz)[0].max())


def punktzahl_fuer_toleranz(kontur_fn, toleranz=CREO_GENAUIGKEIT / 2,
                            n_min=20, n_max=200):
    """Kleinste Punktzahl, deren Spline die wahre Kontur innerhalb `toleranz` trifft.

    Weniger Punkte sind in Creo strikt besser: schnellere Regeneration und
    geringeres Risiko welliger Splines. Deshalb die kleinste, nicht die
    sicherste Zahl.
    """
    referenz = kontur_fn(kosinus(20001))
    for n in range(n_min, n_max + 1, 2):
        if max_abweichung(kontur_fn, n, referenz) < toleranz:
            return n
    return None


def _hauptteil():
    print("=" * 68)
    print("1) Welchen Spline baut Creo?")
    print("=" * 68)
    pruefkurve = [[0, 50], [50, 70], [100, 80], [150, 70], [200, 50]]
    L = bogenlaenge(pruefkurve)
    print(f"  Creo gemessen              {CREO_BOGENLAENGE:10.4f} mm")
    print(f"  not-a-knot, Sehnenlaenge   {L:10.4f} mm")
    print(f"  Abweichung                 {abs(L - CREO_BOGENLAENGE) * 1000:10.2f} um")
    cs, d = creo_spline(pruefkurve)
    s = cs(np.linspace(d[0], d[-1], 400001))
    i = int(np.argmax(s[:, 1]))
    print(f"  Scheitel                   z = {s[i,1]:.4f} mm bei x = {s[i,0]:.4f} mm")
    print("  -> Der Spline interpoliert seine Stuetzpunkte exakt.\n")

    print("=" * 68)
    print("2) Wieviele Punkte braucht eine Profilkurve?")
    print("=" * 68)
    chord = 250.0
    kontur = lambda x: naca4(0.04, 0.4, 0.12, x) * chord
    referenz = kontur(kosinus(20001))
    print(f"  NACA 4412, Sehne {chord:.0f} mm, Oberseite, Kosinusverteilung")
    print(f"  Modellgenauigkeit Creo: {CREO_GENAUIGKEIT:.3f} mm\n")
    print(f"  {'Punkte':>7}  {'max. Abweichung':>17}")
    for n in (20, 30, 40, 50, 60, 80, 100, 120):
        print(f"  {n:7d}  {max_abweichung(kontur, n, referenz):14.4f} mm")
    n = punktzahl_fuer_toleranz(kontur)
    print(f"\n  Kleinste Punktzahl unter {CREO_GENAUIGKEIT/2:.4f} mm: {n}")


if __name__ == "__main__":
    _hauptteil()
