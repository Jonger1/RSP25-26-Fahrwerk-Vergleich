"""
Tests fuer Endplatte und Footplate.

Der Schwerpunkt liegt nicht darauf, dass eine Platte entsteht - das tut sie
auch, wenn die Masse falsch sind. Geprueft wird, dass sie die Kaskade
tatsaechlich umschliesst, dass sie an der AEUSSEREN Station Mass nimmt und
nicht an der Wurzel, und vor allem: dass der bestehende Regelvalidator sie
sieht. Der letzte Punkt ist der eigentliche Zweck des ganzen Moduls.
"""

import numpy as np
import pytest

from aerostudio.geometrie import endplatte as ep
from aerostudio.geometrie.profil import Profil
from aerostudio.geometrie.spannweite import Schnitt, schnitte
from aerostudio.regeln import Bezugsgeometrie, alle_staende, lade, pruefe_fluegel
from aerostudio.spec.modell import (Endplatte, Footplate, Spannweite,
                                    Stuetzstelle)


@pytest.fixture(scope="module")
def profil():
    return Profil.aus_dat("profile/katalog/e423.dat").gespiegelt()


@pytest.fixture(scope="module")
def bezug():
    return Bezugsgeometrie.aus_datei()


def _fluegel(profil, sehne=250.0, winkel=-4.0, lage=(-600.0, 0.0, 90.0),
             spannweite=None):
    return schnitte(profil, spannweite or Spannweite.frontfluegel_aussen(),
                    sehne, winkel, 40, lage=lage)


# ------------------------------------------------------------------ Masse

def test_platte_umschliesst_die_kaskade(profil):
    stapel = _fluegel(profil)
    vorgabe = Endplatte(ueberstand_vorne=30, ueberstand_hinten=30,
                        ueberstand_oben=40, ueberstand_unten=20)
    m = ep.masse([stapel], vorgabe)
    h = ep.huelle([stapel])

    assert m.x_vorne == pytest.approx(h["x_min"] - 30)
    assert m.x_hinten == pytest.approx(h["x_max"] + 30)
    assert m.z_oben == pytest.approx(h["z_max"] + 40)
    assert m.laenge > 0 and m.hoehe > 0


def test_dicke_traegt_nach_aussen_auf(profil):
    stapel = _fluegel(profil)
    m = ep.masse([stapel], Endplatte(dicke=6.0))

    assert m.y_aussen == pytest.approx(m.y_innen + 6.0)
    # Die Innenseite sitzt am Fluegelende, nicht irgendwo.
    assert m.y_innen == pytest.approx(
        max(float(s.punkte[:, 1].max()) for s in stapel))


def test_platte_wird_am_boden_geklemmt(profil):
    """Eine Platte unter z = 0 wuerde schleifen - das ist keine Eingabe,
    das ist ein Vertipper."""
    stapel = _fluegel(profil, lage=(-600.0, 0.0, 30.0))
    m = ep.masse([stapel], Endplatte(ueberstand_unten=500.0))

    assert m.z_unten == 0.0


def test_mass_nimmt_die_aeussere_station_nicht_die_wurzel(profil):
    """Bei einem verjuengten Fluegel ist das der ganze Unterschied.

    Wuerde die Platte um die Wurzelsehne herum gebaut, waere sie aussen
    sinnlos gross - und wuerde Breiten- und Keep-out-Pruefung mit einem
    Bauteil belasten, das so niemand baut.
    """
    stark_verjuengt = Spannweite(stuetzstellen=[
        Stuetzstelle(y=0.0, sehne=1.0),
        Stuetzstelle(y=600.0, sehne=0.4),
    ], schnitte=13)
    stapel = _fluegel(profil, spannweite=stark_verjuengt)
    m = ep.masse([stapel], Endplatte(ueberstand_vorne=0, ueberstand_hinten=0))

    wurzelsehne = stapel[0].sehne
    aussensehne = stapel[-1].sehne
    assert aussensehne < wurzelsehne * 0.6          # die Vorgabe greift wirklich
    # Die Platte ist nur so lang wie die AEUSSERE Sehne, plus etwas Schraege
    # durch den Anstellwinkel - keinesfalls wie die Wurzel.
    assert m.laenge < wurzelsehne * 0.8


def test_ohne_fluegel_ein_klarer_fehler():
    with pytest.raises(ValueError, match="Endplatte"):
        ep.huelle([])


# ------------------------------------------------------------- Schnitte

def test_zwei_schnitte_ohne_footplate(profil):
    stapel = _fluegel(profil)
    platte = ep.schnitte([stapel], Endplatte(footplate=None))

    assert len(platte) == 2
    y = sorted({float(s.punkte[0, 1]) for s in platte})
    assert y[1] - y[0] == pytest.approx(4.0)      # die Vorgabedicke


def test_footplate_kommt_dazu_und_zeigt_nach_innen(profil):
    stapel = _fluegel(profil)
    ohne = ep.schnitte([stapel], Endplatte(footplate=None))
    mit = ep.schnitte([stapel], Endplatte(
        footplate=Footplate(breite=80.0, hoehe=25.0)))

    assert len(mit) > len(ohne)

    y_platte = min(float(s.punkte[:, 1].min()) for s in ohne)
    y_fuss = min(float(s.punkte[:, 1].min()) for s in mit)
    # Nach INNEN, also zur Fahrzeugmitte - kleineres y.
    assert y_fuss == pytest.approx(y_platte - 80.0)


def test_footplate_breite_null_erzeugt_nichts(profil):
    stapel = _fluegel(profil)
    platte = ep.schnitte([stapel], Endplatte(
        footplate=Footplate(breite=0.0, hoehe=25.0)))

    assert len(platte) == 2


def test_footplate_wird_auf_die_platte_geklemmt(profil):
    """Eine Footplate, die oben aus der Endplatte herausragt, gibt es nicht."""
    # Tief gesetzter Fluegel, damit die Platte niedriger bleibt als die
    # groesste zulaessige Footplate-Hoehe - sonst kaeme die Klemmung gar
    # nicht zum Zug und der Test pruefte nichts.
    stapel = _fluegel(profil, sehne=120.0, lage=(-600.0, 0.0, 40.0))
    vorgabe = Endplatte(ueberstand_oben=10.0, ueberstand_unten=20.0,
                        footplate=Footplate(breite=60.0, hoehe=300.0))
    m = ep.masse([stapel], vorgabe)
    platte = ep.schnitte([stapel], vorgabe)

    assert m.z_oben < 300.0, "Aufbau taugt nicht - die Klemmung greift gar nicht"
    z = np.vstack([s.punkte for s in platte])[:, 2]
    assert z.max() <= m.z_oben + 1e-9


def test_kanten_haben_zwischenpunkte(profil):
    """Ohne sie sieht die Regelpruefung nur die Ecken.

    Eine Keep-out-Zone kann mitten durch eine Kante schneiden, ohne eine Ecke
    zu erwischen - dann meldet der Pruefer gruen, obwohl die Platte im Rad
    steht.
    """
    stapel = _fluegel(profil)
    platte = ep.schnitte([stapel], Endplatte())

    for s in platte:
        assert len(s.punkte) > 4 * 4      # deutlich mehr als vier Ecken


# ------------------------------- Der eigentliche Zweck: die Regeln greifen

def test_endplatte_wird_vom_validator_gesehen(profil, bezug):
    """Die Kernaussage des Moduls.

    Eine Endplatte, die absichtlich in die Keep-out-Zone des Vorderrads
    gebaut wird, muss T 2.1.3 reissen - ohne dass in pruefung.py eine Zeile
    dafuer geschrieben wurde.
    """
    regeln = lade("2026")

    # Der Fluegel allein steht weit vor dem Rad und ist sauber.
    stapel = _fluegel(profil, lage=(-600.0, 0.0, 90.0))
    ohne = [b for b in pruefe_fluegel(stapel, regeln, bezug)
            if b.regel == "T 2.1.3"]
    assert all(b.ok for b in ohne), "Der Fluegel allein sollte sauber sein"

    # Die Platte sitzt bei y = 600 mm und damit lateral genau zwischen
    # Innen- und Aussenebene des Vorderrads. Sie muss nur noch weit genug
    # nach hinten reichen - 200 mm Ueberstand genuegen dafuer, das ist ein
    # Wert, den man tatsaechlich einstellen wuerde.
    platte = ep.schnitte([stapel], Endplatte(
        dicke=4.0, ueberstand_hinten=200.0))
    mit = [b for b in pruefe_fluegel(stapel + platte, regeln, bezug)
           if b.regel == "T 2.1.3"]

    assert any(not b.ok for b in mit), (
        "Eine Endplatte in der Radebene muss T 2.1.3 reissen")


def test_endplatte_zaehlt_fuer_die_breite(profil, bezug):
    """T 8.2.2 misst ueber den Betrag von y - die Plattendicke traegt auf.

    Bewusst HINTER der Vorderachse geprueft: Der Regelstand 2026 begrenzt die
    Breite unter 500 mm nur dort. Ein Frontfluegel vor der Vorderachse wird
    von T 8.2.2 gar nicht erfasst - das ist kein Mangel des Pruefers, sondern
    der Wortlaut der Regel.
    """
    regeln = lade("2026")
    stapel = _fluegel(profil, lage=(400.0, 0.0, 90.0))

    def breiteste(s):
        befunde = [b for b in pruefe_fluegel(s, regeln, bezug)
                   if b.regel == "T 8.2.2"]
        assert befunde, "T 8.2.2 greift hier nicht - Aufbau taugt nicht"
        return max(b.ist for b in befunde)

    schmal = breiteste(stapel)
    dick = breiteste(stapel + ep.schnitte([stapel], Endplatte(dicke=40.0)))

    assert dick == pytest.approx(schmal + 40.0)


def test_footplate_trifft_den_bodenkanal_von_t214(profil, bezug):
    """T 2.1.4 (Entwurf 2027): bodennah muss ein Kanal frei bleiben.

    Die Footplate liegt flach und tief und ist der erste Kandidat, ihn
    zuzusetzen. Wenn der Pruefer das nicht bemerkt, taugt die Geometrie
    nichts.
    """
    regeln = lade("2027")
    if regeln["t2_1_4"] is None:
        pytest.skip("Regelstand ohne T 2.1.4")

    # Ein tief sitzender Fluegel vor der Reifenvorderkante.
    stapel = _fluegel(profil, lage=(-700.0, 0.0, 60.0))
    breit = ep.schnitte([stapel], Endplatte(
        footplate=Footplate(breite=350.0, hoehe=60.0)))

    ohne = [b for b in pruefe_fluegel(stapel, regeln, bezug)
            if b.regel == "T 2.1.4"]
    mit = [b for b in pruefe_fluegel(stapel + breit, regeln, bezug)
           if b.regel == "T 2.1.4"]

    assert ohne and mit
    # Die Footplate verengt den freien Streifen, macht ihn also nicht breiter.
    assert min(b.ist for b in mit) <= min(b.ist for b in ohne) + 1e-9


# ------------------------------------------------- Hoehe fuer den Abtrieb

def test_hoehe_faellt_aus_der_geometrie_ab(profil):
    """Niemand soll die Endplattenhoehe zweimal pflegen muessen."""
    stapel = _fluegel(profil)
    vorgabe = Endplatte(ueberstand_oben=40.0, ueberstand_unten=20.0)

    hoehe = ep.hoehe_fuer_abtrieb([stapel], vorgabe)
    m = ep.masse([stapel], vorgabe)

    assert hoehe == pytest.approx(m.z_oben - m.z_unten)
    assert hoehe > 0.0


def test_groessere_ueberstaende_geben_mehr_hoehe(profil):
    stapel = _fluegel(profil)
    klein = ep.hoehe_fuer_abtrieb([stapel], Endplatte(ueberstand_oben=10.0))
    gross = ep.hoehe_fuer_abtrieb([stapel], Endplatte(ueberstand_oben=120.0))

    assert gross > klein + 100.0


# --------------------------------------------------------------- Kaskade

def test_platte_umschliesst_alle_elemente(profil):
    """Bei einer Kaskade muss die Platte um ALLE Elemente herum gehen.

    Nimmt sie nur am Hauptelement Mass, steht der Flap hinten heraus - und
    zwar genau dort, wo die Laengenbegrenzung T 8.2.3 misst.
    """
    haupt = _fluegel(profil)
    # Ein Flap dahinter: um 200 mm nach hinten und 40 mm nach unten versetzt.
    flap = [Schnitt(s.y, s.sehne * 0.4, s.anstellwinkel,
                    s.punkte * np.array([0.4, 1.0, 0.4])
                    + np.array([200.0, 0.0, -40.0]))
            for s in haupt]

    nur_haupt = ep.masse([haupt], Endplatte(ueberstand_hinten=0.0))
    mit_flap = ep.masse([haupt, flap], Endplatte(ueberstand_hinten=0.0))

    assert mit_flap.x_hinten > nur_haupt.x_hinten
    assert mit_flap.z_unten <= nur_haupt.z_unten


# ----------------------------------------------------------------- Export

def test_export_schreibt_eine_lesbare_ibl(profil, tmp_path):
    from aerostudio.formate import export

    stapel = _fluegel(profil)
    plan = export.plane_endplatte([stapel], Endplatte(
        footplate=Footplate(breite=60.0, hoehe=25.0)))

    assert plan.ausgabe == "endplatte"
    assert not plan.ist_fluegel          # kein Sektionsstapel eines Fluegels
    assert plan.punktzahl > 0

    ziel = export.schreibe(plan, tmp_path / "FW_ENDPL.ibl")
    text = ziel.read_text()
    assert text.startswith("closed") or "\nclosed" in text
    assert "begin section" in text


def test_export_duennt_die_ecken_nicht_aus(profil):
    """Bei geraden Kanten ist jeder weggelassene Punkt eine fehlende Ecke.

    Der Fluegelexport duennt aus, weil dort eine gekruemmte Kontur getroffen
    werden muss. Ein Polygon hat nichts zu treffen - hier waere Ausduennen
    reiner Verlust.
    """
    from aerostudio.formate import export

    stapel = _fluegel(profil)
    vorgabe = Endplatte()
    plan = export.plane_endplatte([stapel], vorgabe)
    roh = ep.schnitte([stapel], vorgabe)

    assert plan.ausgeduennt == 0
    assert [len(s) for s in plan.sektionen] == [len(s.punkte) for s in roh]


# ------------------------------------------------------------ Oberflaeche

def test_geometrie_landet_im_spec():
    from aerostudio.spec.projekt import AeroSpec
    from aerostudio.ui import app as UI
    from tests.test_export_ui import werte_mit

    spec, *_ = UI._profil_aktualisieren(*werte_mit(
        endplattenart="geometrie", ep_dicke=6.0, ep_hinten=45.0,
        ep_fuss_breite=70.0, ep_fuss_hoehe=30.0))

    element = AeroSpec.model_validate(spec).elemente[0]
    assert element.endplatte is not None
    assert element.endplatte.dicke == pytest.approx(6.0)
    assert element.endplatte.ueberstand_hinten == pytest.approx(45.0)
    assert element.endplatte.footplate is not None
    assert element.endplatte.footplate.breite == pytest.approx(70.0)


def test_art_keine_erzeugt_keine_geometrie():
    from aerostudio.spec.projekt import AeroSpec
    from aerostudio.ui import app as UI
    from tests.test_export_ui import werte_mit

    # Die Zahlenfelder stehen auf sinnvollen Werten, die Art aber auf "keine" -
    # dann darf nichts entstehen. Sonst haette jeder Entwurf still eine
    # Endplatte, nur weil die Felder Vorgaben tragen.
    spec, *_ = UI._profil_aktualisieren(*werte_mit(
        endplattenart="keine", ep_dicke=6.0, ep_fuss_breite=70.0))

    element = AeroSpec.model_validate(spec).elemente[0]
    assert element.endplatte is None
    assert element.endplattenhoehe == 0.0


def test_blosse_hoehe_landet_im_spec_und_nicht_im_widget():
    """Der Wert gehoerte bisher nur dem Bedienelement - ein Verstoss gegen
    das Zustandsprinzip, den die Geometrie mit aufgeraeumt hat."""
    from aerostudio.spec.projekt import AeroSpec
    from aerostudio.ui import app as UI
    from tests.test_export_ui import werte_mit

    spec, *_ = UI._profil_aktualisieren(*werte_mit(
        endplattenart="hoehe", endplattenhoehe=180.0))

    element = AeroSpec.model_validate(spec).elemente[0]
    assert element.endplatte is None
    assert element.endplattenhoehe == pytest.approx(180.0)


def test_geometrie_schlaegt_die_blosse_hoehe():
    """Wenn beides angegeben waere, gilt die Geometrie - und zwar an genau
    einer Stelle entschieden, nicht in jedem Callback neu."""
    from aerostudio.geometrie.profil import Profil as P
    from aerostudio.spec.modell import Element, ProfilAusDatei

    element = Element(id="X", profil=ProfilAusDatei(datei="e423.dat"),
                      sehne=250.0, endplattenhoehe=599.0,
                      endplatte=Endplatte(ueberstand_oben=40.0))
    stapel = [_fluegel(P.aus_dat("profile/katalog/e423.dat").gespiegelt())]

    hoehe = ep.wirksame_hoehe(element, stapel)
    assert hoehe != pytest.approx(599.0)
    assert hoehe == pytest.approx(ep.masse(stapel, element.endplatte).hoehe)


def test_masse_werden_in_der_oberflaeche_gezeigt():
    from aerostudio.ui import app as UI
    from tests.test_export_ui import werte_mit

    spec, *_ = UI._profil_aktualisieren(*werte_mit(
        endplattenart="geometrie", ep_fuss_breite=70.0))
    karte = UI._endplattenmasse_zeigen(spec)

    text = str(karte)
    assert "Länge × Höhe" in text
    assert "Footplate nach innen" in text


def test_export_ueber_die_oberflaeche(tmp_path):
    from aerostudio.ui import app as UI
    from tests.test_export_ui import export_mit_klick, werte_mit

    spec, *_ = UI._profil_aktualisieren(*werte_mit(
        endplattenart="geometrie", ep_fuss_breite=70.0))
    export_mit_klick(spec, tmp_path, "endplatte", "FW_E1")

    dateien = list(tmp_path.glob("*.ibl"))
    assert len(dateien) == 1
    # Eigener Dateiname - sonst ueberschriebe die Platte die Fluegeldatei.
    assert "Endplatte" in dateien[0].name
    assert "Endplatte samt Footplate" in dateien[0].read_text()


def test_export_ohne_geometrie_erklaert_sich(tmp_path):
    """Kein Absturz und keine leere Datei, sondern ein brauchbarer Satz."""
    from aerostudio.ui import app as UI
    from tests.test_export_ui import werte_mit

    spec, *_ = UI._profil_aktualisieren(*werte_mit(endplattenart="keine"))
    info, *_ = UI._export(spec, 0.005, str(tmp_path), "endplatte", "FW_E1", 1, 0)

    assert "keine Endplatte" in str(info)
    assert not list(tmp_path.glob("*.ibl"))


def test_endplattenexport_kollidiert_nicht_mit_dem_fluegel(tmp_path):
    from aerostudio.ui import app as UI
    from tests.test_export_ui import export_mit_klick, werte_mit

    spec, *_ = UI._profil_aktualisieren(*werte_mit(endplattenart="geometrie"))
    export_mit_klick(spec, tmp_path, "fluegel", "FW_E1")
    export_mit_klick(spec, tmp_path, "endplatte", "FW_E1")

    assert len(list(tmp_path.glob("*.ibl"))) == 2


def test_ohne_geometrie_bleibt_die_masstafel_leer():
    from aerostudio.ui import app as UI
    from tests.test_export_ui import werte_mit

    spec, *_ = UI._profil_aktualisieren(*werte_mit(endplattenart="keine"))
    assert UI._endplattenmasse_zeigen(spec) == ""


def test_beide_regelstaende_laufen_durch(profil, bezug):
    """Die Platte darf keinen der Regelstaende zum Absturz bringen."""
    stapel = _fluegel(profil)
    platte = ep.schnitte([stapel], Endplatte(
        footplate=Footplate(breite=60.0, hoehe=25.0)))

    for regeln in alle_staende():
        befunde = pruefe_fluegel(stapel + platte, regeln, bezug)
        assert befunde, f"Regelstand {regeln.version} lieferte nichts"
