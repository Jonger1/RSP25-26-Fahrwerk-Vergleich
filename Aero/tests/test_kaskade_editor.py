import pytest

from aerostudio.ui.kaskade_editor import system_aus_zeilen, flaps_aus_zeilen


def test_editor_akzeptiert_sechs_unabhaengige_elemente():
    daten = [
        {
            "name": f"E{i}", "gruppe": f"G{i}", "rolle": "Haupt",
            "profil": "e423.dat", "sehne_faktor": 1.0,
            "winkel_relativ": -5.0, "spalt": 0.02, "ueberlappung": 0.02,
            "y_von": -700.0 + i * 200.0, "y_bis": -500.0 + i * 200.0,
            "x": 0.0, "z": 100.0,
        }
        for i in range(6)
    ]
    system = system_aus_zeilen(daten)
    assert len(system.elemente) == 6
    assert len(system.gruppen()) == 6


def test_luecke_in_der_spannweite_ist_zulaessig():
    daten = [
        {"name": "Links", "gruppe": "Front", "rolle": "Haupt", "profil": "e423.dat",
         "sehne_faktor": 1.0, "winkel_relativ": -5.0, "spalt": 0.02,
         "ueberlappung": 0.02, "y_von": -650.0, "y_bis": -250.0,
         "x": 0.0, "z": 100.0},
        {"name": "Rechts", "gruppe": "Front", "rolle": "Haupt", "profil": "e423.dat",
         "sehne_faktor": 1.0, "winkel_relativ": -5.0, "spalt": 0.02,
         "ueberlappung": 0.02, "y_von": 250.0, "y_bis": 650.0,
         "x": 0.0, "z": 100.0},
    ]
    system = system_aus_zeilen(daten)
    assert system.huelle()["breite"] == pytest.approx(1300.0)


def test_lokale_gruppe_verlangt_genau_ein_hauptelement():
    with pytest.raises(ValueError):
        flaps_aus_zeilen([
            {"name": "A", "rolle": "Flap", "profil": "e423.dat",
             "sehne_faktor": 1.0, "winkel_relativ": -5.0, "spalt": 0.02, "ueberlappung": 0.02}
        ])
