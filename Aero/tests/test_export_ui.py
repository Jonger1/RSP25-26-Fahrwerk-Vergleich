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
from aerostudio.spec.modell import ProfilAusDatei, ProfilNaca
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


def test_unmoegliche_toleranz_meldet_sich_deutlich():
    with pytest.raises(ValueError, match="Toleranz"):
        export.plane_element(_profil(), 250.0, 0.0, toleranz_mm=1e-9)


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

WERTE = ("datei", "e423.dat", 4.0, 40.0, 12.0, 250.0, -4.0, ["ja"],
         "prepreg", 0.6, 3.0, 0.2)


def test_hauptcallback_liefert_spec_und_vier_figuren():
    spec, ampel, *figuren = UI._profil_aktualisieren(*WERTE)
    assert AeroSpec.model_validate(spec).elemente[0].sehne == 250.0
    assert len(figuren) == 4
    assert all(hasattr(f, "data") for f in figuren)


def test_naca_zweig_erzeugt_ein_anderes_profil():
    naca = ("naca", None, 6.0, 40.0, 15.0, 180.0, -8.0, ["ja"],
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
    spec, *_ = UI._profil_aktualisieren(*WERTE)
    info, vorschau = UI._export(spec, 0.005, str(tmp_path), 0)
    assert "begin section" in vorschau
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


def test_element_wird_standardmaessig_gespiegelt():
    """Die Vorgabe muss Abtrieb sein - alles andere waere eine Falle."""
    element = AeroSpec.beispiel().elemente[0]
    assert element.invertiert is True
    x, w = profil_fuer(element).woelbungsverlauf()
    assert np.interp(0.4, x, w) < 0
