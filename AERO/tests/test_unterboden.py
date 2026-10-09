"""
Tests fuer das Unterbodenmodell (M8).

Ein Kanalmodell mit geschaetzten Beiwerten liefert keine belastbaren Newton -
das steht im Modul und gehoert in jeden Report. Was es liefern MUSS, ist die
richtige Richtung jeder Aenderung. Genau das pruefen diese Tests: Ein DoE, das
auf einem Modell mit falscher Richtung laeuft, findet zuverlaessig das
schlechteste Auto.
"""

import numpy as np
import pytest

from aerostudio.aero import unterboden as ub
from aerostudio.regeln import lade
from aerostudio.spec.modell import Fahrzeuglage, Unterboden
from aerostudio.spec.projekt import AeroSpec


@pytest.fixture
def basis():
    return Unterboden()


def _mit(basis, **aenderung):
    return basis.model_copy(update=aenderung)


# ---------------------------------------------------------- Physik

def test_der_boden_erzeugt_abtrieb(basis):
    e = ub.rechne(basis)
    assert e.abtrieb > 0.0
    assert e.cp_min < 0.0


def test_abtrieb_waechst_mit_dem_quadrat_der_geschwindigkeit(basis):
    langsam = ub.rechne(basis, geschwindigkeit=10.0).abtrieb
    schnell = ub.rechne(basis, geschwindigkeit=20.0).abtrieb
    assert schnell / langsam == pytest.approx(4.0, rel=1e-6)


def test_tiefere_kehle_bringt_mehr_abtrieb(basis):
    werte = [ub.rechne(_mit(basis, kehle_hoehe_vorne=h + 5.0,
                            kehle_hoehe_hinten=h)).abtrieb
             for h in (70.0, 55.0, 40.0)]
    assert werte == sorted(werte)


def test_ebener_boden_ohne_diffusor_bringt_nichts(basis):
    """Ohne Aufweitung gibt es keinen Druckrueckgewinn - und ohne den keinen
    nennenswerten Sog. Das ist der Grund, warum es Diffusoren gibt."""
    flach = ub.rechne(_mit(basis, diffusor_winkel=0.0)).abtrieb
    mit = ub.rechne(basis).abtrieb
    assert abs(flach) < 0.1 * mit


def test_diffusor_hat_ein_maximum(basis):
    """Steiler bringt mehr - bis die Stroemung abloest, dann weniger.

    Ein Modell ohne dieses Maximum wuerde jedes DoE an den steilsten
    zulaessigen Winkel treiben, und das waere genau der abgeloeste Diffusor.
    """
    winkel = np.arange(0.0, 26.0, 1.0)
    abtrieb = [ub.rechne(_mit(basis, diffusor_winkel=float(w))).abtrieb
               for w in winkel]
    bester = float(winkel[int(np.argmax(abtrieb))])

    assert 8.0 <= bester <= ub.WINKEL_KRITISCH + 1.0
    assert abtrieb[-1] < max(abtrieb) * 0.5


def test_abloesung_wird_gemeldet(basis):
    steil = ub.rechne(_mit(basis, diffusor_winkel=20.0))
    assert steil.abgeloest
    assert any("loest" in h for h in steil.hinweise)
    assert not ub.rechne(basis).abgeloest


def test_rake_macht_den_diffusor_steiler(basis):
    """Der Fehler aus dem ersten Anlauf: Die Sekante ueber die Kehle machte
    den Diffusor mit Rake scheinbar FLACHER, von 10 auf 3,8 Grad."""
    ohne = ub.rechne(basis).diffusor_winkel_wirksam
    mit = ub.rechne(basis, Fahrzeuglage(rake_grad=1.0)).diffusor_winkel_wirksam

    assert mit == pytest.approx(ohne + 1.0, abs=0.1)


def test_rake_um_die_kehle_bringt_abtrieb(basis):
    """Die Richtung der Cologne-Fallstudie - Groessenordnung, nicht Zahl."""
    lage = Fahrzeuglage(rake_grad=0.5, drehpunkt_x=1150.0)
    ohne = ub.rechne(basis).abtrieb
    mit = ub.rechne(basis, lage).abtrieb
    assert mit > ohne


def test_drehpunkt_entscheidet_ueber_die_wirkung(basis):
    """Um die Vorderachse gedreht hebt sich die Kehle mit - der Gewinn
    schrumpft. Das ist keine Schwaeche des Modells, sondern der Grund,
    warum ein Rakewert ohne Drehpunkt nichts aussagt."""
    um_achse = ub.rechne(basis, Fahrzeuglage(rake_grad=1.0)).abtrieb
    um_kehle = ub.rechne(basis, Fahrzeuglage(rake_grad=1.0,
                                             drehpunkt_x=1150.0)).abtrieb
    assert um_kehle > um_achse


def test_druckpunkt_liegt_auf_dem_boden(basis):
    e = ub.rechne(basis)
    assert basis.x_start < e.druckpunkt_x < basis.x_start + basis.laenge


def test_abdichtung_wirkt_linear(basis):
    halb = ub.rechne(_mit(basis, abdichtung=0.35)).abtrieb
    voll = ub.rechne(_mit(basis, abdichtung=0.7)).abtrieb
    assert voll == pytest.approx(2.0 * halb)


def test_aufsetzen_ist_ein_klarer_fehler(basis):
    with pytest.raises(ValueError, match="setzt auf"):
        ub.rechne(basis, hub=-60.0)


def test_widerstand_ist_positiv_und_klein(basis):
    e = ub.rechne(basis)
    assert 0.0 < e.widerstand < e.abtrieb


# ------------------------------------------------------- Kennlinie

def test_kennlinie_ueber_den_hub(basis):
    k = ub.kennlinie(basis, hub_bereich=15.0, stufen=7)
    assert len(k.hub) == len(k.abtrieb) == 7
    # Einfedern bringt den Boden naeher an die Strasse, also mehr Abtrieb.
    assert k.abtrieb[0] > k.abtrieb[-1]
    assert 0.0 < k.stabilitaet <= 1.0


def test_aufsetzen_zaehlt_als_null_nicht_als_luecke(basis):
    """Aufsetzen ist der schlechteste Fall und soll die Stabilitaet auch so
    bewerten - ausgelassen saehe der Boden stabiler aus, als er ist."""
    tief = _mit(basis, kehle_hoehe_vorne=25.0, kehle_hoehe_hinten=20.0)
    k = ub.kennlinie(tief, hub_bereich=30.0, stufen=7)
    assert k.abtrieb[0] == 0.0
    assert k.stabilitaet == 0.0


# -------------------------------------------------------- Regelpruefung

def test_bodenfreiheit_nach_t221(basis):
    befunde = ub.pruefe(basis, regelsatz=lade())
    t221 = [b for b in befunde if b.regel == "T 2.2.1"][0]
    assert t221.ok and t221.grenze == 30.0


def test_zu_tiefer_boden_reisst_t221(basis):
    tief = _mit(basis, kehle_hoehe_vorne=28.0, kehle_hoehe_hinten=25.0)
    t221 = [b for b in ub.pruefe(tief, regelsatz=lade())
            if b.regel == "T 2.2.1"][0]
    assert not t221.ok
    assert t221.ist == pytest.approx(25.0)


def test_rake_zaehlt_fuer_die_bodenfreiheit(basis):
    """Um die Kehle gedreht senkt Rake die Nase - und damit den Einlass."""
    lage = Fahrzeuglage(rake_grad=2.0, drehpunkt_x=1150.0)
    ohne = ub.pruefe(basis)[0].ist
    mit = ub.pruefe(basis, lage)[0].ist
    assert mit < ohne


# ------------------------------------------------------------ Spec

def test_unterboden_im_spec_und_hash_bleibt_fuer_alte_specs():
    """Die M8-Felder duerfen den Hash eines Specs ohne Unterboden nicht
    aendern - er steht als AERO_SPEC_HASH in jeder exportierten IBL."""
    alt = AeroSpec.beispiel()
    vorher = alt.hash()
    neu = AeroSpec.model_validate(alt.model_dump(mode="json"))
    assert neu.hash() == vorher

    mit = alt.model_copy(deep=True)
    mit.unterboden = Unterboden()
    assert mit.hash() != vorher

    gekippt = alt.model_copy(deep=True)
    gekippt.lage = Fahrzeuglage(rake_grad=1.0)
    assert gekippt.hash() != vorher


def test_unterboden_ueberlebt_speichern(tmp_path):
    spec = AeroSpec.beispiel()
    spec.unterboden = Unterboden(diffusor_winkel=12.5)
    spec.lage = Fahrzeuglage(rake_grad=0.8)
    spec.speichern(tmp_path / "s.yaml", historie=False)

    geladen = AeroSpec.laden(tmp_path / "s.yaml")
    assert geladen.unterboden.diffusor_winkel == 12.5
    assert geladen.lage.rake_grad == 0.8
    assert geladen.hash() == spec.hash()


def test_knick_auf_rasterpunkt_erzeugt_keine_scheinsteigung():
    """Review 29.09.: Liegt ein Knick genau auf einem Rasterpunkt, lieferte
    union1d zwei Werte im Abstand 1e-13 und np.gradient eine riesige
    Steigung - der Diffusor galt als abgeloest (285 -> 246 N)."""
    from aerostudio.spec.modell import Unterboden
    a = ub.rechne(Unterboden(einlass_laenge=100, kehle_laenge=980,
                             diffusor_laenge=540, diffusor_winkel=14.9))
    b = ub.rechne(Unterboden(einlass_laenge=100, kehle_laenge=981,
                             diffusor_laenge=540, diffusor_winkel=14.9))
    assert a.diffusor_winkel_wirksam == pytest.approx(14.9, abs=0.05)
    assert not a.abgeloest
    assert a.abtrieb == pytest.approx(b.abtrieb, rel=0.01)
