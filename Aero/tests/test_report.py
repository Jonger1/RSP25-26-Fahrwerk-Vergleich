"""
Tests fuer den Report (M9). Das "Fertig, wenn": Fuer ein Design entsteht per
Kommando ein PDF. Geprueft wird, dass es entsteht, alle Abschnitte hat und
die Zahlen aus denselben Rechenwegen stammen wie im Werkzeug.
"""

import re

import pytest

from aerostudio import regeln
from aerostudio.formate import report
from aerostudio.spec.modell import Unterboden
from aerostudio.spec.projekt import AeroSpec
from aerostudio.ui import app as UI
from tests.test_gesamt import attrappe

FRONT = UI.PROJEKT / "specs/beispiele/frontfluegel_zweielementig.yaml"
HECK = UI.PROJEKT / "specs/beispiele/heckfluegel.yaml"


def _seiten(pfad) -> int:
    return len(re.findall(rb"/Type\s*/Page\b", pfad.read_bytes()))


@pytest.fixture
def schnell(monkeypatch):
    monkeypatch.setattr(UI, "_fluegelkraefte", attrappe)


def test_befunde_nennen_ihren_fahrzustand():
    spec = AeroSpec.laden(FRONT)
    stapel = [s for t in UI._elementstapel(spec.elemente[0]) for s in t]
    befunde = regeln.pruefe_fluegel(stapel, regeln.lade("2026"),
                                    zustand=regeln.Fahrzustand(10.0, 20.0))
    lagen = {b.regel: b.fahrzustand for b in befunde}
    assert lagen["T 2.2.1"] == "eingefedert −20.0 mm"
    assert all(b.fahrzustand for b in befunde)
    assert any(b.fahrzustand.startswith("ausgefedert +10.0") for b in befunde)


def test_ohne_aero_geometrie_und_regeln(tmp_path):
    d = report.sammeln(AeroSpec.laden(FRONT), [AeroSpec.laden(HECK)], mit_aero=False)
    assert len(d.fluegel) == 2
    assert all(set(t.befunde) == {s.version for s in regeln.alle_staende()}
               for t in d.fluegel)
    assert d.bilanz is None
    pfad = report.schreiben(d, tmp_path / "r.pdf")
    assert pfad.read_bytes()[:4] == b"%PDF"
    # Deckblatt, Regeln, je Fluegel Geometrie, Grenzen.
    assert _seiten(pfad) == 1 + 1 + 2 + 1


def test_mit_aero_alle_abschnitte(tmp_path, schnell):
    spec = AeroSpec.laden(FRONT)
    spec.unterboden = Unterboden()
    d = report.sammeln(spec, [AeroSpec.laden(HECK)], ziel=45.0)
    assert d.mit_aero
    assert d.bilanz is not None and len(d.wanderung) == 5
    front, heck = d.fluegel
    assert len(front.hc) == len(report.HC_STUFEN)      # Frontfluegel: h/c-Kurve
    assert heck.hc == []                               # Heckfluegel: keine
    assert front.druck                                 # Druckverteilung da
    pfad = report.schreiben(d, tmp_path / "r.pdf")
    # Deckblatt, Regeln, 2x (Geometrie + Aero), Unterboden, Gesamt, Grenzen
    assert _seiten(pfad) == 1 + 1 + 4 + 1 + 1 + 1


def test_zahlen_wie_im_reiter_balance(schnell):
    """Der Report darf keine andere Zahl zeigen als das Werkzeug."""
    spec = AeroSpec.laden(FRONT)
    spec.unterboden = Unterboden()
    d = report.sammeln(spec, [AeroSpec.laden(HECK)])
    from aerostudio.aero import gesamt
    fluegel, ub = UI._gesamtfahrzeug(spec, [str(HECK)])
    direkt = gesamt.bilanz(fluegel, ub, spec.lage, UI._fluegelkraefte, 20.0,
                           regeln.Bezugsgeometrie.aus_datei().radstand)
    assert d.bilanz.abtrieb == pytest.approx(direkt.abtrieb)
    assert d.bilanz.balance_vorne == pytest.approx(direkt.balance_vorne)


def test_fluegel_ohne_spannweite_bricht_nicht_ab(tmp_path):
    spec = AeroSpec.beispiel()
    spec.elemente[0].spannweite = None
    d = report.sammeln(spec, mit_aero=False)
    assert d.fluegel[0].hinweise
    assert report.schreiben(d, tmp_path / "r.pdf").is_file()


def test_verstoss_wird_markiert(tmp_path):
    spec = AeroSpec.laden(FRONT)
    spec.elemente[0].pos_z = 5.0          # reisst T 2.2.1
    d = report.sammeln(spec, mit_aero=False)
    for befunde in d.fluegel[0].befunde.values():
        assert "Verstoß" in report._urteil(befunde)


def test_kommandozeile(tmp_path, capsys):
    ziel = tmp_path / "r.pdf"
    assert report.main(["--spec", str(FRONT), "--dazu", str(HECK),
                        "--ohne-aero", "--aus", str(ziel)]) == 0
    assert ziel.is_file() and "Geschrieben" in capsys.readouterr().out


def test_report_aus_der_oberflaeche(tmp_path, monkeypatch, schnell):
    daten = AeroSpec.laden(FRONT).model_dump(mode="json")
    monkeypatch.setattr(UI, "PROJEKT", tmp_path)
    download, status = UI._report(1, daten, [], 20.0, 45.0, [])
    assert "Geschrieben" in status
    assert download["filename"].endswith(".pdf")


def test_aufsetzender_unterboden_verhindert_den_report_nicht(tmp_path):
    """Review 29.09.: Der ValueError brach den ganzen Report ab."""
    from aerostudio.spec.modell import Fahrzeuglage
    spec = AeroSpec.laden(FRONT)
    spec.unterboden = Unterboden(kehle_hoehe_hinten=20.0)
    spec.lage = Fahrzeuglage(rake_grad=-2.0)
    d = report.sammeln(spec, mit_aero=False)
    assert d.unterboden is None
    assert any("setzt auf" in h for h in d.hinweise)
    assert any(not b.ok for b in d.unterboden_befunde)
    assert report.schreiben(d, tmp_path / "r.pdf").is_file()
