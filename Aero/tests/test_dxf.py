"""
Tests fuer die Fertigungsvorlagen (M1 Aufgabe 9).

Der wichtigste Test hier ist der auf die WANDSTAERKE. Eine Rippe, deren
Innenkontur ein paar Zehntel daneben liegt, sieht auf dem Bildschirm
tadellos aus und faellt erst auf, wenn das Teil geschnitten ist und nicht in
die Schale passt. Deshalb wird der Abstand zwischen Aussen- und Innenkontur
nicht geglaubt, sondern gemessen - und zwar senkrecht, nicht in y-Richtung:
An der Nase sind das zwei sehr verschiedene Zahlen.
"""

from pathlib import Path

import numpy as np
import pytest

from aerostudio.formate import dxf
from aerostudio.geometrie.profil import Profil
from aerostudio.spec.modell import Fertigung, Spannweite, Stuetzstelle

ezdxf = pytest.importorskip("ezdxf")


@pytest.fixture(scope="module")
def profil():
    return Profil.aus_dat("profile/katalog/e423.dat")


@pytest.fixture
def fertigung():
    return Fertigung(verfahren="prepreg", wandstaerke=0.6, kern=3.0,
                     klebespalt=0.2)


def _punkte(pfad: Path, layer: str) -> list[np.ndarray]:
    """Holt die Polylinien eines Layers aus der geschriebenen Datei zurueck."""
    doc = ezdxf.readfile(pfad)
    return [np.array([(p[0], p[1]) for p in e.get_points()])
            for e in doc.modelspace()
            if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == layer]


def _kuerzester_abstand(punkt: np.ndarray, kurve: np.ndarray) -> float:
    """Punkt zu STRECKENZUG, nicht Punkt zu Punkt.

    Punkt-zu-Punkt haenge am Raster: Zwei Kurven im Abstand 0,6 mm meldeten
    je nach Punktdichte irgendetwas zwischen 0,6 und 0,9 mm.
    """
    a, b = kurve[:-1], kurve[1:]
    ab = b - a
    laenge2 = np.einsum("ij,ij->i", ab, ab)
    laenge2[laenge2 == 0] = 1e-12
    t = np.clip(np.einsum("ij,ij->i", punkt - a, ab) / laenge2, 0.0, 1.0)
    fuss = a + t[:, None] * ab
    return float(np.linalg.norm(fuss - punkt, axis=1).min())


# ------------------------------------------------------------- Schablone

def test_schablone_traegt_die_aussenkontur(profil, tmp_path):
    ziel = dxf.schreibe_schablone(tmp_path / "s.dxf", profil, 250.0)

    konturen = _punkte(ziel, dxf.LAYER_KONTUR)
    assert len(konturen) == 1
    k = konturen[0]
    # Sehne 250 mm, also reicht die Kontur von 0 bis 250.
    assert k[:, 0].min() == pytest.approx(0.0, abs=0.5)
    assert k[:, 0].max() == pytest.approx(250.0, abs=0.5)


def test_schablone_dreht_mit_dem_anstellwinkel(profil, tmp_path):
    """Eine Schablone auf einer Vorrichtung muss so liegen wie das Bauteil."""
    gerade = _punkte(dxf.schreibe_schablone(tmp_path / "a.dxf", profil, 250.0),
                     dxf.LAYER_KONTUR)[0]
    schraeg = _punkte(dxf.schreibe_schablone(tmp_path / "b.dxf", profil, 250.0,
                                             anstellwinkel=-8.0),
                      dxf.LAYER_KONTUR)[0]

    assert not np.allclose(gerade, schraeg)

    # Bei -8 Grad zeigt die Nase nach unten, die Hinterkante also nach oben.
    # Gedreht wird um die VIERTELSEHNE, nicht um die Nase - der hinterste
    # Punkt hat davon 3/4 der Sehne Abstand, und genau um dessen Hebung geht
    # es hier.
    hinten_gerade = gerade[np.argmax(gerade[:, 0]), 1]
    hinten_schraeg = schraeg[np.argmax(schraeg[:, 0]), 1]
    erwartet = 0.75 * 250.0 * np.sin(np.radians(8.0))
    assert hinten_schraeg - hinten_gerade == pytest.approx(erwartet, rel=0.05)


def test_sehnenlinie_liegt_auf_einem_eigenen_layer(profil, tmp_path):
    """Sie ist eine Ausrichthilfe. Wer sie mitschneidet, zersaegt sein Teil."""
    ziel = dxf.schreibe_schablone(tmp_path / "s.dxf", profil, 250.0)
    doc = ezdxf.readfile(ziel)

    linien = [e for e in doc.modelspace() if e.dxftype() == "LINE"]
    assert linien and all(e.dxf.layer == dxf.LAYER_HILFE for e in linien)
    assert dxf.LAYER_HILFE != dxf.LAYER_KONTUR


def test_datei_traegt_millimeter(profil, tmp_path):
    """Ohne $INSUNITS raet das CAM-Programm - und raet gelegentlich Zoll."""
    ziel = dxf.schreibe_schablone(tmp_path / "s.dxf", profil, 250.0)
    assert ezdxf.readfile(ziel).header["$INSUNITS"] == 4


# ------------------------------------------------------------------ Rippe

def test_rippe_hat_aussen_und_innenkontur(profil, tmp_path, fertigung):
    ziel, befund = dxf.schreibe_rippe(tmp_path / "r.dxf", profil, 250.0,
                                      fertigung)

    assert befund.hat_hohlraum
    assert len(_punkte(ziel, dxf.LAYER_KONTUR)) == 1
    assert len(_punkte(ziel, dxf.LAYER_HOHLRAUM)) == 1


def test_wandstaerke_stimmt_senkrecht_gemessen(profil, tmp_path, fertigung):
    """Der Test, der den Unterschied macht.

    Gemessen wird der kuerzeste Abstand jedes Innenpunkts zur Aussenkontur.
    Eine Innenkontur, die nur in y-Richtung versetzt waere, liefe an der
    Nase um ein Vielfaches daneben - dort steht die Kontur fast senkrecht.
    """
    ziel, befund = dxf.schreibe_rippe(tmp_path / "r.dxf", profil, 250.0,
                                      fertigung)
    aussen = _punkte(ziel, dxf.LAYER_KONTUR)[0]
    innen = _punkte(ziel, dxf.LAYER_HOHLRAUM)[0]

    abstaende = np.array([_kuerzester_abstand(p, aussen) for p in innen])

    # Die Enden des Hohlraums sind Geraden quer durchs Profil - dort ist der
    # Abstand naturgemaess groesser. Geprueft wird die Flanke, also die
    # mittleren 80 Prozent.
    x_innen = innen[:, 0]
    mitte = ((x_innen > x_innen.min() + 0.1 * np.ptp(x_innen))
             & (x_innen < x_innen.max() - 0.1 * np.ptp(x_innen)))

    assert abstaende[mitte].mean() == pytest.approx(0.6, abs=0.08)
    assert abstaende[mitte].max() < 1.0


def test_dickere_wand_gibt_kleineren_hohlraum(profil, tmp_path):
    duenn = Fertigung(verfahren="autoklav", wandstaerke=0.4, kern=0.0,
                      klebespalt=0.15)
    dick = Fertigung(verfahren="nasslaminat", wandstaerke=2.5, kern=0.0,
                     klebespalt=0.3)

    _, a = dxf.schreibe_rippe(tmp_path / "a.dxf", profil, 250.0, duenn)
    _, b = dxf.schreibe_rippe(tmp_path / "b.dxf", profil, 250.0, dick)

    assert a.flaeche_hohl > b.flaeche_hohl
    assert b.vollmaterial_anteil > a.vollmaterial_anteil


def test_hohlraum_endet_wo_das_profil_zu_duenn_wird(profil, fertigung):
    """Nach vorne und hinten laeuft jedes Profil zusammen."""
    _, befund = dxf.innenkontur(profil, 250.0, fertigung)

    assert befund.hohl_von > 0.0, "Der Hohlraum darf nicht an der Nase beginnen"
    assert befund.hohl_bis < 1.0, "und nicht an der Hinterkante enden"


def test_sehr_kleine_sehne_wird_vollmaterial(profil, tmp_path):
    """Bei 25 mm Sehne und 2,5 mm Wand ist nichts mehr hohl.

    Das ist kein Fehler, sondern ein Befund - und die Datei muss trotzdem
    entstehen, sonst steht der Anwender ohne Vorlage da.
    """
    grob = Fertigung(verfahren="nasslaminat", wandstaerke=2.5, kern=0.0,
                     klebespalt=0.3)
    ziel, befund = dxf.schreibe_rippe(tmp_path / "klein.dxf", profil, 25.0, grob)

    assert not befund.hat_hohlraum
    assert befund.vollmaterial_anteil == pytest.approx(1.0)
    assert ziel.exists()
    assert len(_punkte(ziel, dxf.LAYER_KONTUR)) == 1
    assert _punkte(ziel, dxf.LAYER_HOHLRAUM) == []


def test_vollmaterial_steht_in_der_beschriftung(profil, tmp_path):
    grob = Fertigung(verfahren="nasslaminat", wandstaerke=2.5, kern=0.0,
                     klebespalt=0.3)
    ziel, _ = dxf.schreibe_rippe(tmp_path / "k.dxf", profil, 25.0, grob)

    texte = [e.dxf.text for e in ezdxf.readfile(ziel).modelspace()
             if e.dxftype() == "TEXT"]
    assert any("VOLLMATERIAL" in t for t in texte)


def test_hohlraum_liegt_innerhalb_der_aussenkontur(profil, tmp_path, fertigung):
    ziel, _ = dxf.schreibe_rippe(tmp_path / "r.dxf", profil, 250.0, fertigung)
    aussen = _punkte(ziel, dxf.LAYER_KONTUR)[0]
    innen = _punkte(ziel, dxf.LAYER_HOHLRAUM)[0]

    assert innen[:, 0].min() > aussen[:, 0].min()
    assert innen[:, 0].max() < aussen[:, 0].max()
    assert innen[:, 1].max() < aussen[:, 1].max()
    assert innen[:, 1].min() > aussen[:, 1].min()


def test_rippe_und_schablone_drehen_gleich(profil, tmp_path, fertigung):
    """Sonst liegt das eine Teil anders als das andere.

    Die Rippe drehte bis zum 23.09. um die NASE, die Schablone ueber
    Profil.angestellt um die VIERTELSEHNE. Zwei verschiedene Drehungen unter
    demselben Wort - auf der Vorrichtung faellt so etwas erst auf, wenn
    beide Teile nebeneinanderliegen.
    """
    schablone = _punkte(
        dxf.schreibe_schablone(tmp_path / "s.dxf", profil, 250.0,
                               anstellwinkel=-8.0), dxf.LAYER_KONTUR)[0]
    rippe = _punkte(
        dxf.schreibe_rippe(tmp_path / "r.dxf", profil, 250.0, fertigung,
                           anstellwinkel=-8.0)[0], dxf.LAYER_KONTUR)[0]

    # Dieselbe Aussenkontur, dieselbe Drehung - also dieselbe Huelle.
    assert rippe[:, 0].min() == pytest.approx(schablone[:, 0].min(), abs=0.01)
    assert rippe[:, 0].max() == pytest.approx(schablone[:, 0].max(), abs=0.01)
    assert rippe[:, 1].min() == pytest.approx(schablone[:, 1].min(), abs=0.01)
    assert rippe[:, 1].max() == pytest.approx(schablone[:, 1].max(), abs=0.01)


def test_gedrehte_rippe_behaelt_ihre_wandstaerke(profil, tmp_path, fertigung):
    """Drehen ist laengentreu - wenn beide Konturen gleich gedreht werden."""
    ziel, _ = dxf.schreibe_rippe(tmp_path / "r.dxf", profil, 250.0, fertigung,
                                 anstellwinkel=-8.0)
    aussen = _punkte(ziel, dxf.LAYER_KONTUR)[0]
    innen = _punkte(ziel, dxf.LAYER_HOHLRAUM)[0]

    abstaende = np.array([_kuerzester_abstand(p, aussen) for p in innen])
    x = innen[:, 0]
    mitte = ((x > x.min() + 0.1 * np.ptp(x)) & (x < x.max() - 0.1 * np.ptp(x)))
    assert abstaende[mitte].mean() == pytest.approx(0.6, abs=0.08)


# ----------------------------------------------------------- Rippensatz

def test_rippensatz_schreibt_je_station_eine_datei(profil, tmp_path, fertigung):
    spw = Spannweite(stuetzstellen=[Stuetzstelle(y=0.0, sehne=1.0),
                                    Stuetzstelle(y=600.0, sehne=0.6)],
                     schnitte=13)
    satz = dxf.schreibe_rippensatz(tmp_path, profil, spw, 250.0, fertigung,
                                   stationen=5)

    assert len(satz) == 5
    assert len(list(tmp_path.glob("*.dxf"))) == 5
    # Nach aussen verjuengt - die Rippen werden kleiner.
    flaechen = [b.flaeche_aussen for _pfad, b in satz]
    assert flaechen == sorted(flaechen, reverse=True)


def test_rippensatz_braucht_mindestens_eine_station(profil, tmp_path, fertigung):
    spw = Spannweite(stuetzstellen=[Stuetzstelle(y=0.0)], schnitte=2)
    with pytest.raises(ValueError, match="mindestens eine"):
        dxf.schreibe_rippensatz(tmp_path, profil, spw, 250.0, fertigung,
                                stationen=0)


def test_rippensatz_nennt_die_spannweitenposition(profil, tmp_path, fertigung):
    spw = Spannweite(stuetzstellen=[Stuetzstelle(y=0.0, sehne=1.0),
                                    Stuetzstelle(y=600.0, sehne=0.6)],
                     schnitte=13)
    satz = dxf.schreibe_rippensatz(tmp_path, profil, spw, 250.0, fertigung,
                                   stationen=3)

    namen = [p.name for p, _b in satz]
    assert any("y0" in n for n in namen)
    assert any("y600" in n for n in namen)
