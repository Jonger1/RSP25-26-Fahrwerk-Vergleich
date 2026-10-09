"""
Tests fuer den Reiter Unterboden (M8).

Gleiches Muster wie bei den Review-Funden: geprueft wird, dass die
Oberflaeche einloest, was sie verspricht - der Haken schaltet den Unterboden
wirklich, ein Klick auf die Front setzt wirklich die Felder, und ein Entwurf
ohne Unterboden behaelt seinen Hash.
"""

import pytest
from dash import callback_context

from aerostudio.aero import doe
from aerostudio.spec.projekt import AeroSpec
from aerostudio.ui import app as UI
from tests.test_export_ui import WERTE, werte_mit


def _spec(**aenderung):
    spec, *_ = UI._profil_aktualisieren(*werte_mit(**aenderung))
    return spec


def _mit_klick(fn, ausloeser, *args):
    original = type(callback_context).triggered_id
    try:
        type(callback_context).triggered_id = property(lambda self: ausloeser)
        return fn(*args)
    finally:
        type(callback_context).triggered_id = original


# ------------------------------------------------------------ Spec

def test_ohne_haken_kein_unterboden_und_alter_hash():
    """Jeder Entwurf von vor M8 muss seinen Hash behalten."""
    spec = AeroSpec.model_validate(_spec())
    assert spec.unterboden is None

    # Dasselbe Spec so, wie es vor M8 aussah: ganz ohne die neuen Schluessel.
    # (Ein erster Anlauf verglich den Entwurf mit sich selbst - der Test
    # waere auch bei gebrochenem Hash gruen gewesen.)
    daten = spec.model_dump(mode="json")
    daten.pop("unterboden")
    daten.pop("lage")
    vor_m8 = AeroSpec.model_validate(daten)
    assert spec.hash() == vor_m8.hash()

    # Und der Hash haengt wirklich an den neuen Feldern, sobald sie etwas
    # sagen - sonst waere der Vergleich oben keiner.
    gekippt = AeroSpec.model_validate(_spec(rake=0.5))
    assert gekippt.hash() != spec.hash()


def test_haken_legt_den_unterboden_an():
    spec = AeroSpec.model_validate(_spec(ub_aktiv=["ja"], ub_diffusor_w=12.5,
                                         rake=0.8, rake_x=1150.0))
    assert spec.unterboden is not None
    assert spec.unterboden.diffusor_winkel == 12.5
    assert spec.lage.rake_grad == 0.8
    assert spec.lage.drehpunkt_x == 1150.0


def test_eingabeliste_passt_weiter_zur_signatur():
    import inspect
    assert len(UI._EINGABEN) == len(inspect.signature(UI._baue_spec).parameters)
    assert len(WERTE) == len(UI._EINGABEN)


# ---------------------------------------------------------- Rechnung

def test_ohne_unterboden_ein_hinweis_statt_bildern():
    karte, schnitt, druck, kennlinie = UI._unterboden_rechnen(_spec(), 20.0)
    assert "Unterboden rechnen" in str(karte)
    assert schnitt["data"] == []


def test_mit_unterboden_karte_und_drei_bilder():
    karte, schnitt, druck, kennlinie = UI._unterboden_rechnen(
        _spec(ub_aktiv=["ja"]), 20.0)
    text = str(karte)
    assert "Abtrieb" in text and "Druckpunkt" in text
    assert "T 2.2.1" in text
    assert "CFD" in text                  # die Grenze des Modells steht dabei
    for fig in (schnitt, druck, kennlinie):
        assert len(fig.data) >= 1


def test_druck_entlang_des_bodens_zeigt_sog_oben():
    _k, _s, druck, _kl = UI._unterboden_rechnen(_spec(ub_aktiv=["ja"]), 20.0)
    assert druck.layout.yaxis.autorange == "reversed"


def test_abgeloester_diffusor_wird_gemeldet():
    karte, schnitt, *_ = UI._unterboden_rechnen(
        _spec(ub_aktiv=["ja"], ub_diffusor_w=22.0), 20.0)
    assert "löst" in str(karte) or "loest" in str(karte)
    assert any("abgelöst" in str(s.name) for s in schnitt.data)


def test_aufsetzen_erklaert_sich():
    karte, *_ = UI._unterboden_rechnen(
        _spec(ub_aktiv=["ja"], rake=-3.0, rake_x=-2000.0), 20.0)
    assert "setzt auf" in str(karte)


# ---------------------------------------------------------------- DoE

def test_doe_aus_der_oberflaeche(tmp_path, monkeypatch):
    monkeypatch.setattr(UI, "PROJEKT", tmp_path)
    fig, status = _mit_klick(UI._doe, "btn-doe", 1, 0, _spec(ub_aktiv=["ja"]),
                             60, 20.0, "doe.yaml")
    assert (tmp_path / "doe.yaml").is_file()
    assert "Pareto-Front" in str(status)
    assert any(s.name == "Pareto-Front" for s in fig.data)


def test_doe_ohne_unterboden_sagt_was_fehlt(tmp_path, monkeypatch):
    monkeypatch.setattr(UI, "PROJEKT", tmp_path)
    _fig, status = _mit_klick(UI._doe, "btn-doe", 1, 0, _spec(), 60, 20.0,
                              "doe.yaml")
    assert "Unterboden rechnen" in str(status)
    assert not (tmp_path / "doe.yaml").exists()


def test_doe_datei_anzeigen_warnt_bei_fremdem_entwurf(tmp_path, monkeypatch):
    """Ein Lauf zu einem anderen Entwurf ist nicht falsch - aber man muss
    wissen, dass nur die variierten Werte uebernommen werden."""
    monkeypatch.setattr(UI, "PROJEKT", tmp_path)
    _mit_klick(UI._doe, "btn-doe", 1, 0, _spec(ub_aktiv=["ja"]), 30, 20.0, "d.yaml")

    anderer = _spec(ub_aktiv=["ja"], ub_breite=900.0)
    _fig, status = _mit_klick(UI._doe, "btn-doe-laden", 0, 1, anderer, 30,
                              20.0, "d.yaml")
    assert "anderen Entwurf" in str(status)


def test_klick_auf_die_front_setzt_die_felder(tmp_path, monkeypatch):
    monkeypatch.setattr(UI, "PROJEKT", tmp_path)
    _mit_klick(UI._doe, "btn-doe", 1, 0, _spec(ub_aktiv=["ja"]), 40, 20.0, "d.yaml")
    lauf = doe.Lauf.laden(tmp_path / "d.yaml")
    nr = lauf.front[0]

    *felder, text = UI._doe_uebernehmen(
        {"points": [{"customdata": nr}]}, "d.yaml")

    erwartet = [round(lauf.varianten[nr][p], 2) for p in UI._DOE_FELDER]
    assert felder == erwartet
    assert f"Variante {nr}" in str(text)


def test_uebernommene_variante_rechnet_wie_im_lauf(tmp_path, monkeypatch):
    """Der ganze Kreis: Front anklicken, Felder setzen, Spec neu bauen - und
    derselbe Abtrieb kommt heraus wie im Lauf. Sonst uebernimmt der Klick
    etwas anderes, als die Front zeigt."""
    monkeypatch.setattr(UI, "PROJEKT", tmp_path)
    _mit_klick(UI._doe, "btn-doe", 1, 0, _spec(ub_aktiv=["ja"]), 40, 20.0, "d.yaml")
    lauf = doe.Lauf.laden(tmp_path / "d.yaml")
    nr = lauf.front[0]
    *felder, _ = UI._doe_uebernehmen({"points": [{"customdata": nr}]}, "d.yaml")

    namen = {"ub-einlass-h": "ub_einlass_h", "ub-kehle-v": "ub_kehle_v",
             "ub-kehle-h": "ub_kehle_h", "ub-diffusor-w": "ub_diffusor_w",
             "ub-diffusor-l": "ub_diffusor_l", "rake": "rake"}
    aenderung = {namen[f]: w for f, w in zip(UI._DOE_FELDER.values(), felder)}
    neu = AeroSpec.model_validate(_spec(ub_aktiv=["ja"], **aenderung))

    ergebnis = doe.unterboden_bewerten(neu)
    # Auf zwei Nachkommastellen gerundet uebernommen - daher nicht exakt.
    assert ergebnis["abtrieb"] == pytest.approx(lauf.ergebnisse[nr]["abtrieb"],
                                                rel=0.01)


def test_klick_ohne_punkt_aendert_nichts():
    *felder, text = UI._doe_uebernehmen(None, "d.yaml")
    assert all(f is UI.no_update for f in felder)
