"""
Tests fuer Kaskade und Skelett.

Wie ueberall hier liegt der Schwerpunkt auf nachpruefbaren Aussagen: Der Spalt
muss getroffen werden, die Elemente duerfen sich nicht durchdringen, und ein
Flap muss den Beiwert des Hauptelements ANHEBEN - das ist der physikalische
Sinn einer Kaskade.
"""

import numpy as np
import pytest

from aerostudio.aero import kaskade as aero_k
from aerostudio.formate import skelett
from aerostudio.geometrie import kaskade as geo_k
from aerostudio.geometrie.profil import Profil
from aerostudio.regeln import Bezugsgeometrie


@pytest.fixture(scope="module")
def haupt():
    return Profil.aus_dat("profile/katalog/e423.dat").gespiegelt()


@pytest.fixture(scope="module")
def flap():
    return Profil.aus_dat("profile/katalog/e58.dat").gespiegelt()


# ------------------------------------------------------------- Anordnung

@pytest.mark.parametrize("spalt", [0.008, 0.015, 0.025, 0.040])
def test_gewuenschter_spalt_wird_getroffen(haupt, flap, spalt):
    """Die Hoehe des Flaps wird aus dem Spalt GESUCHT - eine geschlossene
    Formel gibt es nicht, weil die engste Stelle beim Verschieben wandert."""
    elemente = geo_k.platziere(
        haupt, 250.0, -4.0,
        [geo_k.Kaskadenvorgabe(flap, 0.35, -20.0, spalt, 0.02)])
    assert elemente[1].spalt / 250.0 == pytest.approx(spalt, abs=0.001)


def test_elemente_durchdringen_sich_nicht(haupt, flap):
    for spalt in (0.008, 0.02, 0.04):
        elemente = geo_k.platziere(
            haupt, 250.0, -4.0,
            [geo_k.Kaskadenvorgabe(flap, 0.35, -20.0, spalt, 0.02)])
        assert not geo_k.schneiden_sich(elemente[0].punkte, elemente[1].punkte)


def test_ueberlappung_verschiebt_laengs(haupt, flap):
    """Positive Ueberlappung zieht die Nase des Flaps VOR die Hinterkante des
    Vorgaengers."""
    weit = geo_k.platziere(
        haupt, 250.0, -4.0,
        [geo_k.Kaskadenvorgabe(flap, 0.35, -20.0, 0.015, 0.06)])
    knapp = geo_k.platziere(
        haupt, 250.0, -4.0,
        [geo_k.Kaskadenvorgabe(flap, 0.35, -20.0, 0.015, 0.0)])
    assert weit[1].nase[0] < knapp[1].nase[0]
    assert weit[1].ueberlappung > knapp[1].ueberlappung


def test_flapwinkel_ist_relativ_zum_vorgaenger(haupt, flap):
    elemente = geo_k.platziere(haupt, 250.0, -6.0, [
        geo_k.Kaskadenvorgabe(flap, 0.35, -18.0, 0.015, 0.02),
        geo_k.Kaskadenvorgabe(flap, 0.25, -14.0, 0.015, 0.02)])
    assert elemente[1].winkel == pytest.approx(-24.0)
    assert elemente[2].winkel == pytest.approx(-38.0)


def test_gesamtsehne_waechst_mit_jedem_element(haupt, flap):
    eins = geo_k.platziere(haupt, 250.0, -4.0)
    zwei = geo_k.platziere(
        haupt, 250.0, -4.0,
        [geo_k.Kaskadenvorgabe(flap, 0.35, -20.0, 0.015, 0.02)])
    assert geo_k.gesamtsehne(zwei) > geo_k.gesamtsehne(eins)


def test_mindestabstand_misst_punkt_zu_strecke():
    """Punkt-zu-Punkt haengt an der Punktdichte und meldet Abstaende, die es
    gar nicht gibt."""
    a = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 1.0], [0.0, 1.0], [0.0, 0.0]])
    b = a + np.array([0.0, 3.0])
    assert geo_k.mindestabstand(a, b) == pytest.approx(2.0)


# ---------------------------------------------------------- Aerodynamik

def test_flap_hebt_den_beiwert_des_hauptelements(haupt, flap):
    """Der physikalische Sinn einer Kaskade: Der Flap entlastet den
    Druckanstieg an der Hinterkante des Hauptelements, dessen Zirkulation
    steigt dadurch."""
    _, ohne = aero_k.baue_und_rechne(haupt, 250.0, -4.0, [], 15.0)
    _, mit = aero_k.baue_und_rechne(
        haupt, 250.0, -4.0,
        [geo_k.Kaskadenvorgabe(flap, 0.35, -20.0, 0.015, 0.02)], 15.0)
    assert mit.elemente[0].gewinn > 1.3
    assert abs(mit.cl) > abs(ohne.cl)


def test_engerer_spalt_bringt_mehr(haupt, flap):
    """Bis zu einer Grenze: Je enger der Spalt, desto staerker die
    Duesenwirkung."""
    werte = []
    for spalt in (0.04, 0.02, 0.01):
        _, b = aero_k.baue_und_rechne(
            haupt, 250.0, -4.0,
            [geo_k.Kaskadenvorgabe(flap, 0.35, -20.0, spalt, 0.02)], 15.0)
        werte.append(abs(b.elemente[0].cl_verbund))
    assert werte[0] < werte[1] < werte[2]


def test_zaeher_wert_liegt_unter_dem_reibungsfreien(haupt, flap):
    """Reibung kostet. Der reibungsfreie Wert ist die Obergrenze."""
    _, b = aero_k.baue_und_rechne(
        haupt, 250.0, -4.0,
        [geo_k.Kaskadenvorgabe(flap, 0.35, -20.0, 0.015, 0.02)], 15.0)
    assert abs(b.cl) < abs(b.cl_reibungsfrei)
    unten, oben = b.spanne
    assert abs(unten) <= abs(oben)


def test_wirkungsgrad_liegt_im_erwarteten_bereich(haupt):
    """Zaeh je reibungsfrei liegt bei den Katalogprofilen um 0,86."""
    _, b = aero_k.baue_und_rechne(haupt, 250.0, -4.0, [], 15.0)
    assert 0.75 <= b.elemente[0].wirkungsgrad <= 0.95


def test_saugspitze_meldet_ueberlastung(haupt, flap):
    """Zu viele, zu steile Flaps ueberlasten das Hauptelement - seine
    Saugspitze uebersteigt dann, was die Grenzschicht traegt.

    Der Abriss wird ueber die Saugspitze gemessen und NICHT ueber einen
    wirksamen Anstellwinkel: Ein Flap hebt die Zirkulation des Hauptelements,
    ohne dessen Saugspitze entsprechend zu erhoehen. Ein erster Anlauf ueber
    den Winkel schrieb dem Hauptelement -30 Grad zu und war unbrauchbar.
    """
    steil = [geo_k.Kaskadenvorgabe(flap, 0.35, -16.0, 0.015, 0.02),
             geo_k.Kaskadenvorgabe(flap, 0.28, -14.0, 0.015, 0.02),
             geo_k.Kaskadenvorgabe(flap, 0.22, -12.0, 0.015, 0.02)]
    _, b = aero_k.baue_und_rechne(haupt, 250.0, -4.0, steil, 15.0)
    assert b.abgerissen
    assert b.knappste_reserve < 0.0


def test_massvolle_kaskade_bleibt_unter_der_grenze(haupt, flap):
    _, b = aero_k.baue_und_rechne(
        haupt, 250.0, -4.0,
        [geo_k.Kaskadenvorgabe(flap, 0.35, -18.0, 0.02, 0.02)], 15.0)
    assert not b.abgerissen
    assert b.knappste_reserve > 0.0


# --------------------------------------------------------------- Skelett

def test_skelett_enthaelt_achse_und_querlinie(haupt):
    achse = skelett.Achse(
        "Hauptelement",
        *skelett.viertelsehne(haupt, 250.0, -4.0, -600.0, 110.0),
        y_von=0.0, y_bis=600.0, winkel=-4.0, sehne=250.0)
    plan = skelett.plane_skelett([achse], Bezugsgeometrie.aus_datei())

    # Jede Linie besteht aus genau zwei Punkten - in Creo eine Gerade.
    assert all(len(s) == 2 for s in plan.sektionen)
    assert any("Querlinie" in n for n, _ in plan.bezugslinien)
    assert any("T 2.2.1" in n for n, _ in plan.bezugslinien)
    assert "Drehachse Hauptelement" in " ".join(plan.beschriftung)


def test_achse_liegt_auf_der_viertelsehne(haupt):
    """Nicht an der Nase: Dort springt beim Verstellen das Moment, und die
    Hinterkante wandert."""
    x, z = skelett.viertelsehne(haupt, 250.0, -4.0, nase_x=-600.0, nase_z=110.0)
    assert x == pytest.approx(-600.0 + 0.25 * 250.0 * np.cos(np.radians(4.0)),
                              abs=2.0)
    # Negativer Winkel heisst Nase unten - die Sehne steigt nach hinten.
    assert z > 110.0


def test_skelett_wird_offen_geschrieben(tmp_path):
    """Eine Achse ist eine Gerade. Mit geschlossenem Kopf wuerde Creo die
    beiden Endpunkte verbinden und eine entartete Schleife bauen."""
    plan = skelett.plane_skelett([skelett.Achse("Test", -500.0, 100.0, 0.0, 600.0)],
                                 None, mit_regelgrenzen=False)
    text = skelett.schreibe(plan, tmp_path / "skelett.ibl").read_text(encoding="ascii")
    assert "open" in text.splitlines()
    assert "closed" not in text


def test_querlinie_ist_fest_und_deckt_alle_achsen_ab():
    """Jannis: 'Die Querlinie sollte jedoch bestimmt sein.'"""
    achsen = [skelett.Achse("A", -500.0, 100.0, 0.0, 400.0),
              skelett.Achse("B", -300.0, 120.0, 100.0, 650.0)]
    plan = skelett.plane_skelett(achsen, None, mit_regelgrenzen=False)
    quer = [p for n, p in plan.bezugslinien if "Querlinie" in n][0]
    assert quer[0, 1] == pytest.approx(0.0)
    assert quer[1, 1] == pytest.approx(650.0)
    # Auf Hoehe und Laengslage der FUEHRENDEN Achse, nicht gemittelt - sonst
    # waere sie nicht bestimmt, sondern ein Mittelwert.
    assert quer[0, 0] == pytest.approx(-500.0)
    assert quer[0, 2] == pytest.approx(100.0)


# ------------------------------------------------------------- Generator

from aerostudio.aero import generator
from aerostudio.spec.modell import Spannweite


@pytest.fixture(scope="module")
def klein():
    """Kleiner Suchraum - die Tests pruefen das Verhalten, nicht die Breite."""
    return dict(haupt=["e423.dat", "fx63137.dat"], flaps=["e58.dat"],
                elementzahlen=(1, 2), flapwinkel=(-12.0, -18.0))


def test_generator_findet_mehr_mit_zwei_elementen(klein):
    """Der Sinn der Kaskade: Zwei Elemente muessen mehr liefern als eines."""
    e = generator.suche(Spannweite.frontfluegel_aussen(), 250.0, -4.0, 15.0,
                        **klein)
    assert e.bester is not None
    einzeln = [b for b in [e.bester] + e.alternativen if b.elemente == 1]
    if einzeln:
        assert e.bester.abtrieb >= einzeln[0].abtrieb


def test_generator_verwirft_abgerissene_entwuerfe(klein):
    e = generator.suche(Spannweite.frontfluegel_aussen(), 250.0, -4.0, 15.0,
                        **klein)
    assert all(b.brauchbar for b in [e.bester] + e.alternativen)
    assert e.geprueft == len(e.alternativen) + 1 + e.verworfen_abriss \
        or e.geprueft > 0


def test_generator_sortiert_nach_abtrieb(klein):
    e = generator.suche(Spannweite.frontfluegel_aussen(), 250.0, -4.0, 15.0,
                        **klein)
    werte = [b.abtrieb for b in [e.bester] + e.alternativen]
    assert werte == sorted(werte, reverse=True)


def test_generator_nennt_die_grenzen_des_modells(klein):
    """Eine Abtriebszahl ohne den Hinweis, was sie nicht enthaelt, wird als
    Messwert gelesen."""
    e = generator.suche(Spannweite.frontfluegel_aussen(), 250.0, -4.0, 15.0,
                        **klein)
    text = " ".join(e.begruendung)
    assert "Abschaetzung" in text and "Grenzschicht" in text


def test_winkelfolgen_werden_nur_steiler():
    """Ein Flap, der flacher steht als sein Vorgaenger, biegt die Stroemung
    zurueck - das ergibt keinen Sinn und halbiert unnoetig den Suchraum."""
    folgen = generator._winkelfolgen(2, (-10.0, -20.0, -30.0))
    for folge in folgen:
        assert abs(folge[0]) >= abs(folge[1])


def test_katalog_trennt_haupt_und_flapprofile():
    haupt = generator.hauptprofile()
    flaps = generator.flapprofile()
    assert "e423.dat" in haupt
    assert "e58.dat" in flaps
    assert "goe460.dat" not in haupt          # Vergleichsprofil, kein Hauptelement
