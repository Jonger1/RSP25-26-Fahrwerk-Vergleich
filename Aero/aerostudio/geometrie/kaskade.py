"""
Mehrere Profile zu einer Kaskade anordnen.

Ein Formula-Student-Frontflügel ist fast nie ein einzelnes Profil. Er besteht
aus einem Hauptelement und ein bis drei Flaps dahinter, und der Gewinn kommt
nicht daraus, dass mehr Fläche da ist, sondern aus dem SPALT: Die Luft
beschleunigt zwischen Hauptelement und Flap hindurch, legt sich dem Flap
wieder an und hält die Strömung auch bei Winkeln anliegend, bei denen ein
einzelnes Profil längst abgerissen wäre.

Deshalb steht ein Flap nicht an absoluten Koordinaten, sondern RELATIV zum
Vorgänger, über zwei Maße:

* **Spalt (gap)** — der kürzeste Abstand zwischen der Nase des Flaps und der
  Oberfläche des Vorgängers. Übliche Werte im Formula Student: 1 bis 2 % der
  Sehne des Hauptelements. Zu eng, und die Grenzschichten der beiden
  Elemente wachsen zusammen; zu weit, und die Düsenwirkung geht verloren.

* **Überlappung (overlap)** — wie weit die Nase des Flaps VOR der Hinterkante
  des Vorgängers steht, in Längsrichtung gemessen. Positiv heißt: Der Flap
  schiebt sich unter den Vorgänger. Üblich sind 1 bis 4 %.

Warum relativ und nicht absolut: Beide Maße sind das, was ein Aerodynamiker
einstellt und was in jeder Veröffentlichung steht. Absolute Koordinaten
müsste man bei jeder Sehnenänderung neu ausrechnen, und ein Zahlendreher
fällt dort nicht auf.

Die Höhe des Flaps wird NICHT vorgegeben, sondern aus dem gewünschten Spalt
gesucht. Das ist der Kern dieses Moduls: Die Längslage folgt aus der
Überlappung, die Höhe aus dem Spalt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .profil import Profil


@dataclass
class Elementlage:
    """Ein Element der Kaskade, fertig angeordnet. Längen in mm."""

    profil: Profil
    sehne: float
    winkel: float               # absolut, nicht relativ zum Vorgänger
    punkte: np.ndarray          # Nx2, an seiner Stelle im Verbund
    spalt: float = 0.0          # gemessen, nicht gewünscht
    ueberlappung: float = 0.0
    name: str = ""

    @property
    def nase(self) -> np.ndarray:
        hinten = self.punkte[0]
        return self.punkte[int(np.argmax(np.linalg.norm(self.punkte - hinten,
                                                        axis=1)))]

    @property
    def hinterkante(self) -> np.ndarray:
        return self.punkte[0]


@dataclass
class Kaskadenvorgabe:
    """Wie ein Element hinter seinem Vorgänger sitzen soll."""

    profil: Profil
    sehne_faktor: float = 0.35      # bezogen auf die Sehne des Hauptelements
    winkel_relativ: float = -20.0   # zusätzlich zum Winkel des Vorgängers
    spalt: float = 0.015            # Anteil der Hauptsehne
    ueberlappung: float = 0.02      # Anteil der Hauptsehne
    name: str = ""


def _punkt_zu_strecke(punkte: np.ndarray, a: np.ndarray,
                      b: np.ndarray) -> np.ndarray:
    """Abstand jedes Punktes zu den Strecken a[i] -> b[i], paarweise über i."""
    ab = b - a
    laenge2 = np.sum(ab * ab, axis=1)
    laenge2 = np.where(laenge2 > 0, laenge2, 1.0)
    # (P, S) - jeder Punkt gegen jede Strecke
    diff = punkte[:, None, :] - a[None, :, :]
    t = np.clip(np.sum(diff * ab[None, :, :], axis=2) / laenge2[None, :], 0.0, 1.0)
    fuss = a[None, :, :] + t[:, :, None] * ab[None, :, :]
    return np.linalg.norm(punkte[:, None, :] - fuss, axis=2)


def mindestabstand(a: np.ndarray, b: np.ndarray) -> float:
    """Kürzester Abstand zwischen zwei geschlossenen Streckenzügen.

    Punkt-zu-STRECKE in beide Richtungen, nicht Punkt-zu-Punkt. Bei
    Punkt-zu-Punkt hängt das Ergebnis an der Punktdichte: Zwei Kurven, die
    sich fast berühren, melden dann je nach Auflösung einen Abstand, den es
    nicht gibt.
    """
    hin = _punkt_zu_strecke(a, b[:-1], b[1:]).min()
    zurueck = _punkt_zu_strecke(b, a[:-1], a[1:]).min()
    return float(min(hin, zurueck))


def schneiden_sich(a: np.ndarray, b: np.ndarray, toleranz: float = 1e-9) -> bool:
    """Überschneiden sich zwei Elemente? Dann ist die Anordnung unbrauchbar."""
    from matplotlib.path import Path as MPath

    return bool(MPath(a).contains_points(b).any()
                or MPath(b).contains_points(a).any())


def platziere(haupt: Profil, sehne: float, winkel: float,
              flaps: list[Kaskadenvorgabe] | None = None,
              lage: tuple[float, float] = (0.0, 0.0),
              punkte: int = 120) -> list[Elementlage]:
    """Ordnet Hauptelement und Flaps zu einer Kaskade an.

    Die Längslage jedes Flaps folgt aus seiner Überlappung, die Höhe wird so
    gesucht, dass der gewünschte Spalt herauskommt.

    Warum gesucht und nicht gerechnet: Der Spalt ist der kürzeste Abstand
    zwischen zwei gekrümmten Konturen. Wo dieser kürzeste Abstand liegt,
    hängt von Sehne, Winkel und Profilform ab und wandert beim Verschieben.
    Eine geschlossene Formel dafür gibt es nicht; eine Intervallhalbierung
    über die Höhe braucht rund zwanzig Auswertungen und ist in
    Millisekunden fertig.
    """
    versatz = np.asarray(lage, dtype=float)
    elemente = [Elementlage(
        profil=haupt, sehne=sehne, winkel=winkel,
        punkte=haupt.repanelisiert(punkte).angestellt(winkel, sehne) + versatz,
        name="Hauptelement")]

    for i, vorgabe in enumerate(flaps or [], start=1):
        elemente.append(_setze_flap(elemente[-1], vorgabe, sehne, punkte,
                                    nummer=i))
    return elemente


def _setze_flap(vorgaenger: Elementlage, vorgabe: Kaskadenvorgabe,
                hauptsehne: float, punkte: int, nummer: int) -> Elementlage:
    """Ein Flap hinter seinem Vorgänger, Höhe aus dem Spalt gesucht."""
    sehne = hauptsehne * vorgabe.sehne_faktor
    winkel = vorgaenger.winkel + vorgabe.winkel_relativ
    spalt_mm = hauptsehne * vorgabe.spalt
    ueberlappung_mm = hauptsehne * vorgabe.ueberlappung

    roh = vorgabe.profil.repanelisiert(punkte).angestellt(winkel, sehne)
    # Nase des rohen Flaps, um sie gezielt setzen zu können.
    nase_roh = roh[int(np.argmax(np.linalg.norm(roh - roh[0], axis=1)))]
    ziel_x = vorgaenger.hinterkante[0] - ueberlappung_mm

    def bei_hoehe(z: float) -> np.ndarray:
        return roh + np.array([ziel_x - nase_roh[0], z - nase_roh[1]])

    # Suchbereich: von der Hinterkante des Vorgaengers nach OBEN.
    #
    # Das war zuerst falsch herum, und der Fehler ist grundsaetzlich: Bei
    # einem ABTRIEBSfluegel ist die UNTERSEITE die Saugseite. Der Spalt muss
    # energiereiche Luft von der Druckseite - also von OBEN - auf die
    # Saugseite des Flaps leiten. Dafuer muss die Flapnase UEBER der
    # Hinterkante des Vorgaengers stehen, damit ein konvergenter Kanal von
    # dessen Oberseite auf die Flapunterseite entsteht.
    #
    # Nach unten gesucht ergab die Anordnung eines FLUGZEUGfluegels mit
    # Landeklappe - dort stimmt es, weil dort die Oberseite die Saugseite
    # ist. Gemessen am E423: Die Flapnase lag 7,9 mm UNTER der Hinterkante,
    # und die engste Stelle sass an der Unterseite des Hauptelements, also
    # ausgerechnet auf dessen Saugseite.
    # Die Untergrenze ist die HINTERKANTE selbst, nicht tiefer. Beim
    # Abtriebsprofil ist sie der hoechste Punkt des Vorgaengers; die Flapnase
    # steht damit ueber dem ganzen Element.
    #
    # Ein Versuch mit etwas Spielraum nach unten ging schief: Unterhalb der
    # Durchdringung gibt es einen ZWEITEN freien Bereich - dort haengt der
    # Flap schlicht unter der Hinterkante. Die Halbierung auf "schneidet es
    # sich" setzt aber voraus, dass weiter oben immer frei ist, und landete
    # prompt im unteren Bereich: Die Nase sass 12,5 mm UNTER der
    # Hinterkante, also wieder in der Flugzeuganordnung.
    unten = vorgaenger.hinterkante[1]
    oben = vorgaenger.hinterkante[1] + 0.6 * hauptsehne

    # ZWEI Schritte, und die Reihenfolge ist wesentlich.
    #
    # Der Abstand ist NICHT stetig ueber die ganze Hoehe: Ab einer gewissen
    # Tiefe schneiden sich die Elemente, und dort gibt es keinen Abstand mehr.
    # Gemessen beim E423 mit E58-Flap: einen Schritt vor der Ueberschneidung
    # noch 5,2 mm, im naechsten Schritt Durchdringung. Eine Halbierung ueber
    # diesen Sprung hinweg konvergiert gegen die Sprungstelle und nicht gegen
    # den gesuchten Spalt - sie lieferte fuer 1,2 % und 1,5 % Vorgabe beide
    # Male 2,67 %.
    #
    # Deshalb wird zuerst die TIEFSTE ueberschneidungsfreie Lage gesucht.
    # Darueber ist der Abstand stetig und waechst mit der Hoehe; erst dort
    # wird auf den Spalt halbiert.
    tiefste_freie = _tiefste_freie_lage(vorgaenger.punkte, bei_hoehe, unten, oben)

    if tiefste_freie is None:
        # Ueberall Durchdringung - die Vorgabe ist geometrisch unmoeglich.
        # Statt zu scheitern wird die oberste Lage genommen und der
        # tatsaechliche Spalt gemeldet.
        kontur = bei_hoehe(oben)
    else:
        kleinster = mindestabstand(vorgaenger.punkte, bei_hoehe(tiefste_freie))
        if kleinster >= spalt_mm:
            # Enger geht es mit dieser Ueberlappung nicht. Der gemeldete Spalt
            # sagt dem Anwender, was herausgekommen ist.
            kontur = bei_hoehe(tiefste_freie)
        else:
            a_z, b_z = tiefste_freie, oben
            for _ in range(40):
                m = 0.5 * (a_z + b_z)
                d = mindestabstand(vorgaenger.punkte, bei_hoehe(m))
                if abs(d - spalt_mm) < 1e-4 * hauptsehne:
                    break
                if d < spalt_mm:
                    a_z = m
                else:
                    b_z = m
            kontur = bei_hoehe(0.5 * (a_z + b_z))

    gemessen = (mindestabstand(vorgaenger.punkte, kontur)
                if not schneiden_sich(vorgaenger.punkte, kontur) else 0.0)
    nase = kontur[int(np.argmax(np.linalg.norm(kontur - kontur[0], axis=1)))]

    return Elementlage(
        profil=vorgabe.profil, sehne=sehne, winkel=winkel, punkte=kontur,
        spalt=gemessen,
        ueberlappung=float(vorgaenger.hinterkante[0] - nase[0]),
        name=vorgabe.name or f"Flap {nummer}")


def _tiefste_freie_lage(vorgaenger: np.ndarray, bei_hoehe, unten: float,
                        oben: float, schritte: int = 40) -> float | None:
    """Die tiefste Hoehe, bei der sich die Elemente noch nicht durchdringen.

    Ueber eine Halbierung auf der Ja/Nein-Frage "schneiden sie sich", nicht
    auf dem Abstand: Die Frage ist monoton in der Hoehe - weiter oben ist
    immer frei -, der Abstand dagegen springt an der Grenze.
    """
    if schneiden_sich(vorgaenger, bei_hoehe(oben)):
        return None
    if not schneiden_sich(vorgaenger, bei_hoehe(unten)):
        return unten

    frei, belegt = oben, unten
    for _ in range(schritte):
        mitte = 0.5 * (frei + belegt)
        if schneiden_sich(vorgaenger, bei_hoehe(mitte)):
            belegt = mitte
        else:
            frei = mitte
    return frei


def gesamtsehne(elemente: list[Elementlage]) -> float:
    """Die Sehne der ganzen Kaskade - Nase des ersten bis Hinterkante des letzten.

    Das ist die Länge, die das Reglement begrenzt, und der Bezug, auf den die
    Beiwerte einer Kaskade üblicherweise bezogen werden.
    """
    alle = np.vstack([e.punkte for e in elemente])
    return float(alle[:, 0].max() - alle[:, 0].min())


def huellwerte(elemente: list[Elementlage]) -> dict[str, float]:
    alle = np.vstack([e.punkte for e in elemente])
    return {"x_min": float(alle[:, 0].min()), "x_max": float(alle[:, 0].max()),
            "z_min": float(alle[:, 1].min()), "z_max": float(alle[:, 1].max()),
            "gesamtsehne": gesamtsehne(elemente)}
