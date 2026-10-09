"""
Tests fuer die Druckverteilung am verschiebbaren Schnitt.

Der Zweck der Ansicht ist eine Frage: Wandert die Saugspitze nach aussen,
oder bleibt sie, wo sie war? Deshalb pruefen diese Tests vor allem, dass der
Schnitt wirklich WIRKT - eine Darstellung, die sich beim Verschieben nicht
aendert, sieht richtig aus und ist nutzlos.
"""

import numpy as np
import pytest

from aerostudio.aero import kaskade as aero_k
from aerostudio.geometrie import kaskade as geo_k
from aerostudio.geometrie.profil import Profil
from aerostudio.spec.projekt import AeroSpec
from aerostudio.ui import app as UI
from aerostudio.ui import darstellung


@pytest.fixture(scope="module")
def kaskade():
    haupt = Profil.aus_dat("profile/katalog/e423.dat").gespiegelt()
    flap = Profil.aus_dat("profile/katalog/s1223.dat").gespiegelt()
    return geo_k.platziere(haupt, 250.0, -4.0, [geo_k.Kaskadenvorgabe(
        profil=flap, sehne_faktor=0.35, winkel_relativ=-18.0,
        spalt=0.015, ueberlappung=0.02)], lage=(0.0, 90.0), punkte=120)


@pytest.fixture(scope="module")
def beispiel():
    return AeroSpec.laden("specs/beispiele/frontfluegel_zweielementig.yaml")


# --------------------------------------------------------- Fachrechnung

def test_je_element_ein_verlauf(kaskade):
    verlaeufe = aero_k.druckverteilung(kaskade, -4.0)
    assert len(verlaeufe) == len(kaskade)
    assert [v.name for v in verlaeufe] == [e.name for e in kaskade]


def test_druckbeiwert_bleibt_physikalisch(kaskade):
    """Am Staupunkt wird cp = 1 und nicht mehr - das ist der Grenzwert."""
    for v in aero_k.druckverteilung(kaskade, -4.0):
        assert v.cp.max() <= 1.0 + 1e-6
        assert v.cp.min() < 0.0          # irgendwo muss Sog sein


def test_saugspitze_ueberspringt_die_nasenspitze(kaskade):
    """Sonst liest man die numerische Spitze ab und nicht die echte.

    Das ist derselbe Befund wie beim Abrisskriterium: An der Nase entgleist
    das Panelverfahren, und je hoeher die Zirkulation, desto staerker.
    """
    v = aero_k.druckverteilung(kaskade, -4.0)[0]

    assert v.saugspitze > v.cp.min(), "Die Nasenspitze wurde mitgenommen"
    assert v.saugspitze_bei >= aero_k.NASENAUSSCHLUSS


def test_saugseite_und_druckseite_teilen_das_profil(kaskade):
    for v in aero_k.druckverteilung(kaskade, -4.0):
        assert v.saugseite.any() and (~v.saugseite).any()
        # Auf der Saugseite liegt der kleinste Beiwert.
        frei = v.x_rel >= aero_k.NASENAUSSCHLUSS
        i = int(np.argmin(np.where(frei, v.cp, np.inf)))
        assert v.saugseite[i]


def test_abtriebsfluegel_saugt_unten(kaskade):
    """Die Saugseite eines Abtriebsprofils ist die UNTERE.

    Wer das umgekehrt erwartet, liest jedes cp-Diagramm falsch - deshalb
    steht es als Test da und nicht nur im Docstring.
    """
    v = aero_k.druckverteilung(kaskade, -4.0)[0]
    frei = v.x_rel >= aero_k.NASENAUSSCHLUSS
    i = int(np.argmin(np.where(frei, v.cp, np.inf)))

    # Der Punkt der Saugspitze liegt unterhalb der Profilmitte.
    z_mitte = float(v.punkte[:, 1].mean())
    assert v.punkte[i, 1] < z_mitte


def test_punkte_und_beiwerte_passen_zusammen(kaskade):
    """Ohne das faerbt das Druckbild die falschen Stellen ein."""
    for v in aero_k.druckverteilung(kaskade, -4.0):
        assert len(v.cp) == len(v.punkte) == len(v.x_rel) == len(v.saugseite)


# ------------------------------------------- Der Schnitt muss wirken

def test_verschobener_schnitt_gibt_eine_andere_verteilung(beispiel):
    """Der Kern der Ansicht. Bei einem verjuengten und verwundenen Fluegel
    sieht jede Station anders aus - wenn nicht, zeigt das Bild etwas
    anderes als es behauptet."""
    element = beispiel.elemente[0]

    innen = aero_k.druckverteilung(UI._schnittelemente(element, 0.0),
                                   element.anstellwinkel)[0]
    aussen = aero_k.druckverteilung(UI._schnittelemente(element, 600.0),
                                    element.anstellwinkel)[0]

    assert innen.saugspitze != pytest.approx(aussen.saugspitze, abs=0.05)


def test_schnittelemente_folgen_der_sektionstabelle(beispiel):
    """Sehne und Verwindung an der Station, nicht die der Wurzel."""
    element = beispiel.elemente[0]
    innen = UI._schnittelemente(element, 0.0)
    aussen = UI._schnittelemente(element, 600.0)

    assert innen[0].sehne != pytest.approx(aussen[0].sehne, abs=0.5)


def test_zeichnung_und_druckbild_zeigen_denselben_schnitt(beispiel):
    """Sie werden von zwei Callbacks gezeichnet. Wuerde jeder seine eigene
    Anordnung bauen, koennten sie auseinanderlaufen - deshalb kommt beides
    aus `_schnittelemente`."""
    element = beispiel.elemente[0]
    a = UI._schnittelemente(element, 300.0)
    b = UI._schnittelemente(element, 300.0)

    assert len(a) == len(b)
    for x, y in zip(a, b):
        assert np.allclose(x.punkte, y.punkte)


# ------------------------------------------------------- Darstellung

def test_cp_achse_zeigt_nach_unten(kaskade):
    """Saugseite oben - das ist Konvention in jeder Veroeffentlichung, und
    nur so ist die Flaeche zwischen den Aesten proportional zum Auftrieb."""
    fig = darstellung.druckverlauf(aero_k.druckverteilung(kaskade, -4.0))
    assert fig.layout.yaxis.autorange == "reversed"


def test_druckverlauf_zeigt_saug_und_druckseite_getrennt(kaskade):
    """Zusammen gezeichnet liefe die Linie an der Nase quer durchs Bild."""
    fig = darstellung.druckverlauf(aero_k.druckverteilung(kaskade, -4.0))
    namen = [str(s.name) for s in fig.data if s.name]

    assert any("Saugseite" in n for n in namen)
    assert any("Druckseite" in n for n in namen)


def test_druckverlauf_markiert_die_saugspitze(kaskade):
    verlaeufe = aero_k.druckverteilung(kaskade, -4.0)
    fig = darstellung.druckverlauf(verlaeufe)
    namen = " ".join(str(s.name) for s in fig.data if s.name)

    assert f"{verlaeufe[0].saugspitze:.2f}" in namen


def test_druckverlauf_nennt_die_schnittstelle(kaskade):
    fig = darstellung.druckverlauf(aero_k.druckverteilung(kaskade, -4.0), 425.0)
    assert "425" in fig.layout.title.text


def test_druckbild_faerbt_alle_elemente_auf_derselben_skala(kaskade):
    """Sonst sahe ein Flap mit cp_min -1,5 so tiefblau aus wie ein
    Hauptelement mit -6,6, und der Vergleich zwischen ihnen waere gerade
    das, was das Bild verhindern soll."""
    verlaeufe = aero_k.druckverteilung(kaskade, -4.0)
    fig = darstellung.druckbild(kaskade, verlaeufe)

    grenzen = {(s.marker.cmin, s.marker.cmax) for s in fig.data
               if getattr(s.marker, "cmin", None) is not None}
    assert len(grenzen) == 1
    cmin, cmax = grenzen.pop()
    assert cmin == pytest.approx(-cmax)      # symmetrisch um cp = 0


def test_druckbild_zeigt_den_boden(kaskade):
    fig = darstellung.druckbild(kaskade, aero_k.druckverteilung(kaskade, -4.0))
    assert any(str(s.name) == "Boden" for s in fig.data)


# ------------------------------------------------------- Oberflaeche

def test_ui_liefert_beide_bilder_und_einen_hinweis(beispiel):
    spec = beispiel.model_dump(mode="json")
    bild, verlauf, hinweis = UI._druck_zeichnen(spec, 300.0)

    assert len(bild.data) > 1 and len(verlauf.data) > 1
    text = str(hinweis)
    assert "c_p" in text
    # Der Hinweis muss die beiden Grenzen nennen, sonst liest jemand die
    # Zahlen als Messwerte.
    assert "Reibungsfrei" in text
    assert "numerische Spitze" in text


def test_ui_ohne_spec_bleibt_leer():
    bild, verlauf, hinweis = UI._druck_zeichnen(None, 0.0)
    assert bild["data"] == [] and verlauf["data"] == []
    assert hinweis == ""


def test_ui_reagiert_auf_den_schieber(beispiel):
    spec = beispiel.model_dump(mode="json")
    _b, innen, _h = UI._druck_zeichnen(spec, 0.0)
    _b, aussen, _h = UI._druck_zeichnen(spec, 600.0)

    assert innen.layout.title.text != aussen.layout.title.text


def test_ui_braucht_kein_neuralfoil(beispiel, monkeypatch):
    """Die Druckverteilung kommt aus dem Panelverfahren. Wer nur sie
    ansehen will, soll nicht an einem fehlenden Paket haengen."""
    monkeypatch.setattr(UI, "aero_verfuegbar", lambda: False)
    bild, verlauf, hinweis = UI._druck_zeichnen(
        beispiel.model_dump(mode="json"), 300.0)

    assert len(bild.data) > 1
    assert "Fehler" not in str(hinweis)
