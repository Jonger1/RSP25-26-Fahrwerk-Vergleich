"""
Endplatte und Footplate als Geometrie.

Bis hierher war die Endplatte im Werkzeug eine einzige Zahl: eine Hoehe in mm,
aus der `traglinie.endplattenfaktor` nach Hoerner eine wirksame Streckung
macht. Fuer die Abtriebsabschaetzung reicht das. Fuer alles andere nicht -
denn die Endplatte ist genau das Bauteil, das die Regeln am haertesten
treffen:

* **T 8.2.2** begrenzt die Breite. Die Endplatte ist der aeusserste Punkt des
  ganzen Fluegels, und ihre Dicke traegt nach aussen auf.
* **T 2.1.3** haelt die Seitenansicht der Raeder frei. Die Endplatte steht
  genau dort, wo diese Zone liegt - lateral zwischen Innen- und Aussenebene
  des Rad/Reifen-Verbunds.
* **T 2.1.4** (Entwurf 2027) verlangt bodennah einen freien Kanal. Die
  Footplate liegt flach und tief und ist der erste Kandidat, ihn zuzusetzen.

Diese drei Pruefungen gibt es in `regeln/pruefung.py` laengst. Sie haben die
Endplatte nur nie gesehen, weil sie nicht Teil des Schnittstapels war. Genau
das loest dieses Modul: Es liefert die Platte als gewoehnliche `Schnitt`-
Objekte. Damit greift der gesamte bestehende Validator ohne eine einzige neue
Zeile Regellogik - und zwar auch ueber den Fahrzustands-Envelope, denn der
steckt schon in `pruefe_fluegel`.

**Aufbau der Platte.** Zwei Schnitte, innen und aussen, im Abstand der Dicke.
Jeder Schnitt ist ein geschlossener Umriss in der x-z-Ebene:

        z
        ^      +-------------------+   <- ueberstand_oben
        |      |   ~~~ Kaskade ~~~ |
        |      |                   |   <- ueberstand_vorne / _hinten
        |  +---+                   |
        |  |            Footplate  |   <- nach INNEN, bis footplate.hoehe
        +--+-------------------+---+---> x
        Boden z = 0

Die Footplate ist am Innenschnitt eine Verbreiterung nach innen, am
Aussenschnitt nicht vorhanden - sie haengt an der Innenseite der Platte.

**Bewusste Vereinfachungen**, die in jeden Report gehoeren:

1. Der Umriss ist ein Rechteck um die Kaskadenhuelle, keine geschwungene
   Kontur. Fuer Bauraum und Regelpruefung ist die Huellform die strengere und
   damit richtige Naeherung; wer die Platte schoen zeichnen will, tut das in
   Creo auf dieser Grundlage.
2. Die Footplate ist ein waagerechter Streifen, keine Aufkantung mit Radius.
3. Nichts davon geht in die Abtriebsrechnung ein - dort wirkt weiterhin nur
   die Hoehe nach Hoerner.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .spannweite import Schnitt

# Feinheit des Umrisses. Jede Kante wird in so viele Punkte zerlegt, damit die
# Regelpruefung nicht nur die Ecken sieht: Eine Keep-out-Zone kann mitten
# durch eine Kante schneiden, ohne eine Ecke zu erwischen.
PUNKTE_JE_KANTE = 12


@dataclass
class Endplattenmasse:
    """Die Abmessungen der fertigen Platte, in mm beziehungsweise mm^2.

    Was der Anwender sehen will, ohne im Export nachzumessen - und was der
    Abtriebsrechnung als Hoehe dient.
    """

    laenge: float            # in x
    hoehe: float             # in z, ueber Grund gemessen
    z_unten: float
    z_oben: float
    x_vorne: float
    x_hinten: float
    y_innen: float
    y_aussen: float
    flaeche: float           # Seitenansicht, mm^2
    footplate_breite: float  # 0.0, wenn keine

    @property
    def hoehe_fuer_hoerner(self) -> float:
        """Die Hoehe, mit der die Traglinie rechnet.

        Hoerner setzt die Endplattenhoehe ins Verhaeltnis zur Spannweite. Was
        zaehlt, ist die Erstreckung quer zur Anstroemung, also die Hoehe der
        Platte - nicht ihre Laenge und nicht ihre Flaeche.
        """
        return self.hoehe


def _kante(a: np.ndarray, b: np.ndarray, n: int = PUNKTE_JE_KANTE) -> np.ndarray:
    """Punkte entlang einer Strecke, Anfang inklusive, Ende exklusive."""
    t = np.linspace(0.0, 1.0, n, endpoint=False).reshape(-1, 1)
    return a + t * (b - a)


def _umlauf(ecken: list[tuple[float, float]]) -> np.ndarray:
    """Macht aus Ecken einen geschlossenen Streckenzug mit Zwischenpunkten."""
    p = [np.array(e, dtype=float) for e in ecken]
    teile = [_kante(p[i], p[(i + 1) % len(p)]) for i in range(len(p))]
    return np.vstack(teile + [p[0].reshape(1, 2)])


def huelle(stapel_je_element: list[list[Schnitt]],
           y_aussen: float | None = None,
           fenster: float = 30.0) -> dict[str, float]:
    """Die Huellwerte der Kaskade an ihrer AEUSSERSTEN Station.

    Warum nicht ueber den ganzen Fluegel: Ein verjuengter Fluegel ist innen
    deutlich tiefer als aussen. Eine Endplatte, die um die Wurzelsehne herum
    gebaut wird, waere aussen sinnlos gross - und wuerde die Breiten- und
    Keep-out-Pruefung mit einem Bauteil belasten, das so niemand baut.

    `fenster` ist die Breite des Bands um die aeusserste Station, aus dem die
    Werte genommen werden. Ein einzelner Schnitt genuegt nicht: Die Stationen
    der Flaps liegen nicht auf denselben y-Werten wie die des Hauptelements.
    """
    alle = [s for stapel in stapel_je_element for s in stapel]
    if not alle:
        raise ValueError("Kein Schnitt vorhanden - ohne Fluegel keine Endplatte.")

    if y_aussen is None:
        y_aussen = max(float(s.punkte[:, 1].max()) for s in alle)

    punkte = np.vstack([s.punkte for s in alle])
    im_band = punkte[punkte[:, 1] >= y_aussen - fenster]
    if len(im_band) == 0:                      # kann bei sehr schmalem Band passieren
        im_band = punkte

    return {
        "x_min": float(im_band[:, 0].min()),
        "x_max": float(im_band[:, 0].max()),
        "z_min": float(im_band[:, 2].min()),
        "z_max": float(im_band[:, 2].max()),
        "y_aussen": float(y_aussen),
    }


def masse(stapel_je_element: list[list[Schnitt]], vorgabe) -> Endplattenmasse:
    """Rechnet die Abmessungen der Platte aus Kaskade und Ueberstaenden."""
    h = huelle(stapel_je_element)

    x_vorne = h["x_min"] - vorgabe.ueberstand_vorne
    x_hinten = h["x_max"] + vorgabe.ueberstand_hinten
    z_oben = h["z_max"] + vorgabe.ueberstand_oben

    # Der Boden ist die harte Grenze. Eine Platte, die unter z = 0 gefuehrt
    # wird, existiert nicht - sie wuerde schleifen. Lieber hier klemmen als
    # spaeter eine Bodenfreiheitsverletzung melden, die aus einer
    # Eingabe stammt, die so niemand gemeint hat.
    z_unten = max(0.0, h["z_min"] - vorgabe.ueberstand_unten)

    y_innen = h["y_aussen"]
    y_aussen = y_innen + vorgabe.dicke

    fuss = vorgabe.footplate
    breite = float(fuss.breite) if fuss is not None else 0.0

    return Endplattenmasse(
        laenge=x_hinten - x_vorne,
        hoehe=z_oben - z_unten,
        z_unten=z_unten, z_oben=z_oben,
        x_vorne=x_vorne, x_hinten=x_hinten,
        y_innen=y_innen, y_aussen=y_aussen,
        flaeche=(x_hinten - x_vorne) * (z_oben - z_unten),
        footplate_breite=breite,
    )


def schnitte(stapel_je_element: list[list[Schnitt]], vorgabe) -> list[Schnitt]:
    """Die Endplatte als Schnittstapel - fuer Regelpruefung und Export.

    Zwei Schnitte: Innenseite und Aussenseite. Dazwischen liegt die Dicke.
    Kommt eine Footplate dazu, traegt der INNERE Schnitt sie, weil sie an der
    Innenseite der Platte haengt.

    Das Ergebnis passt ohne Umweg in `regeln.pruefe_fluegel` und in
    `formate.export` - es sind gewoehnliche Schnitte wie die des Fluegels.
    """
    m = masse(stapel_je_element, vorgabe)
    fuss = vorgabe.footplate
    hat_fuss = fuss is not None and fuss.breite > 0.0 and fuss.hoehe > 0.0

    # Der Umriss der Platte in der x-z-Ebene, gegen den Uhrzeigersinn.
    platte = [
        (m.x_vorne, m.z_unten),
        (m.x_hinten, m.z_unten),
        (m.x_hinten, m.z_oben),
        (m.x_vorne, m.z_oben),
    ]

    innen = _umlauf(platte)
    aussen = _umlauf(platte)

    ergebnis = [
        Schnitt(y=m.y_innen, sehne=m.laenge, anstellwinkel=0.0,
                punkte=np.column_stack([innen[:, 0],
                                        np.full(len(innen), m.y_innen),
                                        innen[:, 1]])),
        Schnitt(y=m.y_aussen, sehne=m.laenge, anstellwinkel=0.0,
                punkte=np.column_stack([aussen[:, 0],
                                        np.full(len(aussen), m.y_aussen),
                                        aussen[:, 1]])),
    ]

    if hat_fuss:
        # Die Footplate liegt waagerecht: ein Rechteck in der x-y-Ebene, von
        # der Plattenwurzel `breite` weit nach innen. Sie reicht von der
        # Unterkante der Platte bis `hoehe` ueber Grund - zwei Umrisse, also
        # ein Quader. Die Hoehe wird auf die Platte geklemmt: Eine Footplate,
        # die oben aus der Endplatte herausragt oder unter ihr in der Luft
        # haengt, waere eine Geometrie, die niemand gebaut hat.
        z_oberkante = max(m.z_unten, min(float(fuss.hoehe), m.z_oben))
        y_innen_fuss = m.y_innen - float(fuss.breite)
        umriss = _umlauf([
            (m.x_vorne, y_innen_fuss),
            (m.x_hinten, y_innen_fuss),
            (m.x_hinten, m.y_innen),
            (m.x_vorne, m.y_innen),
        ])

        for z in {m.z_unten, z_oberkante}:
            ergebnis.append(Schnitt(
                # Die Footplate liegt quer, ein einzelnes y beschreibt sie
                # nicht. Eingetragen wird ihre innerste Kante - das ist der
                # Wert, der fuer die Breitenpruefung zaehlt.
                y=y_innen_fuss, sehne=m.laenge, anstellwinkel=0.0,
                punkte=np.column_stack([umriss[:, 0], umriss[:, 1],
                                        np.full(len(umriss), z)])))

    return ergebnis


def hoehe_fuer_abtrieb(stapel_je_element: list[list[Schnitt]],
                       vorgabe) -> float:
    """Die Endplattenhoehe, mit der die Traglinie rechnen soll.

    Damit muss niemand die Hoehe zweimal pflegen: Sie faellt aus der
    Geometrie ab. Wer frueher 'Endplattenhoehe 150 mm' eingetippt und danach
    die Sehne geaendert hat, rechnete ab dann mit einer Platte, die es so
    nicht mehr gab.
    """
    return masse(stapel_je_element, vorgabe).hoehe_fuer_hoerner
