import numpy as np
import pytest

from aerostudio.aero.traglinie_system import rechne, streifen_aus_system, SystemStreifen
from aerostudio.geometrie.fluegel_system import FluegelElement, FluegelSystem, Spannweitenbereich


def _element(name, y0, y1):
    return FluegelElement(
        name=name,
        gruppe="Front",
        profil="e423.dat",
        sehne_mm=250.0,
        winkel_grad=-5.0,
        spannweite=Spannweitenbereich(y0, y1),
    )


def test_symmetrischer_segmentierter_fluegel_liefert_symmetrische_lokalkraefte():
    system = FluegelSystem([
        _element("L", -600.0, -200.0),
        _element("R", 200.0, 600.0),
    ])
    streifen = streifen_aus_system(system, panels_je_element=6)
    result = rechne(streifen, geschwindigkeit=15.0)
    assert result.cl < 0.0
    assert np.allclose(result.cl_lokal[:6], result.cl_lokal[6:][::-1], rtol=1e-5, atol=1e-8)
    assert np.allclose(result.alpha_induziert[:6], result.alpha_induziert[6:][::-1], rtol=1e-5, atol=1e-8)


def test_spannweitenluecke_wird_nicht_mit_panels_aufgefuellt():
    system = FluegelSystem([_element("L", -600.0, -200.0), _element("R", 200.0, 600.0)])
    streifen = streifen_aus_system(system, panels_je_element=5)
    assert len(streifen) == 10
    assert max(s.y for s in streifen if s.y < 0) < -200.0 + 1e-6
    assert min(s.y for s in streifen if s.y > 0) > 200.0 - 1e-6


def test_negative_geschwindigkeit_ist_unzulaessig():
    with pytest.raises(ValueError):
        rechne([SystemStreifen("E", "G", "Frontfluegel", 0, 100, 250, -5, 100, 62.5)], geschwindigkeit=0.0)
