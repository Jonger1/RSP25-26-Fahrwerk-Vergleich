"""
Tests fuer den DoE-Motor (M8).

Das "Fertig, wenn" von M8: Ein DoE ueber mindestens 50 Varianten laeuft ohne
Handeingriff durch und liefert eine Pareto-Front. Das ist der erste Test
hier. Die uebrigen pruefen, was ein DoE unbrauchbar macht, ohne dass es
auffaellt: eine falsch berechnete Front, ein nicht wiederholbarer Lauf, eine
einzelne kaputte Variante, die den ganzen Lauf abbricht.
"""

import math

import pytest

from aerostudio.aero import doe
from aerostudio.regeln import lade
from aerostudio.spec.modell import Unterboden
from aerostudio.spec.projekt import AeroSpec


@pytest.fixture
def basis():
    spec = AeroSpec.beispiel()
    spec.unterboden = Unterboden()
    return spec


# ------------------------------------------------ Das Kriterium von M8

def test_fuenfzig_varianten_ohne_handeingriff(basis):
    lauf = doe.laufen(basis, n=60, regelsatz=lade())

    assert len(lauf.varianten) == len(lauf.ergebnisse) == 60
    assert lauf.gueltige >= 50
    assert len(lauf.front) >= 3
    assert set(lauf.front) <= set(range(60))


# ------------------------------------------------------------ Pareto

def test_pareto_an_einem_handgebauten_fall():
    """Die Front muss stimmen - eine falsche sieht genauso plausibel aus."""
    ziele = [doe.Ziel("a", True), doe.Ziel("b", False)]
    ergebnisse = [
        {"gueltig": True, "a": 10.0, "b": 5.0},   # 0 Front
        {"gueltig": True, "a": 8.0, "b": 3.0},    # 1 Front
        {"gueltig": True, "a": 8.0, "b": 6.0},    # 2 dominiert von 0
        {"gueltig": True, "a": 12.0, "b": 9.0},   # 3 Front
        {"gueltig": True, "a": 5.0, "b": 3.0},    # 4 dominiert von 1
        {"gueltig": False, "a": 99.0, "b": 0.0},  # 5 ungueltig - nie Front
    ]
    assert sorted(doe.pareto(ergebnisse, ziele)) == [0, 1, 3]


def test_ungueltige_varianten_kommen_nie_auf_die_front():
    """Sonst stuende ausgerechnet die Variante vorn, die T 2.2.1 reisst -
    denn die tiefste Kehle bringt den meisten Abtrieb."""
    ziele = [doe.Ziel("a", True)]
    ergebnisse = [{"gueltig": False, "a": 1000.0},
                  {"gueltig": True, "a": 1.0}]
    assert doe.pareto(ergebnisse, ziele) == [1]


def test_pareto_vertraegt_none_aus_geladener_datei():
    """Beim Speichern wird NaN zu None - die Front muss das aushalten."""
    ziele = [doe.Ziel("a", True), doe.Ziel("b", False)]
    ergebnisse = [{"gueltig": True, "a": 1.0, "b": None},
                  {"gueltig": True, "a": 2.0, "b": 1.0}]
    assert doe.pareto(ergebnisse, ziele) == [1]


def test_gleiche_varianten_dominieren_sich_nicht():
    ziele = [doe.Ziel("a", True), doe.Ziel("b", True)]
    ergebnisse = [{"gueltig": True, "a": 1.0, "b": 1.0},
                  {"gueltig": True, "a": 1.0, "b": 1.0}]
    assert sorted(doe.pareto(ergebnisse, ziele)) == [0, 1]


def test_front_der_echten_rechnung_ist_nicht_dominiert(basis):
    lauf = doe.laufen(basis, n=40)
    z = lauf.ziele
    front = [lauf.ergebnisse[i] for i in lauf.front]
    alle = [e for e in lauf.ergebnisse if e.get("gueltig")]

    def dominiert(a, b):
        besser_gleich = all(
            (b[k.name] >= a[k.name]) if k.maximieren else (b[k.name] <= a[k.name])
            for k in z)
        echt = any(
            (b[k.name] > a[k.name]) if k.maximieren else (b[k.name] < a[k.name])
            for k in z)
        return besser_gleich and echt

    for f in front:
        assert not any(dominiert(f, andere) for andere in alle)


# ---------------------------------------------------- Stichprobe

def test_stichprobe_haelt_die_grenzen(basis):
    for v in doe.stichprobe(doe.UNTERBODEN_RAUM, 100):
        for p in doe.UNTERBODEN_RAUM:
            assert p.von <= v[p.pfad] <= p.bis


def test_latin_hypercube_deckt_jeden_bereich_ab():
    """Jedes Zehntel jedes Bereichs bekommt genau eine von zehn Varianten -
    das ist die Eigenschaft, derentwegen es Latin Hypercube ist."""
    raum = [doe.Parameter("a.x", 0.0, 10.0), doe.Parameter("a.y", 0.0, 1.0)]
    for p in raum:
        werte = sorted(v[p.pfad] for v in doe.stichprobe(raum, 10))
        breite = (p.bis - p.von) / 10
        faecher = [int((w - p.von) // breite) for w in werte]
        assert faecher == list(range(10))


def test_gleicher_seed_gleiche_stichprobe():
    """Sonst liesse sich kein Ergebnis nachrechnen."""
    a = doe.stichprobe(doe.UNTERBODEN_RAUM, 20, seed=7)
    b = doe.stichprobe(doe.UNTERBODEN_RAUM, 20, seed=7)
    c = doe.stichprobe(doe.UNTERBODEN_RAUM, 20, seed=8)
    assert a == b
    assert a != c


def test_parameter_mit_falschem_bereich_wird_abgelehnt():
    with pytest.raises(ValueError, match="groesser"):
        doe.Parameter("unterboden.breite", 5.0, 5.0)


# ------------------------------------------------------- Varianten

def test_variante_ist_ein_gewoehnliches_spec(basis):
    v = doe.variante(basis, {"unterboden.diffusor_winkel": 13.5,
                             "lage.rake_grad": 0.7})
    assert v.unterboden.diffusor_winkel == 13.5
    assert v.lage.rake_grad == 0.7
    # Das Basis-Spec bleibt unberuehrt.
    assert basis.unterboden.diffusor_winkel != 13.5
    assert v.hash() != basis.hash()


def test_wert_ausserhalb_des_datenmodells_faellt_auf(basis):
    with pytest.raises(Exception):
        doe.variante(basis, {"unterboden.diffusor_winkel": 90.0})


def test_eine_kaputte_variante_bricht_den_lauf_nicht_ab(basis):
    """Ein Lauf ueber Nacht, der an Variante 37 von 500 stehenbleibt, ist der
    teuerste Fehler, den ein DoE machen kann."""
    raum = [doe.Parameter("unterboden.diffusor_winkel", 0.0, 60.0)]  # ueber 35 ungueltig
    lauf = doe.laufen(basis, raum, n=20)

    assert len(lauf.ergebnisse) == 20
    kaputt = [e for e in lauf.ergebnisse if not e.get("gueltig")]
    assert kaputt and all(e.get("grund") for e in kaputt)


def test_ohne_unterboden_klare_meldung():
    with pytest.raises(ValueError, match="kein Unterboden"):
        doe.unterboden_bewerten(AeroSpec.beispiel())


def test_zu_tiefer_boden_wird_ungueltig(basis):
    tief = doe.variante(basis, {"unterboden.kehle_hoehe_vorne": 25.0,
                                "unterboden.kehle_hoehe_hinten": 22.0})
    e = doe.unterboden_bewerten(tief, regelsatz=lade())
    assert not e["gueltig"]
    assert "T 2.2.1" in e["grund"]


# ---------------------------------------------------- Ergebnisdatei

def test_ergebnisdatei_ueberlebt_speichern_und_laden(basis, tmp_path):
    lauf = doe.laufen(basis, n=15)
    geladen = doe.Lauf.laden(lauf.speichern(tmp_path / "doe.yaml"))

    assert geladen.basis_hash == basis.hash()
    assert geladen.front == lauf.front
    assert geladen.varianten == lauf.varianten
    assert [z.name for z in geladen.ziele] == ["abtrieb", "widerstand",
                                               "stabilitaet"]
    for a, b in zip(lauf.ergebnisse, geladen.ergebnisse):
        assert a["gueltig"] == b["gueltig"]
        if a["gueltig"]:
            assert a["abtrieb"] == pytest.approx(b["abtrieb"])


def test_nan_wird_zu_none_in_der_datei(basis, tmp_path):
    """YAML kennt kein NaN - ein 'nan' in der Datei liest keine andere
    Software zurueck."""
    # Negativer Rake um einen weit hinten liegenden Drehpunkt drueckt das
    # Heck unter die Strasse - die Variante setzt sicher auf und liefert
    # den NaN-Widerstand, um den es geht. (Ein erster Anlauf mit sehr
    # flacher Kehle setzte gar nicht auf und pruefte damit nichts.)
    raum = [doe.Parameter("lage.rake_grad", -3.0, -2.5)]
    basis.lage.drehpunkt_x = -2000.0
    lauf = doe.laufen(basis, raum, n=3)
    assert any(e.get("widerstand") is not None
               and not math.isfinite(e["widerstand"])
               for e in lauf.ergebnisse), "Aufbau taugt nicht - kein NaN"

    text = lauf.speichern(tmp_path / "x.yaml").read_text()
    assert "nan" not in text.lower()


def test_variante_aus_der_datei_laesst_sich_uebernehmen(basis, tmp_path):
    """Der Weg, den die Oberflaeche geht: Front anklicken, Variante ist das
    Basis-Spec plus diese Werte."""
    lauf = doe.laufen(basis, n=20)
    geladen = doe.Lauf.laden(lauf.speichern(tmp_path / "doe.yaml"))
    i = geladen.front[0]

    uebernommen = doe.variante(basis, geladen.varianten[i])
    neu = doe.unterboden_bewerten(uebernommen)
    assert neu["abtrieb"] == pytest.approx(geladen.ergebnisse[i]["abtrieb"])


# ---------------------------------------------------- Kommandozeile

def test_kommandozeile(tmp_path, capsys):
    spec = AeroSpec.beispiel()
    spec.unterboden = Unterboden()
    quelle = spec.speichern(tmp_path / "basis.yaml", historie=False)
    ziel = tmp_path / "doe.yaml"

    assert doe.main(["--spec", str(quelle), "--n", "55",
                     "--aus", str(ziel)]) == 0
    assert ziel.is_file()
    ausgabe = capsys.readouterr().out
    assert "55 Varianten" in ausgabe
    assert "Pareto-Front" in ausgabe


def test_kommandozeile_ohne_unterboden_rechnet_mit_vorgabe(tmp_path, capsys):
    quelle = AeroSpec.beispiel().speichern(tmp_path / "b.yaml", historie=False)
    assert doe.main(["--spec", str(quelle), "--n", "5",
                     "--aus", str(tmp_path / "d.yaml")]) == 0
    assert "Vorgabewerten" in capsys.readouterr().out
