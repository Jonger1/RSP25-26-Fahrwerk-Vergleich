"""
Vom Element zur IBL-Datei.

Bewusst als eigenes Modul und nicht im Dash-Callback: Dieselbe Strecke wird
spaeter von der Kommandozeile, vom DoE-Lauf und vom Reportgenerator gebraucht.
Was nur im Callback stuende, koennte keiner von ihnen benutzen - und liesse
sich auch nicht testen, weil Dash ausserhalb einer echten Anfrage keinen
Kontext hat.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..geometrie.profil import Profil
from ..geometrie.spannweite import als_umlaeufe, huellwerte, schnitte
from ..geometrie.spline import CREO_GENAUIGKEIT_MM, entdoppeln
from .ibl import write_ibl


@dataclass
class Exportplan:
    """Was geschrieben wuerde, bevor es geschrieben wird.

    Erlaubt der Oberflaeche, Punktzahl und Vorschau zu zeigen, ohne dass eine
    Datei entsteht - und dem Anwender, das Ergebnis zu pruefen, bevor er es
    ins CAD laesst.
    """

    sektionen: list[np.ndarray]
    punktzahl: int
    toleranz_mm: float           # tatsaechlich erreichte Toleranz
    toleranz_gefordert: float    # was verlangt war
    geschlossen: bool = True     # eine umlaufende Kurve statt zweier Haelften
    ausgeduennt: int = 0         # Punkte, die Creo nicht haette trennen koennen
    ausgabe: str = "kurve"       # "kurve", "profil" oder "fluegel"
    stapel: list = field(default_factory=list)   # Schnitte, nur beim Fluegel

    @property
    def ist_fluegel(self) -> bool:
        return self.ausgabe == "fluegel"

    @property
    def punkte_gesamt(self) -> int:
        return sum(len(s) for s in self.sektionen)

    @property
    def gelockert(self) -> bool:
        """Musste die Toleranz aufgeweicht werden, damit es ueberhaupt geht?"""
        return self.toleranz_mm > self.toleranz_gefordert * 1.001


def plane_element(profil: Profil, sehne_mm: float, anstellwinkel: float,
                  toleranz_mm: float = 0.005,
                  geschlossen: bool = True) -> Exportplan:
    """Bereitet die Sektionen fuer ein Fluegelelement vor.

    GESCHLOSSEN ist der Normalfall: Das Profil wird als EINE umlaufende Kurve
    geschrieben - Hinterkante, Oberseite, Nase, Unterseite, zurueck zur
    Hinterkante. Nur so entsteht in Creo eine geschlossene Kontur, aus der
    sich unmittelbar eine Skizze und daraus ein Extrudieren machen laesst.

    Der frueher benutzte Weg mit zwei getrennten Haelften ist ueber
    `geschlossen=False` weiter erreichbar. Er hat einen echten Vorteil - der
    Knick an Nase und Hinterkante liegt genau auf der Kurvengrenze und muss
    nicht durch dichte Stuetzpunkte erzwungen werden - aber er liefert zwei
    Kurvenfeatures, die sich nur beruehren. Das ist fuer Creo keine
    geschlossene Kontur.

    Der Preis der geschlossenen Kurve ist die Punktzahl: gemessen etwa das
    Zwei- bis Dreifache bei gleicher Toleranz. Sie wird gerechnet, nicht
    geschaetzt - auf Basis des in M0 vermessenen Creo-Splines.
    """
    # Reicht die geforderte Toleranz nicht, wird sie schrittweise gelockert
    # statt den Export scheitern zu lassen. Eine etwas groebere Kurve ist immer
    # noch besser als gar keine - und der Plan sagt hinterher, womit gerechnet
    # wurde, sodass niemand eine Genauigkeit annimmt, die es nicht gab.
    gefordert = float(toleranz_mm)
    # Kurze Leiter statt fortgesetztem Verdoppeln: Bei einer sehr kleinen
    # Vorgabe braeuchte das Verdoppeln zwei Dutzend Anlaeufe, und jeder davon
    # sucht die Punktzahl von Neuem. Sieben Stufen decken denselben Bereich ab.
    leiter = [gefordert, gefordert * 2, gefordert * 5,
              0.005, 0.010, 0.020, 0.050]
    leiter = sorted({round(t, 6) for t in leiter if t >= gefordert})

    zaehle = profil.punktzahl_umlauf if geschlossen else profil.punktzahl
    n, versuch = None, gefordert
    for versuch in leiter:
        n = zaehle(sehne_mm, versuch)
        if n is not None:
            break

    if n is None:
        raise ValueError(
            f"Selbst mit {versuch:.4f} mm Toleranz laesst sich die Kontur nicht "
            f"treffen. Das deutet auf einen Knick im Profil hin, nicht auf zu "
            f"wenige Punkte - bitte die Quelldatei pruefen.")

    punkte = profil.repanelisiert(n).angestellt(anstellwinkel, sehne_mm)

    if geschlossen:
        roh = [_in_spannweitenebene(punkte)]
    else:
        nase = len(punkte) // 2
        roh = [_in_spannweitenebene(punkte[:nase + 1]),
               _in_spannweitenebene(punkte[nase:])]

    # Die Kosinusverteilung draengt an Nase und Hinterkante Punkte zusammen,
    # die Creo bei 0,01 mm Modellgenauigkeit nicht mehr trennen kann. Sie
    # werden hier entfernt, nicht in Creo - dort waere es ein Importfehler
    # ohne brauchbare Meldung.
    sektionen = []
    entfernt = 0
    for sektion in roh:
        if geschlossen:
            # Der doppelte Endpunkt gehoert zur Definition des Umlaufs und
            # wird erst beim Schreiben entfernt - fuer die Abstandspruefung
            # muss er weg, sonst faellt er selbst dem Filter zum Opfer.
            offen = sektion[:-1] if np.allclose(sektion[0], sektion[-1]) else sektion
            duenn = entdoppeln(offen, CREO_GENAUIGKEIT_MM, geschlossen=True)
            entfernt += len(offen) - len(duenn)
            sektionen.append(np.vstack([duenn, duenn[:1]]))
        else:
            duenn = entdoppeln(sektion, CREO_GENAUIGKEIT_MM, geschlossen=False)
            entfernt += len(sektion) - len(duenn)
            sektionen.append(duenn)

    return Exportplan(sektionen=sektionen, punktzahl=n, toleranz_mm=versuch,
                      toleranz_gefordert=gefordert, geschlossen=geschlossen,
                      ausgeduennt=entfernt,
                      ausgabe="kurve" if geschlossen else "profil")


def plane_fluegel(profil: Profil, spannweite, sehne_mm: float,
                  anstellwinkel: float, lage=(0.0, 0.0, 0.0),
                  toleranz_mm: float = 0.005) -> Exportplan:
    """Bereitet den Schnittstapel eines 3D-Fluegels vor.

    Alle Schnitte bekommen DIESELBE Punktzahl, und zwar die, die an der
    laengsten Sehne noetig ist. Zwei Gruende: Creo verdreht den Verbund,
    sobald die Schnitte ungleich aufgebaut sind, und die laengste Sehne ist
    der schwierigste Fall - was dort reicht, reicht ueberall.

    Die Schnitte sind geschlossene Umlaeufe, keine getrennten Haelften. Nur
    daraus laesst sich in Creo unmittelbar ein Volumen bilden.
    """
    gefordert = float(toleranz_mm)
    leiter = sorted({round(t, 6) for t in
                     [gefordert, gefordert * 2, gefordert * 5,
                      0.005, 0.010, 0.020, 0.050] if t >= gefordert})

    # Laengste Sehne im Stapel bestimmt die Punktzahl.
    laengste = sehne_mm * max(s.sehne for s in spannweite.stuetzstellen)

    n, versuch = None, gefordert
    for versuch in leiter:
        n = profil.punktzahl_umlauf(laengste, versuch)
        if n is not None:
            break
    if n is None:
        raise ValueError(
            f"Selbst mit {versuch:.4f} mm Toleranz laesst sich die Kontur bei "
            f"{laengste:.1f} mm Sehne nicht treffen. Das deutet auf einen Knick "
            f"im Profil hin, nicht auf zu wenige Punkte.")

    stapel = schnitte(profil, spannweite, sehne_mm, anstellwinkel, n, lage=lage)

    sektionen, entfernt = [], 0
    for umlauf in als_umlaeufe(stapel):
        offen = umlauf[:-1] if np.allclose(umlauf[0], umlauf[-1]) else umlauf
        duenn = entdoppeln(offen, CREO_GENAUIGKEIT_MM, geschlossen=True)
        entfernt += len(offen) - len(duenn)
        sektionen.append(np.vstack([duenn, duenn[:1]]))

    # Ungleich lange Schnitte waeren ein verdrehter Verbund. Das Ausduennen
    # kann je Schnitt unterschiedlich viel entfernen - deshalb hier auf die
    # kuerzeste Laenge angleichen statt zu hoffen, dass es passt.
    kuerzeste = min(len(s) for s in sektionen)
    if any(len(s) != kuerzeste for s in sektionen):
        sektionen = [_auf_laenge(s, kuerzeste) for s in sektionen]

    return Exportplan(sektionen=sektionen, punktzahl=n, toleranz_mm=versuch,
                      toleranz_gefordert=gefordert, geschlossen=True,
                      ausgeduennt=entfernt, ausgabe="fluegel", stapel=stapel)


def _auf_laenge(umlauf: np.ndarray, ziel: int) -> np.ndarray:
    """Kuerzt einen Umlauf gleichmaessig auf `ziel` Punkte.

    Gleichmaessig ueber die Bogenlaenge und nicht einfach hinten abgeschnitten
    - sonst wanderte die Naht von Schnitt zu Schnitt, und genau daran verdreht
    sich der Verbund in Creo.
    """
    offen = umlauf[:-1]
    index = np.unique(np.round(np.linspace(0, len(offen) - 1, ziel - 1)).astype(int))
    gekuerzt = offen[index]
    return np.vstack([gekuerzt, gekuerzt[:1]])


def plane_kaskade(haupt: Profil, sehne_mm: float, anstellwinkel: float,
                  vorgaben: list, toleranz_mm: float = 0.005) -> Exportplan:
    """Bereitet eine Kaskade fuer Creo vor: je Element eine geschlossene Kurve.

    Jedes Element wird eine eigene Sektion in derselben Datei. In Creo
    entsteht daraus EIN Kurvenfeature mit mehreren geschlossenen Kurven -
    jede laesst sich einzeln in eine Skizze projizieren und extrudieren.

    Die Punktzahl richtet sich nach dem anspruchsvollsten Element: Flaps sind
    kurz und stark gekruemmt, und was fuer sie reicht, reicht fuer das
    Hauptelement auch. Die Anordnung - Spalt und Ueberlappung - wird mit
    genau dieser Punktzahl neu gesucht, damit das exportierte Paket
    dieselbe Lage hat wie das angezeigte.
    """
    from ..geometrie import kaskade as geo

    gefordert = float(toleranz_mm)
    leiter = sorted({round(t, 6) for t in
                     [gefordert, gefordert * 2, gefordert * 5,
                      0.005, 0.010, 0.020, 0.050] if t >= gefordert})

    # Profile samt eigener Sehne, um fuer jedes die noetige Punktzahl zu
    # bestimmen.
    teile = [(haupt, sehne_mm)] + [(v.profil, sehne_mm * v.sehne_faktor)
                                   for v in vorgaben]

    n, versuch = None, gefordert
    for versuch in leiter:
        zahlen = [p.punktzahl_umlauf(s, versuch) for p, s in teile]
        if all(z is not None for z in zahlen):
            n = max(zahlen)
            break
    if n is None:
        raise ValueError(
            f"Selbst mit {versuch:.4f} mm Toleranz laesst sich eines der "
            f"Elemente nicht treffen - vermutlich ein Knick in einem Profil.")

    elemente = geo.platziere(haupt, sehne_mm, anstellwinkel, vorgaben, punkte=n)

    sektionen, entfernt = [], 0
    for element in elemente:
        umlauf = element.punkte
        offen = umlauf[:-1] if np.allclose(umlauf[0], umlauf[-1]) else umlauf
        duenn = entdoppeln(offen, CREO_GENAUIGKEIT_MM, geschlossen=True)
        entfernt += len(offen) - len(duenn)
        sektionen.append(_in_spannweitenebene(np.vstack([duenn, duenn[:1]])))

    return Exportplan(sektionen=sektionen, punktzahl=n, toleranz_mm=versuch,
                      toleranz_gefordert=gefordert, geschlossen=True,
                      ausgeduennt=entfernt, ausgabe="kaskade")


def schreibe(plan: Exportplan, ziel: str | Path,
             kommentare: list[str] | None = None) -> Path:
    """Schreibt den Plan als IBL-Datei."""
    return write_ibl(ziel, plan.sektionen, kommentare=kommentare,
                     geschlossen=plan.geschlossen)


def dateiname(name: str, endung: str = ".ibl") -> str:
    """Macht aus einem frei getippten Namen einen brauchbaren Dateinamen.

    Creo und Windows vertragen weder Doppelpunkte noch Schraegstriche, und
    Umlaute im Dateinamen sorgen beim Import regelmaessig fuer Aerger. Deshalb
    wird hier eingedampft statt darauf zu hoffen, dass es gutgeht.
    """
    umschrift = {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe",
                 "Ü": "Ue", "ß": "ss"}
    sauber = "".join(umschrift.get(z, z) for z in (name or "").strip())
    # Der PUNKT bleibt erhalten: "Spalt 1.2" ist ein brauchbarer Name, und
    # Windows wie Creo kommen damit zurecht. Fuehrende Punkte und Folgen von
    # Punkten fallen weg - die waeren als Pfadangabe missverstaendlich.
    sauber = "".join(z if (z.isalnum() or z in "-_.") else "_" for z in sauber)
    while "__" in sauber:
        sauber = sauber.replace("__", "_")
    while ".." in sauber:
        sauber = sauber.replace("..", ".")
    sauber = sauber.strip("_.")
    return (sauber or "profil") + endung


def vorschau(plan: Exportplan, zeilen: int = 40) -> str:
    """Erzeugt den Dateitext, ohne eine Datei anzulegen."""
    import tempfile

    with tempfile.TemporaryDirectory() as ordner:
        pfad = write_ibl(Path(ordner) / "vorschau.ibl", plan.sektionen,
                         geschlossen=plan.geschlossen)
        text = pfad.read_text(encoding="ascii").splitlines()
    if len(text) > zeilen:
        text = text[:zeilen] + [f"... ({len(text) - zeilen} weitere Zeilen)"]
    return "\n".join(text)


def _in_spannweitenebene(punkte: np.ndarray) -> np.ndarray:
    """Legt 2D-Profilpunkte in die Ebene y = 0 des Werkzeug-Koordinatensystems.

    Die Spannweitenverteilung kommt erst in M4 dazu; bis dahin liegt jedes
    Element in einer einzigen Schnittebene.
    """
    return np.column_stack([punkte[:, 0], np.zeros(len(punkte)), punkte[:, 1]])
