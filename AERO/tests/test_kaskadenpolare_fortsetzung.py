"""
Regression: die Kaskadenpolare auf der anliegenden Seite linear fortsetzen.

Bis zum 07.10.2026 wurde jenseits der gerechneten +-6 Grad auf den
Randbeiwert geklemmt. Bei kleiner Streckung kippt der induzierte Winkel die
Anstroemung aber um 10 Grad und mehr: Jeder Streifen des Heckfluegel-
Beispiels hing am selben Beiwert, die Last war bis in die Spitze konstant,
der Abtrieb mit 103 N zu hoch und der induzierte Widerstand beim Doppelten
des ideal-elliptischen Werts.
"""

import math

import numpy as np
import pytest

from aerostudio.aero import kaskade3d
from aerostudio.aero.kaskade3d import _anliegend_fortsetzen
from aerostudio.aero.profilpolare import verfuegbar
from aerostudio.spec.projekt import AeroSpec
from aerostudio.ui import app as UI


def _polare(cl):
    a = np.array([-12.0, -9.0, -6.0, -3.0, 0.0])
    return a, np.array(cl, float), np.full(5, 0.02), np.ones(5)


def test_abtrieb_wird_zu_groesseren_winkeln_fortgesetzt():
    a, cl, cd, v = _anliegend_fortsetzen(*_polare([-2.3, -2.4, -2.6, -2.3, -1.9]))
    assert a.max() == pytest.approx(30.0)
    assert a.min() == pytest.approx(-12.0)          # Abrissseite unberuehrt
    steigung = (-1.9 - -2.3) / 3.0
    i = int(np.argmin(np.abs(a - 15.0)))
    assert cl[i] == pytest.approx(-1.9 + steigung * 15.0)
    assert np.all(v[a > 0.0] <= 0.5)                # Vertrauen gesenkt
    assert np.all(np.diff(a) > 0)


def test_auftrieb_wird_zu_kleineren_winkeln_fortgesetzt():
    a, cl, cd, v = _anliegend_fortsetzen(*_polare([1.9, 2.3, 2.6, 2.4, 2.3]))
    assert a.min() == pytest.approx(-42.0)
    assert a.max() == pytest.approx(0.0)


def test_ohne_fallenden_rand_keine_fortsetzung():
    """Faellt der Betrag am Rand nicht, ist es nicht die anliegende Seite."""
    a, *_ = _anliegend_fortsetzen(*_polare([-1.0, -1.5, -2.0, -2.5, -3.0]))
    assert a.max() == pytest.approx(0.0)


@pytest.mark.skipif(not verfuegbar(), reason="NeuralFoil fehlt")
def test_heckfluegel_last_faellt_zur_spitze_und_widerstand_wie_theorie():
    e = AeroSpec.laden(UI.PROJEKT / "specs/beispiele/heckfluegel.yaml").elemente[0]
    r = kaskade3d.rechne(UI.profil_fuer(e), e.spannweite, e.sehne,
                         e.anstellwinkel, UI._vorgaben(e.kaskade), 20.0,
                         lage=UI._lage(e), endplatte_mm=UI._endplattenhoehe(e))
    k = r.kraefte
    y = np.array([s.y for s in k.streifen])
    b = np.array([s.breite for s in k.streifen])
    last = -np.asarray(k.auftrieb_lokal) / b
    mitte = last[np.argmin(np.abs(y))]
    spitze = last[np.argmax(np.abs(y))]
    # Nicht mehr konstant bis in die Spitze.
    assert spitze < 0.5 * mitte

    # Ausserhalb des Bodeneffekts (900 mm): nahe am ideal-elliptischen Wert
    # mit Hoerner-Endplatten - frueher das Doppelte.
    spannweite = ((y + b / 2).max() - (y - b / 2).min()) / 1000.0
    q = 0.5 * 1.2 * 20.0 ** 2
    ideal = k.abtrieb ** 2 / (q * math.pi * spannweite ** 2) / k.endplattenfaktor
    assert k.widerstand_induziert == pytest.approx(ideal, rel=0.25)

    # Und die Rechnung sagt, dass sie hier nur eine Naeherung ist.
    assert any("Streckung" in h for h in r.hinweise)
