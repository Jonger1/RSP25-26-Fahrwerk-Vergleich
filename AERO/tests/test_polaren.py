"""
Polaren ueber mehrere Reynoldszahlen im Reiter Profil.
"""

import json

import numpy as np
import pytest

from aerostudio.aero import profilpolare as pp
from aerostudio.spec.projekt import AeroSpec
from aerostudio.ui import app as UI
from aerostudio.ui import darstellung

nf = pytest.mark.skipif(not pp.verfuegbar(), reason="NeuralFoil fehlt")


def _daten(**aenderung) -> dict:
    spec = AeroSpec.beispiel()
    if aenderung:
        spec.elemente[0] = spec.elemente[0].model_copy(update=aenderung)
    return spec.model_dump(mode="json")


@pytest.mark.parametrize("text, erwartet", [
    ("50k, 1e5; 200 000, 1M", [5e4, 1e5, 2e5, 1e6]),
    ("200.000, 200000, 200k", [2e5]),
    ("1.5M", [1.5e6]),
    ("", []),
    (None, []),
])
def test_reynolds_lesen(text, erwartet):
    assert pp.lies_reynolds(text) == erwartet


@pytest.mark.parametrize("text", ["abc", "10", "1e9"])
def test_reynolds_unsinn_wird_gemeldet(text):
    with pytest.raises(ValueError):
        pp.lies_reynolds(text)


@nf
def test_reihe_ist_aufsteigend_und_reynolds_wirkt():
    """Mit steigender Reynoldszahl sinkt der Mindestwiderstand - das ist die
    Grundaussage der Diagramme und muss herauskommen."""
    profil = UI.profil_aus_datei("e423.dat")
    reihe = pp.polarenreihe(profil, [1e6, 5e4, 2e5],
                            alpha=np.arange(-15.0, 15.01, 0.5), modell="xlarge")
    assert [p.reynolds for p in reihe] == [5e4, 2e5, 1e6]
    cd_min = [pp.kennwerte(p)["cd_min"] for p in reihe]
    assert cd_min[0] > cd_min[1] > cd_min[2]
    # Gespiegelt fuer Abtrieb: das Maximum des Abtriebs ist deutlich negativ.
    assert pp.kennwerte(reihe[-1])["cl_min"] < -1.5


@nf
def test_ncrit_wirkt():
    profil = UI.profil_aus_datei("e423.dat")
    a = np.array([-4.0])
    frueh = pp.polare(profil, 1e5, alpha=a, n_crit=4.0)
    spaet = pp.polare(profil, 1e5, alpha=a, n_crit=9.0)
    assert frueh.cd[0] != pytest.approx(spaet.cd[0])


@nf
def test_fuenf_diagramme_und_gestrichelt_wo_unsicher():
    profil = UI.profil_aus_datei("e423.dat")
    reihe = pp.polarenreihe(profil, [1e5, 5e5], alpha=np.arange(-20.0, 20.01, 0.5),
                            modell="xlarge")
    fig = darstellung.polarendiagramme(reihe)
    titel = [a.text for a in fig.layout.annotations]
    assert titel == ["CL über CD", "CL über α", "CL/CD über α", "CD über α",
                     "CM über α"]
    durchgezogen = [t for t in fig.data if t.line.dash is None]
    assert len(durchgezogen) == 2 * 5
    assert sum(t.showlegend for t in fig.data) == 2
    # Bis 20 Grad ist jedes Profil abgerissen - also gibt es Gestricheltes.
    assert any(t.line.dash == "dot" for t in fig.data)


def test_csv():
    p = pp.Polare(alpha=np.array([-1.0, 0.0]), cl=np.array([-0.2, 0.0]),
                  cd=np.array([0.01, 0.01]), cm=np.array([0.0, 0.0]),
                  vertrauen=np.array([0.9, 0.9]), reynolds=2e5, name="x")
    text = pp.als_csv([p])
    zeilen = text.strip().splitlines()
    assert zeilen[0].startswith("profil;reynolds;alpha_grad;cl;cd")
    assert zeilen[0].endswith(";vertrauen;unsicher")
    assert len(zeilen) == 3 and zeilen[1].startswith("x;200000;-1.00;-0.20000")
    assert zeilen[1].endswith(";nein")


@nf
def test_oberflaeche_rechnet_mit_tempo():
    daten = _daten(sehne=250.0)
    fig, tabelle, hinweis = UI._polaren_zeichnen(
        daten, "100k, 500k", "15", -10.0, 10.0, 9.0, "xlarge")
    namen = [t.name for t in fig.data if t.showlegend]
    # 15 m/s bei 250 mm Sehne: rund 253 000
    assert namen[0] == "Re 100 000" and "(15 m/s)" in namen[1]
    text = json.dumps(tabelle.to_plotly_json(), default=str, ensure_ascii=False)
    assert "CL min (Abtrieb)" in text
    assert "gespiegelt für Abtrieb" in json.dumps(
        hinweis.to_plotly_json(), default=str, ensure_ascii=False)


@nf
def test_oberflaeche_meldet_falsche_eingabe():
    _fig, _tab, hinweis = UI._polaren_zeichnen(_daten(), "quatsch", "", -10.0,
                                               10.0, 9.0, "xlarge")
    assert "quatsch" in json.dumps(hinweis.to_plotly_json(), default=str,
                                   ensure_ascii=False)


@nf
def test_zu_viele_reynoldszahlen():
    _f, _t, hinweis = UI._polaren_zeichnen(
        _daten(), ",".join(str(50_000 * (i + 1)) for i in range(9)), "",
        -5.0, 5.0, 9.0, "xlarge")
    assert "zu viele" in json.dumps(hinweis.to_plotly_json(), default=str,
                                    ensure_ascii=False)


@nf
def test_csv_download():
    ergebnis = UI._polaren_csv(1, _daten(), "200k", "", -2.0, 2.0, 9.0, "xlarge")
    assert ergebnis["filename"].startswith("polaren_")
    assert ergebnis["content"].count("\n") == 1 + 9


def test_sicherer_bereich_um_den_arbeitspunkt():
    a = np.arange(-5.0, 5.01, 1.0)
    v = np.array([.5, .9, .9, .9, .9, .9, .5, .9, .9, .5, .5])
    cd = 0.01 + 0.001 * (a + 1.0) ** 2         # kleinster Widerstand bei -1
    p = pp.Polare(alpha=a, cl=a * 0.1, cd=cd, cm=a * 0, vertrauen=v, reynolds=1e5)
    assert pp.sicherer_bereich(p) == (-4.0, 0.0)
    p.vertrauen = np.full_like(a, 0.3)
    assert pp.sicherer_bereich(p) is None


def _polare(vertrauen, name=""):
    a = np.arange(-5.0, -5.0 + len(vertrauen), 1.0)
    return pp.Polare(alpha=a, cl=a * 0.1, cd=0.01 + 0.001 * a ** 2, cm=a * 0,
                     vertrauen=np.asarray(vertrauen, dtype=float),
                     reynolds=2e5, name=name)


def test_unsichere_bereiche():
    p = _polare([.5, .6, .9, .9, .9, .9, .9, .9, .7, .9, .4])
    assert pp.unsichere_bereiche(p) == [(-5.0, -4.0, 0.5), (3.0, 3.0, 0.7),
                                        (5.0, 5.0, 0.4)]
    assert pp.anteil_sicher(p) == pytest.approx(7 / 11)


def _text(meldungen) -> str:
    return " | ".join(json.dumps(m.to_plotly_json(), default=str,
                                 ensure_ascii=False) for m in meldungen)


def test_meldung_arbeitspunkt_im_unsicheren_bereich():
    element = AeroSpec.beispiel().elemente[0].model_copy(
        update={"anstellwinkel": -4.5})
    p = _polare([.5, .6, .9, .9, .9, .9, .9, .9, .9, .9, .9])
    text = _text(UI._unsicherheitsmeldungen([p], {}, element))
    assert "Dein Anstellwinkel -4,5°" in text and "as-status-fehler" in text
    assert "unsicher bei α -5,0° bis -4,0°" in text


def test_meldung_fast_ueberall_unsicher():
    element = AeroSpec.beispiel().elemente[0].model_copy(
        update={"anstellwinkel": 0.0})
    p = _polare([.5, .5, .5, .5, .5, .5, .5, .9, .9, .5, .5])
    text = _text(UI._unsicherheitsmeldungen([p], {}, element))
    assert "nur bei 18 %" in text and "nicht zum Auslegen" in text
    assert "von +2,0° bis +3,0°" in text


def test_keine_meldung_wenn_alles_sicher():
    element = AeroSpec.beispiel().elemente[0]
    assert UI._unsicherheitsmeldungen([_polare([.9] * 11)], {}, element) == []
