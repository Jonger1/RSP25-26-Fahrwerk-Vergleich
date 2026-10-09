"""
Regression: der induzierte Widerstand darf bei kleinen Lageaenderungen nicht
springen.

Bis zum 28.09. hielt die Traglinien-Iteration an, sobald sich die
GESAMTKRAFT einen Schritt lang kaum aenderte. Hinter dem Abriss pendelt die
Iteration aber, und die Verteilung - mit ihr der induzierte Widerstand -
stand dann an einer zufaelligen Stelle der Schwingung. Beim Frontfluegel-
Beispiel sprang der Widerstand bei 0,1 Grad Winkelaenderung von 61 auf 45 N,
waehrend der Abtrieb glatt verlief. Die streng auskonvergierte Loesung liegt
bei rund 76 N.
"""

import numpy as np
import pytest

from aerostudio.aero import kaskade3d
from aerostudio.aero.profilpolare import verfuegbar
from aerostudio.spec.projekt import AeroSpec
from aerostudio.ui import app as UI

pytestmark = pytest.mark.skipif(not verfuegbar(), reason="NeuralFoil fehlt")


def _rechne(element):
    return kaskade3d.rechne(
        UI.profil_fuer(element), element.spannweite, element.sehne,
        element.anstellwinkel, UI._vorgaben(element.kaskade), 20.0,
        lage=UI._lage(element),
        endplatte_mm=UI._endplattenhoehe(element)).kraefte


@pytest.fixture(scope="module")
def front():
    return AeroSpec.laden(UI.PROJEKT / "specs/beispiele/frontfluegel_zweielementig.yaml").elemente[0]


def test_widerstand_glatt_ueber_dem_winkel(front):
    # Genau die Winkel, an denen es vorher sprang (-0,3 / +0,2 / +0,25).
    deltas = [-0.4, -0.3, -0.2, 0.0, 0.2, 0.25, 0.3]
    k = [_rechne(front.model_copy(update={"anstellwinkel": front.anstellwinkel + d}))
         for d in deltas]
    assert all(r.konvergiert for r in k)
    w = np.array([r.widerstand_induziert for r in k])
    # Glatt heisst: keine Stufe groesser als 5 % zwischen Nachbarn, die
    # hoechstens 0,2 Grad auseinander liegen.
    assert np.all(np.abs(np.diff(w)) / w[:-1] < 0.05), w
    # Und monoton: steiler angestellt, mehr Abtrieb, mehr induzierter Widerstand.
    assert np.all(np.diff(w) < 0.0), w


def test_auskonvergiert_wie_mit_strenger_toleranz(front):
    """Die Vorgabe muss dieselbe Loesung liefern wie eine sehr strenge
    Rechnung mit kleiner Daempfung - sonst misst sie nur, wann sie aufhoert."""
    from functools import partial

    from aerostudio.aero import traglinie

    normal = _rechne(front)
    original = traglinie.rechne
    try:
        traglinie.rechne = partial(original, genauigkeit=1e-7, daempfung=0.1,
                                   schritte_max=3000)
        streng = _rechne(front)
    finally:
        traglinie.rechne = original
    assert normal.widerstand_induziert == pytest.approx(streng.widerstand_induziert, rel=0.01)
    assert normal.abtrieb == pytest.approx(streng.abtrieb, rel=0.005)
