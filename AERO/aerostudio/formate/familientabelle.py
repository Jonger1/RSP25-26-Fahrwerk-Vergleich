"""
DRS-Zustaende als Zeilen einer Creo-Familientabelle.

Das Konzept (4.6): "das Tool exportiert beide Zustaende als getrennte Zeilen
einer Creo-Familientabelle". Eine Zeile je Zustand, eine Spalte je
beweglichem Winkel:

    Instanz      RW_E2_AOA   RW_E2_AOA_AUSSEN
    RW_DRS_ZU    -26.0       -30.0
    RW_DRS_AUF   -6.0        -10.0

Die Spaltennamen folgen der Konvention aus M5, Aufgabe 3
(`FW_E2_AOA` = Winkel von Element 2 gegen seinen Vorgaenger). In Creo
muessen diese Parameter per Relation den Flap um sein Scharnier drehen -
das richtet M5 ein, und das ist bis zur Lizenzfrage blockiert.

**Nicht in Creo geprueft.** Die Datei ist tabulatorgetrennt, damit sie sich
ohne Umweg ueber das Gebietsschema in die Tabelle kopieren laesst, die Creo
unter *Familientabelle > Bearbeiten in Excel* oeffnet. Ob Creo 8 die Spalten
so uebernimmt, steht aus - wie die offenen Punkte von M0.
"""

from __future__ import annotations

import re
from pathlib import Path


def praefix(element) -> str:
    """"RW_E1" -> "RW". Ohne _E-Nummer bleibt die id selbst."""
    treffer = re.match(r"^(.*)_E\d+$", element.id)
    return treffer.group(1) if treffer else element.id


def tabelle(spec) -> tuple[list[str], list[list]]:
    """Kopf und Zeilen - alle Elemente mit DRS in einer Tabelle.

    Der offene Zustand kommt aus `drs.element_offen` - derselben Funktion,
    die gerechnet und gegen die Regeln geprueft wird. Eine eigene Rechnung
    hier liefe auseinander, sobald sich die DRS-Kinematik aendert.
    """
    from ..aero import drs

    kopf = ["Instanz"]
    zu, auf = [], []
    namen = []
    for element in spec.elemente:
        if not drs.hat_drs(element):
            continue
        p = praefix(element)
        offen = drs.element_offen(element)
        for i, (k, ko) in enumerate(zip(element.kaskade, offen.kaskade), start=2):
            if k.drs_winkel is None:
                continue
            kopf.append(f"{p}_E{i}_AOA")
            zu.append(k.winkel)
            auf.append(ko.winkel)
            if k.winkel_aussen is not None:
                kopf.append(f"{p}_E{i}_AOA_AUSSEN")
                zu.append(k.winkel_aussen)
                auf.append(ko.winkel_aussen)
        if p not in namen:
            namen.append(p)
    if not namen:
        return kopf, []
    name = "_".join(namen)
    return kopf, [[f"{name}_DRS_ZU", *zu], [f"{name}_DRS_AUF", *auf]]


def schreiben(spec, pfad: str | Path) -> Path:
    kopf, zeilen = tabelle(spec)
    if not zeilen:
        raise ValueError("Kein Flap mit DRS-Winkel im Entwurf - in der "
                         "Kaskadentabelle die Spalte „DRS offen“ "
                         "fuellen.")
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    text = "\t".join(kopf) + "\n" + "\n".join(
        "\t".join([z[0], *(f"{w:.2f}" for w in z[1:])]) for z in zeilen) + "\n"
    pfad.write_text(text, encoding="utf-8")
    return pfad
