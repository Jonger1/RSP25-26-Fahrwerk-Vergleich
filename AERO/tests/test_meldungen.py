"""
Tests fuer die Fehleruebersetzung (M6 Punkt 2).

Die wichtigste Eigenschaft ist nicht, dass bekannte Fehler schoen aussehen -
sondern dass UNBEKANNTE nicht verschwinden. Eine Oberflaeche, die Fehler
glattbuegelt, ist schlimmer als eine, die sie roh zeigt: Beim Glattbuegeln
sucht der Anwender den Fehler bei sich.
"""

import pytest
from pydantic import ValidationError

from aerostudio.spec.modell import Element, ProfilAusDatei
from aerostudio.spec.projekt import AeroSpec, SperreBelegt
from aerostudio.ui import meldungen


def _fehler(fn):
    with pytest.raises(Exception) as info:
        fn()
    return info.value


# ------------------------------------------------- Nichts verschwindet

def test_unbekannter_fehler_wird_als_unerwartet_benannt():
    m = meldungen.uebersetze(ZeroDivisionError("division by zero"))

    assert not m.erkannt
    assert "ZeroDivisionError" in m.satz
    assert "Programmfehler" in m.rat


def test_rohe_meldung_bleibt_immer_erreichbar():
    """Auch bei erkannten Fehlern - sonst faellt die Diagnose aus."""
    fehler = FileNotFoundError(2, "No such file", "e999.dat")
    fehler.filename = "e999.dat"

    roh = meldungen.technisch(fehler)
    assert "FileNotFoundError" in roh


def test_kein_beruhigender_allgemeinplatz():
    """"Bitte pruefen Sie Ihre Eingaben" hilft niemandem."""
    m = meldungen.uebersetze(RuntimeError("irgendwas"))
    assert "Eingaben" not in m.satz


# ------------------------------------- Was schon gut ist, bleibt stehen

def test_eigene_meldungen_werden_nicht_ueberschrieben():
    """Unsere ValueError tragen schon einen brauchbaren deutschen Satz."""
    eigen = ValueError("Kein Schnitt vorhanden - ohne Fluegel keine Endplatte.")
    m = meldungen.uebersetze(eigen)

    assert m.satz == "Kein Schnitt vorhanden - ohne Fluegel keine Endplatte."
    assert m.erkannt


def test_sperre_behaelt_ihren_text():
    m = meldungen.uebersetze(SperreBelegt("'fw.yaml' wird bereits bearbeitet."))
    assert "bereits bearbeitet" in m.satz


def test_leerer_valuefehler_faellt_nicht_durch():
    """Ein ValueError ohne Text waere ein leerer Kasten."""
    m = meldungen.uebersetze(ValueError())
    assert not m.erkannt
    assert m.satz


# --------------------------------------------------------- Dateifehler

def test_fehlendes_profil_nennt_den_katalog():
    fehler = _fehler(lambda: __import__(
        "aerostudio.geometrie.profil", fromlist=["Profil"]
    ).Profil.aus_dat("profile/katalog/gibtsnicht.dat"))
    m = meldungen.uebersetze(fehler)

    assert "gibtsnicht.dat" in m.satz
    assert "Katalog" in m.satz or "katalog" in m.rat
    # Der Rat nennt einen ORT, nicht nur eine Aufforderung.
    assert "Reiter Profil" in m.rat


def test_fehlender_zielordner_nennt_den_reiter():
    fehler = FileNotFoundError(2, "No such file", "/nirgends/FW_E1.ibl")
    fehler.filename = "/nirgends/FW_E1.ibl"
    m = meldungen.uebersetze(fehler)

    assert "Zielordner" in m.satz
    assert "Reiter Creo" in m.rat


def test_fehlende_schreibrechte_nennen_die_haeufigste_ursache():
    fehler = PermissionError(13, "Permission denied", "FW_E1.ibl")
    fehler.filename = "FW_E1.ibl"
    m = meldungen.uebersetze(fehler)

    assert "Schreibrechte" in m.satz
    assert "Creo" in m.rat        # die Datei ist meist noch offen


# ------------------------------------------------ Pydantic wird lesbar

def test_unbekanntes_feld_wird_erklaert():
    fehler = _fehler(lambda: AeroSpec.model_validate({"quatsch": 1}))
    m = meldungen.uebersetze(fehler)

    assert "quatsch" in m.satz
    assert "Tippfehler" in m.rat or "ältere" in m.rat
    # Kein englischer Pydantic-Jargon mehr.
    assert "extra_forbidden" not in m.vollstaendig
    assert "validation error" not in m.vollstaendig.lower()


def test_fehlendes_pflichtfeld_wird_erklaert():
    fehler = _fehler(lambda: Element(id="x", sehne=250.0))
    m = meldungen.uebersetze(fehler)

    assert "profil" in m.satz
    assert "fehlt" in m.satz


def test_wert_ausserhalb_der_grenzen_nennt_die_grenze():
    fehler = _fehler(lambda: Element(
        id="x", profil=ProfilAusDatei(datei="e423.dat"), sehne=-5.0))
    m = meldungen.uebersetze(fehler)

    assert "sehne" in m.satz
    assert "0" in m.satz
    assert "größer" in m.satz


def test_falsche_datei_wird_als_solche_erkannt():
    fehler = _fehler(lambda: AeroSpec.model_validate("kein dict"))
    m = meldungen.uebersetze(fehler)

    assert "AeroSpec" in m.satz
    assert "beispiele" in m.rat


# ------------------------------------------------------------ Pakete

def test_fehlendes_neuralfoil_sagt_was_noch_geht():
    m = meldungen.uebersetze(ImportError("No module named 'neuralfoil'"))

    assert "neuralfoil" in m.satz
    # Wichtig: Es sagt, dass Geometrie und Export WEITER gehen.
    assert "Export" in m.rat
    assert "requirements.txt" in m.rat


# ----------------------------------------------------------- Karte

def test_fehlerkarte_zeigt_satz_rat_und_rohmeldung():
    from aerostudio.ui import app as UI

    try:
        raise FileNotFoundError(2, "No such file", "e999.dat")
    except FileNotFoundError as fehler:
        fehler.filename = "e999.dat"
        karte = str(UI._fehlerkarte(fehler))

    assert "e999.dat" in karte
    assert "Reiter Profil" in karte
    assert "FileNotFoundError" in karte      # die rohe Meldung
    assert "Technische Einzelheiten" in karte


def test_fehlerkarte_unterscheidet_eingabe_von_programmfehler():
    from aerostudio.ui import app as UI

    try:
        raise ZeroDivisionError("x")
    except ZeroDivisionError as fehler:
        unerwartet = str(UI._fehlerkarte(fehler))
    try:
        raise ValueError("Der Spalt ist zu klein für diese Sehne.")
    except ValueError as fehler:
        eingabe = str(UI._fehlerkarte(fehler))

    assert "as-status-hinweis" in unerwartet
    assert "as-status-fehler" in eingabe
