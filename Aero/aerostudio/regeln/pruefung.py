"""
Regelprüfung der Flügelgeometrie.

Warum das hier und nicht im Kopf des Aeroverantwortlichen: Die Grenzen des
Reglements sind fast alle GEOMETRISCH und beziehen sich auf absolute Lagen am
Fahrzeug - Höhe über Boden, Abstand zur Radvorderkante, Breite zur Radebene.
Ein Flügel, der als Profilschnitt gut aussieht, kann in der Einbaulage
trotzdem drei Regeln reißen. Das fällt beim Scrutineering auf, nicht vorher.

Zwei Dinge machen die Prüfung unbequem, und beide sind hier eingebaut:

1. T 8.2.4 sagt, die Grenzen gelten "with any suspension setup, with or
   without a driver". Die statische Lage genügt also nicht. Geprüft wird
   deshalb über einen Fahrzustands-Envelope: höchste Lage für die
   Höhengrenzen nach oben, tiefste Lage beim Bremsen für die Bodenfreiheit.

2. Es gibt zwei Regelstände, die sich widersprechen. 2026 gilt, 2027 ist
   Entwurf. Der Prüfer läuft über beide und meldet getrennt - so wird
   sichtbar, welcher Entwurf heute zulässig wäre, nächste Saison aber nicht
   mehr. Genau das ist der Punkt, an dem ein Flügel sonst ein Jahr später im
   Müll landet.

Koordinatensystem durchgehend: Ursprung Vorderachsmitte auf der Bodenebene,
x nach hinten, y nach rechts, z nach oben. z = 0 ist der Boden, damit sind
alle Höhengrenzen des Reglements direkt ablesbar.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import yaml

ORDNER = Path(__file__).parent
VEHICLE_REF = ORDNER.parent / "spec" / "vehicle_ref.yaml"


# ------------------------------------------------------------- Regelsatz

@dataclass
class Regelsatz:
    """Ein geladener Regelstand."""

    version: str
    verbindlich: bool
    quelle: str
    daten: dict

    def __getitem__(self, schluessel: str):
        return self.daten.get(schluessel)

    @property
    def entwurf(self) -> bool:
        return not self.verbindlich


_DATEIEN = {
    "2026": "rules_2026.yaml",
    "2027": "rules_2027_draft.yaml",
}


def lade(stand: str = "2026") -> Regelsatz:
    """Lädt einen Regelstand. `stand` ist "2026" oder "2027"."""
    if stand not in _DATEIEN:
        raise ValueError(f"Unbekannter Regelstand {stand!r}. "
                         f"Bekannt: {', '.join(sorted(_DATEIEN))}")
    daten = yaml.safe_load((ORDNER / _DATEIEN[stand]).read_text(encoding="utf-8"))
    meta = daten.get("meta", {})
    return Regelsatz(version=meta.get("version", stand),
                     verbindlich=bool(meta.get("verbindlich", False)),
                     quelle=meta.get("quelle", ""),
                     daten=daten)


def alle_staende() -> list[Regelsatz]:
    """Beide Stände, der geltende zuerst."""
    return [lade("2026"), lade("2027")]


# --------------------------------------------------------- Bezugsgeometrie

@dataclass
class Bezugsgeometrie:
    """Die Fahrzeugmaße, auf die sich das Reglement bezieht - fertig gerechnet.

    Das Reglement nennt Ebenen ("Vertikalebene durch die Vorderkante der
    Vorderreifen"), keine Zahlen. Hier werden sie einmal in Koordinaten
    umgerechnet, damit die Prüfungen darunter nur noch vergleichen müssen.
    """

    radstand: float = 1535.0
    spurweite_vorne: float = 1200.0
    spurweite_hinten: float = 1180.0
    reifen_durchmesser_vorne: float = 406.4
    reifen_breite_vorne: float = 190.5
    reifen_durchmesser_hinten: float = 406.4
    reifen_breite_hinten: float = 190.5
    kopfstuetze_x: float = 1000.0
    bodenfreiheit: float = 40.0

    # ---- abgeleitete Ebenen ---------------------------------------------
    @property
    def radius_vorne(self) -> float:
        return self.reifen_durchmesser_vorne / 2.0

    @property
    def radius_hinten(self) -> float:
        return self.reifen_durchmesser_hinten / 2.0

    @property
    def vorderreifen_vorderkante_x(self) -> float:
        """Vertikalebene durch die Vorderkante der Vorderreifen."""
        return -self.radius_vorne

    @property
    def hinterreifen_hinterkante_x(self) -> float:
        return self.radstand + self.radius_hinten

    @property
    def reifenoberkante_z(self) -> float:
        """Ebene durch die obersten Punkte der vier Reifen.

        Gerechnet aus dem UNBELASTETEN Durchmesser. Unter Last drücken sich
        die Reifen ein paar Millimeter zusammen, die echte Ebene liegt also
        etwas tiefer. Für eine Obergrenze heißt das: dieser Wert ist etwas zu
        großzügig - Rand lassen.
        """
        return max(self.reifen_durchmesser_vorne, self.reifen_durchmesser_hinten)

    @property
    def rad_aussen_vorne(self) -> float:
        return self.spurweite_vorne / 2.0 + self.reifen_breite_vorne / 2.0

    @property
    def rad_innen_vorne(self) -> float:
        return self.spurweite_vorne / 2.0 - self.reifen_breite_vorne / 2.0

    @property
    def rad_aussen_hinten(self) -> float:
        return self.spurweite_hinten / 2.0 + self.reifen_breite_hinten / 2.0

    @property
    def rad_innen_hinten(self) -> float:
        return self.spurweite_hinten / 2.0 - self.reifen_breite_hinten / 2.0

    @property
    def rad_aussen(self) -> float:
        """Äußerster Punkt von Vorder- UND Hinterrad - der weitere gewinnt."""
        return max(self.rad_aussen_vorne, self.rad_aussen_hinten)

    @staticmethod
    def aus_datei(pfad: Path | str | None = None) -> "Bezugsgeometrie":
        """Liest die Fahrzeugreferenz. Fehlt ein Wert, bleibt die Vorgabe."""
        d = yaml.safe_load(Path(pfad or VEHICLE_REF).read_text(encoding="utf-8"))
        r = d.get("raeder", {})
        vorne = r.get("reifen_vorne", {})
        hinten = r.get("reifen_hinten", {})
        return Bezugsgeometrie(
            radstand=float(r.get("radstand", 1535.0)),
            spurweite_vorne=float(r.get("spurweite_vorne", 1200.0)),
            spurweite_hinten=float(r.get("spurweite_hinten", 1180.0)),
            reifen_durchmesser_vorne=float(vorne.get("durchmesser", 406.4)),
            reifen_breite_vorne=float(vorne.get("breite", 190.5)),
            reifen_durchmesser_hinten=float(hinten.get("durchmesser", 406.4)),
            reifen_breite_hinten=float(hinten.get("breite", 190.5)),
            kopfstuetze_x=float(d.get("cockpit", {})
                                .get("kopfstuetze_x_hinterste_position", 1000.0)),
            bodenfreiheit=float(d.get("fahrwerk", {})
                                .get("bodenfreiheit_statisch", 40.0)),
        )


@dataclass
class Fahrzustand:
    """Wie weit sich der Flügel gegenüber der Konstruktionslage bewegt.

    `hoch` ist die größte Anhebung (Ausfedern), `tief` das größte Absenken
    (Einfedern plus Nicken beim Bremsen). Beide positiv in mm.

    Warum getrennt: Die Höhengrenzen des Reglements werden in der HÖCHSTEN
    Lage kritisch, die Bodenfreiheit in der TIEFSTEN. Ein einzelner Wert
    würde immer eine der beiden Prüfungen schönrechnen.
    """

    hoch: float = 24.35     # mm, Ausfederweg vorne aus den RSP-Kinematikexporten
    tief: float = 24.35     # mm, sobald das Nicken bekannt ist, überschrieben
    quelle: str = "Radhub vorne aus den RSP26-Kinematikexporten"

    @staticmethod
    def statisch() -> "Fahrzustand":
        """Nur Konstruktionslage. Für Zwischenstände, nicht für die Abnahme -
        T 8.2.4 verlangt ausdrücklich mehr."""
        return Fahrzustand(hoch=0.0, tief=0.0, quelle="nur Konstruktionslage")

    @staticmethod
    def bremsend(abstand_vor_vorderachse: float,
                 verzoegerung_g: float = 2.0,
                 ausfederweg: float = 24.35) -> "Fahrzustand":
        """Rechnet das Absenken beim Bremsen für einen Punkt vor der Achse.

        Nutzt die Nickrechnung aus fahrzeug.nicken, die auf den gemessenen
        Radraten und dem Anti-Dive der RSP-Kinematik aufsetzt.
        """
        from ..fahrzeug import nicken as nick

        zustand = nick.nicken(nick.Fahrzeug(), verzoegerung_g)
        tief = nick.bodenabstand_aenderung(zustand, abstand_vor_vorderachse)
        return Fahrzustand(
            hoch=ausfederweg, tief=float(tief),
            quelle=f"{verzoegerung_g:.1f} g Bremsen, Nickwinkel "
                   f"{zustand.nickwinkel:.3f} Grad, "
                   f"{abstand_vor_vorderachse:.0f} mm vor der Vorderachse")


# ------------------------------------------------------------- Befund

@dataclass
class Regelbefund:
    """Ein Prüfergebnis gegen das Reglement.

    Anders als der Fertigungsbefund kennt dieser hier eine RICHTUNG: Die
    meisten Regelgrenzen sind Obergrenzen ("nicht höher als"), einige
    Untergrenzen ("mindestens"). Ohne das Feld liest sich jede zweite Zeile
    falsch herum.
    """

    regel: str
    pruefung: str
    ok: bool
    ist: float
    grenze: float
    richtung: str = "max"           # "max" = ist <= grenze, "min" = ist >= grenze
    einheit: str = "mm"
    stufe: str = "fehler"           # "fehler" oder "hinweis"
    hinweis: str = ""
    stand: str = ""
    ort: str = ""                   # wo im Flügel, in Klartext
    neu: bool = False               # Grenze stammt aus dem 2027-Entwurf

    @property
    def blockiert(self) -> bool:
        return not self.ok and self.stufe == "fehler"

    @property
    def reserve(self) -> float:
        """Wieviel Luft bleibt. Negativ heißt Überschreitung."""
        return (self.grenze - self.ist) if self.richtung == "max" \
            else (self.ist - self.grenze)

    def __str__(self) -> str:
        zeichen = "ok  " if self.ok else ("FEHL" if self.stufe == "fehler" else "HINW")
        pfeil = "<=" if self.richtung == "max" else ">="
        text = (f"  {zeichen} [{self.regel:8s}] {self.pruefung:44s} "
                f"{self.ist:9.1f} {pfeil} {self.grenze:8.1f} {self.einheit}"
                f"   Reserve {self.reserve:+8.1f}")
        if self.ort:
            text += f"\n            bei {self.ort}"
        if self.hinweis and not self.ok:
            text += f"\n            {self.hinweis}"
        return text


# ---------------------------------------------------------- Hilfsgrößen

def _wolke(stapel) -> np.ndarray:
    """Alle Flügelpunkte als Nx3, gespiegelt auf beide Fahrzeugseiten.

    Gespiegelt, weil das Reglement Breiten über den BETRAG von y begrenzt und
    ein Flügel, der nur rechts modelliert ist, links genauso weit außen steht.
    Ohne die Spiegelung würde eine Breitenverletzung übersehen, sobald jemand
    die linke Hälfte modelliert.
    """
    punkte = np.vstack([s.punkte for s in stapel]).astype(float)
    gespiegelt = punkte.copy()
    gespiegelt[:, 1] *= -1.0
    return np.vstack([punkte, gespiegelt])


def _ort(punkte: np.ndarray, index: int) -> str:
    p = punkte[index]
    return f"x {p[0]:.0f}, y {p[1]:.0f}, z {p[2]:.0f} mm"


def _hoechster(punkte: np.ndarray, maske: np.ndarray) -> tuple[float, str]:
    if not maske.any():
        return float("-inf"), ""
    i = int(np.argmax(np.where(maske, punkte[:, 2], -np.inf)))
    return float(punkte[i, 2]), _ort(punkte, i)


def _breitester(punkte: np.ndarray, maske: np.ndarray) -> tuple[float, str]:
    if not maske.any():
        return float("-inf"), ""
    betrag = np.abs(punkte[:, 1])
    i = int(np.argmax(np.where(maske, betrag, -np.inf)))
    return float(betrag[i]), _ort(punkte, i)


# ------------------------------------------------------------- Prüfungen

def pruefe_fluegel(stapel, regelsatz: Regelsatz,
                   bezug: Optional[Bezugsgeometrie] = None,
                   zustand: Optional[Fahrzustand] = None) -> list[Regelbefund]:
    """Prüft einen Flügel gegen einen Regelstand.

    `stapel` ist die Schnittliste aus geometrie.spannweite.schnitte(), bereits
    in Fahrzeugkoordinaten. `zustand` beschreibt den Federungs-Envelope; ohne
    Angabe wird der Ausfederweg der RSP-Kinematik angesetzt.
    """
    bezug = bezug or Bezugsgeometrie.aus_datei()
    zustand = zustand or Fahrzustand()

    roh = _wolke(stapel)
    hoch = roh.copy()
    hoch[:, 2] += zustand.hoch          # höchste Lage - für die Höhengrenzen
    tief = roh.copy()
    tief[:, 2] -= zustand.tief          # tiefste Lage - für die Bodenfreiheit

    befunde: list[Regelbefund] = []
    befunde += _laenge(roh, regelsatz, bezug)
    befunde += _hoehe(hoch, regelsatz, bezug, zustand)
    befunde += _breite(hoch, regelsatz, bezug)
    befunde += _bodenfreiheit(tief, regelsatz, bezug, zustand)
    befunde += _keepout(roh, regelsatz, bezug)
    befunde += _quader(roh, regelsatz, bezug)

    for b in befunde:
        b.stand = regelsatz.version
        if regelsatz.entwurf and b.neu and b.stufe == "fehler" and not b.ok:
            # Eine Grenze, die es nur im Entwurf gibt, blockiert nichts -
            # sie warnt. Alles andere bleibt ein harter Verstoß, auch im
            # Entwurfsdurchlauf: T 2.2.1 etwa gilt heute schon, und daraus
            # einen Hinweis zu machen wäre schlicht falsch.
            b.stufe = "hinweis"
    return befunde


def _laenge(p, rs, bz) -> list[Regelbefund]:
    r = rs["t8_2_3"] or {}
    vorne = float(r.get("max_vor_vorderreifen", 700))
    hinten = float(r.get("max_hinter_hinterreifen", 250))

    grenze_vorn = bz.vorderreifen_vorderkante_x - vorne
    grenze_hint = bz.hinterreifen_hinterkante_x + hinten
    i_v = int(np.argmin(p[:, 0]))
    i_h = int(np.argmax(p[:, 0]))

    # Auf null geklemmt: Ein Frontflügel steht nicht "minus zwei Meter" hinter
    # den Hinterreifen heraus, er steht dort gar nicht heraus. Der rohe
    # Abstand wäre eine Zahl, die niemand liest und die in der Ampel nur Platz
    # wegnimmt.
    vor_ist = max(0.0, float(bz.vorderreifen_vorderkante_x - p[i_v, 0]))
    hint_ist = max(0.0, float(p[i_h, 0] - bz.hinterreifen_hinterkante_x))

    return [
        Regelbefund("T 8.2.3", f"Überstand vor den Vorderreifen (max {vorne:.0f})",
                    ok=bool(p[i_v, 0] >= grenze_vorn - 1e-9),
                    ist=vor_ist, grenze=vorne, richtung="max",
                    ort=_ort(p, i_v) if vor_ist > 0 else "",
                    hinweis="Vorderkante des Flügels weiter nach hinten legen "
                            "oder die Sehne kürzen."),
        Regelbefund("T 8.2.3", f"Überstand hinter den Hinterreifen (max {hinten:.0f})",
                    ok=bool(p[i_h, 0] <= grenze_hint + 1e-9),
                    ist=hint_ist, grenze=hinten, richtung="max",
                    ort=_ort(p, i_h) if hint_ist > 0 else "",
                    hinweis="Betrifft nur den Heckflügel."),
    ]


def _hoehe(p, rs, bz, zustand) -> list[Regelbefund]:
    """Höhengrenzen. Hier liegt der größte Unterschied zwischen 2026 und 2027."""
    r = rs["t8_2_1"] or {}
    befunde: list[Regelbefund] = []
    anmerkung = (f"Geprüft in der höchsten Lage: {zustand.hoch:.1f} mm über "
                 f"Konstruktionslage ({zustand.quelle}).")

    vor = r.get("vor_vorderreifen") or {}
    grenze = float(vor.get("max_hoehe", 250))
    if "zusatzbedingung" in vor:
        # Regelstand 2026: vor der VORDERACHSE und weiter außen als der
        # innerste Radpunkt. Innen zwischen den Rädern gelten stattdessen 500.
        maske = (p[:, 0] < 0.0) & (np.abs(p[:, 1]) > bz.rad_innen_vorne)
        text = f"Höhe vor der Vorderachse, außerhalb Radinnenkante (max {grenze:.0f})"
    else:
        # Regelstand 2027: schlicht vor der Reifenvorderkante.
        maske = p[:, 0] < bz.vorderreifen_vorderkante_x
        text = f"Höhe vor der Reifenvorderkante (max {grenze:.0f})"
    if maske.any():
        ist, ort = _hoechster(p, maske)
        befunde.append(Regelbefund(
            "T 8.2.1", text, ok=bool(ist <= grenze + 1e-9), ist=ist, grenze=grenze,
            ort=ort, neu=bool(vor.get("geaendert_2027")),
            hinweis=anmerkung + " Flügel tiefer setzen oder den Anstellwinkel "
                                "zurücknehmen."))

    vor_kopf = r.get("vor_kopfstuetze")
    if vor_kopf:
        grenze = float(vor_kopf["max_hoehe"])
        maske = p[:, 0] < bz.kopfstuetze_x
        if maske.any():
            ist, ort = _hoechster(p, maske)
            befunde.append(Regelbefund(
                "T 8.2.1", f"Höhe vor der Kopfstützenebene (max {grenze:.0f})",
                ok=bool(ist <= grenze + 1e-9), ist=ist, grenze=grenze, ort=ort,
                hinweis=anmerkung))

    if r.get("alle_uebrigen"):
        # Regelstand 2027: alles zwischen Reifenvorderkante und
        # Kopfstützenebene muss unter die Reifenoberkante.
        grenze = bz.reifenoberkante_z
        maske = ((p[:, 0] >= bz.vorderreifen_vorderkante_x)
                 & (p[:, 0] < bz.kopfstuetze_x))
        if maske.any():
            ist, ort = _hoechster(p, maske)
            befunde.append(Regelbefund(
                "T 8.2.1", f"Höhe unter Reifenoberkante (max {grenze:.0f})",
                ok=bool(ist <= grenze + 1e-9), ist=ist, grenze=grenze, ort=ort,
                neu=True,
                hinweis=anmerkung + " Neu 2027: zwischen Reifenvorderkante und "
                                    "Kopfstütze zählt die Reifenoberkante, "
                                    "nicht mehr die feste 500-mm-Ebene."))

    hinter = r.get("hinter_kopfstuetze") or {}
    maske = p[:, 0] >= bz.kopfstuetze_x
    if maske.any():
        grenze = float(hinter.get("max_hoehe", 1100))
        ist, ort = _hoechster(p, maske)
        befunde.append(Regelbefund(
            "T 8.2.1", f"Höhe hinter der Kopfstützenebene (max {grenze:.0f})",
            ok=bool(ist <= grenze + 1e-9), ist=ist, grenze=grenze, ort=ort,
            hinweis=anmerkung))

        unten = hinter.get("min_hoehe")
        if unten is not None:
            unten = float(unten)
            i = int(np.argmin(np.where(maske, p[:, 2], np.inf)))
            tiefster = float(p[i, 2])
            befunde.append(Regelbefund(
                "T 8.2.1", f"Heckflügel nicht unter {unten:.0f}",
                ok=bool(tiefster >= unten - 1e-9), ist=tiefster, grenze=unten,
                richtung="min", ort=_ort(p, i),
                neu=bool(hinter.get("min_hoehe_neu_2027")),
                hinweis="Neu 2027: erstmals eine UNTERGRENZE. Ein tief "
                        "angesetzter Heckflügel, der 2026 zulässig war, fällt "
                        "damit aus."))
    return befunde


def _breite(p, rs, bz) -> list[Regelbefund]:
    r = rs["t8_2_2"] or {}
    befunde: list[Regelbefund] = []

    unten = r.get("unterhalb_reifenoberkante") or {}
    schwelle = unten.get("schwelle_hoehe")
    if schwelle is not None:
        # 2026: feste Höhenschwelle, Längsbezug Vorderachse.
        schwelle = float(schwelle)
        maske = (p[:, 2] < schwelle) & (p[:, 0] > 0.0)
        text = f"Breite unter {schwelle:.0f} mm, hinter der Vorderachse"
    else:
        # 2027: Schwelle ist die Reifenoberkante, Bezug die Reifenvorderkante.
        schwelle = bz.reifenoberkante_z
        maske = (p[:, 2] < schwelle) & (p[:, 0] > bz.vorderreifen_vorderkante_x)
        text = f"Breite unter Reifenoberkante ({schwelle:.0f} mm)"
    if maske.any():
        ist, ort = _breitester(p, maske)
        befunde.append(Regelbefund(
            "T 8.2.2", text, ok=bool(ist <= bz.rad_aussen + 1e-9), ist=ist,
            grenze=bz.rad_aussen, ort=ort,
            neu=bool(unten.get("geaendert_2027")),
            hinweis="Grenze ist der äußerste Punkt von Vorder- und Hinterrad."))

    oben = r.get("oberhalb_reifenoberkante") or {}
    schwelle_o = oben.get("schwelle_hoehe")
    if schwelle_o is not None:
        schwelle_o = float(schwelle_o)
        grenze = bz.rad_innen_hinten          # 2026: INNERSTER Punkt
        zusatz = "2026 ist die Grenze der INNERSTE Punkt des Hinterrads."
    else:
        schwelle_o = bz.reifenoberkante_z
        grenze = bz.rad_aussen_hinten         # 2027: äußerster Punkt
        zusatz = ("Lockerung 2027: statt des innersten zählt jetzt der "
                  "ÄUSSERSTE Punkt des Hinterrads - der Heckflügel darf "
                  f"{bz.rad_aussen_hinten - bz.rad_innen_hinten:.0f} mm je "
                  "Seite breiter werden.")
    maske = p[:, 2] >= schwelle_o
    if maske.any():
        ist, ort = _breitester(p, maske)
        befunde.append(Regelbefund(
            "T 8.2.2", f"Breite über {schwelle_o:.0f} mm",
            ok=bool(ist <= grenze + 1e-9), ist=ist, grenze=grenze, ort=ort,
            neu=bool(oben.get("geaendert_2027")), hinweis=zusatz))
    return befunde


def _bodenfreiheit(p, rs, bz, zustand) -> list[Regelbefund]:
    r = rs["uebernommen_aus_2026"] or {}
    grenze = float(r.get("t2_2_1_bodenfreiheit_min", 30))
    i = int(np.argmin(p[:, 2]))
    tiefster = float(p[i, 2])

    rat = (f"Geprüft in der tiefsten Lage: {zustand.tief:.1f} mm unter "
           f"Konstruktionslage ({zustand.quelle}). Statisch mag der Flügel "
           f"passen - hier zählt der Bremsfall.")
    if tiefster < grenze:
        # Konkreter Vorschlag statt bloßer Meldung: Der Flügel muss genau um
        # die Fehlmenge angehoben werden, weil die Hinterkante starr am Rest
        # hängt und sich nicht einzeln verschieben lässt.
        rat += (f" Der Flügel müsste um {grenze - tiefster:.1f} mm höher "
                f"gesetzt werden - oder der Anstellwinkel an der Wurzel muss "
                f"zurück, dort liegt der tiefste Punkt.")

    return [Regelbefund(
        "T 2.2.1", f"Bodenfreiheit im Fahrzustand (min {grenze:.0f})",
        ok=bool(tiefster >= grenze - 1e-9), ist=tiefster,
        grenze=grenze, richtung="min", ort=_ort(p, i), hinweis=rat)]


def _keepout(p, rs, bz) -> list[Regelbefund]:
    """T 2.1.3: Die Seitenansicht der Räder muss frei bleiben.

    Ausgelegt als Quader: längs von 75 mm vor bis 75 mm hinter dem
    Reifenaußendurchmesser, hoch bis zur Reifenoberkante, seitlich zwischen
    Innen- und Außenebene des Rad/Reifen-Verbunds. Das ist die strenge
    Lesart - die Regel nennt Linien, nicht die Reifenkontur.
    """
    r = rs["t2_1_3"] or {}
    vor = float(r.get("abstand_vor_reifen", 75))
    hinter = float(r.get("abstand_hinter_reifen", 75))
    hoehe_hinten = r.get("hoehe_hinterreifen")

    befunde: list[Regelbefund] = []
    for name, mitte_x, radius, innen, aussen, deckel in (
            ("Vorderrad", 0.0, bz.radius_vorne, bz.rad_innen_vorne,
             bz.rad_aussen_vorne, bz.reifen_durchmesser_vorne),
            ("Hinterrad", bz.radstand, bz.radius_hinten, bz.rad_innen_hinten,
             bz.rad_aussen_hinten,
             float(hoehe_hinten) if hoehe_hinten else bz.reifen_durchmesser_hinten)):
        drin = ((p[:, 0] > mitte_x - radius - vor)
                & (p[:, 0] < mitte_x + radius + hinter)
                & (np.abs(p[:, 1]) >= innen) & (np.abs(p[:, 1]) <= aussen)
                & (p[:, 2] <= deckel))
        anzahl = int(drin.sum())
        ort = _ort(p, int(np.argmax(drin))) if anzahl else ""
        befunde.append(Regelbefund(
            "T 2.1.3", f"Keep-out-Zone {name} frei",
            ok=anzahl == 0, ist=float(anzahl), grenze=0.0, einheit="Punkte",
            ort=ort, neu=bool(r.get("neu_2027")) and name == "Hinterrad",
            hinweis=f"Zone: x von {mitte_x - radius - vor:.0f} bis "
                    f"{mitte_x + radius + hinter:.0f}, |y| von {innen:.0f} bis "
                    f"{aussen:.0f}, z bis {deckel:.0f}. Der Flügel muss davor "
                    f"enden oder außerhalb der Radebene liegen."))
    return befunde


def _quader(p, rs, bz) -> list[Regelbefund]:
    """T 2.1.4, neu in 2027: zwei bodennahe Kanäle müssen frei bleiben.

    Der Entwurfstext nennt eine VARIABLE Keep-out-Zone aus zwei unabhängigen
    Quadern von 75 x 250 mm, unendlich lang nach vorn, zwei Kanten auf dem
    Boden, nicht weiter außen als der äußerste Punkt des Vorderrads. Die
    Lesart hier: Vor der Reifenvorderkante muss es je Fahrzeugseite einen
    75 mm breiten Streifen geben, in dem bis 250 mm Höhe nichts steht. Zwei
    Quader, zwei Seiten - das passt zur Symmetrie des Fahrzeugs.

    ACHTUNG: Der Wortlaut ist Entwurf und lässt auch eine strengere Lesart zu,
    bei der der Prüfer die Quader frei setzen darf. Fällt diese Prüfung durch,
    fällt sie in JEDER Lesart durch; besteht sie, gilt das nur für die hier
    angesetzte.

    Gesehen wird außerdem nur der Flügel. Nasenspitze, Fahrwerkslenker und
    Halterungen stehen nicht im Modell und können denselben Streifen zusetzen.
    """
    r = rs["t2_1_4"]
    if not r:
        return []
    breite = float(r.get("quader_breite", 75))
    hoehe = float(r.get("quader_hoehe", 250))

    stoerend = (p[:, 0] < bz.vorderreifen_vorderkante_x) & (p[:, 2] < hoehe)
    frei, wo = _freier_streifen(np.abs(p[stoerend, 1]), bz.rad_aussen_vorne)

    return [Regelbefund(
        "T 2.1.4", f"Freier Kanal {breite:.0f} x {hoehe:.0f} mm vor dem Rad",
        ok=bool(frei >= breite - 1e-9), ist=frei, grenze=breite, richtung="min",
        ort=wo, neu=True,
        hinweis="Neu 2027. Der Flügel muss vor der Reifenvorderkante einen "
                f"{breite:.0f} mm breiten Streifen bis {hoehe:.0f} mm Höhe "
                f"freilassen, innerhalb von |y| <= {bz.rad_aussen_vorne:.0f} mm. "
                "Das trifft genau das durchgehende untere Element, mit dem "
                "Frontflügel bisher den meisten Abtrieb geholt haben. "
                "Abhilfe: ein Schlitz in der Spannweite, oder das untere "
                "Element hinter die Reifenvorderkante ziehen.")]


def _freier_streifen(y_belegt: np.ndarray,
                     aussen: float) -> tuple[float, str]:
    """Breitester freier Streifen in 0 <= y <= aussen, und wo er liegt.

    Die belegten Stellen sind Punkte einer zusammenhängenden Fläche, keine
    Einzelhindernisse: Zwischen zwei benachbarten Flügelschnitten ist die Haut
    geschlossen. Deshalb gilt der Bereich zwischen zwei belegten Stellen als
    belegt, solange die Lücke nicht deutlich größer ist als der Schnittabstand.
    """
    if y_belegt.size == 0:
        return float(aussen), f"nichts im Weg, |y| 0 bis {aussen:.0f} mm frei"

    y = np.sort(np.unique(np.round(y_belegt, 3)))
    y = y[y <= aussen]
    if y.size == 0:
        return float(aussen), f"nichts im Weg, |y| 0 bis {aussen:.0f} mm frei"

    # Schnittabstand schätzen: der Median der Lücken. Alles, was deutlich
    # größer ist, ist ein echter Schlitz und keine Diskretisierung.
    if y.size > 1:
        luecken = np.diff(y)
        schwelle = max(2.0 * float(np.median(luecken)), 1.0)
    else:
        luecken = np.array([])
        schwelle = 1.0

    kandidaten = [(float(y[0]), 0.0, float(y[0])),
                  (float(aussen - y[-1]), float(y[-1]), float(aussen))]
    for a, b in zip(y[:-1], y[1:]):
        if b - a > schwelle:
            kandidaten.append((float(b - a), float(a), float(b)))

    breite, von, bis = max(kandidaten)
    return breite, f"breitester freier Streifen |y| {von:.0f} bis {bis:.0f} mm"


__all__ = ["Bezugsgeometrie", "Fahrzustand", "Regelbefund", "Regelsatz",
           "alle_staende", "lade", "pruefe_fluegel"]
