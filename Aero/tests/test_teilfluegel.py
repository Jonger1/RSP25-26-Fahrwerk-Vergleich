"""
Tests fuer Teilfluegel, die raeumliche Pruefung und die verbesserte
Abtriebsabschaetzung.

Jannis: "dass auch nur Teilfluegel aufgebaut werden koennen", "schaue dir die
Modelle immer im 3D an ... dass die Flaechenverbunde sich nicht schneiden",
"verbessere die Estimation des Downforcerechners".
"""

import numpy as np
import pytest
from pydantic import ValidationError

from aerostudio.aero import boden, kaskade3d, profilpolare as pol
from aerostudio.aero import kaskade as aero_k
from aerostudio.aero import traglinie as tl
from aerostudio.formate import export
from aerostudio.geometrie import kaskade as geo_k
from aerostudio.geometrie import spannweite as spw
from aerostudio.geometrie.profil import Profil
from aerostudio.spec.modell import Kaskadenstufe, Spannweite


@pytest.fixture(scope="module")
def haupt():
    return Profil.aus_dat("profile/katalog/e423.dat").gespiegelt()


@pytest.fixture(scope="module")
def flap():
    return Profil.aus_dat("profile/katalog/e58.dat").gespiegelt()


@pytest.fixture(scope="module")
def weite():
    return Spannweite.frontfluegel_aussen().skaliert(600.0)


LAGE = (-600.0, 0.0, 90.0)


# ------------------------------------------------------------- Datenmodell

def test_teilflap_braucht_einen_sinnvollen_bereich():
    with pytest.raises(ValidationError):
        Kaskadenstufe(y_von=400.0, y_bis=300.0)
    stufe = Kaskadenstufe(y_von=300.0)
    assert stufe.y_bis is None


def test_flap_existiert_nur_in_seinem_bereich(flap):
    v = geo_k.Kaskadenvorgabe(flap, 0.35, -18.0, 0.015, 0.02, y_von=300.0)
    assert not v.aktiv_bei(100.0, 0.0, 600.0)
    assert v.aktiv_bei(300.0, 0.0, 600.0)
    assert v.aktiv_bei(600.0, 0.0, 600.0)
    # Ein Bereich jenseits des Hauptelements existiert gar nicht.
    ausserhalb = geo_k.Kaskadenvorgabe(flap, y_von=700.0)
    assert not ausserhalb.aktiv_bei(650.0, 0.0, 600.0)


def test_winkel_aussen_verdreht_linear(flap):
    v = geo_k.Kaskadenvorgabe(flap, 0.35, -14.0, 0.015, 0.02, y_von=200.0,
                              winkel_aussen=-22.0)
    assert v.winkel_bei(200.0, 0.0, 600.0) == pytest.approx(-14.0)
    assert v.winkel_bei(400.0, 0.0, 600.0) == pytest.approx(-18.0)
    assert v.winkel_bei(600.0, 0.0, 600.0) == pytest.approx(-22.0)


def test_fehlender_vorgaenger_heisst_am_naechsten_element(flap):
    """Fehlt Flap 1 an einer Stelle, sitzt Flap 2 dort am Hauptelement."""
    v = [geo_k.Kaskadenvorgabe(flap, 0.35, -18.0, y_bis=300.0),
         geo_k.Kaskadenvorgabe(flap, 0.25, -12.0)]
    innen = [i for i, _ in geo_k.vorgaben_bei(v, 100.0, 0.0, 600.0)]
    aussen = [i for i, _ in geo_k.vorgaben_bei(v, 500.0, 0.0, 600.0)]
    assert innen == [0, 1] and aussen == [1]


# --------------------------------------------------------------- Geometrie

def test_teilflap_hat_nur_schnitte_in_seinem_bereich(haupt, flap, weite):
    v = [geo_k.Kaskadenvorgabe(flap, 0.35, -18.0, 0.015, 0.02, y_von=250.0)]
    stapel = spw.kaskadenschnitte(haupt, weite, 250.0, -4.0, v, 30, lage=LAGE)
    assert len(stapel[0]) == weite.schnitte
    ys = [s.y for s in stapel[1]]
    assert min(ys) == pytest.approx(250.0) and max(ys) == pytest.approx(600.0)
    assert len(ys) >= 3
    # Innerhalb eines Elements gleiche Punktzahl - sonst verdreht Creo die
    # Flaeche.
    assert len({len(s.punkte) for s in stapel[1]}) == 1


def test_kurzer_teilflap_bekommt_mindestens_drei_schnitte(haupt, flap, weite):
    v = [geo_k.Kaskadenvorgabe(flap, 0.35, -18.0, y_von=560.0, y_bis=590.0)]
    assert len(spw.kaskadenstationen(weite, v)[1]) >= 3


def test_uebliche_teilkaskade_durchdringt_sich_nicht(haupt, flap, weite):
    v = [geo_k.Kaskadenvorgabe(flap, 0.35, -18.0, 0.015, 0.02, y_von=200.0,
                               winkel_aussen=-24.0),
         geo_k.Kaskadenvorgabe(flap, 0.25, -12.0, 0.015, 0.02, y_von=380.0)]
    stapel = spw.kaskadenschnitte(haupt, weite, 250.0, -4.0, v, 30, lage=LAGE)
    pruefung = spw.pruefe_kaskade_raeumlich(stapel, v, weite)
    assert pruefung.durchdringungsfrei
    assert pruefung.kleinster_spalt > 1.0
    # Auch zwischen den Schnitten nachgesehen.
    anzahl_lagen = len({round(s.y, 6) for st in stapel for s in st})
    assert pruefung.stellen > anzahl_lagen


def test_raumpruefung_findet_eine_durchdringung():
    """Zwei Elemente, die sich zwischen zwei Schnitten kreuzen."""
    quadrat = np.array([[1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0],
                        [1.0, 0.0]])

    def schnitt(y, dz):
        p = quadrat + np.array([0.0, dz])
        return spw.Schnitt(y, 1.0, 0.0,
                           np.column_stack([p[:, 0], np.full(len(p), y), p[:, 1]]))

    unten = [spw.Schnitt(0.0, 1.0, 0.0, schnitt(0.0, 0.0).punkte),
             spw.Schnitt(100.0, 1.0, 0.0, schnitt(100.0, 3.0).punkte)]
    oben = [schnitt(0.0, 3.0), schnitt(100.0, 0.0)]
    pruefung = spw.pruefe_kaskade_raeumlich([unten, oben])
    assert not pruefung.durchdringungsfrei
    assert any("zwischen zwei Schnitten" in b.text for b in pruefung.befunde)


def test_raumpruefung_meldet_vorgaengerwechsel(haupt, flap, weite):
    v = [geo_k.Kaskadenvorgabe(flap, 0.35, -18.0, y_bis=300.0),
         geo_k.Kaskadenvorgabe(flap, 0.25, -12.0, y_von=150.0)]
    stapel = spw.kaskadenschnitte(haupt, weite, 250.0, -4.0, v, 25)
    pruefung = spw.pruefe_kaskade_raeumlich(stapel, v, weite)
    assert any("Vorgänger" in b.text for b in pruefung.befunde)


def test_kaskade_bei_zeigt_nur_die_dort_vorhandenen_flaps(haupt, flap, weite):
    v = [geo_k.Kaskadenvorgabe(flap, 0.35, -18.0, y_von=300.0)]
    assert len(spw.kaskade_bei(haupt, weite, 250.0, -4.0, v, 100.0)) == 1
    assert len(spw.kaskade_bei(haupt, weite, 250.0, -4.0, v, 450.0)) == 2


def test_export_schreibt_teilfluegel_mit_eigener_schnittzahl(haupt, flap, weite):
    v = [geo_k.Kaskadenvorgabe(flap, 0.35, -18.0, 0.015, 0.02, y_von=300.0)]
    plan = export.plane_kaskadenfluegel(haupt, weite, 250.0, -4.0, v,
                                        lage=LAGE, toleranz_mm=0.02)
    assert plan.elementanzahl == 2
    assert plan.schnitte_je_element[0] == weite.schnitte
    assert plan.schnitte_je_element[1] < weite.schnitte
    assert len(plan.sektionen) == sum(plan.schnitte_je_element)
    flapschnitte = plan.sektionen[weite.schnitte:]
    assert len({len(s) for s in flapschnitte}) == 1


# --------------------------------------------------------------- Endplatten

def _ebene_platte():
    a = np.linspace(-40.0, 40.0, 1601)
    return pol.Polare(alpha=a, cl=2 * np.pi * np.radians(a),
                      cd=np.zeros_like(a), cm=np.zeros_like(a),
                      vertrauen=np.ones_like(a), reynolds=2.5e5)


class _Rechteck:
    def __init__(self, y, sehne, winkel, hoehe):
        self.y, self.sehne, self.anstellwinkel = y, sehne, winkel
        self.punkte = np.array([[sehne, y, hoehe], [sehne / 2, y, hoehe],
                                [0.0, y, hoehe], [sehne / 2, y, hoehe - 1e-6],
                                [sehne, y, hoehe]])


def _cl_rechteck(streckung, endplatte_mm=0.0):
    sehne = 2.0 / streckung
    stapel = [_Rechteck(y * 1000.0, sehne * 1000.0, 4.0, 50000.0)
              for y in np.linspace(0.0, 1.0, 25)]
    return tl.rechne(stapel, polaren=_ebene_platte(), mit_boden=False,
                     endplatte_mm=endplatte_mm, panels_je_seite=30).cl


@pytest.mark.parametrize("h_b", [0.1, 0.25])
def test_endplatte_wirkt_wie_die_streckung_nach_hoerner(h_b):
    """AR_wirksam = AR (1 + 1,9 h/b) - geprueft an der ebenen Platte."""
    mit = _cl_rechteck(5.0, endplatte_mm=h_b * 2000.0)
    ziel = _cl_rechteck(5.0 * (1.0 + 1.9 * h_b))
    assert mit == pytest.approx(ziel, rel=0.03)
    assert mit > _cl_rechteck(5.0)


def test_endplattenfaktor_ist_auf_den_belegten_bereich_begrenzt():
    assert tl.endplattenfaktor(0.0, 1200.0) == 1.0
    assert tl.endplattenfaktor(2000.0, 1000.0) == pytest.approx(1.0 + 1.9 * 0.4)


# -------------------------------------------------------------------- Boden

def _profil_auf_hoehe(haupt, h_c):
    k = haupt.angestellt(-4.0, 250.0)
    return k + np.array([0.0, h_c * 250.0 - k[:, 1].min()])


def test_kanalfaktor_ist_frei_fast_eins(haupt):
    assert boden.kanalfaktor([_profil_auf_hoehe(haupt, 4.0)]).faktor \
        == pytest.approx(1.0, abs=0.05)


def test_kanalfaktor_waechst_zum_boden(haupt):
    weit = boden.kanalfaktor([_profil_auf_hoehe(haupt, 1.0)]).faktor
    nah = boden.kanalfaktor([_profil_auf_hoehe(haupt, 0.4)]).faktor
    assert nah > weit > 1.0


def test_kanalfaktor_bricht_unter_dem_maximum_ein(haupt):
    """Zerihan & Zhang: unter etwa 10 % Sehne faellt der Abtrieb."""
    am_maximum = boden.kanalfaktor([_profil_auf_hoehe(haupt, 0.12)])
    darunter = boden.kanalfaktor([_profil_auf_hoehe(haupt, 0.04)])
    assert darunter.faktor < am_maximum.faktor
    assert darunter.im_abfall and not am_maximum.im_abfall


def test_reibungsfreier_bodengewinn_wird_nicht_ungebremst_uebernommen(haupt):
    """Reibungsfrei laeuft der Gewinn bei kleinem Abstand ins Unendliche."""
    w = boden.kanalfaktor([_profil_auf_hoehe(haupt, 0.15)])
    assert w.eingefroren
    assert w.faktor < 2.0


# ------------------------------------------------------ Kaskade raeumlich

def test_kaskadenpolare_dreht_die_anstroemung_richtig(haupt):
    """Anstroemung +2 Grad ist dasselbe wie ein 2 Grad flacheres Element."""
    steil = geo_k.platziere(haupt, 250.0, -4.0, [], punkte=60)
    flach = geo_k.platziere(haupt, 250.0, -2.0, [], punkte=60)
    assert aero_k.rechne(steil, 15.0, anstellwinkel=2.0).cl \
        == pytest.approx(aero_k.rechne(flach, 15.0).cl, abs=0.02)


def test_teilflap_liegt_zwischen_einzeln_und_voller_kaskade(haupt, flap, weite):
    def abtrieb(v):
        return kaskade3d.rechne(haupt, weite, 250.0, -4.0, v, 15.0, lage=LAGE,
                                mit_boden=False, stuetzen=3, punkte=40).abtrieb

    voll = [geo_k.Kaskadenvorgabe(flap, 0.35, -14.0, 0.015, 0.02)]
    teil = [geo_k.Kaskadenvorgabe(flap, 0.35, -14.0, 0.015, 0.02, y_von=300.0)]
    einzeln, halb, ganz = abtrieb([]), abtrieb(teil), abtrieb(voll)
    assert einzeln < halb < ganz


def test_abgleichfaktor_skaliert_den_abtrieb(haupt, weite):
    eins = kaskade3d.rechne(haupt, weite, 250.0, -4.0, [], 15.0, lage=LAGE,
                            stuetzen=2, punkte=40)
    mehr = kaskade3d.rechne(haupt, weite, 250.0, -4.0, [], 15.0, lage=LAGE,
                            stuetzen=2, punkte=40, abgleich=1.2)
    assert mehr.abtrieb / eins.abtrieb == pytest.approx(1.2, rel=0.05)


def test_endplatte_hebt_den_abtrieb_der_kaskade(haupt, flap, weite):
    v = [geo_k.Kaskadenvorgabe(flap, 0.35, -14.0, 0.015, 0.02)]
    ohne = kaskade3d.rechne(haupt, weite, 250.0, -4.0, v, 15.0, lage=LAGE,
                            stuetzen=2, punkte=40)
    mit = kaskade3d.rechne(haupt, weite, 250.0, -4.0, v, 15.0, lage=LAGE,
                           stuetzen=2, punkte=40, endplatte_mm=200.0)
    assert mit.abtrieb > ohne.abtrieb
    assert mit.kraefte.endplattenfaktor > 1.2


# ---------------------------------------------------------------- Generator

def test_generator_feinsuche_rechnet_teilfluegel_mit_einlauf(weite):
    from aerostudio.aero import generator

    e = generator.suche(weite, 250.0, -4.0, 15.0, lage=LAGE,
                        haupt=["e423.dat"], flaps=["e58.dat"],
                        elementzahlen=(2,), flapwinkel=(-12.0,),
                        endplatte_mm=150.0, feinsuche=1,
                        innenbereich_mm=150.0)
    assert e.feinsuche and e.bester is not None
    alle = [e.bester] + e.alternativen
    assert all(b.raeumlich for b in alle)
    assert all(b.durchdringungsfrei is not None for b in alle)
    # Der Einlauf zum Unterboden bleibt in JEDER Variante frei.
    for b in alle:
        for z in b.stufen:
            assert z["y_von"] is not None and z["y_von"] >= 150.0
    assert any(z.get("winkel_aussen") is not None
               for b in alle for z in b.stufen)
    # Empfehlbare Varianten stehen vor den anderen.
    marken = [b.empfehlbar for b in alle]
    assert marken == sorted(marken, reverse=True)


# ------------------------------------------------------------- Oberflaeche

from aerostudio.ui import app as UI


def test_tabelle_nimmt_teilfluegel_an():
    stufen = UI.kaskade_aus_tabelle([
        {"profil": "e58.dat", "y_von": 200, "y_bis": "", "winkel_aussen": -24},
        {"profil": "e58.dat", "y_von": 400, "y_bis": 300}])
    assert stufen[0].y_von == pytest.approx(200.0)
    assert stufen[0].y_bis is None
    assert stufen[0].winkel_aussen == pytest.approx(-24.0)
    assert stufen[1].y_bis is None           # verdrehter Bereich abgefangen
    zurueck = UI._kaskadendaten(stufen)
    assert zurueck[0]["y_von"] == pytest.approx(200.0)


def test_flaps_duerfen_naca_profile_sein():
    profil = UI.profil_aus_datei("NACA 6409")
    assert profil.max_dicke == pytest.approx(0.09, abs=0.01)
    assert any(o["value"] == "NACA 6409" for o in UI.flapoptionen())


def test_profil_und_fluegelfelder_erscheinen_auch_im_reiter_kaskade():
    """Jannis: die Funktionen der ersten beiden Seiten auch bei den Kaskaden."""
    stile = UI._reiter_umblenden("kaskade")
    anzahl = len(UI.ANSICHTEN)
    bloecke = dict(zip(UI.BLOECKE, stile[anzahl:]))
    assert bloecke["block-profil"]["display"] == "block"
    assert bloecke["block-geometrie"]["display"] == "block"
    profil = dict(zip(UI.BLOECKE, UI._reiter_umblenden("profil")[anzahl:]))
    assert profil["block-geometrie"]["display"] == "none"
    assert "endplatte" in UI._SCHRITTE


def _spec_mit_teilflap():
    from tests.test_export_ui import WERTE

    werte = list(WERTE)
    werte[-1] = [{"profil": "e58.dat", "sehne": 0.35, "winkel": -18.0,
                  "spalt": 0.015, "ueberlappung": 0.02, "y_von": 250.0}]
    spec, *_ = UI._profil_aktualisieren(*werte)
    return spec


def test_raeumliche_ansicht_zeigt_elemente_und_pruefungen():
    spec = _spec_mit_teilflap()
    figur, karte = UI._kaskade_raeumlich(spec, "kaskade")
    flaechen = [t for t in figur.data if t.type == "surface"]
    assert len(flaechen) == 2
    from tests.test_kaskade import _text
    text = _text(karte)
    assert "schneiden sich nicht" in text
    assert "Fertigung" in text


def test_raeumliche_ansicht_rechnet_nur_im_reiter_kaskade():
    spec = _spec_mit_teilflap()
    assert all(x is UI.no_update for x in UI._kaskade_raeumlich(spec, "profil"))


# ------------------------------------------------ Hoehe = tiefster Punkt

def _element(spec):
    from aerostudio.spec.projekt import AeroSpec
    return AeroSpec.model_validate(spec).elemente[0]


def test_hoehe_ueber_boden_meint_den_tiefsten_punkt():
    """Jannis: "die Hoehe ueber dem Boden waehlt nicht den tiefsten Punkt"."""
    from tests.test_export_ui import WERTE

    spec, *_ = UI._profil_aktualisieren(*WERTE)          # Feld: 90 mm
    element = _element(spec)
    stapel = spw.schnitte(UI.profil_fuer(element), element.spannweite,
                          element.sehne, element.anstellwinkel, 120,
                          lage=UI._lage(element))
    assert min(s.hoehe_min for s in stapel) == pytest.approx(90.0, abs=0.3)


def test_tiefster_punkt_zaehlt_auch_die_flaps():
    element = _element(_spec_mit_teilflap())             # Feld: 90 mm
    stapel = spw.kaskadenschnitte(
        UI.profil_fuer(element), element.spannweite, element.sehne,
        element.anstellwinkel, UI._vorgaben(element.kaskade), 60,
        lage=UI._lage(element))
    assert min(s.hoehe_min for st in stapel for s in st) \
        == pytest.approx(90.0, abs=1.0)


def test_export_und_regelpruefung_sehen_dieselbe_hoehe(tmp_path):
    from tests.test_export_ui import WERTE

    spec, *_ = UI._profil_aktualisieren(*WERTE)
    info, vorschau, figur, status, regelkarte = UI._export(
        spec, 0.005, str(tmp_path), "fluegel", "", 0, 0)
    from tests.test_kaskade import _text
    assert "Bodenfreiheit" in _text(regelkarte)
    element = _element(spec)
    plan = export.plane_fluegel(UI.profil_fuer(element), element.spannweite,
                                element.sehne, element.anstellwinkel,
                                lage=UI._lage(element))
    assert min(sc.hoehe_min for sc in plan.stapel) == \
        pytest.approx(90.0, abs=0.3)
