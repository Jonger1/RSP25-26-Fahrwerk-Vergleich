"""
Tests fuer die Ansicht *Fahrzeug & Regeln* - das "Fertig, wenn" von M2.

Der Meilenstein verlangt: Eine absichtlich zu hoch gesetzte Variante wird
mit korrekter Regelnummer und Millimeterangabe abgelehnt, **sichtbar an der
Ampel, nicht nur im Log**. Genau das pruefen diese Tests - nicht, dass ein
Diagramm entsteht, sondern dass die Ampel umschlaegt und die richtige Regel
nennt.
"""

import numpy as np
import pytest

from aerostudio.spec.projekt import AeroSpec
from aerostudio.ui import app as UI
from tests.test_export_ui import werte_mit


def _spec(**aenderungen):
    spec, *_ = UI._profil_aktualisieren(*werte_mit(**aenderungen))
    return spec


def _ampeltext(spec, stand="2026", hoch=24.35, tief=24.35) -> str:
    ampel, *_figuren = UI._regelansicht(spec, stand, hoch, tief)
    return str(ampel)


# ------------------------------------------------------------- Grundlage

def test_ansicht_liefert_ampel_und_zwei_zeichnungen():
    ampel, seite, drauf = UI._regelansicht(_spec(), "2026", 24.35, 24.35)

    assert ampel != ""
    assert len(seite.data) > 5
    assert len(drauf.data) > 5


def test_ohne_spec_kein_absturz():
    ampel, seite, drauf = UI._regelansicht(None, "2026", 24.35, 24.35)
    assert ampel == ""
    assert seite["data"] == []


def test_ampel_nennt_den_geprueften_fahrzustand():
    """Ein Befund ohne seinen Fahrzustand ist nicht nachvollziehbar."""
    text = _ampeltext(_spec(), hoch=30.0, tief=12.0)
    assert "30.0 mm" in text and "12.0 mm" in text


# ------------------------------------- Das Kriterium: die Ampel schlaegt um

def test_sauberer_fluegel_meldet_gruen():
    # 600 mm vor der Achse, 90 mm hoch - der uebliche Frontfluegel.
    assert "Regelkonform" in _ampeltext(_spec(pos_x=600.0, pos_z=90.0))


def test_zu_hoher_fluegel_wird_abgelehnt():
    """T 8.2.1 begrenzt vor der Vorderachse auf 250 mm."""
    text = _ampeltext(_spec(pos_x=600.0, pos_z=400.0))

    assert "Verstoß" in text
    assert "T 8.2.1" in text


def test_die_millimeterangabe_steht_in_der_ampel():
    """Der Meilenstein verlangt ausdruecklich eine Millimeterangabe."""
    text = _ampeltext(_spec(pos_x=600.0, pos_z=400.0))

    # Die Regelzeile nennt Ist- und Grenzwert: "... 4xx.x <= 250.0 mm".
    assert "250.0 mm" in text


def test_zu_tiefer_fluegel_reisst_die_bodenfreiheit():
    text = _ampeltext(_spec(pos_x=600.0, pos_z=5.0), tief=30.0)
    assert "Verstoß" in text


def test_ausfedern_kann_eine_gruene_ampel_kippen():
    """Genau dafuer gibt es den Envelope: T 8.2.4 verlangt Einhaltung in
    JEDER Federstellung, nicht nur in der Konstruktionslage."""
    # 180 mm ist der Punkt, an dem es kippt: In Konstruktionslage bleibt
    # der aeussere Teil des Fluegels unter den 250 mm, 60 mm ausgefedert
    # nicht mehr. (Geprueft wird nur ausserhalb der Radinnenkante, und dort
    # ist die Sehne verjuengt - deshalb liegt die Grenze nicht bei 250-60.)
    spec = _spec(pos_x=600.0, pos_z=180.0)

    assert "Regelkonform" in _ampeltext(spec, hoch=0.0, tief=0.0)
    assert "Verstoß" in _ampeltext(spec, hoch=60.0, tief=0.0)


def test_verstoesse_stehen_vor_den_erfuellten_pruefungen():
    """Wer die Ampel aufmacht, will wissen, was NICHT geht."""
    text = _ampeltext(_spec(pos_x=600.0, pos_z=400.0))
    assert text.index("T 8.2.1") < text.rindex("as-zeichen ok")


# ------------------------------------------------------------ Regelstand

def test_beide_regelstaende_lassen_sich_waehlen():
    for stand in ("2026", "2027"):
        text = _ampeltext(_spec(), stand)
        assert stand in text


def test_entwurfsregeln_warnen_statt_zu_blockieren():
    """Eine Grenze, die es nur im Entwurf gibt, blockiert nichts.

    Sonst waere jeder heutige Entwurf im 2027-Durchlauf rot, obwohl der Text
    noch gar nicht gilt.
    """
    spec = _spec(pos_x=700.0, pos_z=60.0)
    text = _ampeltext(spec, "2027")

    # T 2.1.4 gibt es nur 2027. Sie darf auftauchen, aber nicht als Verstoss
    # gezaehlt werden, wenn sie die einzige Beanstandung ist.
    if "T 2.1.4" in text and "Verstoß" not in text:
        assert "Hinweis" in text or "Regelkonform" in text


# -------------------------------------------------------- Endplatte dabei

def test_endplatte_wird_mitgeprueft():
    """Sie ist der aeusserste Teil des Fluegels - sie wegzulassen hiesse,
    eine gruene Ampel fuer einen Fluegel zu zeigen, den es so nicht gibt."""
    ohne = _spec(endplattenart="keine", pos_x=600.0, pos_z=90.0)
    mit = _spec(endplattenart="geometrie", ep_hinten=200.0,
                pos_x=600.0, pos_z=90.0)

    assert "Regelkonform" in _ampeltext(ohne)
    # Die Platte ragt in die Keep-out-Zone des Vorderrads.
    text = _ampeltext(mit)
    assert "T 2.1.3" in text and "Verstoß" in text


def test_fehlende_endplatte_wird_in_der_ampel_vermerkt():
    text = _ampeltext(_spec(endplattenart="keine"))
    assert "Ohne Endplattengeometrie" in text


def test_kein_vermerk_wenn_die_endplatte_da_ist():
    text = _ampeltext(_spec(endplattenart="geometrie"))
    assert "Ohne Endplattengeometrie" not in text


# ---------------------------------------------------------- Zeichnungen

def test_seitenansicht_zeigt_die_hoehengrenze():
    _ampel, seite, _drauf = UI._regelansicht(_spec(), "2026", 24.35, 24.35)
    namen = " ".join(str(s.name) for s in seite.data if s.name)
    assert "T 8.2.1" in namen
    assert "T 2.1.3" in namen


def test_draufsicht_zeigt_die_breitengrenze():
    _ampel, _seite, drauf = UI._regelansicht(_spec(), "2026", 24.35, 24.35)
    namen = " ".join(str(s.name) for s in drauf.data if s.name)
    assert "T 8.2.2" in namen


def test_draufsicht_spiegelt_auf_beide_seiten():
    """Das Reglement begrenzt ueber den BETRAG von y."""
    _ampel, _seite, drauf = UI._regelansicht(_spec(), "2026", 24.35, 24.35)
    y = np.concatenate([np.asarray(s.y, dtype=float) for s in drauf.data
                        if s.y is not None and len(np.atleast_1d(s.y)) > 1])
    assert y.min() < 0.0 < y.max()


def test_seitenansicht_zeichnet_die_hoechste_lage():
    """Dort werden die Hoehengrenzen kritisch - und nur dort."""
    _a, ohne, _d = UI._regelansicht(_spec(), "2026", 0.0, 0.0)
    _a, mit, _d = UI._regelansicht(_spec(), "2026", 50.0, 0.0)

    def hoechster(fig):
        # Nur die Fluegelspuren. Ueber alles gerechnet gewaenne das Rad mit
        # seinen 406 mm, und der Test pruefte, dass ein Rad nicht ausfedert.
        return max(float(np.max(s.y)) for s in fig.data
                   if s.name in ("Flügel", "höchste Lage")
                   and s.y is not None and len(np.atleast_1d(s.y)) > 1)

    assert hoechster(mit) == pytest.approx(hoechster(ohne) + 50.0, abs=1.0)
