"""
Tests fuer die Gesamtbilanz: Frontfluegel, Heckfluegel und Unterboden.

Die Fluegelrechnung wird hier durch eine Attrappe ersetzt, deren Abtrieb
von Hoehe und Anstellwinkel abhaengt. So pruefen die Tests die Buchhaltung
(Hebelarme, Rake, Nicken) gegen Handrechnungen, ohne auf die Traglinie zu
warten. Ein echter Durchlauf steht in test_balance_ui.py.
"""

import math
from types import SimpleNamespace

import pytest

from aerostudio.aero import gesamt, unterboden
from aerostudio.spec.modell import Fahrzeuglage, Spannweite, Unterboden
from aerostudio.spec.projekt import AeroSpec

L = 1535.0


def attrappe(element, geschwindigkeit):
    """Mehr Abtrieb bei steilerem Winkel und tieferer Lage."""
    abtrieb = 100.0 - 10.0 * element.anstellwinkel - 0.1 * element.pos_z
    return SimpleNamespace(abtrieb=abtrieb, widerstand=abtrieb / 10.0,
                           streifen=[], auftrieb_lokal=[])


def fluegel(x: float, z: float = 100.0, winkel: float = -5.0, sehne: float = 200.0):
    e = AeroSpec.beispiel().elemente[0].model_copy(update={
        "pos_x": x, "pos_z": z, "anstellwinkel": winkel, "sehne": sehne,
        "spannweite": Spannweite.gerade(500.0)})
    return e


def beitrag(abtrieb, x, widerstand=0.0, z=0.0):
    return gesamt.Beitrag("t", "fluegel", abtrieb, widerstand, x, z)


# ---------------------------------------------------------- Buchhaltung

def test_hebelgesetz_von_hand():
    b = gesamt.Bilanz([beitrag(100.0, -500.0), beitrag(100.0, L + 200.0)], L, 20.0)
    erwartet = (100.0 * (L + 500.0) + 100.0 * (-200.0)) / L
    assert b.last_vorne == pytest.approx(erwartet)
    assert b.last_vorne + b.last_hinten == pytest.approx(200.0)
    assert b.balance_vorne == pytest.approx(erwartet / 200.0)
    assert b.druckpunkt_x == pytest.approx((L - 300.0) / 2)


def test_abtrieb_genau_auf_einer_achse():
    assert gesamt.Bilanz([beitrag(50.0, 0.0)], L, 20.0).balance_vorne == pytest.approx(1.0)
    assert gesamt.Bilanz([beitrag(50.0, L)], L, 20.0).balance_vorne == pytest.approx(0.0)


def test_widerstand_in_der_hoehe_entlastet_vorn():
    """Ein hoher Heckfluegel zieht nach hinten und hebt damit die Nase an."""
    ohne = gesamt.Bilanz([beitrag(100.0, 700.0)], L, 20.0)
    mit = gesamt.Bilanz([beitrag(100.0, 700.0, widerstand=20.0, z=900.0)], L, 20.0)
    assert mit.last_vorne == pytest.approx(ohne.last_vorne - 20.0 * 900.0 / L)
    assert mit.abtrieb == ohne.abtrieb


def test_ohne_abtrieb_kein_absturz():
    b = gesamt.Bilanz([], L, 20.0)
    assert math.isnan(b.balance_vorne)
    assert math.isnan(b.druckpunkt_x)
    assert b.abtrieb == 0.0


def test_nan_widerstand_verdirbt_die_summe_nicht():
    b = gesamt.Bilanz([beitrag(10.0, 0.0, widerstand=float("nan")),
                       beitrag(10.0, 0.0, widerstand=3.0)], L, 20.0)
    assert b.widerstand == pytest.approx(3.0)


def test_angriffspunkt_folgt_der_lastverteilung():
    streifen = [SimpleNamespace(x_viertel=-600.0, breite=100.0),
                SimpleNamespace(x_viertel=-500.0, breite=100.0)]
    kraefte = SimpleNamespace(streifen=streifen, auftrieb_lokal=[3.0, 1.0])
    assert gesamt.angriffspunkt(kraefte, 0.0) == pytest.approx(-575.0)
    # Ohne Streifen der Rueckfall.
    assert gesamt.angriffspunkt(SimpleNamespace(), -42.0) == -42.0


# -------------------------------------------------------- Fahrzeuglage

def test_rake_senkt_den_frontfluegel_und_hebt_den_heckfluegel():
    """Um die Vorderachse gedreht, hinten hoeher: Alles vor der Achse kommt
    tiefer, alles dahinter hoeher, und beide stehen steiler."""
    gesehen = {}

    def merken(element, v):
        gesehen[element.pos_x] = element
        return attrappe(element, v)

    front, heck = fluegel(-600.0, 80.0, -4.0), fluegel(1600.0, 900.0, -6.0)
    gesamt.bilanz([("FW", front), ("RW", heck)], None,
                  Fahrzeuglage(rake_grad=1.0), merken, radstand=L)

    tan = math.tan(math.radians(1.0))
    assert gesehen[-600.0].pos_z == pytest.approx(80.0 + (-600.0 + 50.0) * tan)
    assert gesehen[1600.0].pos_z == pytest.approx(900.0 + (1600.0 + 50.0) * tan)
    assert gesehen[-600.0].anstellwinkel == pytest.approx(-5.0)
    assert gesehen[1600.0].anstellwinkel == pytest.approx(-7.0)
    # Das Original bleibt unangetastet.
    assert front.pos_z == 80.0 and front.anstellwinkel == -4.0


def test_bremsnicken_dreht_um_die_radstandsmitte():
    lage = gesamt.Lage(None, gesamt.Zustand("Bremsen", 0.5), L)
    assert lage.versatz(L / 2) == pytest.approx(0.0)
    assert lage.versatz(-600.0) < 0.0          # Frontfluegel kommt runter
    assert lage.versatz(L + 100.0) > 0.0
    assert lage.rake_grad == pytest.approx(0.5)


def test_rake_und_nicken_addieren_sich():
    lage = gesamt.Lage(Fahrzeuglage(rake_grad=0.4), gesamt.Zustand("x", 0.3), L)
    assert lage.rake_grad == pytest.approx(0.7)


def test_aufsetzender_fluegel_wird_gemeldet_statt_gerechnet():
    aufgerufen = []
    b = gesamt.bilanz([("FW", fluegel(-600.0, 5.0))], None,
                      Fahrzeuglage(rake_grad=2.0),
                      lambda e, v: aufgerufen.append(e) or attrappe(e, v),
                      radstand=L)
    assert not aufgerufen
    assert b.beitraege[0].abtrieb == 0.0
    assert "Setzt" in b.beitraege[0].hinweis


def test_fluegel_ohne_spannweite_wird_uebersprungen():
    e = fluegel(-600.0).model_copy(update={"spannweite": None})
    b = gesamt.bilanz([("FW", e)], None, Fahrzeuglage(), attrappe, radstand=L)
    assert b.beitraege[0].abtrieb == 0.0
    assert "Spannweite" in b.beitraege[0].hinweis


# -------------------------------------------------------- Unterboden

def test_unterboden_rechnet_wie_im_eigenen_reiter():
    """In Konstruktionslage muss dieselbe Zahl herauskommen wie im Reiter
    Unterboden - sonst gaebe es zwei Wahrheiten."""
    ub, lage = Unterboden(), Fahrzeuglage(rake_grad=0.5, drehpunkt_x=900.0)
    b = gesamt.bilanz([], ub, lage, attrappe, 20.0, L)
    einzeln = unterboden.rechne(ub, lage, 20.0)
    assert b.abtrieb == pytest.approx(einzeln.abtrieb)
    assert b.beitraege[0].x == pytest.approx(einzeln.druckpunkt_x)


def test_aufsetzender_unterboden_bricht_die_bilanz_nicht_ab():
    b = gesamt.bilanz([("FW", fluegel(-600.0))], Unterboden(),
                      Fahrzeuglage(rake_grad=-3.0, drehpunkt_x=-2000.0),
                      attrappe, radstand=L)
    ub = [t for t in b.beitraege if t.art == "unterboden"][0]
    assert ub.abtrieb == 0.0 and "setzt auf" in ub.hinweis


# --------------------------------------------------------- Wanderung

def test_wanderung_rechnet_jeden_zustand():
    reihe = gesamt.wanderung([("FW", fluegel(-600.0)), ("RW", fluegel(1600.0, 900.0))],
                             Unterboden(), Fahrzeuglage(), attrappe, radstand=L)
    assert [b.zustand.nick_grad for b in reihe] == [-0.5, -0.25, 0.0, 0.25, 0.5]
    # Nase tiefer: Der Frontfluegel kommt naeher an den Boden und legt zu.
    fw = [b.beitraege[0].abtrieb for b in reihe]
    assert fw == sorted(fw)


def test_empfindlichkeit_ist_die_steigung():
    reihe = [gesamt.Bilanz([beitrag(100.0, 0.0), beitrag(100.0, L)], L, 20.0,
                           gesamt.Zustand("", n)) for n in (-0.5, 0.0, 0.5)]
    # Konstante Balance: keine Wanderung.
    assert gesamt.empfindlichkeit(reihe) == pytest.approx(0.0, abs=1e-9)

    schief = [gesamt.Bilanz([beitrag(100.0 + 20.0 * n, 0.0), beitrag(100.0, L)],
                            L, 20.0, gesamt.Zustand("", n)) for n in (-1.0, 0.0, 1.0)]
    assert gesamt.empfindlichkeit(schief) > 0.0


def test_hinweise_ohne_heckfluegel():
    b = gesamt.bilanz([("FW", fluegel(-600.0))], None, Fahrzeuglage(),
                      attrappe, radstand=L)
    text = " ".join(b.hinweise)
    assert "hinter der Fahrzeugmitte" in text
    assert "Ohne Unterboden" in text


def test_aufsetzendes_teil_macht_die_balance_nicht_nan():
    """Review 29.09.: widerstand=NaN mal z ergab NaN fuer das ganze Auto."""
    b = gesamt.Bilanz([beitrag(100.0, -500.0),
                       beitrag(0.0, 800.0, widerstand=float("nan"), z=0.0),
                       beitrag(80.0, L + 100.0, widerstand=10.0, z=900.0)], L, 20.0)
    assert math.isfinite(b.balance_vorne)
