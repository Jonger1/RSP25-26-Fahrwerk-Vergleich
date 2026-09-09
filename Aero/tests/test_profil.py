"""Tests fuer den Profilkern.

Der Pruefstein ist durchgehend das analytische NACA-Profil: Seine Kennwerte
sind aus der Definition bekannt, deshalb faellt jede Abweichung sofort auf.
"""

from pathlib import Path

import numpy as np
import pytest

from aerostudio.geometrie.profil import Profil
from aerostudio.geometrie.spline import abweichung_zur_kontur, bogenlaenge
from aerostudio.spec.modell import Fertigung, Verfahren

KATALOG = Path(__file__).resolve().parents[1] / "profile" / "katalog"


def _katalog(name: str) -> Path:
    return KATALOG / name


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

def test_hinterkante_aus_verklebung_blockiert_nicht():
    """Team-Entscheidung: Die Hinterkante entsteht beim Verkleben der Schalen.

    Ein Profil mit spitzer Hinterkante ist damit zulaessig - das Werkzeug
    meldet die gebaute Dicke als Hinweis, nicht als Verstoss.
    """
    p = Profil.aus_naca(0.04, 0.4, 0.12, n=401)
    f = Fertigung(hinterkante_durch_verklebung=True, wandstaerke=0.6)
    befunde = {b.pruefung: b for b in p.pruefe_fertigung(f, 250.0)}
    hk = befunde["Hinterkante gebaut"]
    assert hk.stufe == "hinweis"
    assert not hk.blockiert
    assert hk.ist == pytest.approx(1.4)          # 2 x 0.6 Haut + 0.2 Kleber


def test_hinterkante_ohne_verklebung_ist_ein_verstoss():
    """Wer die Hinterkante ins Profil zeichnet, muss T 2.4.1 einhalten."""
    p = Profil.aus_naca(0.04, 0.4, 0.12, n=401)
    f = Fertigung(hinterkante_durch_verklebung=False)
    befunde = {b.pruefung: b for b in p.pruefe_fertigung(f, 250.0)}
    hk = befunde["Hinterkantendicke"]
    assert hk.blockiert
    assert hk.regel == "T 2.4.1"


def test_dickere_haut_erfuellt_die_regel_von_allein():
    """Nasslaminat mit 1.2 mm Haut ergibt 2.6 mm Hinterkante - regelkonform."""
    f = Fertigung(wandstaerke=1.2, klebespalt=0.2)
    assert f.hinterkante_gebaut == pytest.approx(2.6)
    assert f.hinterkante_gebaut >= f.hinterkante_min


def test_vollmaterial_wird_von_hinten_gesucht():
    """Regression: an der Nase ist die Dicke ebenfalls null.

    Eine Vorwaertssuche findet deshalb immer x = 0 und meldet, das Bauteil sei
    ab der Nase Vollmaterial. Der Wert muss weit hinten liegen.
    """
    p = Profil.aus_dat(_katalog("e423.dat"))
    f = Fertigung(wandstaerke=0.6, kern=2.0)
    befund = {b.pruefung: b for b in p.pruefe_fertigung(f, 250.0)}["Vollmaterial ab"]
    assert befund.ist > 80.0


def test_duennerer_aufbau_verschiebt_das_vollmaterial_nach_hinten():
    """Ohne Kern bleibt das Bauteil laenger Schale."""
    p = Profil.aus_dat(_katalog("s1223.dat"))
    mit = {b.pruefung: b.ist for b in p.pruefe_fertigung(
        Fertigung(wandstaerke=0.6, kern=2.0), 250.0)}["Vollmaterial ab"]
    ohne = {b.pruefung: b.ist for b in p.pruefe_fertigung(
        Fertigung(wandstaerke=0.6, kern=0.0), 250.0)}["Vollmaterial ab"]
    assert ohne > mit


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


# ---------------------------------------------------------- Katalogprofile

@pytest.mark.parametrize("datei,dicke_soll", [
    ("s1223.dat", 0.121),      # publizierter Wert
    ("e423.dat", 0.125),
    ("fx63137.dat", 0.137),    # steht im Namen: FX 63-137
    ("s1210.dat", 0.120),      # steht im Dateikopf: "S1210 12%"
])
def test_katalogprofil_trifft_publizierte_dicke(datei, dicke_soll):
    p = Profil.aus_dat(_katalog(datei))
    assert p.max_dicke == pytest.approx(dicke_soll, abs=0.002)


def test_lednicer_format_wird_erkannt():
    """FX 63-137 liegt im Lednicer-Format vor, die uebrigen in Selig."""
    p = Profil.aus_dat(_katalog("fx63137.dat"))
    assert p.max_dicke == pytest.approx(0.137, abs=0.002)
    assert np.all(np.diff(p.oben()[:, 0]) > 0)


def test_grob_aufgeloestes_profil_liefert_einen_nasenradius():
    """GOE 797 hat nur 27 Punkte - das Suchfenster muss mitwachsen."""
    p = Profil.aus_dat(_katalog("goe797.dat"))
    assert not np.isnan(p.nasenradius())
    assert p.nasenradius() > 0.0


def test_alle_katalogprofile_lassen_sich_lesen():
    dateien = sorted(KATALOG.glob("*.dat"))
    assert len(dateien) >= 10
    for d in dateien:
        p = Profil.aus_dat(d)
        assert 0.02 < p.max_dicke < 0.30, f"{d.name}: Dicke {p.max_dicke:.3f}"
        assert p.punktzahl(250.0, 0.005) is not None, f"{d.name}: keine Punktzahl"
