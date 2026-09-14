import pytest

from aerostudio.geometrie.fluegel_system import (
    MAX_ELEMENTE,
    FluegelElement,
    FluegelSystem,
    Spannweitenbereich,
)


def _element(name, gruppe="Front", y_von=-100.0, y_bis=100.0):
    return FluegelElement(
        name=name,
        gruppe=gruppe,
        profil="e423.dat",
        sehne_mm=250.0,
        winkel_grad=-5.0,
        spannweite=Spannweitenbereich(y_von, y_bis),
    )


def test_sechs_elemente_werden_akzeptiert():
    system = FluegelSystem([_element(f"E{i}") for i in range(MAX_ELEMENTE)])
    assert len(system.elemente) == 6


def test_sieben_elemente_werden_abgelehnt():
    with pytest.raises(ValueError):
        FluegelSystem([_element(f"E{i}") for i in range(MAX_ELEMENTE + 1)])


def test_getrennte_spannweiten_und_gruppen_bleiben_erhalten():
    system = FluegelSystem([
        _element("FW links", "Front links", -650, -200),
        _element("FW rechts", "Front rechts", 200, 650),
        _element("Bullwing", "Bullwing", -180, 180),
    ])
    assert system.gruppen() == ["Front links", "Front rechts", "Bullwing"]
    assert [e.name for e in system.elemente_bei_y(-400)] == ["FW links"]
    assert [e.name for e in system.elemente_bei_y(0)] == ["Bullwing"]


def test_doppelte_namen_werden_verboten():
    with pytest.raises(ValueError):
        FluegelSystem([_element("A"), _element("A")])
