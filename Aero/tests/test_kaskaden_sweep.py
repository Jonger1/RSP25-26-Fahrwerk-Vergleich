from types import SimpleNamespace

import pytest

from aerostudio.aero.kaskaden_sweep import raster, sortiere_nach_effizienz, sweep


def test_raster_inkludiert_ende_ohne_doppelten_fast_float():
    assert raster(0.01, 0.03, 0.01) == (0.01, 0.02, 0.03)


def test_raster_lehnt_ungueltige_schritte_ab():
    with pytest.raises(ValueError):
        raster(0.0, 1.0, 0.0)


def test_sweep_erzeugt_kartesisches_produkt():
    def rechner(gap, overlap, winkel):
        return SimpleNamespace(cl=-1.0 - gap, cd=0.1, knappste_reserve=0.2,
                               abgerissen=False)

    result = sweep(
        gaeps=[0.01, 0.02], overlaps=[0.0, 0.01], winkel=[-10.0, -12.0],
        rechner=rechner, modellgrenze=(-2.0, 0.0), min_reserve=0.1)
    assert len(result) == 8
    assert all(e.gueltig for e in result)


def test_ungueltige_modellpunkte_werden_markiert():
    def rechner(gap, overlap, winkel):
        return SimpleNamespace(cl=-3.0, cd=0.1, knappste_reserve=-0.1,
                               abgerissen=True)

    result = sweep(gaeps=[0.02], overlaps=[0.01], winkel=[-20.0],
                   rechner=rechner, modellgrenze=(-2.0, 0.0), min_reserve=0.0)
    assert not result[0].gueltig
    assert result[0].abgerissen
    assert not result[0].modellgueltig


def test_effizienz_sortierung_setzt_ungueltige_nach_hinten():
    good = SimpleNamespace(cl=-1.5, cd=0.1, reserve=0.1,
                           abgerissen=False, modellgueltig=True,
                           gap=0.02, overlap=0.02, winkel_relativ=-15.0)
    better = SimpleNamespace(cl=-1.8, cd=0.1, reserve=0.1,
                             abgerissen=False, modellgueltig=True,
                             gap=0.02, overlap=0.01, winkel_relativ=-15.0)
    assert sortiere_nach_effizienz([good, better])[0] is better
