"""
Tests fuer die Abtriebsabschaetzung.

Der Schwerpunkt liegt auf NACHPRUEFBAREN Faellen: Die Traglinienrechnung wird
gegen die analytische Loesung der Tragflaechentheorie geprueft, die
Bodenspiegelung gegen ihre eigene Randbedingung. Ein Test, der nur prueft,
dass eine Zahl herauskommt, wuerde jeden Vorzeichenfehler durchlassen - und
genau daran ist der erste Entwurf gescheitert.
"""

import numpy as np
import pytest

from aerostudio.aero import profilpolare as pol
from aerostudio.aero import traglinie as tl
from aerostudio.geometrie.profil import Profil
from aerostudio.geometrie.spannweite import schnitte
from aerostudio.spec.modell import Spannweite, Stuetzstelle


# ------------------------------------------------------------- Hilfsmittel

def ebene_platte(steigung_je_rad: float = 2 * np.pi) -> pol.Polare:
    """Eine Polare mit linearem Verlauf - die ebene Platte der Theorie.

    Damit laesst sich gegen geschlossene Formeln pruefen, ohne dass die
    Unsicherheit von NeuralFoil dazwischenfunkt.
    """
    a = np.linspace(-40.0, 40.0, 1601)
    return pol.Polare(alpha=a, cl=steigung_je_rad * np.radians(a),
                      cd=np.zeros_like(a), cm=np.zeros_like(a),
                      vertrauen=np.ones_like(a), reynolds=2.5e5,
                      name="ebene Platte")


class Rechteckschnitt:
    """Minimaler Ersatz fuer geometrie.spannweite.Schnitt."""

    def __init__(self, y, sehne, winkel, hoehe):
        self.y, self.sehne, self.anstellwinkel = y, sehne, winkel
        self.punkte = np.array([[sehne, y, hoehe], [sehne / 2, y, hoehe],
                                [0.0, y, hoehe], [sehne / 2, y, hoehe - 1e-6],
                                [sehne, y, hoehe]])


def rechteckfluegel(streckung: float, alpha: float, spannweite_m: float = 2.0,
                    hoehe_m: float = 50.0, stationen: int = 15):
    sehne = spannweite_m / streckung
    return [Rechteckschnitt(y * 1000.0, sehne * 1000.0, alpha, hoehe_m * 1000.0)
            for y in np.linspace(0.0, spannweite_m / 2.0, stationen)]


@pytest.fixture(scope="module")
def e423():
    return Profil.aus_dat("profile/katalog/e423.dat").gespiegelt()


@pytest.fixture(scope="module")
def fluegel(e423):
    return schnitte(e423, Spannweite.frontfluegel_aussen(), 250.0, -4.0, 40,
                    lage=(-600.0, 0.0, 90.0))


# ----------------------------------------------------------- Wirbelrechnung

def test_boden_ist_undurchlaessig():
    """Die Spiegelung muss die Bodenebene dicht machen. Ist sie das nicht,
    ist der ganze Bodeneffekt falsch - und zwar unauffaellig falsch."""
    kanten = np.array([[0.0, -1.0, 0.5], [0.0, 0.0, 0.5], [0.0, 1.0, 0.5]])
    auf_dem_boden = np.column_stack([np.linspace(-3, 3, 13),
                                     np.linspace(-3, 3, 13),
                                     np.zeros(13)])

    mit = tl.einflussmatrix(auf_dem_boden, kanten, mit_boden=True)
    ohne = tl.einflussmatrix(auf_dem_boden, kanten, mit_boden=False)

    assert np.abs(mit).max() < 1e-12
    assert np.abs(ohne).max() > 0.01      # ohne Spiegelung stroemt es hindurch


def test_halbgerade_stimmt_mit_einer_langen_strecke_ueberein():
    """Die geschlossene Formel fuer den unendlichen Faden muss dasselbe
    liefern wie ein sehr langes Stueck."""
    punkte = np.array([[0.0, 0.5, 0.3], [1.0, -0.2, 0.8]])
    a = np.array([0.0, 0.0, 0.0])
    lang = tl._strecke(punkte, a, a + np.array([1e6, 0.0, 0.0]))
    exakt = tl._halbgerade(punkte, a, tl.STROMRICHTUNG)
    assert np.allclose(lang, exakt, atol=1e-9)


def test_zwei_dimensionaler_grenzfall():
    """Bei sehr grosser Streckung muss der Flügelbeiwert gegen den
    Profilbeiwert laufen - hier 2 pi alpha."""
    st = rechteckfluegel(streckung=200.0, alpha=5.0, spannweite_m=40.0)
    r = tl.rechne(st, geschwindigkeit=20.0, polaren=ebene_platte(),
                  mit_boden=False, panels_je_seite=40)
    assert r.cl == pytest.approx(2 * np.pi * np.radians(5.0), rel=0.04)


@pytest.mark.parametrize("streckung", [4.0, 6.0, 10.0])
def test_streckung_folgt_der_tragflaechentheorie(streckung):
    """CL = a0 alpha / (1 + a0/(pi AR)).

    Der Rechteckfluegel muss knapp DARUNTER liegen: Die Formel gilt fuer
    elliptische Auftriebsverteilung, und die ist das Optimum.
    """
    r = tl.rechne(rechteckfluegel(streckung, 5.0), geschwindigkeit=20.0,
                  polaren=ebene_platte(), mit_boden=False, panels_je_seite=40)
    a0 = 2 * np.pi
    elliptisch = a0 * np.radians(5.0) / (1 + a0 / (np.pi * streckung))
    assert r.cl < elliptisch
    assert r.cl == pytest.approx(elliptisch, rel=0.06)


def test_induzierter_widerstand_waechst_mit_dem_auftriebsquadrat():
    """CDi ~ CL^2. Verdoppelt sich der Anstellwinkel, vervierfacht sich der
    induzierte Widerstand."""
    klein = tl.rechne(rechteckfluegel(6.0, 3.0), geschwindigkeit=20.0,
                      polaren=ebene_platte(), mit_boden=False)
    gross = tl.rechne(rechteckfluegel(6.0, 6.0), geschwindigkeit=20.0,
                      polaren=ebene_platte(), mit_boden=False)
    verhaeltnis = gross.widerstand_induziert / klein.widerstand_induziert
    assert verhaeltnis == pytest.approx(4.0, rel=0.08)


def test_kleinere_streckung_kostet_auftrieb():
    weit = tl.rechne(rechteckfluegel(10.0, 5.0), geschwindigkeit=20.0,
                     polaren=ebene_platte(), mit_boden=False)
    gedrungen = tl.rechne(rechteckfluegel(3.0, 5.0), geschwindigkeit=20.0,
                          polaren=ebene_platte(), mit_boden=False)
    assert gedrungen.cl < weit.cl


# ------------------------------------------------------------ Bodeneffekt

def test_bodennaehe_erhoeht_den_abtrieb(fluegel, e423):
    """Naeher am Boden muss mehr Abtrieb herauskommen.

    Erfasst ist dabei nur der Anteil ueber die induzierte Stroemung; die
    Kanalwirkung fehlt im Modell. Die RICHTUNG muss trotzdem stimmen.
    """
    kennlinie = tl.bodenkennlinie(fluegel, e423, [40, 100, 300],
                                  geschwindigkeit=15.0, panels_je_seite=12)
    abtriebe = [k.abtrieb for _, k in kennlinie]
    assert abtriebe[0] > abtriebe[1] > abtriebe[2]


def test_ohne_boden_gerechnet_kommt_weniger_heraus(fluegel, e423):
    mit = tl.rechne(fluegel, e423, 15.0, panels_je_seite=12, mit_boden=True)
    ohne = tl.rechne(fluegel, e423, 15.0, panels_je_seite=12, mit_boden=False)
    assert mit.abtrieb > ohne.abtrieb


# -------------------------------------------------------------- Profilpolare

def test_reynoldszahl():
    """15 m/s und 250 mm Sehne ergeben rund 250 000 - der typische
    Formula-Student-Bereich."""
    assert pol.reynolds(15.0, 250.0) == pytest.approx(253_378, rel=0.01)


def test_gespiegeltes_profil_erzeugt_abtrieb(e423):
    p = pol.polare(e423, 250_000.0)
    assert p.cl_bei(-4.0) < -1.0              # Abtrieb
    assert p.cl_bei(0.0) < 0.0


def test_polare_extrapoliert_nicht(e423):
    """Ausserhalb des gerechneten Bereichs wird geklemmt. Extrapoliert liefe
    die Kurve im Abrissbereich beliebig weit ins Falsche, und zwar glatt -
    also unauffaellig."""
    p = pol.polare(e423, 250_000.0)
    assert p.cl_bei(-90.0) == pytest.approx(p.cl[0])
    assert p.cl_bei(+90.0) == pytest.approx(p.cl[-1])


def test_abrisswinkel_liegt_im_erwarteten_bereich(e423):
    """Das gespiegelte E423 reisst bei Re 250 000 um -12 Grad ab."""
    p = pol.polare(e423, 250_000.0)
    assert -15.0 < p.abriss_winkel < -9.0
    assert 1.8 < p.cl_max_betrag < 2.3


def test_niedrige_reynoldszahl_kostet_auftrieb(e423):
    """Bei Re 100 000 platzt die Laminarblase auf. Wer nur bei einer
    Geschwindigkeit rechnet, uebersieht das."""
    schnell = pol.polare(e423, 600_000.0)
    langsam = pol.polare(e423, 100_000.0)
    assert abs(langsam.cl_bei(-4.0)) < abs(schnell.cl_bei(-4.0))
    assert langsam.cd_bei(-4.0) > schnell.cd_bei(-4.0)


# ----------------------------------------------------------- Ganzer Flügel

def test_fluegel_liefert_plausible_groessenordnung(fluegel, e423):
    """Ein Frontfluegel dieser Groesse liegt bei 15 m/s in der Groessenordnung
    einiger Dutzend Newton. Veroeffentlichte FS-Arbeiten nennen fuer
    Frontfluegel Werte im Bereich 30 bis 110 N."""
    r = tl.rechne(fluegel, e423, 15.0)
    assert 20.0 < r.abtrieb < 150.0
    assert r.widerstand > 0.0
    assert r.wirkungsgrad > 3.0
    assert r.konvergiert


def test_abtrieb_waechst_quadratisch_mit_der_geschwindigkeit(fluegel, e423):
    langsam = tl.rechne(fluegel, e423, 10.0, panels_je_seite=12)
    schnell = tl.rechne(fluegel, e423, 20.0, panels_je_seite=12)
    assert schnell.abtrieb / langsam.abtrieb == pytest.approx(4.0, rel=0.25)


def test_mehr_eindrehen_bringt_mehr_abtrieb(e423):
    flach = schnitte(e423, Spannweite.gerade(600.0), 250.0, -2.0, 40,
                     lage=(-600.0, 0.0, 90.0))
    steil = schnitte(e423, Spannweite.gerade(600.0), 250.0, -8.0, 40,
                     lage=(-600.0, 0.0, 90.0))
    assert (tl.rechne(steil, e423, 15.0, panels_je_seite=12).abtrieb
            > tl.rechne(flach, e423, 15.0, panels_je_seite=12).abtrieb)


def test_verwindung_je_sektion_wirkt(e423):
    """Genau die Funktion, um die es beim Sektionseditor geht: Zwei Fluegel
    mit gleicher Wurzel, aber unterschiedlichem Eindrehen aussen."""
    def bau(aussenwinkel):
        spw = Spannweite(stuetzstellen=[
            Stuetzstelle(y=0.0, verwindung=0.0),
            Stuetzstelle(y=600.0, verwindung=aussenwinkel)], schnitte=9)
        return schnitte(e423, spw, 250.0, -4.0, 40, lage=(-600.0, 0.0, 90.0))

    gerade = tl.rechne(bau(0.0), e423, 15.0, panels_je_seite=12)
    gedreht = tl.rechne(bau(-6.0), e423, 15.0, panels_je_seite=12)
    assert gedreht.abtrieb > gerade.abtrieb


def test_streifen_decken_beide_fahrzeugseiten_ab(fluegel):
    """Der Stapel beschreibt nur rechts. Wer nur eine Haelfte rechnet, bekommt
    an der Wurzel einen deutlich zu grossen wirksamen Winkel."""
    streifen = tl.streifen_aus_stapel(fluegel, panels_je_seite=10)
    y = np.array([s.y for s in streifen])
    assert y.min() < -500.0 and y.max() > 500.0
    assert len(streifen) == 20


def test_schlitz_in_der_mitte_bleibt_leer(e423):
    """Ein Fluegel, der erst bei y = 300 beginnt, darf in der Mitte keine
    Streifen bekommen - dort ist kein Fluegel."""
    spw = Spannweite(stuetzstellen=[Stuetzstelle(y=300.0),
                                    Stuetzstelle(y=600.0)], schnitte=7)
    stapel = schnitte(e423, spw, 250.0, -4.0, 40, lage=(-600.0, 0.0, 90.0))
    y = np.abs([s.y for s in tl.streifen_aus_stapel(stapel, panels_je_seite=10)])
    assert y.min() >= 300.0 - 1e-6


def test_ergebnis_meldet_abriss(e423):
    """Ein absichtlich viel zu steiler Fluegel muss als abgerissen gemeldet
    werden, statt einen Traumwert auszuweisen."""
    stapel = schnitte(e423, Spannweite.gerade(600.0), 250.0, -22.0, 40,
                      lage=(-600.0, 0.0, 200.0))
    r = tl.rechne(stapel, e423, 15.0, panels_je_seite=12)
    assert r.abgerissen > 0.5


# ------------------------------------------------------ Flügelvorschlag

from aerostudio.aero import entwurf as ent


@pytest.fixture(scope="module")
def enge_grenzen():
    """Kleines Raster - die Tests pruefen das Verhalten, nicht die Aufloesung."""
    return ent.Grenzen(sehne=(150.0, 350.0), halbspannweite=(400.0, 695.0),
                       stufen_sehne=4, stufen_spannweite=3)


def test_vorschlag_trifft_den_zielwert(e423, enge_grenzen):
    v = ent.suche(60.0, e423, Spannweite.frontfluegel_aussen(),
                  geschwindigkeit=15.0, grenzen=enge_grenzen)
    assert v.gefunden
    assert v.treffer.abtrieb == pytest.approx(60.0, abs=1.0)


def test_alternativen_treffen_denselben_wert(e423, enge_grenzen):
    """Ein frueher Fehler: Zuschnitte, die schon beim flachsten Winkel
    ueberschossen, erschienen als 'weiterer Weg zum selben Ziel' - mit 69
    statt 60 Newton."""
    v = ent.suche(60.0, e423, Spannweite.frontfluegel_aussen(),
                  geschwindigkeit=15.0, grenzen=enge_grenzen)
    for k in v.alternativen:
        assert k.abtrieb == pytest.approx(60.0, abs=1.0)


def test_vorschlag_haelt_die_bodenfreiheit_ein(e423, enge_grenzen):
    """Die Einbauhoehe wird mitgesucht. Hoehensuche und Regelpruefer muessen
    denselben Fahrzustand ansetzen - taten sie das nicht, war jeder Vorschlag
    rechnerisch knapp legal und fiel in der Pruefung durch."""
    from aerostudio import regeln

    v = ent.suche(60.0, e423, Spannweite.frontfluegel_aussen(),
                  geschwindigkeit=15.0, grenzen=enge_grenzen)
    assert v.gefunden
    t = v.treffer
    assert not t.verstoesse, t.verstoesse

    stapel = schnitte(e423, Spannweite.frontfluegel_aussen().skaliert(t.halbspannweite),
                      t.sehne, t.anstellwinkel, 24,
                      lage=(-600.0, 0.0, t.hoehe))
    befunde = regeln.pruefe_fluegel(stapel, regeln.lade("2026"))
    boden = [b for b in befunde if b.regel == "T 2.2.1"][0]
    assert boden.ok


def test_hoeheres_ziel_braucht_mehr_flaeche_oder_winkel(e423, enge_grenzen):
    klein = ent.suche(45.0, e423, Spannweite.frontfluegel_aussen(),
                      geschwindigkeit=15.0, grenzen=enge_grenzen)
    gross = ent.suche(75.0, e423, Spannweite.frontfluegel_aussen(),
                      geschwindigkeit=15.0, grenzen=enge_grenzen)
    assert klein.gefunden and gross.gefunden
    a, b = klein.treffer, gross.treffer
    mehr_flaeche = b.sehne * b.halbspannweite > a.sehne * a.halbspannweite
    steiler = abs(b.anstellwinkel) > abs(a.anstellwinkel)
    assert mehr_flaeche or steiler


def test_unerreichbares_ziel_sagt_was_geht(e423, enge_grenzen):
    v = ent.suche(400.0, e423, Spannweite.frontfluegel_aussen(),
                  geschwindigkeit=15.0, grenzen=enge_grenzen)
    assert not v.gefunden
    assert v.erreichbar_max > 0.0
    # Die Begruendung muss sagen, was stattdessen ginge - sonst steht der
    # Anwender vor einem "geht nicht" ohne Ausweg.
    text = " ".join(v.begruendung)
    assert f"{v.erreichbar_max:.0f} N" in text
    assert "Kaskade" in text or "Profil" in text


def test_verwindung_bleibt_unangetastet(e423, enge_grenzen):
    """Die Entwurfsabsicht des Anwenders darf die Suche nicht ueberschreiben."""
    vorlage = Spannweite.frontfluegel_aussen()
    v = ent.suche(60.0, e423, vorlage, geschwindigkeit=15.0, grenzen=enge_grenzen)
    assert v.gefunden
    skaliert = vorlage.skaliert(v.treffer.halbspannweite)
    assert [st.verwindung for st in skaliert.stuetzstellen] == \
        [st.verwindung for st in vorlage.stuetzstellen]


def test_bester_wirkungsgrad_gewinnt(e423, enge_grenzen):
    v = ent.suche(60.0, e423, Spannweite.frontfluegel_aussen(),
                  geschwindigkeit=15.0, grenzen=enge_grenzen)
    regelkonform = [v.treffer] + [k for k in v.alternativen if k.regelkonform]
    assert v.treffer.wirkungsgrad == max(k.wirkungsgrad for k in regelkonform)


def test_entwurfsregeln_blockieren_keinen_vorschlag(e423, enge_grenzen):
    """T 2.1.4 steht nur im 2027-Entwurf. Wuerde sie hart zaehlen, faende die
    Suche fuer einen Fluegel bis zur Radaussenkante gar nichts mehr."""
    v = ent.suche(60.0, e423, Spannweite.frontfluegel_aussen(),
                  geschwindigkeit=15.0, grenzen=enge_grenzen)
    assert v.gefunden and v.treffer.regelkonform
    # Der Entwurfshinweis geht dabei nicht verloren.
    alle = v.treffer.hinweise + v.treffer.verstoesse
    assert any("2.1.4" in h for h in alle) or v.treffer.halbspannweite < 620.0


def test_verdrehte_grenzen_werden_abgelehnt():
    with pytest.raises(ValueError, match="verdreht"):
        ent.Grenzen(sehne=(400.0, 120.0))


# --------------------------------------------------- Panelverfahren (2D)

from aerostudio.aero import panel


def test_zylinder_ohne_zirkulation():
    """Die klassische Loesung: cp = 1 - 4 sin^2(theta), Auftrieb null.
    Prueft die Quellbelegung und die Tangentialbedingung."""
    n = 200
    t = np.linspace(0.0, 2 * np.pi, n + 1)
    pts = np.column_stack([np.cos(-t), np.sin(-t)])      # im Uhrzeigersinn
    r = panel.loese([panel.Koerper(punkte=pts)], alpha_grad=0.0)
    mitte = -(t[:-1] + t[1:]) / 2
    assert np.abs(r.cp[0] - (1 - 4 * np.sin(mitte) ** 2)).max() < 1e-6
    assert abs(r.cl_gesamt) < 1e-6


def test_umlaufsinn_ist_egal():
    """Profildateien laufen mal so und mal so herum. Ein erster Entwurf nahm
    fest die linke Senkrechte als Aussennormale - beim Zylinder stimmte das,
    beim Profil zeigten alle Normalen nach innen."""
    n = 200
    t = np.linspace(0.0, 2 * np.pi, n + 1)
    rechts = panel.loese([panel.Koerper(punkte=np.column_stack([np.cos(-t), np.sin(-t)]))])
    links = panel.loese([panel.Koerper(punkte=np.column_stack([np.cos(t), np.sin(t)]))])
    assert np.abs(rechts.cp[0] - links.cp[0][::-1]).max() < 1e-6


def test_duennes_profil_trifft_die_theorie():
    """cl = 2 pi alpha, mit einem Dickenzuschlag von etwa 0,77 t/c."""
    p = Profil.aus_naca(0.0, 0.4, 0.08, n=401)
    k = panel.aus_profil(p, 1.0, 0.0, punkte=150)
    for a in (2.0, 4.0, 6.0):
        r = panel.loese([k], alpha_grad=a)
        erwartet = 2 * np.pi * np.radians(a) * (1 + 0.77 * 0.08)
        assert r.cl_gesamt == pytest.approx(erwartet, rel=0.02)


def test_reibungsfrei_heisst_widerstandsfrei():
    """Das Paradoxon von d'Alembert als Selbstpruefung: Kommt hier
    nennenswert Widerstand heraus, ist die Loesung krumm."""
    p = Profil.aus_naca(0.02, 0.4, 0.12, n=401)
    k = panel.aus_profil(p, 1.0, 0.0, punkte=160)
    for a in (0.0, 4.0, 8.0):
        r = panel.loese([k], alpha_grad=a)
        assert abs(r.cd_scheinbar) < 0.002


def test_koerper_drehen_und_anstroemung_drehen_ist_dasselbe(e423):
    """Die Probe, die den Vorzeichenfehler in angestellt() aufgedeckt hat:
    Ein um -4 Grad gedrehter Fluegel in gerader Anstroemung muss dasselbe
    liefern wie ein gerader Fluegel in um -4 Grad gedrehter Anstroemung.
    Vorher unterschieden sich die beiden um fast einen ganzen Beiwert."""
    for a in (-12.0, -4.0, 0.0, 4.0):
        koerper = panel.loese([panel.aus_profil(e423, 1.0, a, punkte=160)],
                              alpha_grad=0.0, bezugssehne=1.0)
        stroemung = panel.loese([panel.aus_profil(e423, 1.0, 0.0, punkte=160)],
                                alpha_grad=a, bezugssehne=1.0)
        assert koerper.cl_gesamt == pytest.approx(stroemung.cl_gesamt, abs=1e-6)


def test_negativer_winkel_dreht_die_nase_nach_unten(e423):
    """Geometrie und Aerodynamik muessen dasselbe Vorzeichen meinen. Sie taten
    es nicht: Bei -8 Grad rechnete das Werkzeug mehr Abtrieb, exportierte nach
    Creo aber einen Fluegel mit der Nase nach OBEN."""
    for winkel, nase_tiefer in ((-8.0, True), (+8.0, False)):
        pts = e423.angestellt(winkel, 250.0)
        hinten = pts[0]
        nase = pts[int(np.argmax(np.linalg.norm(pts - hinten, axis=1)))]
        # bool() ist noetig: numpy liefert np.bool_, und das ist nicht True.
        assert bool(nase[1] < hinten[1]) is nase_tiefer


def test_mehr_anstellwinkel_mehr_abtrieb_auch_geometrisch(e423):
    """Dieselbe Aussage noch einmal ueber die Kraft statt ueber die Lage."""
    flach = panel.loese([panel.aus_profil(e423, 1.0, -2.0, punkte=160)],
                        bezugssehne=1.0)
    steil = panel.loese([panel.aus_profil(e423, 1.0, -10.0, punkte=160)],
                        bezugssehne=1.0)
    assert steil.cl_gesamt < flach.cl_gesamt          # negativer = mehr Abtrieb


# ------------------------------------------------------ Maximaler Abtrieb

def test_maximumsuche_liefert_mehr_als_ein_zielwert(e423, enge_grenzen):
    """Wer auf Maximum stellt, muss mehr bekommen als bei einem Zielwert -
    sonst waere der Schalter sinnlos."""
    ziel = ent.suche(45.0, e423, Spannweite.frontfluegel_aussen(),
                     geschwindigkeit=15.0, grenzen=enge_grenzen)
    maximum = ent.suche_maximum(e423, Spannweite.frontfluegel_aussen(),
                                geschwindigkeit=15.0, grenzen=enge_grenzen)
    assert maximum.gefunden and ziel.gefunden
    assert maximum.treffer.abtrieb > ziel.treffer.abtrieb


def test_maximumsuche_haelt_die_abrissgrenze_ein(e423, enge_grenzen):
    """Ausgereizt wird bis zum Abriss, nicht darueber. Ein Fluegel, dessen
    halbe Flaeche abgerissen ist, erreicht seinen Wert nie im Fahrzeug."""
    v = ent.suche_maximum(e423, Spannweite.frontfluegel_aussen(),
                          geschwindigkeit=15.0, grenzen=enge_grenzen)
    assert v.treffer.kraefte.abgerissen <= enge_grenzen.abriss_max + 1e-9


def test_maximumsuche_waehlt_nach_abtrieb_nicht_nach_wirkungsgrad(e423, enge_grenzen):
    """Der Unterschied zur Zielwertsuche: Hier gewinnt die groesste Last,
    auch wenn sie mehr Widerstand kostet."""
    v = ent.suche_maximum(e423, Spannweite.frontfluegel_aussen(),
                          geschwindigkeit=15.0, grenzen=enge_grenzen)
    regelkonform = [v.treffer] + [k for k in v.alternativen if k.regelkonform]
    assert v.treffer.abtrieb == max(k.abtrieb for k in regelkonform)


def test_maximumsuche_haelt_das_reglement_ein(e423, enge_grenzen):
    v = ent.suche_maximum(e423, Spannweite.frontfluegel_aussen(),
                          geschwindigkeit=15.0, grenzen=enge_grenzen)
    assert v.treffer.regelkonform
    assert not v.treffer.verstoesse


def test_maximumsuche_verweist_auf_die_kaskade(e423, enge_grenzen):
    """Wenn ein Element ausgereizt ist, muss das Werkzeug sagen, wie es
    weitergeht - sonst steht der Anwender vor einer Zahl ohne Ausweg."""
    v = ent.suche_maximum(e423, Spannweite.frontfluegel_aussen(),
                          geschwindigkeit=15.0, grenzen=enge_grenzen)
    assert any("Kaskade" in b for b in v.begruendung)
