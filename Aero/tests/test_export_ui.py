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
from aerostudio.ui import app as UI


# ------------------------------------------------------------------- Export

def _profil() -> Profil:
    return Profil.aus_dat(Path(__file__).resolve().parents[1]
                          / "profile" / "katalog" / "e423.dat")


def test_export_teilt_in_zwei_sektionen():
    """Ober- und Unterseite getrennt - sonst bekommt der Spline an der Nase eine Beule."""
    plan = export.plane_element(_profil(), 250.0, -4.0)
    assert len(plan.sektionen) == 2
    assert all(s.shape[1] == 3 for s in plan.sektionen)


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
    assert text.startswith("open\narclength")
    assert text.count("begin section") == 2
    assert text.count("begin curve") == 2


def test_kommentare_landen_vor_dem_kopf(tmp_path):
    plan = export.plane_element(_profil(), 250.0, 0.0)
    ziel = export.schreibe(plan, tmp_path / "k.ibl", kommentare=["AERO_SPEC_HASH: abc123"])
    zeilen = ziel.read_text(encoding="ascii").splitlines()
    assert zeilen[0].startswith("! AERO_SPEC_HASH")
    assert "open" in zeilen[:5]


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
WERTE = ("datei", "e423.dat", 4.0, 40.0, 12.0, "abtrieb", 250.0, -4.0,
         "prepreg", 0.6, 3.0, 0.2)


def test_hauptcallback_liefert_spec_und_vier_figuren():
    spec, ampel, *figuren = UI._profil_aktualisieren(*WERTE)
    assert AeroSpec.model_validate(spec).elemente[0].sehne == 250.0
    assert len(figuren) == 4
    assert all(hasattr(f, "data") for f in figuren)


def test_naca_zweig_erzeugt_ein_anderes_profil():
    naca = ("naca", None, 6.0, 40.0, 15.0, "abtrieb", 180.0, -8.0,
            "nasslaminat", 1.2, 0.0, 0.2)
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
    info, vorschau, figur, status = UI._export(spec, 0.005, str(tmp_path), 0, 0)
    assert "begin section" in vorschau
    assert hasattr(figur, "data")
    assert status == ""
    assert not list(Path(tmp_path).glob("*.ibl"))


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
