"""
Tests fuer die Adapterschicht zwischen Werkzeug und Creo-Version.

Die Versionsstrategie im Meilensteinplan verspricht, dass eine neue
Creo-Version nur eine neue Profildatei kostet. Dieses Versprechen haelt genau
so lange, wie keine Aussage doppelt gefuehrt wird - deshalb pruefen diese
Tests vor allem Buchhaltung: dass der Code die Profildatei wirklich liest,
dass er bei einer kaputten Datei nicht raet, und dass ein Befund aus Creo
ueber eine Zeile YAML wirkt statt ueber eine Codeaenderung.
"""

from pathlib import Path

import numpy as np
import pytest
import yaml

from aerostudio.creo import profil as profilmodul
from aerostudio.creo.profil import Creoprofil, VORGABE_FRAME, profil, profile
from aerostudio.formate import ibl


@pytest.fixture(autouse=True)
def _frischer_cache():
    """Das Profil wird gehalten - zwischen den Tests zuruecksetzen."""
    profil.cache_clear()
    yield
    profil.cache_clear()


# ------------------------------------------------------------- Grundlagen

def test_creo8_wird_gelesen():
    p = profil()
    assert p.quelle is not None and p.quelle.name == "creo8.yaml"
    assert p.vollstaendig, f"Maengel im Profil: {p.maengel}"
    assert p.daten["creo"]["datecode"] == "8.0.3.0"


def test_profilordner_enthaelt_creo8():
    assert "creo8" in profile()


def test_frame_kommt_aus_der_datei_und_nicht_aus_dem_code():
    """Der eigentliche Zweck der Adapterschicht.

    Bis M0 stand die Achsabbildung zusaetzlich als STANDARD_FRAME in
    formate/ibl.py. Dieser Test wuerde eine Rueckkehr dorthin bemerken: Er
    aendert die Datei und erwartet, dass der Exporter folgt.
    """
    p = profil()
    quelle = yaml.safe_load(p.quelle.read_text(encoding="utf-8"))
    assert p.frame == {s: str(quelle["export"]["frame_map"][s])
                       for s in VORGABE_FRAME}


def test_exporter_folgt_dem_profil(tmp_path, monkeypatch):
    """Eine geaenderte Profildatei aendert das Exportergebnis."""
    gedreht = {"creo_x": "+x", "creo_y": "-z", "creo_z": "+y"}
    monkeypatch.setattr(
        profilmodul, "profil",
        lambda name="creo8": Creoprofil(id="test", quelle=tmp_path / "x.yaml",
                                        daten={"export": {"frame_map": gedreht}}))

    punkte = np.array([[1.0, 2.0, 3.0]])
    assert np.allclose(ibl.to_creo(punkte), [[1.0, -3.0, 2.0]])


# ------------------------------------------- Ehrlicher Fallback statt Raten

def test_fehlende_datei_faellt_auf_die_vorgabe_und_sagt_es(tmp_path, monkeypatch):
    monkeypatch.setattr(profilmodul, "PROFILORDNER", tmp_path)
    profil.cache_clear()
    p = profil("gibtesnicht")

    assert p.quelle is None
    assert not p.vollstaendig
    assert p.maengel and "fehlt" in p.maengel[0]
    # Geraten wird nicht - es gilt die im Code hinterlegte Vorgabe.
    assert p.frame == VORGABE_FRAME


def test_kaputte_datei_faellt_auf_die_vorgabe_und_sagt_es(tmp_path, monkeypatch):
    (tmp_path / "kaputt.yaml").write_text("das: ist: kein: yaml:\n  - [", encoding="utf-8")
    monkeypatch.setattr(profilmodul, "PROFILORDNER", tmp_path)
    profil.cache_clear()
    p = profil("kaputt")

    assert not p.vollstaendig
    assert p.frame == VORGABE_FRAME


def test_unvollstaendige_abbildung_wird_gemeldet(tmp_path, monkeypatch):
    (tmp_path / "halb.yaml").write_text(
        "export:\n  frame_map:\n    creo_x: '+x'\n", encoding="utf-8")
    monkeypatch.setattr(profilmodul, "PROFILORDNER", tmp_path)
    profil.cache_clear()
    p = profil("halb")

    assert not p.vollstaendig
    assert any("frame_map" in m for m in p.maengel)
    assert p.frame == VORGABE_FRAME


# ----------------------------------------------------- Offene Punkte

def test_offene_punkte_trennt_jetzt_von_vertagt():
    p = profil()
    jetzt = dict(p.offene_punkte("jetzt"))
    vertagt = dict(p.offene_punkte("vertagt"))

    # Der Kommentarbefund ist der offene Kern von M0 - jetzt in den drei
    # Einzelstellen, aus denen der Sammelbefund abgeleitet wird.
    assert "befunde.ibl_kommentar_vor_kopf" in jetzt
    # Was erst M4 und M5 beantworten koennen, darf M0 nicht blockieren.
    assert "koordinatensystem.ausrichtung_im_fahrzeugmodell" in vertagt
    assert "umgebung.java_konflikt_geklaert" in vertagt
    assert not (set(jetzt) & set(vertagt))


def test_beantworteter_befund_verschwindet_aus_der_liste(tmp_path, monkeypatch):
    (tmp_path / "fertig.yaml").write_text(
        "befunde:\n  ibl_kommentar_vor_kopf: true\n", encoding="utf-8")
    monkeypatch.setattr(profilmodul, "PROFILORDNER", tmp_path)
    profil.cache_clear()

    assert profil("fertig").offene_punkte("jetzt") == []


# ------------------------------------------- Kommentare, der M0-Kernbefund

def test_kommentare_werden_geschrieben_solange_der_befund_offen_ist(tmp_path):
    """Status quo: Das Werkzeug schreibt sie seit M1, ein Fehlschlag faellt
    beim Import sofort auf. Deshalb wird nicht vorsorglich abgeschaltet."""
    assert profil().kommentarbefund_offen
    ziel = ibl.write_ibl(tmp_path / "a.ibl", [np.zeros((2, 3))],
                         kommentare=["AERO_SPEC_HASH: abc"])
    assert "! AERO_SPEC_HASH: abc" in ziel.read_text()


def test_negativer_befund_schaltet_kommentare_ab_ohne_codeaenderung(
        tmp_path, monkeypatch):
    """Der Kern der Adapterschicht: Ein Befund aus Creo wirkt ueber YAML."""
    monkeypatch.setattr(
        profilmodul, "profil",
        lambda name="creo8": Creoprofil(
            id="test", quelle=tmp_path / "x.yaml",
            daten={"befunde": {"ibl_kommentar_vor_kopf": False}}))

    ziel = ibl.write_ibl(tmp_path / "b.ibl", [np.zeros((2, 3))],
                         kommentare=["AERO_SPEC_HASH: abc"])
    text = ziel.read_text()
    assert "AERO_SPEC_HASH" not in text
    # Die Geometrie bleibt unberuehrt, und "begin section ! 1" auch: Das
    # Ausrufezeichen dort ist nachweislich unproblematisch.
    assert "begin section ! 1" in text


@pytest.mark.parametrize("ort,erwartet_vor_open", [
    ("vor_kopf", True),
    ("nach_kopf", False),
    ("zwischen", False),
])
def test_kommentarorte(tmp_path, ort, erwartet_vor_open):
    ziel = ibl.write_ibl(tmp_path / f"{ort}.ibl", [np.zeros((2, 3)), np.ones((2, 3))],
                         kommentare=["Marke"], kommentarort=ort)
    zeilen = ziel.read_text().splitlines()
    vor_open = [z for z in zeilen[:zeilen.index("open")]]
    assert bool(vor_open) is erwartet_vor_open

    if ort == "zwischen":
        # Eine Kommentarzeile je Sektion, also zweimal.
        assert sum(1 for z in zeilen if z == "! Marke") == 2
    else:
        assert sum(1 for z in zeilen if z == "! Marke") == 1


def test_unbekannter_kommentarort_wird_abgelehnt(tmp_path):
    with pytest.raises(ValueError, match="Kommentarort"):
        ibl.write_ibl(tmp_path / "x.ibl", [np.zeros((2, 3))],
                      kommentare=["a"], kommentarort="irgendwo")


# ----------------------------------------------------------- M0-Pruefkurven

def _abnahme():
    """Laedt M0_abnahme.py - es liegt neben den Pruefkurven, nicht im Paket."""
    import importlib.util
    pfad = (Path(__file__).parent.parent / "aerostudio" / "creo" / "test"
            / "M0_abnahme.py")
    spec = importlib.util.spec_from_file_location("m0_abnahme", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.mark.parametrize("pruefung", ["pruefe_frame", "pruefe_masse",
                                      "pruefe_lage", "pruefe_pruefkurven"])
def test_abnahme_rechenpruefungen_sind_gruen(pruefung):
    """Was M0_abnahme.py ohne Creo nachrechnet, muss stimmen.

    Sonst faellt es erst auf, wenn jemand vor Creo sitzt und die Abnahme
    laufen laesst - also genau dann, wenn es stoert.
    """
    ok, text = getattr(_abnahme(), pruefung)()
    assert ok, text


def test_versionierte_pruefkurven_sind_aktuell(tmp_path):
    """Erzeugt erzeuge_pruefkurve.py noch genau die Dateien im Repo?

    Dieselbe Buchhaltung wie bei der Paketliste: Sobald Erzeuger und
    erzeugte Datei auseinanderlaufen, prueft in Creo jemand eine Geometrie,
    die das Werkzeug so gar nicht mehr schreiben wuerde.
    """
    import importlib.util
    ordner = Path(__file__).parent.parent / "aerostudio" / "creo" / "test"
    spec = importlib.util.spec_from_file_location(
        "m0_erzeuger", ordner / "erzeuge_pruefkurve.py")
    erzeuger = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(erzeuger)

    sektionen = erzeuger.pruefgeometrie()
    frisch = ibl.write_ibl(tmp_path / "M0_pruefkurve.ibl", sektionen)
    versioniert = ordner / "M0_pruefkurve.ibl"

    assert frisch.read_text() == versioniert.read_text(), (
        "M0_pruefkurve.ibl im Repo weicht von dem ab, was "
        "erzeuge_pruefkurve.py heute schreibt - Skript laufen lassen."
    )

    for ort in erzeuger.KOMMENTARORTE:
        frisch = ibl.write_ibl(tmp_path / f"k_{ort}.ibl", sektionen,
                               kommentare=erzeuger.kommentartext(ort),
                               kommentarort=ort)
        assert frisch.read_text() == (ordner / f"M0_kommentar_{ort}.ibl").read_text(), (
            f"M0_kommentar_{ort}.ibl ist nicht mehr aktuell."
        )


def test_sammelbefund_wird_abgeleitet_nicht_gepflegt(tmp_path, monkeypatch):
    """Was sich ausrechnen laesst, soll niemand eintippen.

    Bis zum 23.09. gab es in creo8.yaml einen vierten Eintrag, der die drei
    Einzelbefunde zusammenfasste. Das war eine weitere Stelle, an der jemand
    ein `false` vergessen konnte, ohne dass es auffiel.
    """
    (tmp_path / "p.yaml").write_text(
        "befunde:\n"
        "  ibl_kommentar_vor_kopf: false\n"
        "  ibl_kommentar_nach_kopf: true\n"
        "  ibl_kommentar_zwischen_sektionen: true\n", encoding="utf-8")
    monkeypatch.setattr(profilmodul, "PROFILORDNER", tmp_path)
    profil.cache_clear()
    p = profil("p")

    # Der Exporter schreibt vor den Kopf - dort steht false, also nein.
    assert p.kommentare_erlaubt is False
    assert not p.kommentarbefund_offen
    # Die anderen beiden bleiben als Rueckfallebene sichtbar.
    assert p.kommentarorte()["ibl_kommentar_nach_kopf"] is True


def test_ein_offener_kommentarort_haelt_den_befund_offen(tmp_path, monkeypatch):
    (tmp_path / "halb.yaml").write_text(
        "befunde:\n"
        "  ibl_kommentar_vor_kopf: true\n"
        "  ibl_kommentar_nach_kopf: AUSFUELLEN\n", encoding="utf-8")
    monkeypatch.setattr(profilmodul, "PROFILORDNER", tmp_path)
    profil.cache_clear()
    p = profil("halb")

    assert p.kommentarbefund_offen
    assert p.kommentarorte()["ibl_kommentar_nach_kopf"] is None
