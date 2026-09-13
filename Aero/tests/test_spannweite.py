"""
Tests fuer den 3D-Fluegel und die Regelpruefung.

Der Schwerpunkt liegt bewusst nicht darauf, dass der Pruefer gruen meldet -
das tut er auch, wenn er nichts tut. Geprueft wird, dass er bei absichtlich
regelwidriger Geometrie ANSCHLAEGT, und zwar bei der richtigen Regel und im
richtigen Regelstand.
"""

import numpy as np
import pytest

from aerostudio.geometrie.profil import Profil
from aerostudio.geometrie.spannweite import (Schnitt, als_sektionen, huellwerte,
                                             schnitte)
from aerostudio.regeln import (Bezugsgeometrie, Fahrzustand, alle_staende, lade,
                               pruefe_fluegel)
from aerostudio.spec.modell import Spannweite, Stuetzstelle


@pytest.fixture(scope="module")
def profil():
    return Profil.aus_dat("profile/katalog/e423.dat").gespiegelt()


@pytest.fixture(scope="module")
def bezug():
    return Bezugsgeometrie.aus_datei()


def _fluegel(profil, spannweite=None, sehne=250.0, winkel=-4.0,
             lage=(-600.0, 0.0, 90.0)):
    return schnitte(profil, spannweite or Spannweite.frontfluegel_aussen(),
                    sehne, winkel, 60, lage=lage)


# ---------------------------------------------------------------- Geometrie

def test_schnittzahl_und_aufbau(profil):
    stapel = _fluegel(profil)
    assert len(stapel) == 13
    # Gleicher Aufbau ueberall - sonst verdreht der Boundary Blend die Flaeche.
    punktzahlen = {len(s.punkte) for s in stapel}
    assert len(punktzahlen) == 1


def test_lage_verschiebt_alles_gleich(profil):
    ohne = _fluegel(profil, lage=(0.0, 0.0, 0.0))
    mit = _fluegel(profil, lage=(-600.0, 25.0, 90.0))
    for a, b in zip(ohne, mit):
        versatz = b.punkte - a.punkte
        assert np.allclose(versatz, [-600.0, 25.0, 90.0])


def test_verwindung_wirkt_additiv(profil):
    """Die Wurzel des Frontfluegel-Presets steht -10 Grad gegen den Grundwinkel."""
    stapel = _fluegel(profil, winkel=-4.0)
    assert stapel[0].anstellwinkel == pytest.approx(-14.0)
    assert stapel[-1].anstellwinkel == pytest.approx(-2.0)


def test_sehne_wirkt_multiplikativ(profil):
    stapel = _fluegel(profil, sehne=250.0)
    assert stapel[0].sehne == pytest.approx(0.85 * 250.0)
    assert stapel[-1].sehne == pytest.approx(1.00 * 250.0)


def test_verlauf_schwingt_nicht_ueber(profil):
    """PCHIP statt kubischem Spline: zwischen zwei Stationen darf keine
    Sehne herauskommen, die groesser ist als beide Nachbarn."""
    spw = Spannweite(stuetzstellen=[
        Stuetzstelle(y=0.0, sehne=0.6),
        Stuetzstelle(y=300.0, sehne=1.0),
        Stuetzstelle(y=600.0, sehne=1.0)], schnitte=41)
    stapel = _fluegel(profil, spannweite=spw)
    sehnen = np.array([s.sehne for s in stapel])
    assert sehnen.max() <= 1.0 * 250.0 + 1e-9
    assert np.all(np.diff(sehnen) >= -1e-9)      # monoton steigend


def test_sektionen_paarweise_und_gleich_lang(profil):
    stapel = _fluegel(profil)
    sektionen = als_sektionen(stapel)
    assert len(sektionen) == 2 * len(stapel)
    laengen = {len(s) for s in sektionen}
    assert len(laengen) == 1
    # Ober- und Unterseite muessen sich an der Nase treffen.
    assert np.allclose(sektionen[0][-1], sektionen[1][0])


def test_huellwerte_stimmen_mit_der_wolke(profil):
    stapel = _fluegel(profil)
    h = huellwerte(stapel)
    alle = np.vstack([s.punkte for s in stapel])
    assert h["x_min"] == pytest.approx(alle[:, 0].min())
    assert h["z_max"] == pytest.approx(alle[:, 2].max())
    assert h["spannweite"] == pytest.approx(600.0)
    assert h["flaeche"] > 0.0


def test_einzelne_stuetzstelle_ergibt_rechteckfluegel(profil):
    spw = Spannweite(stuetzstellen=[Stuetzstelle(y=0.0)], schnitte=2)
    stapel = schnitte(profil, spw, 200.0, -3.0, 40)
    assert {s.sehne for s in stapel} == {200.0}
    assert {s.anstellwinkel for s in stapel} == {-3.0}


# ------------------------------------------------------------ Regelstaende

def test_beide_staende_laden():
    staende = alle_staende()
    assert [r.version for r in staende] == ["2026-v1.1", "2027-draft"]
    assert staende[0].verbindlich is True
    assert staende[1].entwurf is True


def test_2027_kennt_die_quaderregel_2026_nicht():
    assert lade("2026")["t2_1_4"] is None
    assert lade("2027")["t2_1_4"]["quader_breite"] == 75


def test_unbekannter_stand_meldet_sich():
    with pytest.raises(ValueError, match="Unbekannter Regelstand"):
        lade("2025")


def test_bezugsebenen_aus_der_fahrzeugreferenz(bezug):
    assert bezug.vorderreifen_vorderkante_x == pytest.approx(-203.2)
    assert bezug.reifenoberkante_z == pytest.approx(406.4)
    assert bezug.rad_aussen_vorne == pytest.approx(695.25)
    assert bezug.rad_innen_hinten == pytest.approx(494.75)


# -------------------------------------------------------------- Pruefungen

def _befund(befunde, regel, teil):
    treffer = [b for b in befunde if b.regel == regel and teil in b.pruefung]
    assert treffer, f"Keine Pruefung {regel} / {teil} in " \
                    f"{[b.pruefung for b in befunde]}"
    return treffer[0]


def test_brauchbarer_frontfluegel_besteht_beide_staende(profil, bezug):
    stapel = _fluegel(profil)
    zustand = Fahrzustand.bremsend(600.0)
    for rs in alle_staende():
        befunde = pruefe_fluegel(stapel, rs, bezug, zustand)
        schlecht = [b for b in befunde if not b.ok]
        assert not schlecht, [str(b) for b in schlecht]


def test_zu_tiefer_fluegel_faellt_ueber_die_bodenfreiheit(profil, bezug):
    stapel = _fluegel(profil, lage=(-600.0, 0.0, 55.0))
    b = _befund(pruefe_fluegel(stapel, lade("2026"), bezug,
                               Fahrzustand.bremsend(600.0)),
                "T 2.2.1", "Bodenfreiheit")
    assert not b.ok and b.blockiert
    assert "höher gesetzt" in b.hinweis


def test_bremsfall_ist_strenger_als_die_konstruktionslage(profil, bezug):
    """Genau der Fall, den T 8.2.4 meint: statisch in Ordnung, im Fahrzustand
    nicht mehr."""
    # 70 mm ist so gewaehlt, dass der tiefste Punkt bei 35,4 mm liegt: ueber
    # den geforderten 30 mm, aber weniger als die 6,6 mm Absinken darueber,
    # die der Bremsfall kostet. Genau dieses schmale Fenster ist der Sinn des
    # Tests. (Vor der Korrektur der Drehrichtung in angestellt() lag es bei
    # 78 mm - der Fluegel war damals andersherum gedreht.)
    stapel = _fluegel(profil, lage=(-600.0, 0.0, 70.0))
    statisch = _befund(pruefe_fluegel(stapel, lade("2026"), bezug,
                                      Fahrzustand.statisch()),
                       "T 2.2.1", "Bodenfreiheit")
    fahrend = _befund(pruefe_fluegel(stapel, lade("2026"), bezug,
                                     Fahrzustand.bremsend(600.0)),
                      "T 2.2.1", "Bodenfreiheit")
    assert statisch.ok
    assert not fahrend.ok
    assert fahrend.ist < statisch.ist


def test_zu_weit_vorstehender_fluegel_reisst_die_laengengrenze(profil, bezug):
    stapel = _fluegel(profil, lage=(-1100.0, 0.0, 90.0))
    b = _befund(pruefe_fluegel(stapel, lade("2026"), bezug),
                "T 8.2.3", "vor den Vorderreifen")
    assert not b.ok
    assert b.ist > 700.0


def test_hoher_fluegel_reisst_2027_frueher_als_2026(profil, bezug):
    """300 mm hoch vor dem Rad: 2026 unzulaessig (250), 2027 zulaessig (350).

    Das ist die einzige Hoehenaenderung, die den Frontfluegel LOCKERT - und
    genau deshalb der Fall, an dem sich zeigt, ob der Pruefer die Staende
    wirklich auseinanderhaelt.
    """
    stapel = _fluegel(profil, lage=(-600.0, 0.0, 300.0))
    zustand = Fahrzustand.statisch()
    b26 = _befund(pruefe_fluegel(stapel, lade("2026"), bezug, zustand),
                  "T 8.2.1", "vor der Vorderachse")
    b27 = _befund(pruefe_fluegel(stapel, lade("2027"), bezug, zustand),
                  "T 8.2.1", "vor der Reifenvorderkante")
    assert not b26.ok
    assert b27.ok


def test_breiter_fluegel_setzt_den_quaderkanal_zu(profil, bezug):
    """T 2.1.4: Ein bis zur Radaussenkante durchgezogener Frontfluegel laesst
    keinen 75-mm-Kanal mehr frei. 2026 gibt es die Regel nicht."""
    breit = Spannweite(stuetzstellen=[
        Stuetzstelle(y=0.0, sehne=0.85, verwindung=-10.0),
        Stuetzstelle(y=695.0, sehne=1.0, verwindung=2.0)], schnitte=25)
    stapel = _fluegel(profil, spannweite=breit)

    befunde26 = pruefe_fluegel(stapel, lade("2026"), bezug)
    assert not [b for b in befunde26 if b.regel == "T 2.1.4"]

    b = _befund(pruefe_fluegel(stapel, lade("2027"), bezug), "T 2.1.4", "Kanal")
    assert not b.ok
    assert b.ist < 75.0
    # Entwurf blockiert nicht, er warnt.
    assert b.stufe == "hinweis" and not b.blockiert


def test_schlitz_in_der_spannweite_rettet_den_quaderkanal(profil, bezug):
    """Gegenprobe: Mit einer Luecke von 100 mm besteht derselbe Fluegel."""
    innen = _fluegel(profil, spannweite=Spannweite(stuetzstellen=[
        Stuetzstelle(y=0.0, sehne=0.85, verwindung=-10.0),
        Stuetzstelle(y=300.0, sehne=0.95, verwindung=-4.0)], schnitte=13))
    aussen = _fluegel(profil, spannweite=Spannweite(stuetzstellen=[
        Stuetzstelle(y=400.0, sehne=1.0, verwindung=0.0),
        Stuetzstelle(y=695.0, sehne=1.0, verwindung=2.0)], schnitte=13))
    b = _befund(pruefe_fluegel(innen + aussen, lade("2027"), bezug),
                "T 2.1.4", "Kanal")
    assert b.ok
    assert b.ist == pytest.approx(100.0, abs=1.0)


def test_tiefer_heckfluegel_faellt_erst_2027(profil, bezug):
    """Die neue Untergrenze von 700 mm. 2026 gibt es sie nicht."""
    stapel = _fluegel(profil, lage=(1200.0, 0.0, 600.0), winkel=-8.0,
                      spannweite=Spannweite.gerade(500.0))
    befunde26 = pruefe_fluegel(stapel, lade("2026"), bezug)
    assert not [b for b in befunde26 if "nicht unter" in b.pruefung]

    b = _befund(pruefe_fluegel(stapel, lade("2027"), bezug),
                "T 8.2.1", "nicht unter")
    assert not b.ok
    assert b.stufe == "hinweis"


def test_hoher_heckfluegel_besteht_die_untergrenze(profil, bezug):
    stapel = _fluegel(profil, lage=(1200.0, 0.0, 900.0), winkel=-8.0,
                      spannweite=Spannweite.gerade(500.0))
    b = _befund(pruefe_fluegel(stapel, lade("2027"), bezug),
                "T 8.2.1", "nicht unter")
    assert b.ok


def test_breitengrenze_oben_lockert_sich_2027(profil, bezug):
    """Ueber Reifenoberkante zaehlt 2027 der AEUSSERSTE statt des innersten
    Hinterradpunkts - die einzige Lockerung im Entwurf."""
    stapel = _fluegel(profil, lage=(1200.0, 0.0, 900.0), winkel=-8.0,
                      spannweite=Spannweite.gerade(550.0))
    b26 = _befund(pruefe_fluegel(stapel, lade("2026"), bezug), "T 8.2.2", "über")
    b27 = _befund(pruefe_fluegel(stapel, lade("2027"), bezug), "T 8.2.2", "über")
    assert b26.grenze == pytest.approx(bezug.rad_innen_hinten)
    assert b27.grenze == pytest.approx(bezug.rad_aussen_hinten)
    assert not b26.ok
    assert b27.ok


def test_geltende_regeln_bleiben_auch_im_entwurf_hart(profil, bezug):
    """T 2.2.1 gilt heute. Im Entwurfsdurchlauf darf daraus kein Hinweis
    werden - sonst liest sich ein harter Verstoss wie eine Fussnote."""
    stapel = _fluegel(profil, lage=(-600.0, 0.0, 50.0))
    b = _befund(pruefe_fluegel(stapel, lade("2027"), bezug,
                               Fahrzustand.bremsend(600.0)),
                "T 2.2.1", "Bodenfreiheit")
    assert not b.ok
    assert b.stufe == "fehler" and b.blockiert


def test_keepout_greift_wenn_der_fluegel_neben_dem_rad_sitzt(profil, bezug):
    """Ein Fluegel in Radhoehe seitlich neben dem Vorderrad verletzt T 2.1.3."""
    stapel = _fluegel(profil, lage=(-100.0, 550.0, 200.0),
                      spannweite=Spannweite.gerade(80.0))
    b = _befund(pruefe_fluegel(stapel, lade("2026"), bezug,
                               Fahrzustand.statisch()),
                "T 2.1.3", "Vorderrad")
    assert not b.ok
    assert b.ist > 0


def test_gespiegelte_haelfte_wird_mitgeprueft(profil, bezug):
    """Wer die linke Haelfte modelliert, darf nicht durch die Breitenpruefung
    rutschen."""
    rechts = _fluegel(profil, lage=(1200.0, 0.0, 900.0), winkel=-8.0,
                      spannweite=Spannweite.gerade(550.0))
    links = [Schnitt(-s.y, s.sehne, s.anstellwinkel,
                     s.punkte * np.array([1.0, -1.0, 1.0])) for s in rechts]
    b_r = _befund(pruefe_fluegel(rechts, lade("2026"), bezug), "T 8.2.2", "über")
    b_l = _befund(pruefe_fluegel(links, lade("2026"), bezug), "T 8.2.2", "über")
    assert b_r.ist == pytest.approx(b_l.ist)
    assert not b_l.ok


def test_reserve_zeigt_in_die_richtige_richtung(profil, bezug):
    stapel = _fluegel(profil)
    for b in pruefe_fluegel(stapel, lade("2026"), bezug,
                            Fahrzustand.bremsend(600.0)):
        assert (b.reserve >= -1e-9) == b.ok
