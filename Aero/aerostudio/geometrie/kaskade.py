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

    # Startbereich: von knapp unter der Hinterkante des Vorgaengers bis
    # deutlich darunter. Ein Abtriebsfluegel staffelt nach unten.
    oben = vorgaenger.hinterkante[1]
    unten = oben - 0.6 * hauptsehne

    # Erst grob abtasten, um ein Intervall zu finden, in dem der Abstand die
    # Vorgabe kreuzt. Direkt halbieren geht nicht: Ganz oben ueberschneiden
    # sich die Elemente, dort ist der Abstand null und nicht monoton.
    letzte = None
    intervall = None
    for z in np.linspace(oben, unten, 25):
        kontur = bei_hoehe(z)
        if schneiden_sich(vorgaenger.punkte, kontur):
            letzte = (z, -1.0)
            continue
        abstand = mindestabstand(vorgaenger.punkte, kontur)
        if letzte is not None and (letzte[1] - spalt_mm) * (abstand - spalt_mm) <= 0:
            intervall = (letzte[0], z)
            break
        letzte = (z, abstand)

    if intervall is None:
        # Der gewuenschte Spalt ist in diesem Bereich nicht erreichbar. Statt
        # zu scheitern wird die tiefste ueberschneidungsfreie Lage genommen
        # und der TATSAECHLICHE Spalt gemeldet - der Anwender sieht dann, dass
        # die Vorgabe nicht eingehalten werden konnte.
        z = oben - 0.1 * hauptsehne
        kontur = bei_hoehe(z)
    else:
        a, b = intervall
        for _ in range(30):
            m = 0.5 * (a + b)
            kontur = bei_hoehe(m)
            if schneiden_sich(vorgaenger.punkte, kontur):
                abstand = -1.0
            else:
                abstand = mindestabstand(vorgaenger.punkte, kontur)
            if abs(abstand - spalt_mm) < 1e-4 * hauptsehne:
                break
            if abstand < spalt_mm:
                a = m
            else:
                b = m
        kontur = bei_hoehe(0.5 * (a + b))

    gemessen = (mindestabstand(vorgaenger.punkte, kontur)
                if not schneiden_sich(vorgaenger.punkte, kontur) else 0.0)
    nase = kontur[int(np.argmax(np.linalg.norm(kontur - kontur[0], axis=1)))]

    return Elementlage(
        profil=vorgabe.profil, sehne=sehne, winkel=winkel, punkte=kontur,
        spalt=gemessen,
        ueberlappung=float(vorgaenger.hinterkante[0] - nase[0]),
        name=vorgabe.name or f"Flap {nummer}")


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
