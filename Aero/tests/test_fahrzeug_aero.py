import pytest

from aerostudio.aero.fahrzeug_aero import last_aus_beiwert


def test_last_aus_beiwert():
    last = last_aus_beiwert("Front", "Frontfluegel", -2.0, 0.12,
                            0.25, 20.0, x_mm=-900.0)
    assert last.abtrieb_n > 0.0
    assert last.widerstand_n > 0.0
    assert last.q_pa == pytest.approx(245.0)


def test_negative_flaeche_wird_abgelehnt():
    with pytest.raises(ValueError):
        last_aus_beiwert("x", "x", -1.0, 0.1, 0.0, 20.0)
