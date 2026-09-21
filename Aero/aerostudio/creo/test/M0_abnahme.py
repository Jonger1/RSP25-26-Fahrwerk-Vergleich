"""
M0-Abnahme: Was ist bewiesen, was fehlt noch, und wer kann es beantworten?

Warum als Skript und nicht als Haekchenliste im Protokoll: Die Liste in
M0_PRUEFPROTOKOLL.md wird von Hand gepflegt. Am 21.09.2026 stand dort noch
"Mapkey entfaellt", obwohl die Begruendung dafuer auf einer Verwechslung
beruhte, und der Kommentarbefund war als EIN Haken gefuehrt, obwohl drei
verschiedene Stellen dahinterstecken. Eine handgepflegte Liste weiss immer
nur so viel, wie zuletzt jemand hineingeschrieben hat.

Dieses Skript liest stattdessen die Profildatei und die Pruefkurven und
rechnet nach, was ohne Creo nachrechenbar ist. Was nur ein Mensch an einem
Creo-Bildschirm beantworten kann, sagt es genau so - mit dem Pfad in die
YAML, in den die Antwort gehoert.

Aufruf:  python M0_abnahme.py
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from aerostudio.creo.profil import profil  # noqa: E402
from aerostudio.formate.ibl import frame_matrix  # noqa: E402

HIER = Path(__file__).parent

# Die Sollmasse der Pruefkurve, im Werkzeug-Koordinatensystem.
SOLL = {
    "grosses Rechteck": (200.0, 50.0),
    "kleines Rechteck": (100.0, 25.0),
    "Querabstand": 300.0,
    "Richtungsmarke": 150.0,
}


def _sektionen(pfad: Path) -> list[np.ndarray]:
    """Liest die Punkte einer .ibl zurueck - ohne Kommentare und Kopf."""
    sektionen: list[np.ndarray] = []
    aktuell: list[list[float]] = []
    for zeile in pfad.read_text(encoding="ascii").splitlines():
        text = zeile.strip()
        if not text or text.startswith("!"):
            continue
        if text.startswith("begin section"):
            if aktuell:
                sektionen.append(np.array(aktuell))
            aktuell = []
            continue
        if text.startswith(("begin curve", "open", "closed", "arclength")):
            continue
        teile = text.split()
        # Fuehrende Punktnummer ist optional.
        zahlen = [float(t) for t in (teile[1:] if len(teile) == 4 else teile)]
        aktuell.append(zahlen)
    if aktuell:
        sektionen.append(np.array(aktuell))
    return sektionen


# --------------------------------------------------------- Nachrechenbares

def pruefe_frame() -> tuple[bool, str]:
    """Ist die Achsabbildung eine Drehung und keine Spiegelung?"""
    p = profil()
    try:
        M = frame_matrix(p.frame)
    except ValueError as fehler:
        return False, str(fehler)
    det = float(np.linalg.det(M))
    return True, (f"Achsabbildung {p.frame['creo_x']}/{p.frame['creo_y']}/"
                  f"{p.frame['creo_z']}, Determinante {det:+.0f} - eine Drehung, "
                  f"keine Spiegelung")


def pruefe_pruefkurven() -> tuple[bool, str]:
    """Haben alle Kommentarvarianten wirklich dieselbe Geometrie?

    Das ist die Voraussetzung dafuer, dass der Kommentartest ueberhaupt
    etwas aussagt: Sieht die Form in Creo anders aus, muss das an den
    Kommentaren liegen und darf nicht an unterschiedlichen Punkten liegen.
    """
    basis = HIER / "M0_pruefkurve.ibl"
    if not basis.exists():
        return False, "M0_pruefkurve.ibl fehlt - erzeuge_pruefkurve.py laufen lassen"

    referenz = _sektionen(basis)
    varianten = sorted(HIER.glob("M0_kommentar_*.ibl"))
    if not varianten:
        return False, ("Keine Kommentarvarianten gefunden - "
                       "erzeuge_pruefkurve.py laufen lassen")

    for pfad in varianten:
        andere = _sektionen(pfad)
        if len(andere) != len(referenz):
            return False, f"{pfad.name} hat {len(andere)} statt {len(referenz)} Sektionen"
        for nr, (a, b) in enumerate(zip(referenz, andere), start=1):
            if a.shape != b.shape or not np.allclose(a, b):
                return False, f"{pfad.name}, Sektion {nr} weicht ab"

    return True, (f"{len(varianten) + 1} Dateien, {len(referenz)} Sektionen, "
                  f"Geometrie punktgleich - der Unterschied sind allein die "
                  f"Kommentare")


def pruefe_masse() -> tuple[bool, str]:
    """Stecken die Sollmasse wirklich in der erzeugten Datei?

    Gemessen wurde am 09.09. in Creo. Hier wird geprueft, dass die Datei,
    die heute entsteht, dieselben Masse traegt - sonst beweist die alte
    Messung nichts ueber den heutigen Exporter.
    """
    basis = HIER / "M0_pruefkurve.ibl"
    if not basis.exists():
        return False, "M0_pruefkurve.ibl fehlt"

    # Zurueckdrehen ins Werkzeugsystem, dann sind die Masse direkt ablesbar.
    M = frame_matrix(profil().frame)
    punkte = np.vstack([s @ M for s in _sektionen(basis)])

    bei_y0 = punkte[np.isclose(punkte[:, 1], 0.0)]
    bei_y300 = punkte[np.isclose(punkte[:, 1], 300.0)]
    if len(bei_y0) == 0 or len(bei_y300) == 0:
        return False, "Sektionen bei y = 0 oder y = 300 fehlen"

    gross = (bei_y0[:, 0].max() - bei_y0[:, 0].min(),
             bei_y0[:, 2].max() - bei_y0[:, 2].min())
    klein = (bei_y300[:, 0].max() - bei_y300[:, 0].min(),
             bei_y300[:, 2].max() - bei_y300[:, 2].min())
    quer = bei_y300[:, 1].max() - bei_y0[:, 1].max()

    # Das grosse Rechteck teilt sich seine z-Ausdehnung mit dem Spline
    # (Scheitel bei z = 80), deshalb wird davon nur die Laenge geprueft.
    abweichungen = []
    for name, ist, soll in (
        ("grosses Rechteck lang", gross[0], SOLL["grosses Rechteck"][0]),
        ("kleines Rechteck lang", klein[0], SOLL["kleines Rechteck"][0]),
        ("kleines Rechteck hoch", klein[1], SOLL["kleines Rechteck"][1]),
        ("Querabstand", quer, SOLL["Querabstand"]),
    ):
        if not np.isclose(ist, soll, atol=1e-6):
            abweichungen.append(f"{name} {ist:.3f} statt {soll:.0f}")

    if abweichungen:
        return False, "; ".join(abweichungen)
    return True, ("200 x 50 / 100 x 25 mm, Querabstand 300 mm - exakt, "
                  "wie am 09.09. in Creo nachgemessen")


# ----------------------------------------------------------------- Ausgabe

def _zeile(ok: bool, titel: str, text: str) -> str:
    return f"  [{'x' if ok else ' '}] {titel}\n      {text}"


def _hauptteil() -> int:
    p = profil()

    print()
    print("M0 - Abnahme")
    print("=" * 70)
    print()

    if p.quelle is None:
        print("  ACHTUNG: Versionsprofil nicht gelesen.")
        for mangel in p.maengel:
            print(f"    {mangel}")
        print()
    else:
        print(f"  Profil: {p.quelle.name}   Creo {p.daten['creo']['datecode']}")
        for mangel in p.maengel:
            print(f"    Mangel: {mangel}")
        print()

    print("Ohne Creo nachgerechnet")
    print("-" * 70)
    ergebnisse = []
    for titel, pruefung in (("Achsabbildung ist eine Drehung", pruefe_frame),
                            ("Sollmasse stecken in der Datei", pruefe_masse),
                            ("Kommentarvarianten sind geometriegleich",
                             pruefe_pruefkurven)):
        ok, text = pruefung()
        ergebnisse.append(ok)
        print(_zeile(ok, titel, text))
    print()

    jetzt_offen = p.offene_punkte("jetzt")
    vertagt = p.offene_punkte("vertagt")

    print("Nur an einem Creo-Bildschirm zu beantworten")
    print("-" * 70)
    if jetzt_offen:
        for pfad, wert in jetzt_offen:
            print(f"  [ ] {pfad}")
        datei = p.quelle.name if p.quelle else "creo8.yaml"
        print()
        print(f"  {len(jetzt_offen)} offene Eintraege, alle in {datei}.")
        print("  Sie warten auf einen Durchlauf nach M0_PRUEFPROTOKOLL.md.")
    else:
        print("  Keine. Alle Befunde sind eingetragen.")
    print()

    if vertagt:
        print("Bewusst vertagt - blockiert M0 nicht")
        print("-" * 70)
        for pfad, wert in vertagt:
            print(f"  ... {pfad}: {wert}")
        print()

    fertig = all(ergebnisse) and not jetzt_offen
    print("=" * 70)
    if fertig:
        print("  M0 ist abgeschlossen.")
    else:
        print(f"  M0 ist NICHT abgeschlossen: "
              f"{sum(1 for e in ergebnisse if not e)} Rechenpruefung(en) rot, "
              f"{len(jetzt_offen)} Befund(e) offen.")
    print()
    return 0 if fertig else 1


if __name__ == "__main__":
    raise SystemExit(_hauptteil())
