"""
Kanalwirkung am Boden — der Teil des Bodeneffekts, den die Traglinie nicht kennt.

Die Traglinie (traglinie.py) spiegelt ihre Hufeisenwirbel am Boden. Das
erfasst, wie der Boden den Abwind verändert. Es erfasst NICHT, dass die Luft
zwischen Flügelunterseite und Boden beschleunigt wird. Genau dieser Kanal
macht aber den Großteil des Bodeneffekts eines Frontflügels aus: Zerihan &
Zhang messen am Tyrrell-026-Flügel deutlich mehr Abtrieb, sobald der Abstand
unter 20 % der Sehne fällt.

**Wie der Faktor entsteht:**

1. Das 2D-Panelverfahren rechnet das Profil (oder die ganze Kaskade) frei
   und mit Bodenspiegelung. Das Verhältnis ist der Bodengewinn im Schnitt.
2. Ein Teil davon steckt schon in der Traglinie: Ihr gebundener Wirbel auf
   der Viertelsehne hat ein Spiegelbild, das auf den Kontrollpunkt auf der
   Dreiviertelsehne wirkt. Für diesen einen Wirbel gilt geschlossen

       Verhältnis = 1 + c² / (16 · h²),   h = Höhe der Viertelsehne.

   Dieser Anteil wird herausgeteilt, sonst wäre er doppelt gezählt.
3. Übrig bleibt die Kanalwirkung. Sie wirkt als Faktor auf den Profilbeiwert.

**Grenzen, und wie mit ihnen umgegangen wird:**

* Reibungsfrei gerechnet wächst der Gewinn bei kleinem Abstand ohne Ende
  (gemessen am E423: Faktor 4,7 bei h/c = 0,1). In Wirklichkeit löst die
  Grenzschicht ab. Deshalb wird das Panelverfahren nur bis zu
  `HOEHE_VERLAESSLICH` Sehnen benutzt; darunter bleibt der Faktor auf diesem
  Wert stehen. Das ist bewusst VORSICHTIG - der wahre Gewinn zwischen 0,4 und
  0,15 Sehnen ist größer.
* Unterhalb des Abtriebsmaximums bricht der Abtrieb ein. Das Maximum liegt
  laut Literatur beim Einzelflügel um h/c = 0,1 (Zerihan & Zhang 2000:
  Einbruch unter 10 % Sehne), bei der Kaskade früher, um h/c = 0,15
  (Zhang & Zerihan 2003, stationär 0,153 bei Zhou et al. 2026). Darunter
  wird der Faktor linear bis auf `REST_AM_BODEN` zurückgenommen. Wie tief der
  Einbruch wirklich ist, hängt am Flapwinkel - das ist eine Annahme und gehört
  mit CFD abgeglichen.

Quellen:
  Zerihan, Zhang: Aerodynamics of a Single Element Wing in Ground Effect.
    J. Aircraft 37(6), 2000.
  Zhang, Zerihan: Aerodynamics of a Double-Element Wing in Ground Effect.
    AIAA Journal 41(6), 2003.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import panel

# Bis hierhin, in Sehnen gemessen, ist die reibungsfreie Spiegelung brauchbar.
HOEHE_VERLAESSLICH = panel.BODENABSTAND_MIN
# Lage des Abtriebsmaximums, in Sehnen - siehe Modul-Docstring.
HOEHE_MAXIMUM_EINZEL = 0.10
HOEHE_MAXIMUM_KASKADE = 0.15
# Was direkt am Boden vom Faktor übrig bleibt. Annahme, mit CFD abgleichen.
REST_AM_BODEN = 0.5


@dataclass
class Bodenwirkung:
    """Der Kanalfaktor und woraus er entstanden ist."""

    faktor: float               # wirkt auf den Profilbeiwert
    hoehe_sehnen: float         # tiefster Punkt über Boden / Sehne
    gerechnet_bei: float        # h/c, bei dem das Panelverfahren lief
    panel_verhaeltnis: float    # Bodengewinn im Schnitt, reibungsfrei
    wirbel_verhaeltnis: float   # davon schon in der Traglinie
    maximum_bei: float          # h/c des Abtriebsmaximums laut Literatur

    @property
    def eingefroren(self) -> bool:
        return self.hoehe_sehnen < self.gerechnet_bei - 1e-9

    @property
    def im_abfall(self) -> bool:
        return self.hoehe_sehnen < self.maximum_bei

    @property
    def text(self) -> str:
        teile = [f"Kanalwirkung ×{self.faktor:.2f} bei h/c = "
                 f"{self.hoehe_sehnen:.2f}"]
        if self.im_abfall:
            teile.append(f"unter dem Abtriebsmaximum (h/c ≈ "
                         f"{self.maximum_bei:.2f}) - dort bricht der "
                         f"Abtrieb ein, der Wert ist unsicher")
        elif self.eingefroren:
            teile.append(f"unter h/c = {self.gerechnet_bei:.1f} vorsichtig "
                         f"festgehalten, der wahre Gewinn ist größer")
        return "; ".join(teile) + "."


def kanalfaktor(konturen, mehrelementig: bool | None = None) -> Bodenwirkung:
    """Kanalfaktor für einen Schnitt aus einem oder mehreren Elementen.

    `konturen` sind die (x, z)-Punkte der Elemente in mm, mit z über Boden -
    das Hauptelement zuerst, so wie geometrie.kaskade.platziere sie liefert.
    """
    konturen = [np.asarray(k, dtype=float)[:, :2] for k in konturen]
    if mehrelementig is None:
        mehrelementig = len(konturen) > 1
    maximum_bei = HOEHE_MAXIMUM_KASKADE if mehrelementig else HOEHE_MAXIMUM_EINZEL

    alle = np.vstack(konturen)
    sehne = float(alle[:, 0].max() - alle[:, 0].min())
    z_min = float(alle[:, 1].min())
    hoehe = max(z_min, 0.0) / max(sehne, 1e-9)
    gerechnet = max(hoehe, HOEHE_VERLAESSLICH)
    schub = gerechnet * sehne - z_min

    frei = panel.loese([panel.Koerper(punkte=k) for k in konturen],
                       alpha_grad=0.0, mit_boden=False,
                       bezugssehne=sehne).cl_gesamt
    am_boden = panel.loese(
        [panel.Koerper(punkte=k + np.array([0.0, schub])) for k in konturen],
        alpha_grad=0.0, mit_boden=True, bodenhoehe=0.0,
        bezugssehne=sehne).cl_gesamt
    panel_verh = am_boden / frei if abs(frei) > 1e-6 else 1.0

    # Viertelsehne wie in der Traglinie: von der Nase des Hauptelements zur
    # Hinterkante des letzten Elements.
    erstes = konturen[0]
    nase = erstes[int(np.argmax(np.linalg.norm(erstes - erstes[0], axis=1)))]
    hinten = konturen[-1][0]
    z_viertel = nase[1] + 0.25 * (hinten[1] - nase[1]) + schub
    wirbel_verh = 1.0 + sehne ** 2 / (16.0 * max(z_viertel, 1e-6) ** 2)

    faktor = max(panel_verh / wirbel_verh, 1.0)
    if hoehe < maximum_bei:
        faktor *= REST_AM_BODEN + (1.0 - REST_AM_BODEN) * hoehe / maximum_bei

    return Bodenwirkung(faktor=float(faktor), hoehe_sehnen=float(hoehe),
                        gerechnet_bei=float(gerechnet),
                        panel_verhaeltnis=float(panel_verh),
                        wirbel_verhaeltnis=float(wirbel_verh),
                        maximum_bei=maximum_bei)


def fluegel(stapel, profil, geschwindigkeit: float = 15.0,
            endplatte_mm: float = 0.0, kanal: bool = True,
            abgleich: float = 1.0, **kwargs):
    """Abtrieb eines einfachen Flügels mit Endplatten und Kanalwirkung.

    Der Kanalfaktor kommt vom TIEFSTEN Schnitt - dort ist der Kanal am
    engsten, und ein Flügel, der nach außen ansteigt, soll nicht mit dem
    Abstand seiner Spitze gerechnet werden.
    """
    from . import traglinie

    wirkung = None
    faktor = float(abgleich)
    if kanal:
        tiefster = min(stapel, key=lambda s: s.hoehe_min)
        wirkung = kanalfaktor([tiefster.punkte[:, [0, 2]]], False)
        faktor *= wirkung.faktor
    kraefte = traglinie.rechne(stapel, profil, geschwindigkeit,
                               endplatte_mm=endplatte_mm,
                               beiwertfaktor=faktor, **kwargs)
    return kraefte, wirkung


def kennlinie(stapel, profil, hoehen_mm, geschwindigkeit: float = 15.0,
              endplatte_mm: float = 0.0, kanal: bool = True,
              abgleich: float = 1.0, **kwargs):
    """Abtrieb über dem Bodenabstand, mit Kanalwirkung je Höhe."""
    from dataclasses import replace

    from . import traglinie

    bezug = traglinie._wurzelhoehe(stapel)
    ergebnisse = []
    for h in hoehen_mm:
        versatz = np.array([0.0, 0.0, float(h) - bezug])
        versetzt = [replace(s, punkte=s.punkte + versatz) for s in stapel]
        kraefte, wirkung = fluegel(versetzt, profil, geschwindigkeit,
                                   endplatte_mm, kanal, abgleich, **kwargs)
        ergebnisse.append((float(h), kraefte, wirkung))
    return ergebnisse
