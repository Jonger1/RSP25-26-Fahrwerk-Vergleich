"""
Tests zu den Funden des Code-Review vom 26.09.2026.

Zwoelf Funde, alle in Code aus dieser Sitzung, keiner von der bestehenden
Testabdeckung erfasst. Das ist der Grund fuer diese Datei: Jeder Fund
bekommt einen Test, der genau die Eigenschaft prueft, die gefehlt hat -
sonst kehren sie beim naechsten Umbau zurueck.

Ein Muster zieht sich durch mehrere davon: Die Oberflaeche versprach etwas
(Anstellwinkel uebernehmen, Footplate 60 mm, Regelstand waehlbar), und der
Code loeste es nicht ein. Solche Fehler sind besonders teuer, weil sie nicht
auffallen - es kommt ja ein Ergebnis heraus.
"""

import numpy as np
import pytest

from aerostudio.aero import kaskade as aero_k
from aerostudio.aero import panel
from aerostudio.geometrie import endplatte as ep
from aerostudio.geometrie import kaskade as geo_k
from aerostudio.geometrie.profil import Profil
from aerostudio.regeln import lade
from aerostudio.spec.modell import Endplatte, Fertigung, Footplate
from aerostudio.spec.projekt import AeroSpec
from aerostudio.ui import app as UI
from aerostudio.ui import darstellung


@pytest.fixture(scope="module")
def beispiel():
    return AeroSpec.laden("specs/beispiele/frontfluegel_zweielementig.yaml")


# --- Fund 1: Saugseite wurde in der Nasensingularitaet gesucht ----------

def test_saugseite_ignoriert_die_nasenspitze():
    """Der Fund, der das ganze Abrisskriterium betraf.

    `_saugseite` suchte die Spitze mit dem rohen argmin - und der landet in
    genau der numerischen Spitze an der Nase, die `saugspitze` bewusst
    ausschliesst. Bei drei Elementen traf die Maske die DRUCKseite, und der
    Rueckgewinn mischte anschliessend beide Flaechen.
    """
    haupt = Profil.aus_dat("profile/katalog/e423.dat").gespiegelt()
    flap = Profil.aus_dat("profile/katalog/s1223.dat").gespiegelt()
    flaps = [geo_k.Kaskadenvorgabe(profil=flap, sehne_faktor=0.35 - 0.06 * i,
                                   winkel_relativ=w, spalt=0.015,
                                   ueberlappung=0.02)
             for i, w in enumerate((-16.0, -14.0))]

    el = geo_k.platziere(haupt, 250.0, -4.0, flaps, punkte=100)
    koerper = [panel.Koerper(punkte=e.punkte) for e in el]
    loesung = panel.loese(koerper, alpha_grad=-4.0,
                          bezugssehne=geo_k.gesamtsehne(el))

    cp, punkte = loesung.cp[0], koerper[0].punkte
    x_rel = aero_k._x_relativ(punkte)
    maske = aero_k._saugseite(cp, x_rel)

    # Die Spitze ausserhalb der Nase muss auf der gewaehlten Seite liegen.
    frei = x_rel >= aero_k.NASENAUSSCHLUSS
    spitze = int(np.argmin(np.where(frei, cp, np.inf)))
    assert maske[spitze], "Die Maske liegt auf der falschen Seite"

    # Und die Maske darf nur EINE Seite umfassen, nicht beide.
    nase = int(np.argmin(x_rel))
    assert maske[:nase].all() or maske[nase:].all()
    assert not maske.all()


# --- Fund 4: Footplate hatte null Hoehe --------------------------------

def test_footplate_hat_echte_erstreckung(beispiel):
    """Sie bekam still null Hoehe, waehrend die Oberflaeche Vollzug meldete.

    Grund war die Semantik: `hoehe` galt als "ueber Grund", aber die
    Plattenunterkante liegt beim Frontfluegel bei 71 mm. Eine Footplate
    "bis 25 mm ueber Grund" kann daran nicht haengen.
    """
    element = beispiel.elemente[0]
    teile = UI._elementstapel(element)
    masse = ep.masse(teile, element.endplatte)
    schnitte = ep.schnitte(teile, element.endplatte)

    assert len(schnitte) == 4, "Platte innen/aussen plus Footplate unten/oben"

    z_fuss = sorted({float(s.punkte[0, 2]) for s in schnitte[2:]})
    assert len(z_fuss) == 2, "Die Footplate hat keine vertikale Erstreckung"
    assert z_fuss[1] - z_fuss[0] == pytest.approx(
        element.endplatte.footplate.hoehe, abs=0.01)
    assert z_fuss[0] == pytest.approx(masse.z_unten, abs=0.01)


def test_footplate_wird_nach_oben_geklemmt():
    """Ueber die Endplatte hinaus gibt es sie nicht."""
    profil = Profil.aus_dat("profile/katalog/e423.dat").gespiegelt()
    from aerostudio.geometrie.spannweite import schnitte as spw_schnitte
    from aerostudio.spec.modell import Spannweite

    stapel = spw_schnitte(profil, Spannweite.frontfluegel_aussen(), 250.0,
                          -4.0, 40, lage=(-600.0, 0.0, 90.0))
    vorgabe = Endplatte(footplate=Footplate(breite=60.0, hoehe=300.0))
    masse = ep.masse([stapel], vorgabe)
    z = np.vstack([s.punkte for s in ep.schnitte([stapel], vorgabe)])[:, 2]

    assert z.max() <= masse.z_oben + 1e-9


# --- Fund 5: Rippensatz lag immer flach --------------------------------

def test_rippensatz_uebernimmt_den_anstellwinkel(tmp_path):
    """Die Oberflaeche versprach es, der Code reichte ihn nicht durch."""
    from aerostudio.formate import dxf
    from aerostudio.spec.modell import Spannweite, Stuetzstelle

    pytest.importorskip("ezdxf")
    import ezdxf

    profil = Profil.aus_dat("profile/katalog/e423.dat")
    spw = Spannweite(stuetzstellen=[Stuetzstelle(y=0.0, sehne=1.0),
                                    Stuetzstelle(y=600.0, sehne=1.0)],
                     schnitte=5)
    fertigung = Fertigung(verfahren="prepreg", wandstaerke=0.6, kern=3.0)

    def hoehe(ordner, winkel):
        satz = dxf.schreibe_rippensatz(ordner, profil, spw, 250.0, fertigung,
                                       stationen=2, grundwinkel=winkel)
        doc = ezdxf.readfile(satz[0][0])
        p = [np.array([(q[0], q[1]) for q in e.get_points()])
             for e in doc.modelspace()
             if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == dxf.LAYER_KONTUR][0]
        return p[np.argmax(p[:, 0]), 1]

    flach = hoehe(tmp_path / "flach", 0.0)
    schraeg = hoehe(tmp_path / "schraeg", -8.0)

    assert schraeg != pytest.approx(flach, abs=0.5), \
        "Der Rippensatz liegt flach, obwohl ein Winkel vorgegeben ist"
    assert schraeg - flach == pytest.approx(
        0.75 * 250.0 * np.sin(np.radians(8.0)), rel=0.05)


# --- Funde 2 und 3: Die Zeichnungen lasen ihren Regelstand nicht -------

def _stapel(beispiel):
    element = beispiel.elemente[0]
    return [s for teil in UI._elementstapel(element) for s in teil]


def test_draufsicht_folgt_dem_regelstand(beispiel):
    """2026 gilt oberhalb der Schwelle der INNERSTE Radpunkt (494,75 mm),
    2027 der aeusserste (695,25). Die Zeichnung las den Satz gar nicht."""
    from aerostudio.regeln import Bezugsgeometrie

    bezug = Bezugsgeometrie.aus_datei()
    stapel = _stapel(beispiel)

    def grenzen(stand):
        fig = darstellung.draufsicht(stapel, bezug, lade(stand))
        return {s.name for s in fig.data if s.name and "T 8.2.2" in s.name}

    assert grenzen("2026") != grenzen("2027")
    assert any(f"{bezug.rad_innen_hinten:.0f}" in n for n in grenzen("2026"))
    assert any(f"{bezug.rad_aussen_hinten:.0f}" in n for n in grenzen("2027"))


def test_seitenansicht_folgt_dem_regelstand(beispiel):
    """2027 ersetzt die 500-mm-Kopfstuetzenebene durch die Reifenoberkante.
    Fest verdrahtet war das Bild grosszuegiger als die Ampel daneben."""
    from aerostudio.regeln import Bezugsgeometrie, Fahrzustand

    bezug = Bezugsgeometrie.aus_datei()
    stapel = _stapel(beispiel)

    def texte(stand):
        fig = darstellung.seitenansicht(stapel, bezug, lade(stand),
                                        Fahrzustand())
        return " ".join(str(s.name) for s in fig.data if s.name)

    assert "500" in texte("2026")
    assert f"{bezug.reifenoberkante_z:.0f}" in texte("2027")
    assert "500 mm" not in texte("2027")


# --- Fund 6: Port-Meldung griff auf Windows nicht ----------------------

@pytest.mark.parametrize("errno,text", [
    (98, "Address already in use"),                    # Linux
    (48, "Address already in use"),                    # macOS
    (10048, "Normalerweise darf jede Socketadresse"),  # Windows, uebersetzt
])
def test_belegter_port_wird_auf_jeder_plattform_erkannt(errno, text,
                                                        monkeypatch, capsys):
    """Windows ist die Zielplattform - und dort ist die Meldung ausserdem
    uebersetzt. Auf "in use" zu pruefen greift genau da nicht."""
    fehler = OSError(errno, text)

    def kaputt(*a, **k):
        raise fehler

    monkeypatch.setattr(UI.app, "run", kaputt)
    with pytest.raises(SystemExit):
        UI.starten(port=8051, browser=False)

    ausgabe = capsys.readouterr().out
    assert "Port 8051 ist belegt" in ausgabe
    assert "8052" in ausgabe            # der Vorschlag fuer einen anderen


def test_anderer_oserror_wird_nicht_verschluckt(monkeypatch):
    """Nur der belegte Port bekommt die freundliche Behandlung."""
    def kaputt(*a, **k):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(UI.app, "run", kaputt)
    with pytest.raises(OSError):
        UI.starten(port=8051, browser=False)


# --- Fund 12: Exportinfo beschrieb die Endplatte falsch ----------------

def test_exportinfo_kennt_die_endplatte(beispiel, tmp_path):
    from aerostudio.formate import export

    element = beispiel.elemente[0]
    plan = export.plane_endplatte(UI._elementstapel(element), element.endplatte)
    text = str(UI._exportinfo(plan, tmp_path / "x.ibl", None))

    assert "Endplatte" in text
    # Keine erfundene Toleranz fuer ein Polygon aus geraden Kanten.
    assert "0.0000 mm Toleranz" not in text
    assert "gerade Kanten" in text
