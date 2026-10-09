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


# ------------------------------------------------------ Paket optimieren

def _klick(fn, ausloeser, *args):
    from dash import callback_context
    original = type(callback_context).triggered_id
    try:
        type(callback_context).triggered_id = property(lambda self: ausloeser)
        return fn(*args)
    finally:
        type(callback_context).triggered_id = original


@pytest.fixture
def projekt(tmp_path, monkeypatch, schnell):
    """Ein Projektordner mit dem Heckfluegel-Beispiel, damit auch das
    Speichern der Variante nicht im echten Repo landet."""
    (tmp_path / "specs" / "beispiele").mkdir(parents=True)
    (tmp_path / "specs" / "beispiele" / "heckfluegel.yaml").write_text(
        (UI.PROJEKT / HECK).read_text(encoding="utf-8"), encoding="utf-8")
    daten = _front()
    monkeypatch.setattr(UI, "PROJEKT", tmp_path)
    # Die echte Regelpruefung kostet je Frontvariante eine halbe Sekunde -
    # hier zaehlt der Ablauf, sie selbst hat einen eigenen Test unten.
    monkeypatch.setattr(UI, "_regelverstoesse", lambda element, lage=None: [])
    UI._KENNFELD_ZWISCHENSPEICHER.clear()
    return tmp_path, daten


def test_paket_optimieren_bild_und_datei(projekt):
    ordner, daten = projekt
    bild, status = _klick(UI._paket_doe, "btn-paket", 1, 0, daten, [HECK],
                          60, 20.0, 45.0, "export/p.yaml")
    assert (ordner / "export" / "p.yaml").is_file()
    assert len(bild["data"]) >= 1
    assert "60 Varianten" in _text(status)


def test_paket_ohne_ziel_sagt_was_fehlt(projekt):
    _, daten = projekt
    _, status = _klick(UI._paket_doe, "btn-paket", 1, 0, daten, [HECK],
                       20, 20.0, None, "export/p.yaml")
    assert "Zielbalance" in _text(status)


def test_unerreichbares_ziel_wird_gesagt(projekt):
    """Mit dem Ziel 0 % vorn kommt keine Variante auch nur in die Naehe."""
    _, daten = projekt
    _, status = _klick(UI._paket_doe, "btn-paket", 1, 0, daten, [HECK],
                       20, 20.0, 0.0, "export/p.yaml")
    assert "nicht erreichbar" in _text(status)


def test_kennfelder_werden_zwischengespeichert(projekt, monkeypatch):
    _, daten = projekt
    _klick(UI._paket_doe, "btn-paket", 1, 0, daten, [HECK], 10, 20.0, 45.0, "export/p.yaml")
    aufrufe = []
    monkeypatch.setattr(UI, "_fluegelkraefte",
                        lambda e, v: aufrufe.append(1) or attrappe(e, v))
    _klick(UI._paket_doe, "btn-paket", 2, 0, daten, [HECK], 30, 20.0, 45.0, "export/p.yaml")
    assert aufrufe == []


def test_frontpunkt_zeigen_und_als_spec_speichern(projekt):
    ordner, daten = projekt
    _klick(UI._paket_doe, "btn-paket", 1, 0, daten, [HECK], 30, 20.0, 45.0, "export/p.yaml")
    from aerostudio.aero import doe
    lauf = doe.Lauf.laden(ordner / "export" / "p.yaml")
    nr = lauf.front[0]

    anzeige, wahl = UI._paket_zeigen({"points": [{"customdata": nr}]}, "export/p.yaml")
    assert wahl == nr
    assert "Anstellwinkel" in _text(anzeige)

    meldung = UI._paket_speichern(1, wahl, "export/p.yaml", daten, [HECK])
    datei = ordner / "specs" / "pakete" / f"paket_variante_{nr}.yaml"
    assert datei.is_file(), meldung
    gespeichert = AeroSpec.laden(datei)
    assert len(gespeichert.elemente) == 2
    for pfad, wert in lauf.varianten[nr].items():
        teile = pfad.split(".")
        ist = gespeichert
        for t in teile:
            ist = ist[int(t)] if t.isdigit() else getattr(ist, t)
        assert ist == pytest.approx(wert)


def test_speichern_bei_geaendertem_paket_verweigert(projekt):
    ordner, daten = projekt
    _klick(UI._paket_doe, "btn-paket", 1, 0, daten, [HECK], 10, 20.0, 45.0, "export/p.yaml")
    meldung = UI._paket_speichern(1, 0, "export/p.yaml", daten, [])   # ohne Heck
    assert "Basis-Hash" in meldung
    assert not (ordner / "specs" / "pakete").exists()


def test_speichern_ohne_wahl():
    assert "anklicken" in UI._paket_speichern(1, None, "x.yaml", {}, [])


def test_spec_auswahl_ohne_editor_und_pakete(tmp_path, monkeypatch):
    """Review 29.09.: aktuell.yaml oder eine Paketvariante dazugenommen
    zaehlten die Fluegel doppelt."""
    for name in ("aktuell.yaml", "pakete/paket_variante_3.yaml", "heck.yaml"):
        (tmp_path / "specs" / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "specs" / name).write_text("x")
    monkeypatch.setattr(UI, "PROJEKT", tmp_path)
    assert [o["label"] for o in UI._spec_dateien()] == ["heck.yaml"]


def test_ziellinie_beruecksichtigt_das_widerstandsmoment():
    from aerostudio.aero import gesamt as g
    b = g.Bilanz([g.Beitrag("a", "fluegel", 100.0, 20.0, -500.0, 900.0),
                  g.Beitrag("b", "fluegel", 100.0, 10.0, 1600.0, 900.0)], 1535.0, 20.0)
    ziel = 100.0 * b.balance_vorne
    # Genau am Ziel: Die Linie liegt auf dem Druckpunkt.
    assert b.druckpunkt_fuer(ziel) == pytest.approx(b.druckpunkt_x)


def test_regelverstoesse_eines_fluegels():
    """Die Pruefung, die der Paket-DoE auf der Front laufen laesst."""
    from aerostudio.aero import gesamt
    from aerostudio.spec.modell import Fahrzeuglage

    heck = AeroSpec.laden(UI.PROJEKT / HECK).elemente[0]
    assert UI._regelverstoesse(heck) == []
    # 250 mm hoeher: ueber die 1100 mm hinter der Kopfstuetze.
    zu_hoch = heck.model_copy(update={"pos_z": heck.pos_z + 250.0})
    assert any("T 8.2.1" in v for v in UI._regelverstoesse(zu_hoch))
    # Rake wirkt mit: 3 Grad um die Vorderachse heben den Heckfluegel an.
    lage = gesamt.Lage(Fahrzeuglage(rake_grad=3.0), gesamt.Zustand(), 1535.0)
    assert any("T 8.2.1" in v for v in UI._regelverstoesse(heck, lage))


def test_paket_mit_groesse_aus_der_oberflaeche(projekt):
    ordner, daten = projekt
    _bild, status = _klick(UI._paket_doe, "btn-paket", 1, 0, daten, [HECK],
                           20, 20.0, 45.0, "export/g.yaml", ["ja"])
    from aerostudio.aero import doe
    lauf = doe.Lauf.laden(ordner / "export" / "g.yaml")
    assert any(p.pfad.endswith("halbspannweite") for p in lauf.raum)
    assert "gegen" in _text(status) or "Regelprüfung" in _text(status)
