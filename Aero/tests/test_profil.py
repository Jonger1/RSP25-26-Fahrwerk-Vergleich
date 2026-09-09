"""Tests fuer den Profilkern.

Der Pruefstein ist durchgehend das analytische NACA-Profil: Seine Kennwerte
sind aus der Definition bekannt, deshalb faellt jede Abweichung sofort auf.
"""

import numpy as np
import pytest

from aerostudio.geometrie.profil import Profil
from aerostudio.geometrie.spline import abweichung_zur_kontur, bogenlaenge
from aerostudio.spec.modell import Fertigung, Verfahren


# ------------------------------------------------------------------ Kennwerte

def test_naca_dicke_und_lage():
    """NACA 4412: 12 % Dicke bei 30 % Sehne, per Definition."""
    p = Profil.aus_naca(0.04, 0.4, 0.12, n=401)
    assert p.max_dicke == pytest.approx(0.12, abs=0.001)
    assert p.max_dicke_bei == pytest.approx(0.30, abs=0.01)


def test_naca_woelbung():
    p = Profil.aus_naca(0.04, 0.4, 0.12, n=401)
    assert p.max_woelbung == pytest.approx(0.04, abs=0.003)


def test_symmetrisches_profil_hat_keine_woelbung():
    p = Profil.aus_naca(0.0, 0.4, 0.12, n=401)
    assert p.max_woelbung == pytest.approx(0.0, abs=1e-6)


def test_normierung_haelt_x_in_null_bis_eins():
    """Voraussetzung fuer CST - ausserhalb ist die Darstellung undefiniert."""
    for woelbung in (0.0, 0.04, 0.09):
        p = Profil.aus_naca(woelbung, 0.4, 0.12, n=401)
        assert p.punkte[:, 0].min() >= 0.0
        assert p.punkte[:, 0].max() <= 1.0


def test_seiten_sind_streng_steigend():
    """Sonst liefert np.interp stillschweigend Unsinn."""
    p = Profil.aus_naca(0.06, 0.4, 0.15, n=401)
    for seite in (p.oben(), p.unten()):
        assert np.all(np.diff(seite[:, 0]) > 0)


# ------------------------------------------------------------------- Umformung

def test_repanelisierung_erhaelt_die_form():
    p = Profil.aus_naca(0.04, 0.4, 0.12, n=601)
    grob = p.repanelisiert(40)
    assert grob.max_dicke == pytest.approx(p.max_dicke, abs=0.0005)
    assert abweichung_zur_kontur(grob.punkte, p.punkte) < 2e-4   # < 50 um bei 250 mm


def test_skalierung_ist_linear():
    p = Profil.aus_naca(0.04, 0.4, 0.12, n=201)
    assert np.allclose(p.skaliert(500.0), 2.0 * p.skaliert(250.0))


def test_anstellen_veraendert_die_form_nicht():
    """Drehen darf nur drehen - die Sehnenlaenge bleibt erhalten."""
    p = Profil.aus_naca(0.0, 0.4, 0.12, n=201)
    for winkel in (0.0, -6.0, 12.0):
        q = p.angestellt(winkel, sehne_mm=250.0)
        spanne = np.linalg.norm(q[0] - q[len(q) // 2])
        assert spanne == pytest.approx(250.0, rel=0.02)


# ------------------------------------------------------------------------ CST

def test_cst_rundlauf_konvergiert_mit_der_ordnung():
    p = Profil.aus_naca(0.04, 0.4, 0.12, n=601)
    fehler = []
    for ordnung in (5, 7, 9, 11):
        ob, un, dz = p.nach_cst(ordnung=ordnung)
        fehler.append(abweichung_zur_kontur(
            Profil.aus_cst(ob, un, dz, n=601).punkte, p.punkte))
    assert fehler == sorted(fehler, reverse=True), "hoehere Ordnung muss besser sein"
    assert fehler[-1] < 2e-4


def test_cst_erhaelt_die_hinterkantendicke():
    p = Profil.aus_naca(0.04, 0.4, 0.12, n=401)
    _, _, dz = p.nach_cst()
    assert dz == pytest.approx(p.hinterkante_dicke, rel=0.02)


# --------------------------------------------------------------- Creo-Spline

def test_creo_spline_trifft_den_gemessenen_wert():
    """Der M0-Nachweis: Creo mass 210.184 mm an genau dieser Punktfolge."""
    punkte = np.array([[0, 50], [50, 70], [100, 80], [150, 70], [200, 50]], float)
    assert bogenlaenge(punkte) == pytest.approx(210.184, abs=0.01)


def test_punktzahl_waechst_mit_der_sehne():
    p = Profil.aus_naca(0.04, 0.4, 0.12, n=401)
    n120 = p.punktzahl(120.0, 0.005)
    n400 = p.punktzahl(400.0, 0.005)
    assert n120 is not None and n400 is not None
    assert n400 > n120


# ------------------------------------------------------------ Fertigungsregeln

def test_duenne_hinterkante_faellt_durch():
    """T 2.4.1 verlangt 1 mm Radius, also mindestens 2 mm Dicke."""
    p = Profil.aus_naca(0.04, 0.4, 0.12, n=401)
    befunde = {b.pruefung: b for b in p.pruefe_fertigung(Fertigung(), 250.0)}
    assert not befunde["Hinterkantendicke"].ok
    assert befunde["Hinterkantendicke"].regel == "T 2.4.1"


def test_dieselbe_form_kann_an_der_sehne_scheitern():
    """Das Reglement nennt absolute Masse - gleiche Form, kleine Sehne, anderes Urteil."""
    p = Profil.aus_naca(0.04, 0.4, 0.20, n=401)
    f = Fertigung(verfahren=Verfahren.nasslaminat, wandstaerke=1.0)
    # Nasenradius des 20-%-Profils liegt bei rund 4.5 % der Sehne. Bei 400 mm
    # sind das 18 mm, bei 60 mm nur noch 2.7 mm - unter den 3 mm aus T 2.4.1.
    gross = {b.pruefung: b.ok for b in p.pruefe_fertigung(f, 400.0)}
    klein = {b.pruefung: b.ok for b in p.pruefe_fertigung(f, 60.0)}
    assert gross["Nasenradius"], "18 mm Nasenradius muessen durchgehen"
    assert not klein["Nasenradius"], "2.7 mm Nasenradius muessen durchfallen"


def test_mindestdicke_folgt_aus_dem_aufbau():
    assert Fertigung(wandstaerke=0.6, kern=2.0).dicke_min == pytest.approx(3.2)
    assert Fertigung(wandstaerke=1.5).dicke_min == pytest.approx(3.0)
    assert Fertigung(dicke_min_ueberschreibung=1.8).dicke_min == pytest.approx(1.8)


def test_regelgrenzen_lassen_sich_nicht_unterschreiten():
    """Hinterkante und Nasenradius kommen aus T 2.4.1 - nur hoeher setzbar."""
    with pytest.raises(Exception):
        Fertigung(hinterkante_min=1.0)
    with pytest.raises(Exception):
        Fertigung(nasenradius_min=2.0)
