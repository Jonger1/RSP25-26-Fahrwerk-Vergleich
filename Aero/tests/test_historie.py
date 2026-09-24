"""
Tests fuer die Spec-Historie (M6 Punkt 3, Undo).

Das Konzept verspricht seit M1: "Rueckgaengig ist ein Sprung zur vorherigen
Version, kein eigener Mechanismus." Das Versprechen war bis zum 24.09.2026
leer - `speichern` ueberschrieb die Datei, und damit gab es keine vorherige
Version mehr.

Geprueft wird hier vor allem, was beim Zurueckspringen schiefgehen kann:
dass die Reihenfolge stimmt, dass ein Fehlgriff sich wieder rueckgaengig
machen laesst, und dass unveraendertes Speichern die Liste nicht zumuellt.
"""

from pathlib import Path

import pytest

from aerostudio.spec.projekt import (AeroSpec, HISTORIE_MAX, historie,
                                     historienordner, zurueck)


@pytest.fixture
def ziel(tmp_path):
    return tmp_path / "fw.yaml"


def _speichern(ziel, sehne: float) -> AeroSpec:
    spec = AeroSpec.laden(ziel) if ziel.is_file() else AeroSpec.beispiel()
    spec.elemente[0].sehne = sehne
    spec.speichern(ziel)
    return spec


# ------------------------------------------------------------ Anlegen

def test_erstes_speichern_legt_keinen_stand_an(ziel):
    """Es gibt noch nichts zu sichern."""
    AeroSpec.beispiel().speichern(ziel)
    assert historie(ziel) == []


def test_jede_aenderung_legt_einen_stand_an(ziel):
    _speichern(ziel, 250.0)
    _speichern(ziel, 300.0)
    _speichern(ziel, 180.0)

    assert len(historie(ziel)) == 2


def test_unveraendertes_speichern_legt_nichts_an(ziel):
    """Sonst stuenden nach einem Nachmittag dreissig gleiche Eintraege da."""
    spec = AeroSpec.beispiel()
    spec.speichern(ziel)
    spec.elemente[0].sehne = 300.0
    spec.speichern(ziel)

    vorher = len(historie(ziel))
    spec.speichern(ziel)
    spec.speichern(ziel)
    assert len(historie(ziel)) == vorher


def test_historie_laesst_sich_abschalten(ziel):
    """Fuer Stapellaeufe - fuenfhundert DoE-Varianten brauchen keine."""
    AeroSpec.beispiel().speichern(ziel)
    spec = AeroSpec.beispiel()
    spec.elemente[0].sehne = 999.0
    spec.speichern(ziel, historie=False)

    assert historie(ziel) == []


def test_historie_liegt_neben_dem_spec(ziel):
    _speichern(ziel, 250.0)
    _speichern(ziel, 300.0)

    ordner = historienordner(ziel)
    assert ordner.is_dir()
    assert ordner.parent.name == ".historie"
    assert ordner.name == "fw"


# --------------------------------------------------------- Reihenfolge

def test_neuester_stand_steht_oben(ziel):
    for sehne in (250.0, 300.0, 180.0, 420.0):
        _speichern(ziel, sehne)

    sehnen = [AeroSpec.laden(s.datei).elemente[0].sehne for s in historie(ziel)]
    assert sehnen == [180.0, 300.0, 250.0]


def test_reihenfolge_haelt_auch_im_selben_augenblick(ziel):
    """Der Grund fuer die Millisekunden im Dateinamen.

    Mit Sekundenaufloesung entschied bei zwei Sicherungen in derselben
    Sekunde die alphabetische Sortierung nach dem HASH, welcher Stand als
    neuerer gilt - also der Zufall. Beim Klicken passiert das leicht.
    """
    for sehne in (250.0, 251.0, 252.0, 253.0, 254.0):
        _speichern(ziel, sehne)     # alles in derselben Sekunde

    sehnen = [AeroSpec.laden(s.datei).elemente[0].sehne for s in historie(ziel)]
    assert sehnen == [253.0, 252.0, 251.0, 250.0]


def test_zeitpunkt_ist_lesbar(ziel):
    _speichern(ziel, 250.0)
    _speichern(ziel, 300.0)

    lesbar = historie(ziel)[0].lesbar
    # "24.09.2026 11:25" - so liest es jemand vor.
    assert len(lesbar) == 16 and lesbar[2] == "." and lesbar[13] == ":"


# ----------------------------------------------------------- Zurueck

def test_zurueck_stellt_den_stand_wieder_her(ziel):
    _speichern(ziel, 250.0)
    _speichern(ziel, 300.0)
    _speichern(ziel, 180.0)

    zurueck(ziel, historie(ziel)[-1].datei)      # der aelteste
    assert AeroSpec.laden(ziel).elemente[0].sehne == 250.0


def test_zurueck_ist_selbst_rueckgaengig_zu_machen(ziel):
    """Ohne das waere ein Fehlgriff endgueltig - und genau davor hat man
    Angst, wenn man den Knopf zum ersten Mal drueckt."""
    _speichern(ziel, 250.0)
    _speichern(ziel, 300.0)

    zurueck(ziel, historie(ziel)[-1].datei)
    assert AeroSpec.laden(ziel).elemente[0].sehne == 250.0

    # Die Fassung mit 300 muss noch da sein.
    sehnen = [AeroSpec.laden(s.datei).elemente[0].sehne for s in historie(ziel)]
    assert 300.0 in sehnen

    zurueck(ziel, historie(ziel)[0].datei)
    assert AeroSpec.laden(ziel).elemente[0].sehne == 300.0


def test_zurueck_liefert_das_geladene_spec(ziel):
    _speichern(ziel, 250.0)
    _speichern(ziel, 300.0)

    spec = zurueck(ziel, historie(ziel)[0].datei)
    assert isinstance(spec, AeroSpec)
    assert spec.elemente[0].sehne == 250.0


def test_verschwundener_stand_meldet_sich_verstaendlich(ziel, tmp_path):
    _speichern(ziel, 250.0)
    with pytest.raises(FileNotFoundError, match="gibt es nicht mehr"):
        zurueck(ziel, tmp_path / "weg.yaml")


# ------------------------------------------------------------ Grenzen

def test_historie_waechst_nicht_unbegrenzt(ziel):
    for i in range(HISTORIE_MAX + 12):
        _speichern(ziel, 200.0 + i)

    assert len(historie(ziel)) == HISTORIE_MAX
    # Weggeworfen wird das AELTESTE, nicht das neueste.
    sehnen = [AeroSpec.laden(s.datei).elemente[0].sehne for s in historie(ziel)]
    assert sehnen[0] > sehnen[-1]


def test_kaputte_datei_wird_trotzdem_gesichert(ziel):
    """Erst recht - sie ist ja gerade das, was man zurueckhaben will."""
    AeroSpec.beispiel().speichern(ziel)
    ziel.write_text("das: ist: kein: gueltiges: spec\n", encoding="utf-8")

    spec = AeroSpec.beispiel()
    spec.elemente[0].sehne = 333.0
    spec.speichern(ziel)

    staende = historie(ziel)
    assert len(staende) == 1
    assert "unlesbar" in staende[0].kennung
    assert Path(staende[0].datei).read_text().startswith("das:")


def test_historie_eines_unbekannten_specs_ist_leer(tmp_path):
    assert historie(tmp_path / "gibtsnicht.yaml") == []


# --------------------------------------------------------- Oberflaeche

def _ui_mit_spec(tmp_path, monkeypatch):
    """Zeigt die Oberflaeche auf ein Spec im Testordner."""
    from aerostudio.ui import app as UI

    ziel = tmp_path / "fw.yaml"
    monkeypatch.setattr(UI, "SPEC_VORGABE", ziel)
    return UI, ziel


def test_ui_zeigt_die_staende(tmp_path, monkeypatch):
    UI, ziel = _ui_mit_spec(tmp_path, monkeypatch)
    _speichern(ziel, 250.0)
    _speichern(ziel, 300.0)

    text = str(UI._historie_zeigen(None, None))
    assert "zurückholen" in text
    assert historie(ziel)[0].kennung in text


def test_ui_ohne_staende_erklaert_sich(tmp_path, monkeypatch):
    UI, ziel = _ui_mit_spec(tmp_path, monkeypatch)
    AeroSpec.beispiel().speichern(ziel)

    assert "Noch keine früheren Stände" in str(UI._historie_zeigen(None, None))


def test_ui_holt_einen_stand_zurueck(tmp_path, monkeypatch):
    from dash import callback_context

    UI, ziel = _ui_mit_spec(tmp_path, monkeypatch)
    _speichern(ziel, 250.0)
    _speichern(ziel, 300.0)

    original = type(callback_context).triggered_id
    try:
        type(callback_context).triggered_id = property(
            lambda self: {"typ": "stand", "nr": 0})
        status = UI._stand_zurueckholen([1])
    finally:
        type(callback_context).triggered_id = original

    assert "zurückgeholt" in str(status)
    assert AeroSpec.laden(ziel).elemente[0].sehne == 250.0
