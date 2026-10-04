"""
Tests fuer den DoE ueber das ganze Paket.

Die Fluegelrechnung ist die Attrappe aus test_gesamt - linear in Winkel und
Hoehe, also gibt das bilineare Kennfeld sie exakt wieder. Damit laesst sich
die Kennfeld-Abkuerzung gegen die "echte" Rechnung pruefen, ohne auf die
Traglinie zu warten.
"""

import math

import pytest

from aerostudio.aero import doe, gesamt, paket
from aerostudio.regeln import lade
from aerostudio.spec.modell import Unterboden
from aerostudio.spec.projekt import AeroSpec
from tests.test_gesamt import attrappe, fluegel

L = 1535.0


def _paket():
    front = AeroSpec.beispiel()
    front.elemente = [fluegel(-600.0, 80.0, -4.0).model_copy(update={"id": "FW"})]
    front.unterboden = Unterboden()
    heck = AeroSpec.beispiel()
    heck.elemente = [fluegel(1600.0, 900.0, -6.0).model_copy(update={"id": "RW"})]
    return paket.bauen(front, [heck])


def test_paket_sammelt_fluegel_und_unterboden():
    front = AeroSpec.beispiel()
    heck = AeroSpec.beispiel()
    heck.unterboden = Unterboden(breite=333.0)
    p = paket.bauen(front, [heck])
    assert len(p.elemente) == 2
    assert p.unterboden.breite == 333.0
    # Gleiche ids werden auseinandergehalten - sonst teilten sich zwei
    # Fluegel ein Kennfeld.
    assert len({e.id for e in p.elemente}) == 2
    # Die Quellen bleiben unberuehrt.
    assert len(front.elemente) == 1 and front.unterboden is None


def test_raum_enthaelt_jeden_fluegel_und_den_rake():
    pfade = [p.pfad for p in paket.raum(_paket())]
    assert "elemente.0.anstellwinkel" in pfade
    assert "elemente.1.anstellwinkel" in pfade
    assert "lage.rake_grad" in pfade
    assert "unterboden.diffusor_winkel" in pfade


def test_kennfeld_trifft_die_rechnung():
    """Bilinear auf einer linearen Funktion: exakt, auch zwischen den
    Stuetzstellen."""
    e = fluegel(-600.0, 80.0, -4.0)
    feld = paket.kennfeld(e, attrappe, 20.0, (-8.0, 0.0), (60.0, 100.0))
    for a, z in ((-4.0, 80.0), (-6.3, 71.2), (-0.5, 99.0)):
        erwartet = attrappe(e.model_copy(update={"anstellwinkel": a, "pos_z": z}), 20.0)
        assert feld(a, z).abtrieb == pytest.approx(erwartet.abtrieb)
        assert feld(a, z).widerstand == pytest.approx(erwartet.widerstand)
    assert feld.enthaelt(-4.0, 80.0)
    assert not feld.enthaelt(-9.0, 80.0)


def test_kennfeld_deckt_den_ganzen_lauf_ab():
    """Rake und Nicken verschieben Winkel und Hoehe - das Kennfeld muss
    alles abdecken, was der Lauf erzeugt, sonst wird still am Rand
    abgeschnitten."""
    p = _paket()
    lauf, bewertung = paket.laufen(p, attrappe, 45.0, n=40, radstand=L)
    assert bewertung.ausserhalb == 0
    assert len(lauf.ergebnisse) == 40


def test_kennfeld_ergebnis_gleich_der_direkten_bilanz():
    p = _paket()
    lauf, _ = paket.laufen(p, attrappe, 45.0, n=10, radstand=L)
    i = lauf.front[0]
    spec = doe.variante(p, lauf.varianten[i])
    direkt = gesamt.bilanz(paket.fluegel_des_pakets(spec), spec.unterboden,
                           spec.lage, attrappe, 20.0, L)
    assert lauf.ergebnisse[i]["abtrieb"] == pytest.approx(direkt.abtrieb, rel=1e-6)
    assert lauf.ergebnisse[i]["balance"] == pytest.approx(
        100 * direkt.balance_vorne, abs=1e-4)


def test_fuenfzig_varianten_mit_front():
    lauf, _ = paket.laufen(_paket(), attrappe, 45.0, n=60, radstand=L,
                           regelsatz=lade("2026"))
    assert lauf.gueltige >= 50
    assert len(lauf.front) >= 2
    assert [z.name for z in lauf.ziele] == ["abtrieb", "balancefehler", "wanderung"]
    for i in lauf.front:
        e = lauf.ergebnisse[i]
        assert e["balancefehler"] == pytest.approx(abs(e["balance"] - 45.0))
        assert math.isfinite(e["wanderung"]) and e["wanderung"] >= 0.0


def test_zu_tiefer_unterboden_macht_die_variante_ungueltig():
    p = _paket()
    parameter = [doe.Parameter("unterboden.kehle_hoehe_vorne", 20.0, 25.0),
                 doe.Parameter("unterboden.kehle_hoehe_hinten", 20.0, 25.0)]
    lauf, _ = paket.laufen(p, attrappe, 45.0, n=5, parameter=parameter, radstand=L,
                           regelsatz=lade("2026"))
    assert all(not e["gueltig"] and "T 2.2.1" in e["grund"] for e in lauf.ergebnisse)
    assert lauf.front == []


def test_ergebnisdatei(tmp_path):
    lauf, _ = paket.laufen(_paket(), attrappe, 45.0, n=12, radstand=L)
    geladen = doe.Lauf.laden(lauf.speichern(tmp_path / "p.yaml"))
    assert geladen.front == lauf.front
    assert geladen.ergebnisse[0]["balance"] == pytest.approx(lauf.ergebnisse[0]["balance"])


def test_vorhandene_kennfelder_werden_wiederverwendet():
    p = _paket()
    aufrufe = []

    def zaehlen(e, v):
        aufrufe.append(1)
        return attrappe(e, v)

    felder = paket.kennfelder(p, paket.raum(p), zaehlen, 20.0, L)
    vorher = len(aufrufe)
    paket.laufen(p, zaehlen, 45.0, n=10, radstand=L, felder=felder)
    assert len(aufrufe) == vorher
    assert vorher == 2 * 7 * 4


def test_kommandozeile(tmp_path, monkeypatch, capsys):
    from aerostudio.ui import app as UI
    monkeypatch.setattr(UI, "_fluegelkraefte", attrappe)
    p = _paket()
    front = p.model_copy(update={"elemente": p.elemente[:1]})
    heck = p.model_copy(update={"elemente": p.elemente[1:], "unterboden": None})
    a = front.speichern(tmp_path / "f.yaml", historie=False)
    b = heck.speichern(tmp_path / "h.yaml", historie=False)
    ziel = tmp_path / "doe.yaml"

    assert paket.main(["--spec", str(a), "--dazu", str(b), "--ziel", "45",
                       "--n", "55", "--aus", str(ziel)]) == 0
    assert ziel.is_file()
    ausgabe = capsys.readouterr().out
    assert "55 Varianten" in ausgabe and "Kennfeld" in ausgabe
    assert len(doe.Lauf.laden(ziel).front) >= 1


def test_zielbalance_steht_in_der_ergebnisdatei(tmp_path):
    """Review 29.09.: Ohne sie liesse sich eine geladene Front nicht lesen."""
    lauf, _ = paket.laufen(_paket(), attrappe, 47.0, n=8, radstand=L)
    geladen = doe.Lauf.laden(lauf.speichern(tmp_path / "p.yaml"))
    assert geladen.zusatz["zielbalance"] == 47.0
