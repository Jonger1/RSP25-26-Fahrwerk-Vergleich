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


def test_abtriebsflap_liegt_ueber_der_hinterkante_des_vorgaengers(haupt, flap):
    """Nicht wie eine Flugzeug-Landeklappe nach unten hängen.

    Beim spiegelverkehrten Abtriebsprofil ist die Unterseite die Saugseite.
    Die Flapnase muss darum über der Hinterkante des Vorgängers liegen, damit
    der Schlitz die Druckseite mit der Saugseite des Flaps verbindet.
    """
    elemente = geo_k.platziere(
        haupt, 250.0, -4.0,
        [geo_k.Kaskadenvorgabe(flap, 0.35, -20.0, 0.015, 0.02)])
    assert elemente[1].nase[1] > elemente[0].hinterkante[1]


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


def test_baue_und_rechne_nutzt_bodenhoehe_nur_fuer_die_geometrie(haupt, flap):
    """Die 2D-Boden-Spiegelung darf einen Flügel nicht hochrechnen."""
    _, frei = aero_k.baue_und_rechne(haupt, 250.0, -4.0, [], 15.0)
    _, bodennah = aero_k.baue_und_rechne(haupt, 250.0, -4.0, [], 15.0,
                                          hoehe_ueber_boden=30.0)
    assert bodennah.cl == pytest.approx(frei.cl)
    assert not bodennah.bodennah


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


# --------------------------------------------------- Kaskade im Werkzeug

from aerostudio.ui import app as UI


def test_tabelle_wird_zur_kaskade():
    zeilen = [{"profil": "e58.dat", "sehne": 0.35, "winkel": -20.0,
               "spalt": 0.015, "ueberlappung": 0.02},
              {"profil": "e58.dat", "sehne": 0.25, "winkel": -16.0,
               "spalt": 0.015, "ueberlappung": 0.02}]
    stufen = UI.kaskade_aus_tabelle(zeilen)
    assert len(stufen) == 2
    assert stufen[0].winkel == pytest.approx(-20.0)
    assert stufen[1].sehne == pytest.approx(0.25)


def test_leere_tabelle_heisst_einzelnes_element():
    assert UI.kaskade_aus_tabelle([]) == []
    assert UI.kaskade_aus_tabelle(None) == []


def test_unvollstaendige_zeile_wird_uebersprungen():
    """Wer eine Zeile hinzufuegt und noch tippt, darf keine Fehlermeldung
    bekommen."""
    stufen = UI.kaskade_aus_tabelle([{"profil": ""}, {"profil": None},
                                     {"profil": "e58.dat"}])
    assert len(stufen) == 1
    assert stufen[0].sehne == pytest.approx(0.35)      # Vorgabe


def test_werte_ausserhalb_des_gueltigen_werden_geklemmt():
    """Ein Tippfehler darf nicht die ganze Oberflaeche in eine Fehlermeldung
    schicken - das Datenmodell wuerde sonst ablehnen."""
    stufen = UI.kaskade_aus_tabelle([{"profil": "e58.dat", "sehne": 99.0,
                                      "spalt": -5.0, "winkel": 900.0}])
    assert 0.0 < stufen[0].sehne <= 1.0
    assert stufen[0].spalt > 0.0
    assert abs(stufen[0].winkel) <= 60.0


def test_kaskade_landet_im_spec():
    werte = list(UI._EINGABEN)          # nur zur Laengenpruefung
    from tests.test_export_ui import werte_mit
    eigene = werte_mit(kaskadenzeilen=[
        {"profil": "e58.dat", "sehne": 0.3, "winkel": -22.0,
         "spalt": 0.012, "ueberlappung": 0.03}])
    spec, *_ = UI._profil_aktualisieren(*eigene)
    from aerostudio.spec.projekt import AeroSpec
    element = AeroSpec.model_validate(spec).elemente[0]
    assert len(element.kaskade) == 1
    assert element.kaskade[0].winkel == pytest.approx(-22.0)
    assert len(werte) > 0


def test_element_hinzufuegen_macht_es_kuerzer_und_flacher():
    """Jedes weitere Element ist kuerzer und flacher als sein Vorgaenger -
    so bauen es alle, und der Entwurf bleibt beim Hinzufuegen brauchbar."""
    erste = UI._stufe_hinzufuegen(1, [])
    assert len(erste) == 1
    zweite = UI._stufe_hinzufuegen(1, erste)
    assert len(zweite) == 2
    assert zweite[1]["sehne"] < zweite[0]["sehne"]
    assert abs(zweite[1]["winkel"]) < abs(zweite[0]["winkel"])


# ------------------------------------------- Lage des Flaps (Abtrieb!)

def test_flap_sitzt_UEBER_der_hinterkante(haupt, flap):
    """Der Kern der umgedrehten Anordnung.

    Bei einem ABTRIEBSfluegel ist die UNTERSEITE die Saugseite. Der Spalt muss
    energiereiche Luft von der Druckseite - also von oben - auf die Saugseite
    des Flaps leiten. Die Flapnase gehoert deshalb UEBER die Hinterkante des
    Vorgaengers.

    Gebaut war zuerst die Flugzeuganordnung mit Landeklappe: Die Nase lag
    7,9 mm UNTER der Hinterkante, und die engste Stelle sass auf der
    Unterseite des Hauptelements - ausgerechnet auf dessen Saugseite.
    """
    for winkel in (-14.0, -20.0, -26.0):
        h, f = geo_k.platziere(
            haupt, 250.0, -4.0,
            [geo_k.Kaskadenvorgabe(flap, 0.35, winkel, 0.015, 0.02)])
        assert f.nase[1] > h.hinterkante[1], f"bei {winkel} Grad"


def test_engste_stelle_liegt_auf_der_druckseite(haupt, flap):
    """Der Spalt muss gegen die OBERSEITE des Hauptelements messen. Liegt die
    engste Stelle unten, saugt der Flap an der falschen Seite."""
    h, f = geo_k.platziere(
        haupt, 250.0, -4.0,
        [geo_k.Kaskadenvorgabe(flap, 0.35, -20.0, 0.015, 0.02)])

    abstaende = np.linalg.norm(h.punkte[:, None, :] - f.punkte[None, :, :], axis=2)
    i, _ = np.unravel_index(abstaende.argmin(), abstaende.shape)
    # In Selig-Reihenfolge laeuft der Umlauf von der Hinterkante ueber die
    # Oberseite zur Nase und zurueck - vor dem Nasenindex liegt die Oberseite.
    nase = int(np.argmax(np.linalg.norm(h.punkte - h.punkte[0], axis=1)))
    assert i < nase, "engste Stelle auf der Unterseite - falsche Seite"


def test_flapnase_steht_ueber_dem_ganzen_hauptelement(haupt, flap):
    """Die Hinterkante ist beim Abtriebsprofil der hoechste Punkt. Steht die
    Nase darueber, steht sie ueber dem ganzen Element."""
    h, f = geo_k.platziere(
        haupt, 250.0, -4.0,
        [geo_k.Kaskadenvorgabe(flap, 0.35, -20.0, 0.015, 0.02)])
    assert f.nase[1] >= h.punkte[:, 1].max() - 1e-6


def test_spalt_wird_ueber_den_ganzen_bereich_getroffen(haupt, flap):
    """Die Suche muss stetig bleiben. Zwei Anlaeufe sind gescheitert: einer an
    der Sprungstelle zur Durchdringung, einer am ZWEITEN freien Bereich
    unterhalb der Hinterkante - dort haengt der Flap schlicht darunter."""
    for spalt in (0.008, 0.012, 0.015, 0.02, 0.03, 0.04):
        h, f = geo_k.platziere(
            haupt, 250.0, -4.0,
            [geo_k.Kaskadenvorgabe(flap, 0.35, -20.0, spalt, 0.02)])
        assert f.spalt / 250.0 == pytest.approx(spalt, abs=0.0015), \
            f"Vorgabe {spalt}"


def test_zwei_elemente_bringen_deutlich_mehr(haupt, flap):
    """Nach der Korrektur der Anordnung: rund 40 Prozent mehr Beiwert."""
    _, eins = aero_k.baue_und_rechne(haupt, 250.0, -4.0, [], 15.0)
    _, zwei = aero_k.baue_und_rechne(
        haupt, 250.0, -4.0,
        [geo_k.Kaskadenvorgabe(flap, 0.35, -20.0, 0.015, 0.02)], 15.0)
    assert abs(zwei.cl) / abs(eins.cl) > 1.25


# ------------------------------------- Kombination aus dem Generator holen

KOMBINATIONEN = [
    {"hauptprofil": "fx63137.dat",
     "zeilen": [{"profil": "e58.dat", "sehne": 0.35, "winkel": -18.0,
                 "spalt": 0.015, "ueberlappung": 0.02}]},
    {"hauptprofil": "s1223.dat", "zeilen": []},
    {"hauptprofil": "e423.dat",
     "zeilen": [{"profil": "e58.dat", "sehne": 0.35, "winkel": -18.0,
                 "spalt": 0.015, "ueberlappung": 0.02},
                {"profil": "e58.dat", "sehne": 0.28, "winkel": -14.0,
                 "spalt": 0.015, "ueberlappung": 0.02}]},
]


def _klick_kombination(nr):
    """Simuliert den Klick auf den Uebernehmen-Knopf der Zeile `nr`."""
    from dash import callback_context

    klicks = [0] * len(KOMBINATIONEN)
    klicks[nr] = 1
    original = type(callback_context).triggered_id
    try:
        type(callback_context).triggered_id = property(
            lambda self, _nr=nr: {"typ": "kombination", "nr": _nr})
        return UI._kombination_uebernehmen(klicks, KOMBINATIONEN)
    finally:
        type(callback_context).triggered_id = original


def test_kombination_setzt_tabelle_und_hauptprofil():
    """Jannis: 'wie kann ich Kaskaden kombinationen uebernehmen'. Vorher gab
    es die Liste nur zum Ansehen."""
    zeilen, hauptprofil, meldung = _klick_kombination(0)
    assert hauptprofil == "fx63137.dat"
    assert len(zeilen) == 1
    assert zeilen[0]["winkel"] == pytest.approx(-18.0)


def test_einzelnes_element_leert_die_tabelle():
    """Eine Kombination ohne Flaps muss die Tabelle auch wirklich leeren -
    sonst bleiben Elemente stehen, die nicht mehr zum Vorschlag gehoeren."""
    zeilen, hauptprofil, _ = _klick_kombination(1)
    assert zeilen == []
    assert hauptprofil == "s1223.dat"


def test_dreielementige_kombination_kommt_vollstaendig_an():
    zeilen, hauptprofil, _ = _klick_kombination(2)
    assert hauptprofil == "e423.dat"
    assert [z["winkel"] for z in zeilen] == [-18.0, -14.0]
    # Jedes weitere Element ist kuerzer.
    assert zeilen[1]["sehne"] < zeilen[0]["sehne"]


def test_ohne_kombinationen_aendert_sich_nichts():
    assert all(e is UI.no_update
               for e in UI._kombination_uebernehmen([0], None))


def test_uebernommene_kombination_laesst_sich_rechnen(haupt):
    """Die Probe aufs Exempel: Was uebernommen wurde, muss durch die
    Kaskadenrechnung laufen."""
    zeilen, hauptprofil, _ = _klick_kombination(2)
    stufen = UI.kaskade_aus_tabelle(zeilen)
    profil = UI.profil_aus_datei(hauptprofil)
    elemente = geo_k.platziere(profil, 250.0, -4.0, UI._vorgaben(stufen))
    assert len(elemente) == 3
    beiwert = aero_k.rechne(elemente, 15.0)
    assert beiwert.cl < 0.0            # Abtrieb


# ---------------------------------------------------- Kaskade nach Creo

from aerostudio.formate import export


def test_kaskadenexport_schreibt_je_element_eine_kurve(haupt, flap):
    """Jannis: alles in die GUI, damit es nutzbar ist. Eine Kaskade, die sich
    nicht nach Creo bringen laesst, ist es nicht - vorher schrieb der Export
    nur das Hauptelement."""
    plan = export.plane_kaskade(
        haupt, 250.0, -4.0,
        [geo_k.Kaskadenvorgabe(flap, 0.35, -20.0, 0.015, 0.02),
         geo_k.Kaskadenvorgabe(flap, 0.28, -16.0, 0.015, 0.02)])
    assert plan.ausgabe == "kaskade"
    assert len(plan.sektionen) == 3
    for s in plan.sektionen:
        assert np.allclose(s[0], s[-1])          # geschlossen
        assert np.allclose(s[:, 1], 0.0)         # in der Schnittebene


def test_kaskadenexport_hat_dieselbe_lage_wie_die_anzeige(haupt, flap):
    """Die Anordnung wird mit der Exportpunktzahl neu gesucht. Sie muss dabei
    dieselbe bleiben - sonst sitzt der Flap in Creo woanders als im Bild."""
    vorgaben = [geo_k.Kaskadenvorgabe(flap, 0.35, -20.0, 0.015, 0.02)]
    plan = export.plane_kaskade(haupt, 250.0, -4.0, vorgaben)
    angezeigt = geo_k.platziere(haupt, 250.0, -4.0, vorgaben)

    flap_export = plan.sektionen[1][:, [0, 2]]
    nase_export = flap_export[int(np.argmax(np.linalg.norm(
        flap_export - flap_export[0], axis=1)))]
    assert np.allclose(nase_export, angezeigt[1].nase, atol=0.3)


def test_kaskadenexport_haelt_die_creo_genauigkeit(haupt, flap):
    from aerostudio.geometrie.spline import CREO_GENAUIGKEIT_MM

    plan = export.plane_kaskade(
        haupt, 250.0, -4.0,
        [geo_k.Kaskadenvorgabe(flap, 0.35, -20.0, 0.015, 0.02)])
    for s in plan.sektionen:
        abstand = np.linalg.norm(np.diff(s, axis=0), axis=1)
        assert abstand.min() >= CREO_GENAUIGKEIT_MM


def test_kaskadenexport_ohne_flaps_ist_ein_element(haupt):
    plan = export.plane_kaskade(haupt, 250.0, -4.0, [])
    assert len(plan.sektionen) == 1


def test_elemente_im_export_durchdringen_sich_nicht(haupt, flap):
    plan = export.plane_kaskade(
        haupt, 250.0, -4.0,
        [geo_k.Kaskadenvorgabe(flap, 0.35, -20.0, 0.015, 0.02),
         geo_k.Kaskadenvorgabe(flap, 0.28, -16.0, 0.015, 0.02)])
    ebenen = [s[:, [0, 2]] for s in plan.sektionen]
    for a, b in zip(ebenen[:-1], ebenen[1:]):
        assert not geo_k.schneiden_sich(a, b)


# ----------------------------------------- Geschwindigkeit im Kaskadenreiter

def _text(komponente) -> str:
    if komponente is None:
        return ""
    if isinstance(komponente, str):
        return komponente
    if isinstance(komponente, (list, tuple)):
        return " ".join(_text(k) for k in komponente)
    return _text(getattr(komponente, "children", None))


def test_kaskadenreiter_hat_eigene_geschwindigkeit():
    """Jannis: 'bei welcher Geschwindigkeit wird das berechnet, da ich ja
    selbst nichts angeben kann'. Das einzige Feld stand im Reiter Fluegel und
    wurde hier unsichtbar mitgelesen."""
    assert "kaskadentempo" in UI._SCHRITTE
    layout = _text(UI._ansicht_kaskade())
    assert "Geschwindigkeit" in layout


def test_kaskadenkarte_nennt_kraft_und_geschwindigkeit(haupt, flap):
    elemente = geo_k.platziere(
        haupt, 250.0, -4.0,
        [geo_k.Kaskadenvorgabe(flap, 0.35, -20.0, 0.015, 0.02)])
    b = aero_k.rechne(elemente, 20.0)
    text = _text(UI._kaskadenkarte(elemente, b, 20.0, 600.0))
    assert "20.0 m/s" in text and "72 km/h" in text
    assert " N" in text
    assert "Reynoldszahl" in text


def test_kraft_waechst_mit_dem_quadrat_der_geschwindigkeit(haupt, flap):
    """Staudruck geht mit v^2. Der Beiwert aendert sich ueber die
    Reynoldszahl nur wenig - die Kraft muss also rund vierfach werden."""
    import re

    elemente = geo_k.platziere(
        haupt, 250.0, -4.0,
        [geo_k.Kaskadenvorgabe(flap, 0.35, -20.0, 0.015, 0.02)])

    def kraft(v):
        b = aero_k.rechne(elemente, v)
        text = _text(UI._kaskadenkarte(elemente, b, v, 600.0))
        return float(re.search(r"(-?\d+) N", text).group(1))

    verhaeltnis = kraft(30.0) / kraft(15.0)
    assert verhaeltnis == pytest.approx(4.0, rel=0.25)
