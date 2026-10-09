"""
Vom 2D-Profil zum 3D-Flügel.

Ein Flügel ist ein Stapel identisch aufgebauter Profilschnitte entlang der
Spannweite. "Identisch aufgebaut" heißt: gleiche Punktzahl, gleiche Reihenfolge,
gleicher Startpunkt. Das ist keine Förmlichkeit, sondern die Bedingung dafür,
dass Creo daraus einen sauberen Boundary Blend baut - bei ungleich strukturierten
Schnitten verdreht sich die Fläche.

Was andere Formula-Student-Teams machen, und woher das kommt:

* Der Frontflügel ist spannweitig SEGMENTIERT, nicht gleichmäßig verjüngt. Eine
  schwedische Arbeit zum FS-Frontflügel (Jönköping 2024) beschreibt vier
  Elemente im mittleren Bereich und drei im äußeren, und begründet das mit den
  Geometriegrenzen des Reglements: außen ist schlicht weniger Höhe erlaubt.
* Innen wird der Flügel NEGATIV angestellt, um die Luft nach außen um das Rad
  herumzuleiten. Dieselbe Arbeit misst dafür −10 Grad als bestes Ergebnis und
  weist den Erfolg über den gesunkenen Widerstand der Vorderräder nach.
* Außen am Rad sitzt die längste Sehne und der größte Anstellwinkel - so
  beschreibt es eMotorsports Cologne für ihren Frontflügel.

Diese drei Punkte sind der Grund, warum hier Sehne, Verwindung, Höhe und
Längsversatz einzeln über die Spannweite verteilbar sind statt über einen
einzigen Verjüngungsfaktor.

ACHTUNG bei der Übertragung des zweiten Punktes - hier ist schon einmal ein
Fehler passiert:

Die −10 Grad gelten für ein eigenes ELEMENT eines segmentierten Flügels, nicht
für die Verwindung einer durchgehenden Fläche. Als Verwindung eingetragen
ergaben sie 24 Grad je Meter; der Berandungsverbund in Creo schnürte in der
Mitte sichtbar ein, und die Wurzel stand zwei Grad jenseits des Abrisses. Ein
segmentierter Flügel hat dort eine KANTE zwischen zwei Bauteilen - eine
durchgehende Haut muss den Unterschied über die Spannweite verteilen und
verdreht sich dabei.

Die Vorgabe in spec.modell.Spannweite ist deshalb maßvoll gehalten, und
geometrie.verwindung warnt, sobald die Rate zu groß wird oder ein Schnitt an
den Abriss kommt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import PchipInterpolator

from .profil import Profil


@dataclass
class Schnitt:
    """Ein Profilschnitt an einer Spannweitenposition, in Millimetern."""

    y: float
    sehne: float
    anstellwinkel: float
    punkte: np.ndarray          # Nx3 im Werkzeug-Koordinatensystem

    @property
    def hoehe_min(self) -> float:
        return float(self.punkte[:, 2].min())

    @property
    def hoehe_max(self) -> float:
        return float(self.punkte[:, 2].max())


def _verlauf(stellen: list[float], werte: list[float]) -> callable:
    """Formerhaltender Verlauf über die Spannweite.

    PCHIP und nicht der gewöhnliche kubische Spline: Der überschwingt zwischen
    Stützstellen und erfindet dabei Sehnen oder Winkel, die niemand eingegeben
    hat. Bei einer Verjüngung von innen nach außen fällt das sofort auf - der
    Flügel würde zwischen zwei Stationen dicker als an beiden.
    """
    if len(stellen) == 1:
        wert = float(werte[0])
        return lambda y: np.full_like(np.asarray(y, dtype=float), wert)
    ordnung = np.argsort(stellen)
    return PchipInterpolator(np.asarray(stellen, dtype=float)[ordnung],
                             np.asarray(werte, dtype=float)[ordnung],
                             extrapolate=True)


def schnitte(profil: Profil, spannweite, grundsehne: float,
             grundwinkel: float, punkte_je_seite: int,
             lage: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> list[Schnitt]:
    """Baut den Schnittstapel eines Flügels.

    grundsehne und grundwinkel sind die Werte an der Wurzel; die Verteilungen
    wirken multiplikativ beziehungsweise additiv darauf.

    `lage` verschiebt den fertigen Stapel ins Fahrzeug-Koordinatensystem. Ohne
    diese Verschiebung ließe sich keine Regel prüfen - das Reglement nennt
    ausschließlich absolute Lagen am Fahrzeug, nie relative.
    """
    stellen = [s.y for s in spannweite.stuetzstellen]
    f_sehne = _verlauf(stellen, [s.sehne for s in spannweite.stuetzstellen])
    f_twist = _verlauf(stellen, [s.verwindung for s in spannweite.stuetzstellen])
    f_z = _verlauf(stellen, [s.z for s in spannweite.stuetzstellen])
    f_x = _verlauf(stellen, [s.x for s in spannweite.stuetzstellen])

    fein = profil.repanelisiert(punkte_je_seite)
    ergebnis: list[Schnitt] = []

    for y in np.linspace(min(stellen), max(stellen), spannweite.schnitte):
        sehne = grundsehne * float(f_sehne(y))
        winkel = grundwinkel + float(f_twist(y))
        eben = fein.angestellt(winkel, sehne)

        punkte = np.column_stack([
            eben[:, 0] + float(f_x(y)) + lage[0],
            np.full(len(eben), float(y) + lage[1]),
            eben[:, 1] + float(f_z(y)) + lage[2],
        ])
        ergebnis.append(Schnitt(float(y), sehne, winkel, punkte))

    return ergebnis


def kaskadenstationen(spannweite, vorgaben: list) -> list[list[float]]:
    """Die Spannweitenstationen je Element, Hauptelement zuerst.

    Das Hauptelement bekommt die gleichmaessig verteilten Schnitte wie
    bisher. Ein Teilflap bekommt SEINE Enden als Schnitte, dazu alle
    Hauptelementschnitte dazwischen und die Enden anderer Teilflaps, die in
    seinem Bereich liegen - dort wechselt womoeglich sein Vorgaenger, und
    genau dort muss geprueft werden. Mindestens drei Schnitte, damit Creo
    einen Verbund und keine gerade Flaeche daraus macht.
    """
    stellen = [s.y for s in spannweite.stuetzstellen]
    innen, aussen = float(min(stellen)), float(max(stellen))
    haupt = [float(y) for y in np.linspace(innen, aussen, spannweite.schnitte)]
    ergebnis = [haupt]
    enden = sorted({e for v in vorgaben for e in v.bereich(innen, aussen)})

    for v in vorgaben:
        von, bis = v.bereich(innen, aussen)
        if bis - von < 1e-6:
            ergebnis.append([])
            continue
        ys = {round(von, 6), round(bis, 6)}
        ys |= {round(y, 6) for y in haupt + enden if von + 1e-6 < y < bis - 1e-6}
        ys = sorted(ys)
        while len(ys) < 3:
            luecke = int(np.argmax(np.diff(ys)))
            ys.insert(luecke + 1, 0.5 * (ys[luecke] + ys[luecke + 1]))
        ergebnis.append([float(y) for y in ys])
    return ergebnis


def kaskadenschnitte(haupt: Profil, spannweite, grundsehne: float,
                     grundwinkel: float, vorgaben: list,
                     punkte_je_seite: int,
                     lage: tuple[float, float, float] = (0.0, 0.0, 0.0)
                     ) -> list[list[Schnitt]]:
    """Baut eine vollständige 3D-Kaskade, getrennt nach Elementen.

    Die 2D-Anordnung wird an *jeder* Spannweitenstation neu bestimmt. Das ist
    wichtig: Ein Flap, der nur am Wurzelschnitt korrekt sitzt und dann als
    starrer Körper nach außen kopiert wird, verliert bei Verjüngung und
    Verwindung seinen Spalt. Hier bleiben Spalt und Überlappung an jeder
    Station relativ zum jeweiligen Vorgänger erhalten.

    Die Rückgabe ist ``[Hauptelement, Flap 1, ...]``. Innerhalb eines
    Elements haben alle Schnitte dieselbe Punktzahl und können in Creo als
    eigener Boundary Blend verwendet werden. Zwischen den Elementen wird
    bewusst *kein* Blend erzeugt: Der Schlitz muss offen bleiben.

    **Teilflügel:** Ein Flap mit `y_von`/`y_bis` bekommt nur Schnitte in
    seinem Bereich (siehe `kaskadenstationen`). An jeder Station wird die
    Kaskade aus den Elementen gebaut, die DORT existieren - der Vorgänger
    eines Flaps ist also das nächste vorhandene Element davor.
    """
    # Lokaler Import: kaskade importiert Profil; ein Modulimport oben würde
    # unnötig einen Kreis erzeugen.
    from . import kaskade as kaskade_geo

    stellen = [s.y for s in spannweite.stuetzstellen]
    innen, aussen = float(min(stellen)), float(max(stellen))
    f_sehne = _verlauf(stellen, [s.sehne for s in spannweite.stuetzstellen])
    f_twist = _verlauf(stellen, [s.verwindung for s in spannweite.stuetzstellen])
    f_z = _verlauf(stellen, [s.z for s in spannweite.stuetzstellen])
    f_x = _verlauf(stellen, [s.x for s in spannweite.stuetzstellen])

    stationen = kaskadenstationen(spannweite, vorgaben)
    gesucht = [{round(y, 6) for y in ys} for ys in stationen]
    alle = sorted(set().union(*gesucht))

    stapel: list[list[Schnitt]] = [[] for _ in range(len(vorgaben) + 1)]
    for y in alle:
        aktiv = kaskade_geo.vorgaben_bei(vorgaben, y, innen, aussen)
        benoetigt = [i for i, _ in aktiv if y in gesucht[i + 1]]
        # Die Kette nur so weit bauen, wie sie hier gebraucht wird - hinter
        # dem letzten benoetigten Flap haengt nichts mehr davon ab.
        kette = ([(i, v) for i, v in aktiv if i <= max(benoetigt)]
                 if benoetigt else [])
        sehne = grundsehne * float(f_sehne(y))
        winkel = grundwinkel + float(f_twist(y))
        elemente = kaskade_geo.platziere(haupt, sehne, winkel,
                                         [v for _, v in kette],
                                         punkte=punkte_je_seite)
        indizes = [0] + [i + 1 for i, _ in kette]
        for index, element in zip(indizes, elemente):
            if y not in gesucht[index]:
                continue
            punkte = np.column_stack([
                element.punkte[:, 0] + float(f_x(y)) + lage[0],
                np.full(len(element.punkte), float(y) + lage[1]),
                element.punkte[:, 1] + float(f_z(y)) + lage[2],
            ])
            stapel[index].append(Schnitt(float(y), element.sehne,
                                         element.winkel, punkte))
    return stapel


def kaskade_bei(haupt: Profil, spannweite, grundsehne: float,
                grundwinkel: float, vorgaben: list, y: float,
                punkte: int = 120,
                lage: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> list:
    """Die Kaskade im Schnitt an der Stelle y - so, wie sie dort wirklich steht.

    Sehne, Verwindung, Höhe und Längsversatz folgen der Sektionstabelle, und
    es sind nur die Flaps dabei, die an dieser Stelle existieren. Die Punkte
    sind (x, z) mit `lage` verschoben.
    """
    from . import kaskade as kaskade_geo

    stellen = [s.y for s in spannweite.stuetzstellen]
    innen, aussen = float(min(stellen)), float(max(stellen))
    y = min(max(float(y), innen), aussen)
    f_sehne = _verlauf(stellen, [s.sehne for s in spannweite.stuetzstellen])
    f_twist = _verlauf(stellen, [s.verwindung for s in spannweite.stuetzstellen])
    f_z = _verlauf(stellen, [s.z for s in spannweite.stuetzstellen])
    f_x = _verlauf(stellen, [s.x for s in spannweite.stuetzstellen])
    aktiv = kaskade_geo.vorgaben_bei(vorgaben, y, innen, aussen)
    return kaskade_geo.platziere(
        haupt, grundsehne * float(f_sehne(y)), grundwinkel + float(f_twist(y)),
        [v for _, v in aktiv],
        lage=(float(f_x(y)) + lage[0], float(f_z(y)) + lage[2]), punkte=punkte)


@dataclass
class Raumbefund:
    """Ein Ergebnis der räumlichen Prüfung einer Kaskade."""

    stufe: str                  # "fehler", "hinweis" oder "ok"
    text: str
    y: float | None = None


@dataclass
class Raumpruefung:
    befunde: list[Raumbefund]
    kleinster_spalt: float | None       # mm, über alle Paare und Stellen
    y_kleinster_spalt: float | None
    stellen: int                        # wie viele y-Lagen geprüft wurden

    @property
    def durchdringungsfrei(self) -> bool:
        return not any(b.stufe == "fehler" for b in self.befunde)


def _schnitt_bei(stapel: list[Schnitt], y: float) -> np.ndarray | None:
    """Die (x, z)-Kontur eines Elements bei y, linear zwischen den Schnitten.

    Linear, weil eine Verbundfläche zwischen zwei Schnitten in erster Näherung
    genau so verläuft. Liegt y außerhalb des Elements, gibt es dort keins.
    """
    if not stapel or y < stapel[0].y - 1e-6 or y > stapel[-1].y + 1e-6:
        return None
    ys = np.array([s.y for s in stapel])
    j = int(np.searchsorted(ys, y - 1e-6))
    if j < len(ys) and abs(ys[j] - y) < 1e-6:
        return stapel[j].punkte[:, [0, 2]]
    if j == 0:
        return stapel[0].punkte[:, [0, 2]]
    a, b = stapel[j - 1], stapel[min(j, len(stapel) - 1)]
    if len(a.punkte) != len(b.punkte) or b.y - a.y < 1e-9:
        return a.punkte[:, [0, 2]]
    t = (y - a.y) / (b.y - a.y)
    return ((1.0 - t) * a.punkte + t * b.punkte)[:, [0, 2]]


def pruefe_kaskade_raeumlich(stapel_je_element: list[list[Schnitt]],
                             vorgaben: list | None = None,
                             spannweite=None,
                             spalt_min_mm: float = 0.5) -> Raumpruefung:
    """Prüft, ob sich die Elemente einer 3D-Kaskade irgendwo schneiden.

    An den Schnitten selbst ist das durch die Anordnung ausgeschlossen. Nicht
    aber DAZWISCHEN: Creo verbindet die Schnitte zu einer Fläche, und wenn
    zwei Elemente an benachbarten Schnitten verschieden stark verdreht sind,
    kann die Fläche des einen durch die des anderen laufen. Deshalb wird auch
    in der Mitte zwischen allen Schnittlagen nachgesehen.

    Zusätzlich gemeldet: ein Teilflap, dessen Vorgänger innerhalb seiner
    Spannweite wechselt. Der Flap springt dort in eine andere Lage, und die
    Verbundfläche dazwischen ist verdreht - besser zwei Teilflaps daraus
    machen.
    """
    from . import kaskade as kaskade_geo

    befunde: list[Raumbefund] = []
    lagen = sorted({round(s.y, 6) for st in stapel_je_element for s in st})
    if not lagen:
        return Raumpruefung([], None, None, 0)
    mitten = [0.5 * (a + b) for a, b in zip(lagen[:-1], lagen[1:])]
    pruefstellen = sorted(lagen + mitten)
    namen = ["Hauptelement"] + [f"Flap {i}" for i in
                                range(1, len(stapel_je_element))]

    kleinster, y_kleinster = None, None
    gemeldet = set()
    for y in pruefstellen:
        konturen = [(i, _schnitt_bei(st, y))
                    for i, st in enumerate(stapel_je_element)]
        konturen = [(i, k) for i, k in konturen if k is not None]
        for a in range(len(konturen)):
            for b in range(a + 1, len(konturen)):
                ia, ka = konturen[a]
                ib, kb = konturen[b]
                if kaskade_geo.schneiden_sich(ka, kb):
                    schluessel = (ia, ib)
                    if schluessel not in gemeldet:
                        gemeldet.add(schluessel)
                        befunde.append(Raumbefund(
                            "fehler",
                            f"{namen[ia]} und {namen[ib]} durchdringen sich "
                            f"bei y = {y:.0f} mm"
                            + (" (zwischen zwei Schnitten)"
                               if round(y, 6) not in lagen else "")
                            + ". Winkel oder Spalt dort ändern, oder mehr "
                              "Schnitte setzen.", y))
                    continue
                d = kaskade_geo.mindestabstand(ka, kb)
                if kleinster is None or d < kleinster:
                    kleinster, y_kleinster = d, y

    if kleinster is not None and kleinster < spalt_min_mm and not gemeldet:
        befunde.append(Raumbefund(
            "hinweis", f"Engster Spalt nur {kleinster:.2f} mm bei y = "
                       f"{y_kleinster:.0f} mm - im Laminat kaum zu halten.",
            y_kleinster))

    if vorgaben and spannweite is not None:
        stellen = [s.y for s in spannweite.stuetzstellen]
        innen, aussen = float(min(stellen)), float(max(stellen))
        for k, st in enumerate(stapel_je_element[1:]):
            vorher, wechsel = None, None
            for schnitt in st:
                aktiv = [i for i, _ in kaskade_geo.vorgaben_bei(
                    vorgaben, schnitt.y, innen, aussen) if i < k]
                v = (max(aktiv) + 1) if aktiv else 0
                if vorher is not None and v != vorher[0] and wechsel is None:
                    wechsel = (vorher[1], schnitt.y)
                vorher = (v, schnitt.y)
            if wechsel is not None:
                befunde.append(Raumbefund(
                    "hinweis",
                    f"Flap {k + 1} wechselt zwischen y = {wechsel[0]:.0f} und "
                    f"{wechsel[1]:.0f} mm seinen Vorgänger und springt dort in "
                    f"eine andere Lage. Besser in zwei Teilflaps teilen, die "
                    f"dort enden.", wechsel[1]))

    if not befunde:
        befunde.append(Raumbefund(
            "ok", f"Keine Durchdringung an {len(pruefstellen)} Prüfstellen"
                  + (f", engster Spalt {kleinster:.1f} mm bei y = "
                     f"{y_kleinster:.0f} mm." if kleinster is not None else ".")))
    return Raumpruefung(befunde, kleinster, y_kleinster, len(pruefstellen))


def als_sektionen(stapel: list[Schnitt]) -> list[np.ndarray]:
    """Zerlegt den Stapel in IBL-Sektionen: je Schnitt Ober- und Unterseite.

    Getrennt, weil ein durchgehender Spline über die Nase in Creo fast immer
    eine Beule erzeugt. Alle Sektionen haben dieselbe Punktzahl und laufen in
    derselben Richtung - sonst verdreht der Boundary Blend die Fläche.
    """
    sektionen: list[np.ndarray] = []
    for schnitt in stapel:
        nase = len(schnitt.punkte) // 2
        sektionen.append(schnitt.punkte[:nase + 1])
        sektionen.append(schnitt.punkte[nase:])
    return sektionen


def als_umlaeufe(stapel: list[Schnitt]) -> list[np.ndarray]:
    """Ein geschlossener Umlauf je Schnitt - die Form für einen Volumenkörper.

    Anders als `als_sektionen` liefert das eine geschlossene Kurve pro Schnitt
    statt zweier Hälften. Genau die braucht Creo, um zwischen den Schnitten
    einen Verbund (Boundary Blend oder Zug) als VOLUMEN zu bilden: Offene
    Hälften ergeben Flächen, die man hinterher einzeln vernähen muss.

    Der doppelte Punkt an der Hinterkante bleibt hier stehen; entfernt wird er
    erst beim Schreiben, wo auch der Kopf auf "closed" gesetzt wird.
    """
    return [schnitt.punkte.copy() for schnitt in stapel]


def huellwerte(stapel: list[Schnitt]) -> dict[str, float]:
    """Abmessungen des fertigen Flügels - die Größen, die das Reglement nennt."""
    alle = np.vstack([s.punkte for s in stapel])
    return {
        "spannweite": float(alle[:, 1].max() - alle[:, 1].min()),
        "y_min": float(alle[:, 1].min()),
        "y_max": float(alle[:, 1].max()),
        "x_min": float(alle[:, 0].min()),
        "x_max": float(alle[:, 0].max()),
        "z_min": float(alle[:, 2].min()),
        "z_max": float(alle[:, 2].max()),
        "flaeche": _flaeche(stapel),
    }


def _flaeche(stapel: list[Schnitt]) -> float:
    """Grundrissfläche in mm², aus den Sehnen über die Spannweite integriert."""
    if len(stapel) < 2:
        return 0.0
    y = np.array([s.y for s in stapel])
    c = np.array([s.sehne for s in stapel])
    return float(np.trapezoid(c, y)) if hasattr(np, "trapezoid") else float(np.trapz(c, y))
