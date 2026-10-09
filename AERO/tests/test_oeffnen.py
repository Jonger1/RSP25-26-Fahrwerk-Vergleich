"""
Ein gespeichertes Spec in der Oberflaeche oeffnen.

Bis zum 09.10.2026 startete die Oberflaeche immer mit den Vorgabewerten -
ein gespeicherter Entwurf liess sich nicht wieder laden. Der Massstab hier:
Oeffnen und unveraendert neu bauen ergibt DASSELBE Spec, mit demselben Hash.
Sonst passte die IBL-Datei nicht mehr zu ihrer Spec-Datei.
"""

import pytest

from aerostudio.spec.modell import Fahrzeuglage, Unterboden
from aerostudio.spec.projekt import AeroSpec
from aerostudio.ui import app as UI

BEISPIELE = ["specs/beispiele/frontfluegel_zweielementig.yaml",
             "specs/beispiele/heckfluegel.yaml"]


def _rundreise(spec: AeroSpec) -> AeroSpec:
    werte, basis, _ = UI.felder_aus_spec(spec)
    return UI._baue_spec(*werte, basis)


@pytest.mark.parametrize("pfad", BEISPIELE)
def test_beispiele_kommen_unveraendert_zurueck(pfad):
    spec = AeroSpec.laden(UI.PROJEKT / pfad)
    zurueck = _rundreise(spec)
    assert zurueck.hash() == spec.hash()
    assert zurueck.model_dump(mode="json")["elemente"] == \
        spec.model_dump(mode="json")["elemente"]


def test_unterboden_rake_und_naca_kommen_zurueck():
    from aerostudio.spec.modell import Spannweite
    spec = AeroSpec.beispiel()
    spec.elemente[0].spannweite = Spannweite.gerade(450.0)
    spec.unterboden = Unterboden(kehle_hoehe_vorne=62.0, diffusor_winkel=12.5)
    spec.lage = Fahrzeuglage(rake_grad=0.7, drehpunkt_x=900.0)
    from aerostudio.spec.modell import ProfilNaca
    spec.elemente[0].profil = ProfilNaca(woelbung=0.06, woelbungslage=0.4, dicke=0.09)
    assert _rundreise(spec).hash() == spec.hash()


def test_paket_mit_zwei_fluegeln_oeffnet_den_ersten_mit_hinweis():
    from aerostudio.aero import paket
    p = paket.bauen(AeroSpec.laden(UI.PROJEKT / BEISPIELE[0]),
                    [AeroSpec.laden(UI.PROJEKT / BEISPIELE[1])])
    werte, basis, hinweise = UI.felder_aus_spec(p)
    assert basis["element_id"] == p.elemente[0].id
    assert hinweise and "2 Flügel" in hinweise[0]


def test_eingabeliste_und_umkehrung_passen_zusammen():
    import inspect
    werte, _, _ = UI.felder_aus_spec(AeroSpec.beispiel())
    assert len(werte) + 1 == len(UI._EINGABEN) == \
        len(inspect.signature(UI._baue_spec).parameters)


def test_oeffnen_aus_der_oberflaeche(monkeypatch):
    from dash import callback_context
    original = type(callback_context).triggered_id
    try:
        type(callback_context).triggered_id = property(lambda self: "btn-oeffnen")
        aus = UI._oeffnen(1, None, BEISPIELE[1])
    finally:
        type(callback_context).triggered_id = original
    *felder, basis, meldung = aus
    assert basis["element_id"] == "RW_E1"
    assert "Geöffnet" in str(meldung.to_plotly_json())
    assert UI._baue_spec(*felder, basis).hash() == \
        AeroSpec.laden(UI.PROJEKT / BEISPIELE[1]).hash()


def test_beim_start_wird_aktuell_geoeffnet(tmp_path, monkeypatch):
    spec = AeroSpec.laden(UI.PROJEKT / BEISPIELE[0])
    datei = spec.speichern(tmp_path / "aktuell.yaml", historie=False)
    *felder, basis, _ = UI._oeffnen(0, str(datei), None)
    assert UI._baue_spec(*felder, basis).hash() == spec.hash()


def test_ohne_datei_beim_start_bleibt_alles():
    aus = UI._oeffnen(0, None, None)
    from dash import no_update
    assert all(a is no_update for a in aus)


def test_kaputte_datei_gibt_eine_fehlerkarte(tmp_path):
    (tmp_path / "x.yaml").write_text("meta: [kaputt")
    *felder, meldung = UI._oeffnen(0, str(tmp_path / "x.yaml"), None)
    from dash import no_update
    assert all(f is no_update for f in felder)
    assert meldung is not no_update


def test_spec_ohne_spannweite_wird_ergaenzt_und_sagt_es():
    """Der Editor legt immer eine Spannweite an - ein ebener Schnitt kommt
    deshalb nicht mit demselben Hash zurueck. Das muss die Meldung sagen."""
    spec = AeroSpec.beispiel()
    spec.elemente[0].spannweite = None
    _, _, hinweise = UI.felder_aus_spec(spec)
    assert any("keine Spannweite" in h for h in hinweise)
