import pytest

from aerostudio.aero.endplatten import Endplatte


def test_neutrale_endplatte_verfaelscht_keine_rechnung():
    ep = Endplatte()
    assert not ep.aktiv
    assert ep.aequivalente_halbspannweite(600.0) == pytest.approx(600.0)


def test_geometrische_endplatte_bleibt_ohne_kalibrierung_neutral():
    ep = Endplatte(hoehe=80.0, laenge=120.0, wirkungsgrad=0.0)
    assert ep.aktiv
    assert ep.aequivalente_halbspannweite(600.0) == pytest.approx(600.0)
    assert "neutral" in ep.hinweis().lower()


def test_kalibrierung_erhoeht_aequivalente_halbspannweite():
    ep = Endplatte(hoehe=100.0, laenge=150.0, wirkungsgrad=0.25)
    assert ep.aequivalente_halbspannweite(600.0) == pytest.approx(625.0)


def test_ungueltige_wirkungsgrade_werden_abgelehnt():
    with pytest.raises(ValueError):
        Endplatte(hoehe=100.0, laenge=150.0, wirkungsgrad=1.1)
