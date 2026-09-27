import pytest

from aerostudio.geometrie.fluegel_system import (
    BAUGRUPPEN,
    FluegelElement,
    FluegelSystem,
    Spannweitenbereich,
)


def _e(name, baugruppe):
    return FluegelElement(
        name=name,
        gruppe=name,
        profil="e423.dat",
        sehne_mm=250.0,
        winkel_grad=-5.0,
        spannweite=Spannweitenbereich(-200.0, 200.0),
        baugruppe=baugruppe,
    )


def test_baugruppen_koennen_getrennt_verwaltet_werden():
    system = FluegelSystem([
        _e("FW", "Frontfluegel"),
        _e("SP", "Seitenkasten"),
        _e("BW", "Bullwing"),
        _e("RW", "Heckfluegel"),
    ])
    assert system.baugruppen() == ["Frontfluegel", "Seitenkasten", "Bullwing", "Heckfluegel"]
    assert [e.name for e in system.elemente_der_baugruppe("Bullwing")] == ["BW"]


def test_unbekannte_baugruppe_wird_abgelehnt():
    with pytest.raises(ValueError):
        _e("X", "irgendwas")


def test_bekannte_baugruppen_sind_zentral_definiert():
    for name in ("Frontfluegel", "Seitenkasten", "Bullwing", "Heckfluegel", "Beamwing"):
        assert name in BAUGRUPPEN
