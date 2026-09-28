"""
Der Reiter Balance: Front- und Heckfluegel aus getrennten Specs plus
Unterboden, zusammen gerechnet.
"""

import json

import pytest

from aerostudio.aero import gesamt
from aerostudio.aero.profilpolare import verfuegbar
from aerostudio.spec.modell import Unterboden
from aerostudio.spec.projekt import AeroSpec
from aerostudio.ui import app as UI
from tests.test_gesamt import attrappe

FRONT = "specs/beispiele/frontfluegel_zweielementig.yaml"
HECK = "specs/beispiele/heckfluegel.yaml"


def _front(unterboden: bool = True) -> dict:
    spec = AeroSpec.laden(UI.PROJEKT / FRONT)
    if unterboden:
        spec.unterboden = Unterboden()
    return spec.model_dump(mode="json")


def _text(komponente) -> str:
    return json.dumps(komponente.to_plotly_json(), default=str, ensure_ascii=False)


@pytest.fixture
def schnell(monkeypatch):
    """Die Fluegelrechnung durch die Attrappe ersetzen."""
    monkeypatch.setattr(UI, "_fluegelkraefte", attrappe)
    monkeypatch.setattr(UI, "aero_verfuegbar", lambda: True)


def test_reiter_ist_da():
    assert "balance" in UI.ANSICHTEN
    stile = UI._reiter_umblenden("balance")
    assert stile[UI.ANSICHTEN.index("balance")]["display"] == "block"


def test_beispielspecs_stehen_zur_auswahl():
    werte = [o["value"] for o in UI._spec_dateien()]
    assert FRONT in werte and HECK in werte
    assert not any(".historie" in w for w in werte)


def test_heckfluegel_aus_zweitem_spec_kommt_dazu():
    fluegel, ub = UI._gesamtfahrzeug(AeroSpec.model_validate(_front(False)), [HECK])
    assert [e.pos_x for _, e in fluegel] == [-700.0, 1550.0]
    assert ub is None


def test_unterboden_aus_dem_editor_hat_vorrang(tmp_path, monkeypatch):
    anderes = AeroSpec.laden(UI.PROJEKT / HECK)
    anderes.unterboden = Unterboden(breite=300.0)
    anderes.speichern(tmp_path / "h.yaml", historie=False)
    mit, ohne = _front(True), _front(False)
    monkeypatch.setattr(UI, "PROJEKT", tmp_path)

    _, ub = UI._gesamtfahrzeug(AeroSpec.model_validate(mit), ["h.yaml"])
    assert ub.breite == 700.0
    _, ub = UI._gesamtfahrzeug(AeroSpec.model_validate(ohne), ["h.yaml"])
    assert ub.breite == 300.0


def test_karte_und_bilder(schnell):
    karte, bild, wanderung = UI._balance_rechnen(1, _front(), [HECK], 20.0, 45.0, ["ja"])
    text = _text(karte)
    assert "Balance vorn" in text and "Wanderung je Grad" in text
    assert "gegenüber dem Ziel von 45 %" in text
    assert len(bild["data"]) == 3            # FW, RW, Unterboden
    assert len(wanderung["data"]) == 1


def test_ohne_nicken_nur_ein_zustand(schnell):
    karte, _bild, wanderung = UI._balance_rechnen(1, _front(), [], 20.0, None, [])
    assert "Wanderung je Grad" not in _text(karte)
    assert wanderung["data"] == []


def test_fehlende_datei_gibt_eine_fehlerkarte(schnell):
    karte, _, _ = UI._balance_rechnen(1, _front(), ["specs/gibtsnicht.yaml"],
                                      20.0, None, [])
    assert "gibtsnicht" in _text(karte)


@pytest.mark.skipif(not verfuegbar(), reason="NeuralFoil fehlt")
def test_echte_rechnung_front_und_heck():
    """Ein Durchlauf mit der echten Traglinie: Der Frontfluegel liegt vor der
    Vorderachse, der Heckfluegel hinter der Hinterachse - beide ziehen die
    Balance in ihre Richtung, und der Zwischenspeicher liefert beim zweiten
    Mal dieselbe Zahl."""
    spec = AeroSpec.model_validate(_front())
    fluegel, ub = UI._gesamtfahrzeug(spec, [HECK])
    b = gesamt.bilanz(fluegel, ub, spec.lage, UI._fluegelkraefte, 20.0, 1535.0)

    fw, rw, boden = b.beitraege
    assert fw.abtrieb > 0 and rw.abtrieb > 0 and boden.abtrieb > 0
    assert fw.x < 0 < 1535.0 < rw.x
    assert fw.last_vorne(1535.0) > fw.abtrieb      # vor der Achse: mehr als 100 %
    assert rw.last_vorne(1535.0) < 0.0
    assert 0.0 < b.balance_vorne < 1.0

    nochmal = gesamt.bilanz(fluegel, ub, spec.lage, UI._fluegelkraefte, 20.0, 1535.0)
    assert nochmal.abtrieb == b.abtrieb
