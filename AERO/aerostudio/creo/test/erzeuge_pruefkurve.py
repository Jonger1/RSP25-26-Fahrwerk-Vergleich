"""
Erzeugt die M0-Pruefkurven.

Die Geometrie ist hier EINMAL im Werkzeug-Koordinatensystem definiert
(x nach hinten, y nach rechts, z nach oben). Die Umrechnung in das
Koordinatensystem der Creo-Vorlage erledigt der Exporter.

Damit muss in Creo kein Koordinatensystem von Hand angelegt werden: Die
erzeugte Datei laesst sich direkt auf das Standard-Koordinatensystem
importieren - oder sogar per Datei -> Oeffnen laden - und sitzt richtig.

Aufruf:  python erzeuge_pruefkurve.py
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from aerostudio.formate.ibl import write_ibl  # noqa: E402  (Pfad muss vorher gesetzt sein)

HIER = Path(__file__).parent


def pruefgeometrie() -> list[np.ndarray]:
    """Zehn Sektionen, so gewaehlt, dass jeder Fehler ohne Messen auffaellt."""
    A = np.array   # Kurzform

    # Grosses Rechteck 200 x 50 bei y = 0, Ecke im Ursprung.
    # Vier Sektionen mit je zwei Punkten -> vier Geraden. Der erste Punkt
    # jeder Sektion ist der letzte der vorigen, damit Creo sie verbindet.
    rechteck_gross = [
        A([[0, 0, 0], [200, 0, 0]], float),
        A([[200, 0, 0], [200, 0, 50]], float),
        A([[200, 0, 50], [0, 0, 50]], float),
        A([[0, 0, 50], [0, 0, 0]], float),
    ]

    # Spline mit fuenf Stuetzpunkten, Scheitel exakt bei x = 100 / z = 80.
    # Creo baut daraus einen interpolierenden kubischen Spline (not-a-knot),
    # nachgewiesen in spline_verifikation.py.
    spline = [A([[0, 0, 50], [50, 0, 70], [100, 0, 80], [150, 0, 70], [200, 0, 50]], float)]

    # Kleines Rechteck 100 x 25, um 300 mm in Spannweitenrichtung versetzt.
    rechteck_klein = [
        A([[0, 300, 0], [100, 300, 0]], float),
        A([[100, 300, 0], [100, 300, 25]], float),
        A([[100, 300, 25], [0, 300, 25]], float),
        A([[0, 300, 25], [0, 300, 0]], float),
    ]

    # Richtungsmarke: 150 mm entlang +y. Zeigt, wo unsere Spannweitenrichtung landet.
    marke = [A([[0, 0, 0], [0, 150, 0]], float)]

    return rechteck_gross + spline + rechteck_klein + marke


# Die drei Stellen, an denen eine Kommentarzeile stehen kann. Getrennte
# Dateien, weil ein einzelner Fehlschlag mit einer gemischten Datei nicht
# sagt, WELCHE Stelle Creo stoert - und weil davon abhaengt, ob der
# AERO_SPEC_HASH in die Datei darf oder in einen Creo-Parameter muss.
#
# Inline hinter "begin section" ist bereits bewiesen: Jede geschriebene
# Sektion traegt "begin section ! 1", und der Import vom 09.09.2026 lief.
KOMMENTARORTE = {
    "vor_kopf": "Kommentarzeilen VOR dem Kopf (ueber 'open')",
    "nach_kopf": "Kommentarzeilen NACH dem Kopf (unter 'arclength')",
    "zwischen": "Kommentarzeilen vor JEDER Sektion",
}


def kommentartext(ort: str) -> list[str]:
    return [
        "RSP Aero Studio - M0 Kommentartest",
        f"Variante: {KOMMENTARORTE[ort]}",
        "Geometrie identisch zu M0_pruefkurve.ibl",
        "AERO_SPEC_HASH: 0000000000000000000000000000000000000000",
        "Einheiten: mm",
    ]


def main() -> None:
    sektionen = pruefgeometrie()
    geschrieben = [write_ibl(HIER / "M0_pruefkurve.ibl", sektionen)]

    for ort in KOMMENTARORTE:
        geschrieben.append(write_ibl(
            HIER / f"M0_kommentar_{ort}.ibl", sektionen,
            kommentare=kommentartext(ort), kommentarort=ort,
        ))

    # Die alte Sammeldatei bleibt, damit aeltere Protokollstaende weiter
    # aufgehen - sie ist identisch mit der Variante "vor_kopf".
    geschrieben.append(write_ibl(
        HIER / "M0_pruefkurve_kommentiert.ibl", sektionen,
        kommentare=kommentartext("vor_kopf"), kommentarort="vor_kopf",
    ))

    print(f"Geschrieben: {len(sektionen)} Sektionen je Datei")
    for pfad in geschrieben:
        print(f"  {pfad.name}")
    print()
    print("Die Koordinaten sind bereits in das System der Creo-Vorlage gedreht.")
    print("Import ohne eigenes Koordinatensystem, direkt auf das Standard-KS.")
    print()
    print("Alle vier Dateien haben IDENTISCHE Geometrie. Was sie unterscheidet,")
    print("sind allein die Kommentarzeilen - wer in Creo einen Unterschied in")
    print("der Form sieht, hat einen Befund, keinen Zufall.")


if __name__ == "__main__":
    main()
