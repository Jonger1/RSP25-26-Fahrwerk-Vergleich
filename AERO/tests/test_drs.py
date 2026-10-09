"""
DRS: zwei Zustaende desselben Flaps, Familientabelle, Achslast-Vorgabe.
"""

import re
from types import SimpleNamespace

import pytest
from dash import callback_context

from aerostudio.aero import drs, gesamt, paket
from aerostudio.formate import familientabelle, report
from aerostudio.spec.projekt import AeroSpec
from aerostudio.ui import app as UI

HECK = UI.PROJEKT / "specs/beispiele/heckfluegel.yaml"


def _heck(drs_winkel=-8.0, aussen=None) -> AeroSpec:
    spec = AeroSpec.laden(HECK)
    k = spec.elemente[0].kaskade[0]
    spec.elemente[0].kaskade[0] = k.model_copy(update={
        "drs_winkel": drs_winkel, "winkel_aussen": aussen})
    return spec


def flapabhaengig(element, v):
    """Abtrieb und Widerstand wachsen mit dem Flapwinkel (Betrag)."""
    w = sum(abs(k.winkel) for k in element.kaskade)
    return SimpleNamespace(abtrieb=50.0 + 2.0 * w, widerstand=5.0 + 0.5 * w,
                           streifen=[], auftrieb_lokal=[])


def _klick(fn, ausloeser, *args):
    original = type(callback_context).triggered_id
    try:
        type(callback_context).triggered_id = property(lambda self: ausloeser)
        return fn(*args)
    finally:
        type(callback_context).triggered_id = original


# ------------------------------------------------------------- Modell

def test_ohne_drs_bleibt_der_hash():
    """Sonst bekaeme jedes aeltere Spec einen neuen Hash - und der steht als
    AERO_SPEC_HASH in jeder exportierten IBL."""
    spec = AeroSpec.laden(HECK)
    roh = spec.model_dump(mode="json")
    for e in roh["elemente"]:
        for k in e["kaskade"]:
            k.pop("drs_winkel", None)
    assert AeroSpec.model_validate(roh).hash() == spec.hash()
    assert _heck().hash() != spec.hash()


def test_offen_setzt_den_drs_winkel():
    spec = _heck(-8.0)
    zu = spec.elemente[0].kaskade[0].winkel
    auf = drs.offen(spec).elemente[0].kaskade[0]
    assert auf.winkel == -8.0
    assert spec.elemente[0].kaskade[0].winkel == zu      # Original unberuehrt


def test_verwundener_flap_dreht_als_ganzes():
    spec = _heck(-8.0, aussen=-30.0)
    zu = spec.elemente[0].kaskade[0]
    auf = drs.element_offen(spec.elemente[0]).kaskade[0]
    assert auf.winkel_aussen - auf.winkel == pytest.approx(zu.winkel_aussen - zu.winkel)


def test_ohne_drs_ist_offen_dasselbe():
    spec = AeroSpec.laden(HECK)
    assert not drs.hat_drs(spec.elemente[0])
    assert drs.element_offen(spec.elemente[0]) is spec.elemente[0]


def test_vergleich():
    v = drs.vergleich(_heck(-8.0).elemente[0], flapabhaengig)
    assert v.auf_abtrieb < v.zu_abtrieb and v.auf_widerstand < v.zu_widerstand
    assert 0 < v.abtrieb_verlust < 1 and 0 < v.widerstand_gewinn < 1


# ------------------------------------------------------ Familientabelle

def test_familientabelle(tmp_path):
    kopf, zeilen = familientabelle.tabelle(_heck(-8.0, aussen=-30.0))
    zu = _heck().elemente[0].kaskade[0].winkel
    assert kopf == ["Instanz", "RW_E2_AOA", "RW_E2_AOA_AUSSEN"]
    assert zeilen[0] == ["RW_DRS_ZU", zu, -30.0]
    assert zeilen[1] == ["RW_DRS_AUF", -8.0, pytest.approx(-30.0 + (-8.0 - zu))]

    pfad = familientabelle.schreiben(_heck(), tmp_path / "f.txt")
    zeilen_text = pfad.read_text().splitlines()
    assert zeilen_text[0].split("\t") == ["Instanz", "RW_E2_AOA"]
    assert re.fullmatch(r"RW_DRS_AUF\t-8\.00", zeilen_text[2])


def test_familientabelle_ohne_drs_sagt_was_fehlt(tmp_path):
    with pytest.raises(ValueError, match="DRS offen"):
        familientabelle.schreiben(AeroSpec.laden(HECK), tmp_path / "f.txt")


# ---------------------------------------------------------- Oberflaeche

def test_tabellenspalte_hin_und_zurueck():
    stufen = _heck(-8.0).elemente[0].kaskade
    zurueck = UI.kaskade_aus_tabelle(UI._kaskadendaten(stufen))
    assert zurueck[0].drs_winkel == -8.0
    leer = UI.kaskade_aus_tabelle([{**UI._kaskadendaten(stufen)[0], "drs_winkel": ""}])
    assert leer[0].drs_winkel is None


def test_drs_knopf_familientabelle(tmp_path, monkeypatch):
    daten = _heck().model_dump(mode="json")
    monkeypatch.setattr(UI, "PROJEKT", tmp_path)
    karte = _klick(UI._drs, "btn-familie", 0, 1, daten, 20.0)
    assert list(tmp_path.rglob("familientabelle_drs_RW.txt"))
    assert "RW_DRS_AUF" in str(karte.to_plotly_json())


def test_drs_knopf_vergleich(monkeypatch):
    monkeypatch.setattr(UI, "_fluegelkraefte", flapabhaengig)
    monkeypatch.setattr(UI, "aero_verfuegbar", lambda: True)
    karte = _klick(UI._drs, "btn-drs", 1, 0, _heck().model_dump(mode="json"), 20.0)
    text = str(karte.to_plotly_json())
    assert "DRS offen" in text and "Abtrieb" in text


def test_drs_knopf_ohne_drs():
    karte = _klick(UI._drs, "btn-drs", 1, 0,
                   AeroSpec.laden(HECK).model_dump(mode="json"), 20.0)
    assert "DRS offen" in str(karte.to_plotly_json())


def test_balance_mit_offenem_drs_verschiebt_nach_vorn(monkeypatch):
    """Heckfluegel verliert Abtrieb -> Balance wandert nach vorn."""
    monkeypatch.setattr(UI, "_fluegelkraefte", flapabhaengig)
    monkeypatch.setattr(UI, "aero_verfuegbar", lambda: True)
    front = AeroSpec.laden(UI.PROJEKT / "specs/beispiele/frontfluegel_zweielementig.yaml")
    heck = _heck(-4.0)
    fluegel = paket.fluegel_des_pakets(paket.bauen(front, [heck]))
    zu = gesamt.bilanz(fluegel, None, front.lage, flapabhaengig, radstand=1535.0)
    auf = gesamt.bilanz([(n, drs.element_offen(e)) for n, e in fluegel], None,
                        front.lage, flapabhaengig, radstand=1535.0)
    assert auf.balance_vorne > zu.balance_vorne

    karte, _, _ = UI._balance_rechnen(1, front.model_dump(mode="json"), [],
                                      20.0, None, [], ["ja"])
    assert "DRS offen" in str(karte.to_plotly_json())


# --------------------------------------------------------------- Report

def test_report_prueft_auch_den_offenen_zustand(tmp_path, monkeypatch):
    monkeypatch.setattr(UI, "_fluegelkraefte", flapabhaengig)
    d = report.sammeln(_heck(-8.0))
    teil = d.fluegel[0]
    assert any(k.endswith("DRS offen") for k in teil.befunde)
    assert teil.drs is not None and d.bilanz_drs is not None
    assert d.familientabelle[1]
    pfad = report.schreiben(d, tmp_path / "r.pdf")
    # Deckblatt, Regeln (2 Seiten bei 4 Staenden), Geometrie, Aero, Gesamt,
    # DRS, Grenzen - gezaehlt wird nur, dass die DRS-Seite dazukommt.
    ohne = report.schreiben(report.sammeln(AeroSpec.laden(HECK)), tmp_path / "o.pdf")
    seiten = lambda p: len(re.findall(rb"/Type\s*/Page\b", p.read_bytes()))
    assert seiten(pfad) > seiten(ohne)


# ------------------------------------------------------------ Achslast

def test_zielbalance_aus_datei(tmp_path):
    datei = tmp_path / "v.yaml"
    datei.write_text("fahrdynamik:\n  achslast_vorne_prozent: 46.5\n")
    assert gesamt.zielbalance_aus_datei(datei) == 46.5
    datei.write_text("fahrdynamik:\n  achslast_vorne_prozent: null\n")
    assert gesamt.zielbalance_aus_datei(datei) is None
    assert gesamt.zielbalance_aus_datei(tmp_path / "fehlt.yaml") is None


def test_echte_fahrzeugdatei_hat_noch_keinen_wert():
    """Die Zahl kommt von der Waage. Bis sie eingetragen ist, fragt das
    Werkzeug - dieser Test erinnert daran, ihn anzupassen, wenn sie da ist."""
    assert gesamt.zielbalance_aus_datei() is None


def test_paket_kommandozeile_ohne_ziel_bricht_mit_hinweis_ab(tmp_path, capsys):
    quelle = AeroSpec.laden(HECK).speichern(tmp_path / "h.yaml", historie=False)
    with pytest.raises(SystemExit):
        paket.main(["--spec", str(quelle)])
    assert "achslast_vorne_prozent" in capsys.readouterr().err
