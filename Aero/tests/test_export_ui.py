"""Tests fuer Export und Oberflaeche.

Die Callbacks werden direkt als Funktionen aufgerufen, ohne Server. Das geht
nur, weil in ihnen keine Fachlogik steht - genau die Trennung, die das Konzept
verlangt. Bricht ein Test hier, ist meist Logik in den Callback gerutscht.
"""

from pathlib import Path

import numpy as np
import pytest

from aerostudio.formate import export
from aerostudio.formate.ibl import frame_matrix, to_creo, write_ibl
from aerostudio.geometrie.profil import (Profil, aus_quelle, katalogprofile,
                                          profil_fuer)
from aerostudio.spec.modell import ProfilAusDatei, ProfilNaca, Wirkrichtung
from aerostudio.spec.projekt import AeroSpec, SperreBelegt, sperre
from dash import html

from aerostudio.ui import app as UI


# ------------------------------------------------------------------- Export

def _profil() -> Profil:
    return Profil.aus_dat(Path(__file__).resolve().parents[1]
                          / "profile" / "katalog" / "e423.dat")


def test_export_liefert_eine_geschlossene_kurve():
    """Der Normalfall. Zwei Kurven, die sich nur beruehren, sind fuer Creo
    keine geschlossene Kontur - daraus laesst sich nichts extrudieren."""
    plan = export.plane_element(_profil(), 250.0, -4.0)
    assert plan.geschlossen
    assert len(plan.sektionen) == 1
    assert plan.sektionen[0].shape[1] == 3
    # Der Umlauf muss sich schliessen: Anfang und Ende am selben Ort.
    umlauf = plan.sektionen[0]
    assert np.allclose(umlauf[0], umlauf[-1])


def test_geteilter_export_bleibt_moeglich():
    """Die alte Form ist nicht verschwunden - sie braucht weniger Punkte und
    legt den Knick genau auf die Kurvengrenze."""
    plan = export.plane_element(_profil(), 250.0, -4.0, geschlossen=False)
    assert not plan.geschlossen
    assert len(plan.sektionen) == 2
    oben, unten = plan.sektionen
    assert np.allclose(oben[-1], unten[0])       # an der Nase
    assert np.allclose(oben[0], unten[-1])       # an der Hinterkante


def test_geschlossene_kurve_braucht_mehr_punkte():
    """Der Preis der geschlossenen Form: Der Knick an der Hinterkante muss
    durch dichte Stuetzpunkte erzwungen werden statt durch die Kurvengrenze."""
    zu = export.plane_element(_profil(), 250.0, -4.0, geschlossen=True)
    auf = export.plane_element(_profil(), 250.0, -4.0, geschlossen=False)
    assert zu.punktzahl > auf.punktzahl


def test_export_punktzahl_folgt_der_toleranz():
    grob = export.plane_element(_profil(), 250.0, 0.0, toleranz_mm=0.05)
    fein = export.plane_element(_profil(), 250.0, 0.0, toleranz_mm=0.002)
    assert fein.punktzahl > grob.punktzahl


def test_export_sektionen_liegen_in_der_spannweitenebene():
    plan = export.plane_element(_profil(), 250.0, -4.0)
    for s in plan.sektionen:
        assert np.allclose(s[:, 1], 0.0)


def test_geschriebene_ibl_ist_lesbar(tmp_path):
    plan = export.plane_element(_profil(), 250.0, -4.0)
    ziel = export.schreibe(plan, tmp_path / "FW_E1.ibl")
    text = ziel.read_text(encoding="ascii")
    assert text.startswith("closed\narclength")
    assert text.count("begin section") == 1
    assert text.count("begin curve") == 1


def test_geteilte_ibl_traegt_den_offenen_kopf(tmp_path):
    plan = export.plane_element(_profil(), 250.0, -4.0, geschlossen=False)
    text = export.schreibe(plan, tmp_path / "geteilt.ibl").read_text(encoding="ascii")
    assert text.startswith("open\narclength")
    assert text.count("begin section") == 2


def test_geschlossene_ibl_wiederholt_den_ersten_punkt_nicht(tmp_path):
    """Creo schliesst bei "closed" selbst. Stuende der erste Punkt noch einmal
    am Ende, entstuende ein Segment der Laenge null."""
    plan = export.plane_element(_profil(), 250.0, -4.0)
    zeilen = [z for z in export.schreibe(plan, tmp_path / "zu.ibl")
              .read_text(encoding="ascii").splitlines()
              if z[:5].strip().isdigit()]
    erste = zeilen[0].split()[1:]
    letzte = zeilen[-1].split()[1:]
    assert erste != letzte
    assert len(zeilen) == plan.sektionen[0].shape[0] - 1


def test_dateiname_wird_brauchbar_gemacht():
    assert export.dateiname("Frontflügel Hauptelement v3") == \
        "Frontfluegel_Hauptelement_v3.ibl"
    assert export.dateiname("A/B: C") == "A_B_C.ibl"
    assert export.dateiname("") == "profil.ibl"
    assert export.dateiname("   ") == "profil.ibl"


def test_kommentare_landen_vor_dem_kopf(tmp_path):
    plan = export.plane_element(_profil(), 250.0, 0.0)
    ziel = export.schreibe(plan, tmp_path / "k.ibl", kommentare=["AERO_SPEC_HASH: abc123"])
    zeilen = ziel.read_text(encoding="ascii").splitlines()
    assert zeilen[0].startswith("! AERO_SPEC_HASH")
    assert "closed" in zeilen[:5]


def test_zu_enge_toleranz_wird_gelockert_statt_zu_scheitern():
    """Eine etwas groebere Kurve ist besser als gar keine - aber sie muss
    sich als solche zu erkennen geben."""
    plan = export.plane_element(_profil(), 250.0, 0.0, toleranz_mm=0.0005)
    assert plan.gelockert
    assert plan.toleranz_mm > 0.0005
    assert plan.toleranz_gefordert == pytest.approx(0.0005)


def test_erreichbare_toleranz_wird_nicht_gelockert():
    plan = export.plane_element(_profil(), 250.0, 0.0, toleranz_mm=0.005)
    assert not plan.gelockert
    assert plan.toleranz_mm == pytest.approx(0.005)


@pytest.mark.parametrize("sehne", [1.0, 37.5, 253.7, 1200.0, 4999.0])
def test_beliebige_sehnenlaengen_auch_mit_komma(sehne):
    """Die Sehne darf jede Zahl sein - vorher liess das Eingabefeld nur
    Vielfache der Schrittweite zu."""
    plan = export.plane_element(_profil(), sehne, -4.0)
    assert plan.punktzahl > 10
    assert plan.sektionen[0][:, 0].max() == pytest.approx(sehne, rel=0.02)


# ------------------------------------------------------- Koordinatendrehung

def test_drehung_ist_eine_drehung_keine_spiegelung():
    assert round(float(np.linalg.det(frame_matrix()))) == 1


def test_werkzeugachsen_landen_richtig():
    """z nach oben wird zu Y der Vorlage, y nach rechts zu -Z."""
    assert np.allclose(to_creo([[0, 0, 500]])[0], [0, 500, 0])
    assert np.allclose(to_creo([[0, 150, 0]])[0], [0, 0, -150])
    assert np.allclose(to_creo([[200, 0, 0]])[0], [200, 0, 0])


def test_spiegelnde_abbildung_wird_abgelehnt():
    with pytest.raises(ValueError, match="Drehung"):
        frame_matrix({"creo_x": "+x", "creo_y": "+z", "creo_z": "+y"})


# -------------------------------------------------------------------- Spec

def test_hash_ignoriert_zeitstempel_und_bearbeiter():
    """Sonst waere jedes Speichern ein neuer Stand, auch ohne Aenderung."""
    a = AeroSpec.beispiel()
    b = AeroSpec.beispiel()
    b.meta.geaendert = "2030-01-01 00:00"
    b.meta.bearbeiter = "jemand anders"
    assert a.hash() == b.hash()


def test_hash_reagiert_auf_geometrie():
    a = AeroSpec.beispiel()
    b = AeroSpec.beispiel()
    b.elemente[0].sehne += 1.0
    assert a.hash() != b.hash()


def test_spec_ueberlebt_speichern_und_laden(tmp_path):
    a = AeroSpec.beispiel()
    a.speichern(tmp_path / "s.yaml")
    assert AeroSpec.laden(tmp_path / "s.yaml").hash() == a.hash()


def test_sperre_verhindert_zwei_bearbeiter(tmp_path):
    ziel = tmp_path / "s.yaml"
    ziel.write_text("meta: {}", encoding="utf-8")
    with sperre(ziel):
        with pytest.raises(SperreBelegt, match="bearbeitet"):
            with sperre(ziel):
                pass
    with sperre(ziel):        # nach dem Freigeben wieder moeglich
        pass


# --------------------------------------------------------------- Profilquelle

def test_katalog_ist_gefuellt():
    assert len(katalogprofile()) >= 10
    assert "e423.dat" in katalogprofile()


def test_quelle_datei_und_naca():
    assert aus_quelle(ProfilAusDatei(datei="e423.dat")).name == "E423"
    assert aus_quelle(ProfilNaca(woelbung=0.04, woelbungslage=0.4,
                                 dicke=0.12)).name == "NACA 4412"


# ---------------------------------------------------------------- Callbacks

# Reihenfolge wie in _EINGABEN:
# quelle, katalogdatei, naca-woelbung, naca-lage, naca-dicke, wirkrichtung,
# sehne, aoa, verfahren, wandstaerke, kern, klebespalt
# Reihenfolge wie _EINGABEN in app.py. Die letzten vier beschreiben den
# Fluegel: Sektionstabelle, Schnitte, Nase vor der Vorderachse, Hoehe ueber
# Boden. Der Test test_eingabeliste_und_spec_bauer_passen_zusammen wacht
# darueber, dass diese Folge zur Signatur passt.
SEKTIONEN = [
    {"y": 0.0, "sehne": 0.85, "verwindung": -10.0, "z": 0.0, "x": 0.0},
    {"y": 250.0, "sehne": 0.95, "verwindung": -4.0, "z": 0.0, "x": 0.0},
    {"y": 450.0, "sehne": 1.0, "verwindung": 0.0, "z": 8.0, "x": 0.0},
    {"y": 600.0, "sehne": 1.0, "verwindung": 2.0, "z": 22.0, "x": 0.0},
]

WERTE = ("datei", "e423.dat", 4.0, 40.0, 12.0, "abtrieb", 250.0, -4.0,
         "prepreg", 0.6, 3.0, 0.2, "Frontfluegel Hauptelement",
         SEKTIONEN, 13.0, 600.0, 90.0)


def test_hauptcallback_liefert_spec_und_vier_figuren():
    spec, ampel, *figuren = UI._profil_aktualisieren(*WERTE)
    assert AeroSpec.model_validate(spec).elemente[0].sehne == 250.0
    assert len(figuren) == 4
    assert all(hasattr(f, "data") for f in figuren)


def test_naca_zweig_erzeugt_ein_anderes_profil():
    naca = ("naca", None, 6.0, 40.0, 15.0, "abtrieb", 180.0, -8.0,
            "nasslaminat", 1.2, 0.0, 0.2, "NACA-Versuch",
            [{"y": 0.0}, {"y": 500.0}], 9.0, 500.0, 80.0)
    a, *_ = UI._profil_aktualisieren(*WERTE)
    b, *_ = UI._profil_aktualisieren(*naca)
    assert AeroSpec.model_validate(a).hash() != AeroSpec.model_validate(b).hash()


def test_fehlende_datei_bricht_die_oberflaeche_nicht():
    """Eine Fehleingabe darf eine Meldung erzeugen, aber nichts umwerfen."""
    kaputt = list(WERTE)
    kaputt[1] = "gibtsnicht.dat"
    ergebnis = UI._profil_aktualisieren(*kaputt)
    assert ergebnis[0] is UI.no_update          # Spec bleibt unveraendert
    assert ergebnis[1] is not None              # aber es gibt eine Meldung


def test_export_callback_schreibt_ohne_klick_nichts(tmp_path):
    """Vorschau und Diagramm entstehen bei jeder Aenderung, die Datei nur
    auf Klick - sonst laege bei jedem Reglerzucken eine neue IBL auf der Platte."""
    spec, *_ = UI._profil_aktualisieren(*WERTE)
    info, vorschau, figur, status, regeln = UI._export(
        spec, 0.005, str(tmp_path), "kurve", 0, 0)
    assert "begin section" in vorschau
    assert hasattr(figur, "data")
    assert status == ""
    assert not list(Path(tmp_path).glob("*.ibl"))


def test_entwurfsname_landet_im_spec_und_im_dateinamen():
    """Damit sich ein Export spaeter wiederfinden laesst."""
    werte = list(WERTE)
    werte[12] = "Heckflügel Flap 2"
    spec, *_ = UI._profil_aktualisieren(*werte)
    element = AeroSpec.model_validate(spec).elemente[0]
    assert element.name == "Heckflügel Flap 2"
    assert export.dateiname(element.anzeigename) == "Heckfluegel_Flap_2.ibl"


def test_leerer_name_faellt_auf_die_id_zurueck():
    """Eine namenlose Datei darf nie entstehen."""
    werte = list(WERTE)
    werte[12] = "   "
    spec, *_ = UI._profil_aktualisieren(*werte)
    element = AeroSpec.model_validate(spec).elemente[0]
    assert element.anzeigename == element.id


def test_katalognotiz_erscheint_und_faellt_weich_aus():
    """Die Notiz sagt, wofuer ein Profil taugt. Fehlt sie, darf nichts brechen."""
    from aerostudio.geometrie.profil import katalognotiz, katalogoptionen
    assert "Hauptelement" in katalognotiz("e423.dat")["eignung"]
    assert katalognotiz("gibtsnicht.dat") == {}
    optionen = katalogoptionen()
    assert {o["value"] for o in optionen} >= {"e423.dat", "s1223.dat"}
    e423 = next(o for o in optionen if o["value"] == "e423.dat")
    assert "E423" in e423["label"] and "Hauptelement" in e423["label"]


# ------------------------------------------------------------- Spiegelung

def test_spiegeln_kehrt_die_woelbung_um():
    """Ein Abtriebsfluegel ist ein umgedrehtes Auftriebsprofil."""
    p = _profil()
    g = p.gespiegelt()
    x, w = p.woelbungsverlauf()
    xg, wg = g.woelbungsverlauf()
    assert np.interp(0.4, x, w) > 0
    assert np.interp(0.4, xg, wg) == pytest.approx(-np.interp(0.4, x, w), rel=1e-6)


def test_spiegeln_laesst_die_dicke_unveraendert():
    p = _profil()
    assert p.gespiegelt().max_dicke == pytest.approx(p.max_dicke, rel=1e-9)


def test_zweimal_spiegeln_ergibt_das_original():
    p = _profil()
    assert np.allclose(p.gespiegelt().gespiegelt().punkte, p.punkte, atol=1e-9)


def test_vorgabe_ist_abtrieb():
    """Die Vorgabe muss Abtrieb sein - alles andere waere eine Falle."""
    element = AeroSpec.beispiel().elemente[0]
    assert element.wirkrichtung == Wirkrichtung.abtrieb
    x, w = profil_fuer(element).woelbungsverlauf()
    assert np.interp(0.4, x, w) < 0


def test_auftrieb_fuer_bullwings_spiegelt_nicht():
    """Bullwings brauchen Auftrieb - dann bleibt das Katalogprofil, wie es ist."""
    element = AeroSpec.beispiel().elemente[0]
    element.wirkrichtung = Wirkrichtung.auftrieb
    x, w = profil_fuer(element).woelbungsverlauf()
    assert np.interp(0.4, x, w) > 0


# ------------------------------------------------------- Schrittschaltflaechen

def test_plus_und_minus_rechnen_mit_der_schrittweite():
    assert UI.schritt_rechnen(250.0, 5.0, "plus") == pytest.approx(255.0)
    assert UI.schritt_rechnen(250.0, 5.0, "minus") == pytest.approx(245.0)


def test_schritte_halten_die_grenzen_ein():
    assert UI.schritt_rechnen(10.0, 5.0, "minus", minimum=10.0) == 10.0
    assert UI.schritt_rechnen(25.0, 5.0, "plus", maximum=25.0) == 25.0


def test_schrittweite_steckt_nicht_im_eingabefeld():
    """Sonst erklaert HTML jeden Wert fuer ungueltig, der kein Vielfaches ist.

    Genau daran liessen sich Sehnenlaengen wie 253.7 nicht eintragen.
    """
    feld = UI._zahlenfeld("pruef-feld", 100.0, 5.0, 1.0, 500.0)
    eingabe = feld.children[1]
    assert eingabe.step == "any"
    assert UI._SCHRITTE["pruef-feld"] == 5.0


def test_schritte_erzeugen_keine_gleitkommareste():
    """Ohne Runden entstuenden Werte wie 0.30000000000000004 - und die landen
    dann so im Spec und in der IBL."""
    w = 0.2
    for _ in range(6):
        w = UI.schritt_rechnen(w, 0.05, "plus")
    assert w == pytest.approx(0.5)
    assert len(str(w)) < 8


def test_negative_woelbung_ist_erlaubt():
    """Fuer direkt nach unten gewoelbte Profile."""
    p = Profil.aus_naca(-0.06, 0.4, 0.12, n=301)
    x, w = p.woelbungsverlauf()
    assert np.interp(0.4, x, w) < 0


def test_woelbung_ueber_zehn_prozent_geht():
    p = Profil.aus_naca(0.15, 0.4, 0.12, n=301)
    assert p.max_woelbung > 0.13
    assert "NACA-Typ" in p.name        # keine erfundene Ziffernfolge


# --------------------------------------------------------------- Verfahren

def test_verfahren_setzt_eigene_startwerte():
    """Vorher war das Feld eine reine Beschriftung - es stand etwas anderes da,
    gerechnet wurde aber weiter mit denselben Zahlen."""
    prepreg = UI._verfahren_gewaehlt("prepreg", {})
    nass = UI._verfahren_gewaehlt("nasslaminat", {})
    autoklav = UI._verfahren_gewaehlt("autoklav", {})
    assert prepreg != nass != autoklav
    # Handlaminat traegt am dicksten auf, der Autoklav am duennsten.
    assert nass[0] > prepreg[0] > autoklav[0]


def test_eigene_werte_werden_je_verfahren_gemerkt():
    speicher = UI._verfahren_merken(0.9, 5.0, 0.4, "prepreg", {})
    assert UI._verfahren_gewaehlt("prepreg", speicher) == (0.9, 5.0, 0.4)
    # Ein anderes Verfahren bleibt davon unberuehrt.
    assert UI._verfahren_gewaehlt("autoklav", speicher) == (0.4, 3.0, 0.15)


def test_vorgaben_sind_kopien():
    """Sonst veraendert ein Bearbeiter versehentlich die Vorgabe fuer alle."""
    from aerostudio.spec.modell import vorgaben_fuer
    a = vorgaben_fuer("prepreg")
    a["wandstaerke"] = 99.0
    assert vorgaben_fuer("prepreg")["wandstaerke"] == 0.6


def test_unbekanntes_verfahren_faellt_zurueck():
    from aerostudio.spec.modell import vorgaben_fuer
    assert vorgaben_fuer("gibtsnicht") == vorgaben_fuer("unbestimmt")


# ------------------------------------------------- Punktabstand fuer Creo

def test_kein_punktabstand_unter_der_creo_genauigkeit():
    """Die Kosinusverteilung draengt an der Hinterkante Punkte zusammen. Liegen
    zwei naeher als 0,01 mm, haelt Creo sie fuer denselben Punkt und der Spline
    entartet - gemessen beim FX 63-137 bei 250 mm Sehne: 0,0070 mm."""
    from aerostudio.geometrie.spline import CREO_GENAUIGKEIT_MM

    for datei in ("e423.dat", "s1223.dat", "fx63137.dat", "e58.dat"):
        profil = Profil.aus_dat(Path(__file__).resolve().parents[1]
                                / "profile" / "katalog" / datei).gespiegelt()
        for sehne in (30.0, 250.0):
            plan = export.plane_element(profil, sehne, -4.0)
            umlauf = plan.sektionen[0][:-1]        # so steht es in der Datei
            abstand = np.linalg.norm(
                np.diff(np.vstack([umlauf, umlauf[:1]]), axis=0), axis=1)
            assert abstand.min() >= CREO_GENAUIGKEIT_MM, \
                f"{datei} bei {sehne} mm: {abstand.min():.4f} mm"


def test_ausduennen_haelt_die_toleranz_ein():
    """Was ausgeduennt wird, liegt unter der Modellgenauigkeit - es darf die
    Kontur also nicht messbar veraendern."""
    from aerostudio.geometrie.spline import abweichung_zur_kontur

    profil = Profil.aus_dat(Path(__file__).resolve().parents[1]
                            / "profile" / "katalog" / "fx63137.dat").gespiegelt()
    plan = export.plane_element(profil, 250.0, -4.0)
    assert plan.ausgeduennt > 0
    wahr = profil.repanelisiert(1500).angestellt(-4.0, 250.0)
    abw = abweichung_zur_kontur(plan.sektionen[0][:, [0, 2]], wahr,
                                geschlossen=True)
    assert abw < plan.toleranz_mm * 1.1


def test_entdoppeln_behaelt_den_endpunkt_der_offenen_kurve():
    """Bei zwei getrennten Haelften ist der Endpunkt die Nahtstelle zur
    Nachbarkurve - er darf nie wegfallen."""
    from aerostudio.geometrie.spline import entdoppeln

    punkte = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0],
                       [2.0005, 0.0], [2.001, 0.0]])
    duenn = entdoppeln(punkte, 0.01, geschlossen=False)
    assert np.allclose(duenn[0], punkte[0])
    assert np.allclose(duenn[-1], punkte[-1])
    assert len(duenn) < len(punkte)


# ------------------------------------------------------- Drei Ausgabeformen

def _text(komponente) -> str:
    """Sammelt allen Text aus einem Dash-Baum.

    str() auf einer Dash-Komponente kuerzt verschachtelte Kinder weg - ein
    Test, der darauf prueft, bestaetigt dann nur die Kuerzung.
    """
    if komponente is None:
        return ""
    if isinstance(komponente, str):
        return komponente
    if isinstance(komponente, (list, tuple)):
        return " ".join(_text(k) for k in komponente)
    return _text(getattr(komponente, "children", None))


def _werte(index, wert):
    """Eine Stelle der Eingabefolge aendern, der Rest bleibt."""
    werte = list(WERTE)
    werte[index] = wert
    return werte


def test_die_drei_ausgabeformen_liefern_verschiedenes(tmp_path):
    """Eine Kurve, ein Profil aus zwei Kurven, ein Schnittstapel."""
    spec, *_ = UI._profil_aktualisieren(*WERTE)

    kurve = UI._export(spec, 0.005, str(tmp_path), "kurve", 0, 0)
    profil = UI._export(spec, 0.005, str(tmp_path), "profil", 0, 0)
    fluegel = UI._export(spec, 0.005, str(tmp_path), "fluegel", 0, 0)

    assert kurve[1].startswith("closed")
    assert profil[1].startswith("open")
    assert fluegel[1].startswith("closed")
    # Die Vorschau ist gekuerzt; die Zahl der Schnitte steht in der Grafik.
    assert len(fluegel[2].data) == 13


def test_fluegelplan_hat_gleich_aufgebaute_schnitte():
    """Ungleiche Schnitte verdrehen den Verbund in Creo - das ist keine
    Schoenheitsfrage, sondern der haeufigste Grund fuer eine kaputte Flaeche."""
    from aerostudio.spec.modell import Spannweite

    profil = Profil.aus_dat(Path(__file__).resolve().parents[1]
                            / "profile" / "katalog" / "e423.dat").gespiegelt()
    plan = export.plane_fluegel(profil, Spannweite.frontfluegel_aussen(),
                                250.0, -4.0, lage=(-600.0, 0.0, 90.0))
    assert plan.ist_fluegel
    assert len({len(s) for s in plan.sektionen}) == 1
    assert len(plan.sektionen) == 13
    for s in plan.sektionen:
        assert np.allclose(s[0], s[-1])          # jeder Schnitt schliesst sich


def test_fluegelschnitte_halten_den_creo_punktabstand_ein():
    from aerostudio.geometrie.spline import CREO_GENAUIGKEIT_MM
    from aerostudio.spec.modell import Spannweite

    profil = Profil.aus_dat(Path(__file__).resolve().parents[1]
                            / "profile" / "katalog" / "fx63137.dat").gespiegelt()
    plan = export.plane_fluegel(profil, Spannweite.frontfluegel_aussen(),
                                250.0, -4.0, lage=(-600.0, 0.0, 90.0))
    for s in plan.sektionen:
        d = np.linalg.norm(np.diff(s, axis=0), axis=1)
        assert d.min() >= CREO_GENAUIGKEIT_MM


def test_verteilung_laesst_sich_auf_die_spannweite_strecken():
    from aerostudio.spec.modell import Spannweite

    gestreckt = Spannweite.frontfluegel_aussen().skaliert(450.0)
    assert max(s.y for s in gestreckt.stuetzstellen) == pytest.approx(450.0)
    # Der Verlauf bleibt: innen Outwash, aussen die volle Sehne.
    assert gestreckt.stuetzstellen[0].verwindung == pytest.approx(-10.0)
    assert gestreckt.stuetzstellen[-1].sehne == pytest.approx(1.0)


def test_regelkarte_erscheint_nur_beim_fluegel(tmp_path):
    """Ein ebener Schnitt hat keine Lage am Fahrzeug - eine gruene Ampel waere
    dort eine Falschaussage."""
    spec, *_ = UI._profil_aktualisieren(*WERTE)
    ohne = UI._export(spec, 0.005, str(tmp_path), "kurve", 0, 0)[4]
    mit = UI._export(spec, 0.005, str(tmp_path), "fluegel", 0, 0)[4]
    assert _text(ohne) == ""
    assert "Regelprüfung" in _text(mit)
    # Beide Regelstaende stehen nebeneinander.
    assert "2026-v1.1" in _text(mit) and "2027-draft" in _text(mit)


def test_zu_tiefer_fluegel_wird_in_der_oberflaeche_rot(tmp_path):
    """Derselbe Flügel 40 mm tiefer muss die Bodenfreiheit reissen."""
    hoch, *_ = UI._profil_aktualisieren(*_werte(16, 90.0))
    tief, *_ = UI._profil_aktualisieren(*_werte(16, 50.0))
    text_hoch = _text(UI._export(hoch, 0.005, str(tmp_path), "fluegel", 0, 0)[4])
    text_tief = _text(UI._export(tief, 0.005, str(tmp_path), "fluegel", 0, 0)[4])
    assert "Bodenfreiheit" in text_tief
    assert "höher gesetzt" in text_tief
    assert "höher gesetzt" not in text_hoch


def test_eingabeliste_und_spec_bauer_passen_zusammen():
    """Die Kopplung ist rein ueber die Reihenfolge - ein zusaetzliches Feld an
    der falschen Stelle verschiebt stillschweigend alle folgenden Werte. Genau
    das ist beim Bau dieser Tests passiert: Die Hoehe landete in der
    Laengslage, und die Regelampel meldete trotzdem gruen."""
    import inspect

    parameter = inspect.signature(UI._baue_spec).parameters
    assert len(UI._EINGABEN) == len(parameter)
    assert len(WERTE) == len(parameter)


def test_laengslage_wird_nach_vorne_gezaehlt():
    """Im Bedienfeld steht "Nase vor der Vorderachse" - im Werkzeug zeigt x
    nach hinten. Ein Vorzeichenfehler hier legt den Fluegel hinter das Auto."""
    spec, *_ = UI._profil_aktualisieren(*_werte(15, 600.0))
    element = AeroSpec.model_validate(spec).elemente[0]
    assert element.pos_x == pytest.approx(-600.0)


# ------------------------------------------------------- Sektionstabelle

def test_tabelle_wird_zur_spannweite():
    spw = UI.spannweite_aus_tabelle(SEKTIONEN, schnitte=15)
    assert len(spw.stuetzstellen) == 4
    assert spw.schnitte == 15
    assert spw.stuetzstellen[0].verwindung == pytest.approx(-10.0)
    assert spw.stuetzstellen[-1].y == pytest.approx(600.0)


def test_halb_ausgefuellte_zeile_bricht_nichts():
    """Wer eine Sektion hinzufuegt und noch tippt, darf keine Fehlermeldung
    bekommen - die Zeile wird uebersprungen, bis sie brauchbar ist."""
    spw = UI.spannweite_aus_tabelle(
        [{"y": 0.0, "sehne": 1.0}, {"y": None}, {"y": "", "sehne": 2.0},
         {"y": 400.0, "verwindung": -3.0}])
    assert [st.y for st in spw.stuetzstellen] == [0.0, 400.0]
    # Fehlende Spalten fallen auf sinnvolle Vorgaben zurueck.
    assert spw.stuetzstellen[1].sehne == pytest.approx(1.0)
    assert spw.stuetzstellen[1].verwindung == pytest.approx(-3.0)


def test_doppelte_spannweitenposition_macht_die_tabelle_nicht_unbenutzbar():
    """Beim Tippen entsteht kurzzeitig ein Duplikat. Das Datenmodell wuerde es
    ablehnen - hier gewinnt die spaetere Zeile."""
    spw = UI.spannweite_aus_tabelle(
        [{"y": 0.0, "verwindung": -10.0}, {"y": 300.0, "verwindung": -4.0},
         {"y": 300.0, "verwindung": -1.0}])
    assert len(spw.stuetzstellen) == 2
    assert spw.stuetzstellen[-1].verwindung == pytest.approx(-1.0)


def test_leere_tabelle_faellt_auf_die_vorgabe_zurueck():
    assert len(UI.spannweite_aus_tabelle([]).stuetzstellen) >= 2
    assert len(UI.spannweite_aus_tabelle(None).stuetzstellen) >= 2


def test_einzelne_sektion_wird_zu_einem_rechteckfluegel():
    """Eine Stuetzstelle allein hat keine Spannweite. Statt zu scheitern wird
    eine zweite gleiche angelegt."""
    spw = UI.spannweite_aus_tabelle([{"y": 500.0, "sehne": 0.8}])
    assert len(spw.stuetzstellen) == 2
    assert spw.stuetzstellen[0].sehne == pytest.approx(0.8)


def test_negative_spannweitenposition_wird_gespiegelt():
    """Der Stapel beschreibt eine Haelfte. Wer -300 eintippt, meint 300."""
    spw = UI.spannweite_aus_tabelle([{"y": 0.0}, {"y": -300.0}])
    assert all(st.y >= 0 for st in spw.stuetzstellen)


def test_sektion_hinzufuegen_veraendert_den_fluegel_nicht():
    """Eine neue Sektion uebernimmt die Werte der aeussersten. Eine Zeile mit
    Nullen wuerde den Fluegel sofort verbiegen."""
    vorher = UI.spannweite_aus_tabelle(SEKTIONEN)
    erweitert = list(SEKTIONEN) + [dict(SEKTIONEN[-1], y=700.0)]
    nachher = UI.spannweite_aus_tabelle(erweitert)
    assert nachher.stuetzstellen[-1].verwindung == \
        pytest.approx(vorher.stuetzstellen[-1].verwindung)
    assert nachher.stuetzstellen[-1].y == pytest.approx(700.0)


def test_eindrehen_landet_im_spec():
    """Der eigentliche Zweck des Editors: Verwindung je Sektion."""
    sektionen = [{"y": 0.0, "sehne": 1.0, "verwindung": 0.0},
                 {"y": 600.0, "sehne": 1.0, "verwindung": -7.5}]
    spec, *_ = UI._profil_aktualisieren(*_werte(13, sektionen))
    element = AeroSpec.model_validate(spec).elemente[0]
    assert element.spannweite.stuetzstellen[-1].verwindung == pytest.approx(-7.5)


# --------------------------------------------------------- Vorschlag

def test_vorschlag_uebernehmen_setzt_die_felder():
    """Der Anwender soll die Zahlen nicht abtippen muessen."""
    vorschlag = {"sehne": 260.0, "halbspannweite": 695.0,
                 "anstellwinkel": -0.25, "hoehe": 101.9}
    sehne, aoa, weite, hoehe, tabelle = UI._vorschlag_uebernehmen(
        1, vorschlag, SEKTIONEN)
    assert sehne == pytest.approx(260.0)
    assert aoa == pytest.approx(-0.25)
    assert weite == pytest.approx(695.0)
    assert hoehe == pytest.approx(101.9)
    assert max(z["y"] for z in tabelle) == pytest.approx(695.0)


def test_uebernehmen_laesst_die_verwindung_stehen():
    """Nur die Spannweite wird gestreckt. Die Verwindung ist die
    Entwurfsabsicht des Anwenders - die Suche hat sie ohnehin nicht
    angefasst."""
    vorschlag = {"sehne": 200.0, "halbspannweite": 450.0,
                 "anstellwinkel": -5.0, "hoehe": 95.0}
    *_, tabelle = UI._vorschlag_uebernehmen(1, vorschlag, SEKTIONEN)
    assert [z["verwindung"] for z in tabelle] == \
        [s["verwindung"] for s in SEKTIONEN]
    assert max(z["y"] for z in tabelle) == pytest.approx(450.0)


def test_uebernehmen_ohne_vorschlag_aendert_nichts():
    ergebnis = UI._vorschlag_uebernehmen(1, None, SEKTIONEN)
    assert all(e is UI.no_update for e in ergebnis)


# -------------------------------------------- Genauigkeit der Messfunktion

def test_abweichungsmessung_ist_drehinvariant():
    """Eine Drehung darf einen Abstand nicht aendern. Die alte Fassung sah nur
    die zwei Nachbarstrecken des naechsten Abtastpunkts; an der duennen
    Hinterkante des GOE 797 lag der aber auf der GEGENUEBERLIEGENDEN Seite.
    Ergebnis: 0.0037 mm ungedreht, 0.0125 mm nach einer Drehung derselben
    Geometrie - und darauf beruhte die zugesagte Exporttoleranz."""
    import math
    from aerostudio.geometrie.spline import abweichung_zur_kontur

    profil = Profil.aus_dat(Path(__file__).resolve().parents[1]
                            / "profile" / "katalog" / "goe797.dat").gespiegelt()
    kurve = profil.repanelisiert(324).punkte[:-1] * 250.0
    referenz = profil.repanelisiert(2001).punkte[:-1] * 250.0

    def dreh(p, grad):
        c, s = math.cos(math.radians(grad)), math.sin(math.radians(grad))
        return p @ np.array([[c, s], [-s, c]])

    ohne = abweichung_zur_kontur(kurve, referenz, geschlossen=True)
    for grad in (6.0, 37.0, 90.0):
        mit = abweichung_zur_kontur(dreh(kurve, grad), dreh(referenz, grad),
                                    geschlossen=True)
        assert mit == pytest.approx(ohne, rel=1e-6), f"bei {grad} Grad"


def test_zugesagte_toleranz_wird_eingehalten():
    """Der Export nennt eine Toleranz. Sie muss unabhaengig nachmessbar sein -
    auch fuer grob aufgeloeste Quelldateien wie das GOE 797 mit 27 Punkten."""
    from aerostudio.geometrie.spline import abweichung_zur_kontur

    wurzel = Path(__file__).resolve().parents[1] / "profile" / "katalog"
    for datei in ("e423.dat", "s1223.dat", "goe797.dat", "fx63137.dat"):
        profil = Profil.aus_dat(wurzel / datei).gespiegelt()
        for sehne in (250.0, 600.0):
            plan = export.plane_element(profil, sehne, -6.0)
            wahr = profil.repanelisiert(2001).angestellt(-6.0, sehne)
            abw = abweichung_zur_kontur(plan.sektionen[0][:, [0, 2]], wahr,
                                        geschlossen=True)
            assert abw <= plan.toleranz_mm * 1.05, \
                f"{datei} bei {sehne} mm: {abw:.5f} statt {plan.toleranz_mm:.5f}"


def test_punktzahlsuche_nimmt_keinen_gluecksstreffer():
    """Bei grob aufgeloesten Profilen faellt die Abweichung nicht monoton mit
    der Punktzahl. Verlangt werden deshalb zwei aufeinanderfolgende Treffer."""
    from aerostudio.geometrie.spline import punktzahl_fuer_umlauf

    profil = Profil.aus_dat(Path(__file__).resolve().parents[1]
                            / "profile" / "katalog" / "goe797.dat").gespiegelt()

    def umlauf(n):
        return profil.repanelisiert(n).punkte[:-1] * 250.0

    n = punktzahl_fuer_umlauf(umlauf, 0.005)
    assert n is not None
    # Der gefundene Wert und der naechste Schritt muessen beide halten.
    from aerostudio.geometrie.spline import abweichung_zur_kontur
    referenz = umlauf(4001)
    for versuch in (n, n + 4):
        assert abweichung_zur_kontur(umlauf(versuch), referenz,
                                     geschlossen=True) < 0.005


def test_neuralfoil_fehlt_meldet_sich_verstaendlich(monkeypatch):
    """Genau das ist passiert: NeuralFoil lag im System-Python, das Werkzeug
    laeuft aber aus der projekteigenen .venv. In der Oberflaeche stand nur
    eine Fehlermeldung ohne Ausweg."""
    import builtins
    from aerostudio.aero import profilpolare

    profilpolare._rechne.cache_clear()
    echt = builtins.__import__

    def ohne_neuralfoil(name, *rest):
        if name == "neuralfoil":
            raise ImportError("kein neuralfoil")
        return echt(name, *rest)

    monkeypatch.setattr(builtins, "__import__", ohne_neuralfoil)
    profil = Profil.aus_dat(Path(__file__).resolve().parents[1]
                            / "profile" / "katalog" / "e423.dat")
    with pytest.raises(RuntimeError, match="Aero Studio.bat"):
        profilpolare.polare(profil, 250_000.0)
    profilpolare._rechne.cache_clear()


# ------------------------------------------------------- 3D-Ansicht

def test_ganzer_fluegel_wird_als_flaeche_gezeichnet():
    """Ein Stapel Ringe zeigt nicht, ob der Fluegel verdreht ist - eine
    durchgehende Haut schon."""
    from aerostudio.geometrie.spannweite import schnitte
    from aerostudio.spec.modell import Spannweite
    from aerostudio.ui import darstellung

    profil = Profil.aus_dat(Path(__file__).resolve().parents[1]
                            / "profile" / "katalog" / "e423.dat").gespiegelt()
    stapel = schnitte(profil, Spannweite.frontfluegel_aussen(), 250.0, -4.0, 30,
                      lage=(-600.0, 0.0, 110.0))

    flaeche = darstellung.fluegel3d(stapel, "E423", darstellung="flaeche")
    assert [t.type for t in flaeche.data] == ["surface"]

    linien = darstellung.fluegel3d(stapel, "E423", darstellung="schnitte")
    assert len(linien.data) == len(stapel)
    assert all(t.type == "scatter3d" for t in linien.data)

    beides = darstellung.fluegel3d(stapel, "E423", darstellung="beides")
    assert len(beides.data) == len(stapel) + 1


def test_jeder_schnitt_ist_einzeln_abschaltbar():
    """Eigene Spur je Schnitt, sonst laesst sich in der Legende nichts
    einzeln ausblenden."""
    from aerostudio.geometrie.spannweite import schnitte
    from aerostudio.spec.modell import Spannweite
    from aerostudio.ui import darstellung

    profil = Profil.aus_dat(Path(__file__).resolve().parents[1]
                            / "profile" / "katalog" / "e423.dat").gespiegelt()
    stapel = schnitte(profil, Spannweite.gerade(600.0), 250.0, -4.0, 30,
                      lage=(-600.0, 0.0, 110.0))
    fig = darstellung.fluegel3d(stapel, darstellung="schnitte")
    namen = [t.name for t in fig.data]
    assert len(set(namen)) == len(namen)          # jeder Eintrag eindeutig
    assert all("y =" in n for n in namen)


def test_schnittfarben_sind_innen_dunkel():
    """Die alte Anzeige war innen hellgrau auf weissem Grund - praktisch
    unsichtbar. Innen muss dunkel sein."""
    from aerostudio.ui import darstellung

    def helligkeit(farbe):
        werte = [int(v) for v in farbe.removeprefix("rgb(").removesuffix(")").split(",")]
        return sum(werte) / 3.0

    innen = helligkeit(darstellung._schnittfarbe(0.0))
    mitte = helligkeit(darstellung._schnittfarbe(0.5))
    aussen = helligkeit(darstellung._schnittfarbe(1.0))
    assert innen < 80                       # deutlich dunkler als der Grund
    assert innen < mitte < aussen           # durchgehender Verlauf


def test_ungleiche_schnitte_brechen_die_anzeige_nicht():
    """Der Export sorgt fuer gleiche Punktzahlen. Die Anzeige darf sich aber
    nicht darauf verlassen - sonst faellt sie bei einem Zwischenstand aus."""
    import numpy as np
    from aerostudio.geometrie.spannweite import Schnitt
    from aerostudio.ui import darstellung

    stapel = [Schnitt(y=float(y), sehne=200.0, anstellwinkel=-4.0,
                      punkte=np.column_stack([
                          np.linspace(0, 200, n), np.full(n, float(y)),
                          np.linspace(100, 90, n)]))
              for y, n in ((0, 40), (200, 35), (400, 50))]
    fig = darstellung.fluegel3d(stapel, darstellung="flaeche")
    assert len(fig.data) == 1
