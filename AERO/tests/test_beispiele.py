"""
Tests fuer die Beispiel-Specs (M6 Punkt 6).

Sie sind der Startpunkt fuer jemanden, der das Werkzeug zum ersten Mal
oeffnet. Ein Beispiel, das mit roter Ampel startet, ist schlimmer als gar
keins: Der Anfaenger haelt den Verstoss fuer normal oder sucht den Fehler
bei sich.

Diese Tests haben nebenbei einen echten Fehler gefunden - `_elementstapel`
reichte die Kaskadenstufen des Specs direkt an die Geometrie durch, die
aber ein anderes Datenmodell erwartet. Aufgefallen ist das nie, weil die
Testdaten der Oberflaeche keine Kaskade enthalten. Die Beispiele hier haben
eine, und genau deshalb stehen sie im Testlauf.
"""

from pathlib import Path

import pytest

from aerostudio.geometrie import endplatte as gep
from aerostudio.regeln import Bezugsgeometrie, alle_staende, pruefe_fluegel
from aerostudio.spec.projekt import AeroSpec
from aerostudio.ui import app as UI

ORDNER = Path(__file__).resolve().parents[1] / "specs" / "beispiele"


def _beispiele() -> list[Path]:
    return sorted(ORDNER.glob("*.yaml"))


def test_es_gibt_beispiele():
    """Ohne sie startet jeder bei null - das war M6 Punkt 6."""
    assert len(_beispiele()) >= 2


@pytest.mark.parametrize("datei", _beispiele(), ids=lambda p: p.stem)
def test_beispiel_laedt(datei):
    spec = AeroSpec.laden(datei)
    assert spec.elemente
    assert spec.meta.name


@pytest.mark.parametrize("datei", _beispiele(), ids=lambda p: p.stem)
def test_beispiel_hat_alles_was_die_oberflaeche_zeigt(datei):
    """Spannweite, Kaskade und Endplatte - sonst sieht der Anfaenger leere
    Reiter und haelt sie fuer kaputt."""
    element = AeroSpec.laden(datei).elemente[0]

    assert element.spannweite is not None
    assert element.kaskade, "ein Beispiel ohne Flap zeigt den Kaskadenreiter nicht"
    assert element.endplatte is not None


@pytest.mark.parametrize("datei", _beispiele(), ids=lambda p: p.stem)
def test_beispiel_ist_regelkonform(datei):
    """In BEIDEN Regelstaenden. Ein Beispiel, das nur 2026 besteht, waere in
    einem Jahr eine Falle."""
    element = AeroSpec.laden(datei).elemente[0]
    teile = UI._elementstapel(element)
    stapel = [s for t in teile for s in t]
    if element.endplatte is not None:
        stapel += gep.schnitte(teile, element.endplatte)

    bezug = Bezugsgeometrie.aus_datei()
    for satz in alle_staende():
        schlecht = [b for b in pruefe_fluegel(stapel, satz, bezug)
                    if b.blockiert]
        assert not schlecht, (
            f"{datei.name} verstoesst gegen {satz.version}: " +
            "; ".join(f"{b.regel} {b.pruefung} ist {b.ist:.1f}, "
                      f"Grenze {b.grenze:.1f}" for b in schlecht))


@pytest.mark.parametrize("datei", _beispiele(), ids=lambda p: p.stem)
def test_beispiel_laesst_sich_exportieren(datei, tmp_path):
    """Der ganze Weg bis zur IBL - sonst faellt ein Beispiel erst auf, wenn
    jemand es nach Creo bringen will."""
    from aerostudio.formate import export

    element = AeroSpec.laden(datei).elemente[0]
    plan = export.plane_kaskadenfluegel(
        UI.profil_fuer(element), element.spannweite, element.sehne,
        element.anstellwinkel, UI._vorgaben(element.kaskade),
        lage=UI._lage(element))

    ziel = export.schreibe(plan, tmp_path / "x.ibl")
    assert ziel.read_text().count("begin section") == len(plan.sektionen)


def test_elementstapel_vertraegt_eine_kaskade():
    """Der Fehler, den die Beispiele aufgedeckt haben.

    `_elementstapel` reichte die Kaskadenstufen des Specs direkt weiter; die
    Geometrie erwartet aber ihr eigenes Vorgabenmodell, in dem das
    Flapprofil ein geladenes Profil ist und kein Dateiname. Ohne Flaps ist
    die Liste leer und der Fehler unsichtbar - deshalb hier ein Beispiel MIT
    Flap.
    """
    element = AeroSpec.laden(_beispiele()[0]).elemente[0]
    assert element.kaskade, "Testaufbau taugt nicht - das Beispiel hat keinen Flap"

    teile = UI._elementstapel(element)
    assert len(teile) == len(element.kaskade) + 1
    assert all(t for t in teile)


def test_endplattenhoehe_vertraegt_eine_kaskade():
    """Dieselbe Stelle, anderer Aufrufer - die Hoehe fuer die Hoerner-
    Rechnung faellt aus der Geometrie ab und lief ueber denselben Weg."""
    element = AeroSpec.laden(_beispiele()[0]).elemente[0]
    hoehe = UI._endplattenhoehe(element)

    assert hoehe > 0.0
    # Die Platte umschliesst die ganze Kaskade, ist also hoeher als das
    # Hauptelement allein dick ist.
    assert hoehe > element.sehne * 0.1
