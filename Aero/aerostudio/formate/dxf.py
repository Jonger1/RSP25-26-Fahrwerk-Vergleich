"""
Fertigungsvorlagen als DXF - Rippen und Schablonen zum Zuschneiden.

M1 Aufgabe 9. Die Nebenstrecke zum IBL-Export: Waehrend die .ibl nach Creo
geht und dort zum Bauteil wird, geht eine .dxf direkt an den Laser, den
Wasserstrahl oder die Fraese.

Zwei Vorlagen, weil ein Fluegel auf zwei Arten entsteht:

**Schablone** - die reine Aussenkontur. Zum Auflegen auf die Form, zum
Pruefen einer laminierten Schale, als Anriss fuer den Formenbau.

**Rippe** - Aussenkontur plus Innenkontur. Das Teil, das im fertigen Fluegel
steckt und die Schale in Form haelt. Die Innenkontur ist der Punkt, an dem
es interessant wird: Sie existiert nur dort, wo die Schale ueberhaupt hohl
ist. Nach vorne und nach hinten laeuft jedes Profil zusammen, und irgendwann
passt keine zwei Haeute mehr nebeneinander - dann ist das Bauteil
Vollmaterial und die Rippe dort schlicht voll.

Wo genau diese Grenze liegt, wird hier NICHT neu erfunden: `Profil.
laminatzonen` beantwortet die Frage bereits fuer die Fertigungspruefung, aus
Wandstaerke und Kerndicke des gewaehlten Verfahrens. Eine zweite Antwort
daneben waere eine zweite Wahrheit - und die Rippe wuerde irgendwann anders
aussehen als die Ampel im Profil-Editor behauptet.

**Warum ezdxf und nicht selbst geschrieben.** Das IBL-Format schreibt dieses
Projekt selbst: zehn Zeilen Kopf, gegen Creo verifiziert, in zehn Jahren noch
lesbar. DXF ist das Gegenteil - Sections, Tabellen, Handles, ein Dutzend
Versionen. Ein selbstgebautes DXF faellt irgendeinem CAM-Programm vor die
Fuesse, und das merkt man erst beim Zuschnitt. Dann ist das Material weg.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..geometrie.profil import Profil

# Layer, und was auf ihnen liegt. Getrennt, weil beim Zuschnitt nicht alles
# geschnitten werden soll: Die Sehnenlinie ist eine Hilfe zum Ausrichten, kein
# Schnittpfad. Wer sie mitschneidet, zersaegt sein Teil.
LAYER_KONTUR = "KONTUR"           # Aussenkontur - wird geschnitten
LAYER_HOHLRAUM = "HOHLRAUM"       # Innenkontur der Rippe - wird geschnitten
LAYER_HILFE = "SEHNE"             # Sehnenlinie - NICHT schneiden
LAYER_TEXT = "BESCHRIFTUNG"       # Name und Masse - NICHT schneiden

# AutoCAD-Farbindex. Rot fuer alles, was geschnitten wird, Grau fuer Hilfen -
# das ist die Konvention, die die gaengigen CAM-Programme erwarten.
_FARBEN = {LAYER_KONTUR: 1, LAYER_HOHLRAUM: 3, LAYER_HILFE: 8, LAYER_TEXT: 8}


@dataclass
class Rippenbefund:
    """Was beim Bau der Rippe herauskam - fuer Anzeige und Pruefung."""

    hohl_von: float          # Sehnenanteil, ab dem die Rippe hohl ist
    hohl_bis: float
    hat_hohlraum: bool
    wandstaerke: float
    flaeche_aussen: float    # mm^2
    flaeche_hohl: float      # mm^2

    @property
    def vollmaterial_anteil(self) -> float:
        """Wieviel der Sehne massiv bleibt. Ueber 0,5 wird die Rippe schwer."""
        return 1.0 - max(0.0, self.hohl_bis - self.hohl_von)


def _flaeche(umlauf: np.ndarray) -> float:
    """Flaeche eines geschlossenen Streckenzugs, nach Gauss."""
    x, y = umlauf[:, 0], umlauf[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)


def innenkontur(profil: Profil, sehne_mm: float, fertigung,
                n: int = 400) -> tuple[np.ndarray | None, Rippenbefund]:
    """Die Innenkontur einer Rippe, oder None wenn nirgends Platz ist.

    Gerechnet wird als Normalenversatz von Ober- und Unterseite nach innen,
    begrenzt auf den Bereich, in dem `laminatzonen` ueberhaupt eine Schale
    zulaesst. Vorne und hinten wird der Hohlraum mit einer Geraden
    geschlossen - dort endet er, weil das Profil zu duenn wird.

    Nicht als allgemeiner Polygon-Offset: Der wuerde sich an der Nase und an
    der Hinterkante selbst durchdringen und muesste anschliessend aufgeraeumt
    werden. Ueber die beiden Seiten getrennt gerechnet, tritt das Problem
    gar nicht erst auf.
    """
    wand = float(fertigung.wandstaerke)

    # Wo laesst das Verfahren ueberhaupt eine Schale zu? Dieselbe Antwort wie
    # in der Fertigungsampel - nicht daneben noch einmal hergeleitet.
    zonen = [z for z in profil.laminatzonen(fertigung, sehne_mm)
             if z.art in ("schale", "sandwich")]

    aussen = profil.skaliert(sehne_mm)
    flaeche_aussen = _flaeche(aussen)

    if not zonen:
        return None, Rippenbefund(0.0, 0.0, False, wand, flaeche_aussen, 0.0)

    von = min(z.von for z in zonen)
    bis = max(z.bis for z in zonen)

    x = np.linspace(von, bis, n)
    oben, unten = profil.seiten_auf(x)

    # Normalenversatz nach innen, in Sehnenanteilen gerechnet.
    #
    # Die Normale an eine Kurve y(x) ist (-y', 1) / sqrt(1 + y'^2). Nach
    # INNEN heisst das an der Oberseite (y', -1)/norm und an der Unterseite
    # (-y', 1)/norm. Beide Komponenten teilen sich dasselbe norm - wer nur
    # die y-Komponente normiert, bekommt an steilen Stellen eine Wand, die
    # zu duenn ist, und genau dort ist sie kritisch: an der Nase.
    d = wand / float(sehne_mm)

    def versetzt(y: np.ndarray, oberseite: bool) -> np.ndarray:
        ys = np.gradient(y, x)
        norm = np.sqrt(1.0 + ys**2)
        s = 1.0 if oberseite else -1.0
        return np.column_stack([x + s * d * ys / norm,
                                y - s * d / norm])

    innen_oben = versetzt(oben, oberseite=True)
    innen_unten = versetzt(unten, oberseite=False)

    # Wo sich die beiden Innenseiten ueberholen, ist kein Hohlraum mehr -
    # das kann trotz der Zonenpruefung an den Raendern passieren, weil die
    # Zonen ueber die DICKE gehen und der Versatz ueber die NORMALE.
    offen = innen_oben[:, 1] > innen_unten[:, 1]
    if not offen.any():
        return None, Rippenbefund(von, bis, False, wand, flaeche_aussen, 0.0)

    i = np.where(offen)[0]
    innen_oben = innen_oben[i[0]:i[-1] + 1]
    innen_unten = innen_unten[i[0]:i[-1] + 1]

    umlauf = np.vstack([innen_oben[::-1], innen_unten[1:]])
    umlauf = np.vstack([umlauf, umlauf[:1]]) * float(sehne_mm)

    befund = Rippenbefund(
        hohl_von=float(x[i[0]]), hohl_bis=float(x[i[-1]]), hat_hohlraum=True,
        wandstaerke=wand, flaeche_aussen=flaeche_aussen,
        flaeche_hohl=_flaeche(umlauf))
    return umlauf, befund


# ------------------------------------------------------------------ Schreiben

def _zeichnung():
    """Ein leeres DXF mit unseren Layern. R2010, weil das jedes CAM liest."""
    import ezdxf

    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4        # Millimeter, ausdruecklich
    for name, farbe in _FARBEN.items():
        doc.layers.add(name, color=farbe)
    return doc


def _gedreht(punkte: np.ndarray, winkel: float, sehne_mm: float,
             drehpunkt: float = 0.25) -> np.ndarray:
    """Dreht Millimeterpunkte um die Viertelsehne - wie `Profil.angestellt`.

    Muss dieselbe Drehung sein wie dort, sonst laege die Rippe anders als die
    Schablone desselben Profils: Die eine um die Viertelsehne gedreht, die
    andere um die Nase. Auf der Vorrichtung faellt so etwas erst auf, wenn
    beide Teile nebeneinanderliegen und nicht zusammenpassen.

    Auch das Vorzeichen stammt von dort: Negativer Winkel senkt die Nase.
    """
    if not winkel:
        return punkte
    mitte = float(drehpunkt) * float(sehne_mm)
    p = punkte.copy()
    p[:, 0] -= mitte
    a = np.radians(-float(winkel))
    c, s = np.cos(a), np.sin(a)
    gedreht = np.column_stack([p[:, 0] * c - p[:, 1] * s,
                               p[:, 0] * s + p[:, 1] * c])
    gedreht[:, 0] += mitte
    return gedreht


def _polylinie(msp, punkte: np.ndarray, layer: str) -> None:
    geschlossen = bool(np.allclose(punkte[0], punkte[-1]))
    msp.add_lwpolyline([(float(a), float(b)) for a, b in
                        (punkte[:-1] if geschlossen else punkte)],
                       close=geschlossen, dxfattribs={"layer": layer})


def schreibe_schablone(ziel: str | Path, profil: Profil, sehne_mm: float,
                       *, anstellwinkel: float = 0.0,
                       beschriftung: str = "") -> Path:
    """Die reine Aussenkontur, zum Auflegen und Anreissen.

    `anstellwinkel` dreht die Kontur mit. Fuer eine Schablone, die auf einer
    Vorrichtung sitzt, ist das der Unterschied zwischen passend und
    unbrauchbar - sie muss so liegen, wie das Bauteil spaeter steht.
    """
    kontur = (profil.angestellt(anstellwinkel, sehne_mm) if anstellwinkel
              else profil.skaliert(sehne_mm))

    doc = _zeichnung()
    msp = doc.modelspace()
    _polylinie(msp, kontur, LAYER_KONTUR)

    # Sehnenlinie als Ausrichthilfe - auf eigenem Layer, damit sie beim
    # Zuschnitt nicht mitgeschnitten wird.
    msp.add_line((0.0, 0.0), (float(sehne_mm), 0.0),
                 dxfattribs={"layer": LAYER_HILFE})

    text = beschriftung or f"{profil.name} - Sehne {sehne_mm:.1f} mm"
    if anstellwinkel:
        text += f", {anstellwinkel:+.1f} Grad"
    msp.add_text(text, height=sehne_mm * 0.03,
                 dxfattribs={"layer": LAYER_TEXT}).set_placement(
                     (0.0, -sehne_mm * 0.12))

    ziel = Path(ziel)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(ziel)
    return ziel


def schreibe_rippe(ziel: str | Path, profil: Profil, sehne_mm: float,
                   fertigung, *, anstellwinkel: float = 0.0,
                   beschriftung: str = "") -> tuple[Path, Rippenbefund]:
    """Aussenkontur plus Hohlraum - das Teil, das im Fluegel steckt.

    Gibt neben dem Pfad den Befund zurueck: wo die Rippe hohl ist und wo
    nicht. Das ist keine Nebensache - eine Rippe, die zu 80 % Vollmaterial
    ist, wiegt zu viel und gehoert anders konstruiert. Wer nur die Datei
    bekommt, sieht das erst am fertigen Teil auf der Waage.
    """
    hohl, befund = innenkontur(profil, sehne_mm, fertigung)

    doc = _zeichnung()
    msp = doc.modelspace()

    _polylinie(msp, _gedreht(profil.skaliert(sehne_mm), anstellwinkel,
                             sehne_mm), LAYER_KONTUR)
    if hohl is not None:
        _polylinie(msp, _gedreht(hohl, anstellwinkel, sehne_mm), LAYER_HOHLRAUM)

    msp.add_line((0.0, 0.0), (float(sehne_mm), 0.0),
                 dxfattribs={"layer": LAYER_HILFE})

    text = beschriftung or f"Rippe {profil.name} - Sehne {sehne_mm:.1f} mm"
    text += f", Wand {befund.wandstaerke:.1f} mm"
    if not befund.hat_hohlraum:
        text += " - VOLLMATERIAL"
    msp.add_text(text, height=sehne_mm * 0.03,
                 dxfattribs={"layer": LAYER_TEXT}).set_placement(
                     (0.0, -sehne_mm * 0.12))

    ziel = Path(ziel)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(ziel)
    return ziel, befund


def schreibe_rippensatz(ordner: str | Path, profil: Profil, spannweite,
                        grundsehne: float, fertigung, *,
                        stationen: int = 5, grundwinkel: float = 0.0,
                        name: str = "Rippe") -> list[tuple[Path, Rippenbefund]]:
    """Mehrere Rippen ueber die Spannweite, je eine Datei.

    Je eine Datei und nicht alle in einer: Beim Zuschnitt wird Blatt fuer
    Blatt geschachtelt, und eine Datei mit fuenf ineinanderliegenden
    Konturen muss man dafuer erst wieder auseinandernehmen.

    Die Sehne an jeder Station kommt aus derselben Verteilung wie der
    Export nach Creo - sonst passten die Rippen nicht in die Schale, die aus
    den IBL-Kurven entsteht.
    """
    from ..geometrie.spannweite import schnitte as spannweitenschnitte

    ordner = Path(ordner)
    stapel = spannweitenschnitte(profil, spannweite, grundsehne, grundwinkel,
                                 40)
    if stationen < 1:
        raise ValueError("Ein Rippensatz braucht mindestens eine Station.")

    index = np.unique(np.round(
        np.linspace(0, len(stapel) - 1, stationen)).astype(int))

    ergebnis = []
    for nr, i in enumerate(index, start=1):
        schnitt = stapel[i]
        ziel = ordner / f"{name}_{nr:02d}_y{schnitt.y:.0f}.dxf"
        ergebnis.append(schreibe_rippe(
            ziel, profil, schnitt.sehne, fertigung,
            beschriftung=f"{name} {nr} bei y = {schnitt.y:.0f} mm, "
                         f"Sehne {schnitt.sehne:.1f} mm"))
    return ergebnis
