"""
Das 2D-Profil - Kern des Werkzeugs.

Ein Profil wird intern immer auf Einheitssehne gehalten, in der Selig-Reihenfolge:
von der Hinterkante ueber die Oberseite zur Nase und ueber die Unterseite zurueck.
Sehne, Anstellwinkel und Lage kommen erst beim Export dazu. Das haelt Geometrie
und Anordnung sauber getrennt - genau die Trennung, die spaeter bei
Mehrelementkaskaden zaehlt, wo dasselbe Profil mehrfach in unterschiedlicher
Groesse und Anstellung auftaucht.

Drei Wege zu einem Profil, alle mit demselben Ergebnistyp:
  aus_dat   Koordinatendatei, etwa aus der UIUC-Datenbank
  aus_naca  analytisch erzeugtes NACA-4-Profil
  aus_cst   CST/Kulfan-Darstellung, die Form fuer die Optimierung
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.optimize import lsq_linear
from scipy.special import comb

from .spline import punktzahl_fuer_toleranz, punktzahl_fuer_umlauf


# --------------------------------------------------------------- Verteilungen

def kosinus(n: int) -> np.ndarray:
    """Kosinusverteilung auf [0, 1]: dicht an Nase und Hinterkante.

    Der Grund fuer die Verdichtung ist unterschiedlich: an der Nase, weil die
    Kruemmung dort am groessten ist; an der Hinterkante, weil dort die
    Fertigungsgrenze sitzt und ein paar Zehntel ueber Sein oder Nichtsein des
    Bauteils entscheiden.
    """
    return 0.5 * (1.0 - np.cos(np.linspace(0.0, math.pi, n)))


# ------------------------------------------------------------------- CST/Kulfan

def _cst_seite(x: np.ndarray, koeff: np.ndarray, dz_te: float = 0.0,
               n1: float = 0.5, n2: float = 1.0) -> np.ndarray:
    """Eine Profilseite aus CST-Koeffizienten.

    y = C(x) * S(x) + x * dz_te
    mit der Klassenfunktion C(x) = x^n1 * (1-x)^n2 und der Formfunktion S als
    Bernsteinpolynom. n1 = 0.5 erzeugt die runde Nase, n2 = 1.0 die spitze
    Hinterkante; dz_te oeffnet sie wieder auf das gewuenschte Mass.
    """
    x = np.asarray(x, dtype=float)
    ordnung = len(koeff) - 1
    klasse = x**n1 * (1.0 - x)**n2
    form = np.zeros_like(x)
    for i, a in enumerate(koeff):
        form += a * comb(ordnung, i) * x**i * (1.0 - x)**(ordnung - i)
    return klasse * form + x * dz_te


def _cst_matrix(x: np.ndarray, ordnung: int, n1: float = 0.5,
                n2: float = 1.0) -> np.ndarray:
    """Entwurfsmatrix fuer die Ausgleichsrechnung der CST-Koeffizienten."""
    x = np.asarray(x, dtype=float)
    klasse = x**n1 * (1.0 - x)**n2
    return np.column_stack([
        klasse * comb(ordnung, i) * x**i * (1.0 - x)**(ordnung - i)
        for i in range(ordnung + 1)
    ])


# ------------------------------------------------------------------- Befunde

@dataclass
class Befund:
    """Ein Prüfergebnis.

    `ok` heisst regel- und fertigungskonform. `stufe` trennt harte Verstoesse
    von Dingen, die die Fertigung von sich aus loest: Ein Hinweis darf rot
    aussehen, blockiert aber kein Design.
    """

    pruefung: str
    ok: bool
    ist: float
    soll: float
    einheit: str = "mm"
    regel: str | None = None
    hinweis: str | None = None
    stufe: str = "fehler"          # "fehler" oder "hinweis"

    @property
    def blockiert(self) -> bool:
        return not self.ok and self.stufe == "fehler"

    def __str__(self) -> str:
        zeichen = "ok  " if self.ok else ("FEHL" if self.stufe == "fehler" else "HINW")
        quelle = f"  [{self.regel}]" if self.regel else ""
        text = (f"  {zeichen} {self.pruefung:26s} "
                f"ist {self.ist:8.3f}, soll >= {self.soll:6.3f} {self.einheit}{quelle}")
        if self.hinweis and not self.ok:
            text += f"\n         {self.hinweis}"
        return text


@dataclass
class Zone:
    """Ein Abschnitt der Sehne mit gleichem Laminataufbau."""

    art: str        # "vollmaterial" | "schale" | "sandwich"
    von: float      # Sehnenanteil, 0 bis 1
    bis: float

    @property
    def laenge(self) -> float:
        return self.bis - self.von

    def __str__(self) -> str:
        return (f"  {self.art:<13}{self.von*100:6.1f} % .. {self.bis*100:5.1f} %"
                f"   ({self.laenge*100:4.1f} % der Sehne)")


# --------------------------------------------------------------------- Profil

@dataclass
class Profil:
    """Ein Profil auf Einheitssehne, Selig-Reihenfolge."""

    punkte: np.ndarray
    name: str = "unbenannt"
    herkunft: str = ""
    _cst: tuple[np.ndarray, np.ndarray, float] | None = field(
        default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        p = np.asarray(self.punkte, dtype=float)
        if p.ndim != 2 or p.shape[1] != 2:
            raise ValueError(f"Profilpunkte muessen ein Nx2-Feld sein, sind {p.shape}.")
        if len(p) < 5:
            raise ValueError("Ein Profil braucht mindestens fuenf Punkte.")
        self.punkte = _normiere(p)

    # ------------------------------------------------------------ Konstruktoren

    @staticmethod
    def aus_dat(pfad: str | Path, name: str | None = None) -> "Profil":
        """Liest eine Koordinatendatei.

        Erkennt beide in der UIUC-Datenbank ueblichen Formate:
        Selig (ein durchgehender Umlauf von der Hinterkante) und Lednicer
        (zwei getrennte Bloecke, jeweils von der Nase aus, mit einer Zeile
        Punktzahlen davor).
        """
        pfad = Path(pfad)
        zeilen = pfad.read_text(encoding="utf-8", errors="ignore").splitlines()

        kopf = ""
        werte: list[tuple[float, float]] = []
        zahlen_je_zeile: list[int] = []

        for z in zeilen:
            teile = z.split()
            if len(teile) != 2:
                if not werte and z.strip():
                    kopf = z.strip()
                continue
            try:
                a, b = float(teile[0]), float(teile[1])
            except ValueError:
                if not werte and z.strip():
                    kopf = z.strip()
                continue
            # Lednicer beginnt mit einer Zeile wie "61. 61." - Punktzahlen,
            # erkennbar daran, dass beide Werte deutlich groesser als 1 sind.
            if not werte and a > 1.5 and b > 1.5:
                zahlen_je_zeile = [int(round(a)), int(round(b))]
                continue
            werte.append((a, b))

        if len(werte) < 5:
            raise ValueError(f"{pfad.name}: keine brauchbaren Koordinaten gefunden.")

        p = np.array(werte, dtype=float)
        if zahlen_je_zeile:
            n_oben = zahlen_je_zeile[0]
            oben, unten = p[:n_oben], p[n_oben:]
            # Lednicer laeuft von der Nase nach hinten; Selig will die Oberseite
            # rueckwaerts, also von der Hinterkante zur Nase.
            p = np.vstack([oben[::-1], unten[1:]])

        return Profil(p, name=name or kopf or pfad.stem, herkunft=f"dat:{pfad.name}")

    @staticmethod
    def aus_naca(woelbung: float = 0.04, woelbungslage: float = 0.4,
                 dicke: float = 0.12, n: int = 201) -> "Profil":
        """Analytisch erzeugtes NACA-4-Profil.

        Vergleichsbasis und Testfall - fuer Abtrieb sind diese Profile
        nicht die erste Wahl, aber sie sind exakt reproduzierbar und eignen
        sich deshalb als Pruefstein fuer alles Nachgelagerte.
        """
        m, p_, t = float(woelbung), float(woelbungslage), float(dicke)
        x = kosinus(n)

        yt = 5 * t * (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x**2
                      + 0.2843 * x**3 - 0.1015 * x**4)
        if m != 0.0:
            yc = np.where(x < p_, m / p_**2 * (2 * p_ * x - x**2),
                          m / (1 - p_)**2 * ((1 - 2 * p_) + 2 * p_ * x - x**2))
            dy = np.where(x < p_, 2 * m / p_**2 * (p_ - x),
                          2 * m / (1 - p_)**2 * (p_ - x))
        else:
            yc = np.zeros_like(x)
            dy = np.zeros_like(x)
        th = np.arctan(dy)

        oben = np.column_stack([x - yt * np.sin(th), yc + yt * np.cos(th)])
        unten = np.column_stack([x + yt * np.sin(th), yc - yt * np.cos(th)])

        punkte = np.vstack([oben[::-1], unten[1:]])
        if -0.095 <= m <= 0.095 and abs(m * 100) < 10:
            name = (f"NACA {int(round(abs(m)*100))}{int(round(p_*10))}"
                    f"{int(round(t*100)):02d}"
                    + (" (negativ gewölbt)" if m < 0 else ""))
        else:
            # Ausserhalb der Standardfamilie gibt es keine gueltige Ziffernfolge -
            # dann lieber die Werte nennen als eine Bezeichnung erfinden, die es
            # nicht gibt.
            name = (f"NACA-Typ  Wölbung {m*100:+.1f} % bei {p_*100:.0f} %, "
                    f"Dicke {t*100:.1f} %")
        return Profil(punkte, name=name, herkunft="naca")

    @staticmethod
    def aus_cst(oben: list[float] | np.ndarray, unten: list[float] | np.ndarray,
                hinterkante_dicke: float = 0.0, n: int = 201,
                name: str = "CST") -> "Profil":
        """Profil aus CST/Kulfan-Koeffizienten."""
        x = kosinus(n)
        yo = _cst_seite(x, np.asarray(oben, dtype=float), +hinterkante_dicke / 2.0)
        yu = _cst_seite(x, np.asarray(unten, dtype=float), -hinterkante_dicke / 2.0)
        punkte = np.vstack([
            np.column_stack([x, yo])[::-1],
            np.column_stack([x, yu])[1:],
        ])
        pr = Profil(punkte, name=name, herkunft="cst")
        pr._cst = (np.asarray(oben, dtype=float), np.asarray(unten, dtype=float),
                   float(hinterkante_dicke))
        return pr

    # ------------------------------------------------------------------ Zugriff

    def _nasenindex(self) -> int:
        """Index des Nasenpunkts: groesster Abstand zur Hinterkante.

        Nicht min(x) - bei gewoelbten Profilen liegt der vorderste Punkt wegen
        des senkrechten Dickenauftrags leicht neben der Nase.
        """
        hk = 0.5 * (self.punkte[0] + self.punkte[-1])
        return int(np.argmax(np.linalg.norm(self.punkte - hk, axis=1)))

    def oben(self) -> np.ndarray:
        """Oberseite, von der Nase zur Hinterkante, streng steigend in x."""
        return _monoton(self.punkte[:self._nasenindex() + 1][::-1])

    def unten(self) -> np.ndarray:
        """Unterseite, von der Nase zur Hinterkante, streng steigend in x."""
        return _monoton(self.punkte[self._nasenindex():])

    def _seiten_auf(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Ober- und Unterseite an gegebenen x-Stellen.

        Interpoliert mit PCHIP, nicht linear. Katalogprofile haben oft nur 30
        bis 100 Punkte; linear interpoliert waere die Kontur dazwischen ein
        Polygonzug mit Knicken an jedem Stuetzpunkt. Dicke, Woelbung und jede
        Toleranzbetrachtung waeren dann von der Punktzahl der Quelldatei
        abhaengig statt von der Form.

        PCHIP und nicht der gewoehnliche kubische Spline, weil PCHIP
        formerhaltend ist: Er ueberschwingt nicht und erfindet damit keine
        Dicke, die das Profil nicht hat.
        """
        o, u = self.oben(), self.unten()
        return (_werte_auf(o, x), _werte_auf(u, x))

    def dickenverlauf(self, n: int = 401) -> tuple[np.ndarray, np.ndarray]:
        x = kosinus(n)
        yo, yu = self._seiten_auf(x)
        return x, yo - yu

    def woelbungsverlauf(self, n: int = 401) -> tuple[np.ndarray, np.ndarray]:
        """Mittellinie als Mittel von Ober- und Unterseite bei gleichem x.

        Das ist die uebliche Definition aus Koordinaten. Sie stimmt bei
        NACA-Profilen bis auf wenige Hundertstel Prozent mit der Skelettlinie
        ueberein, aus der sie konstruiert werden.
        """
        x = kosinus(n)
        yo, yu = self._seiten_auf(x)
        return x, 0.5 * (yo + yu)

    # --------------------------------------------------------------- Kennwerte

    @property
    def max_dicke(self) -> float:
        return float(self.dickenverlauf()[1].max())

    @property
    def max_dicke_bei(self) -> float:
        x, d = self.dickenverlauf()
        return float(x[int(np.argmax(d))])

    @property
    def max_woelbung(self) -> float:
        return float(np.abs(self.woelbungsverlauf()[1]).max())

    @property
    def hinterkante_dicke(self) -> float:
        """Dicke an der Hinterkante, in Sehnenanteilen."""
        o, u = self.oben(), self.unten()
        return float(abs(o[-1, 1] - u[-1, 1]))

    def nasenradius(self, anteil: float = 0.01) -> float:
        """Nasenradius aus einem Kreisfit an die vorderen Punkte.

        Numerisch statt aus der CST-Formel, damit der Wert fuer alle drei
        Profilquellen auf dieselbe Art entsteht und vergleichbar bleibt.

        Das Fenster waechst, bis mindestens fuenf Punkte darin liegen. Sonst
        liefern grob aufgeloeste Katalogprofile - manche haben nur 27 Punkte -
        gar kein Ergebnis, obwohl ihre Nase voellig in Ordnung ist.
        """
        nahe = self.punkte[self.punkte[:, 0] <= anteil]
        while len(nahe) < 5 and anteil < 0.2:
            anteil *= 1.5
            nahe = self.punkte[self.punkte[:, 0] <= anteil]
        if len(nahe) < 3:
            return float("nan")
        # Kreisfit: x^2+y^2 + D x + E y + F = 0
        A = np.column_stack([nahe[:, 0], nahe[:, 1], np.ones(len(nahe))])
        b = -(nahe[:, 0]**2 + nahe[:, 1]**2)
        (D, E, F), *_ = np.linalg.lstsq(A, b, rcond=None)
        return float(math.sqrt(max(D * D / 4 + E * E / 4 - F, 0.0)))

    def kruemmung(self, n: int = 801) -> tuple[np.ndarray, np.ndarray]:
        """Kruemmung entlang der Kontur, ueber der Lauflaenge.

        Ein zappelnder Kruemmungsverlauf ist der beste Fruehwarnindikator fuer
        ein schlechtes Profil: Er erzeugt im CFD Laminarblasen, die es real
        nicht gibt, und faellt an der fertigen Form als Welligkeit auf.
        """
        p = self.punkte
        s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
        st = np.linspace(s[0], s[-1], n)
        x = np.interp(st, s, p[:, 0])
        y = np.interp(st, s, p[:, 1])
        dx, dy = np.gradient(x, st), np.gradient(y, st)
        ddx, ddy = np.gradient(dx, st), np.gradient(dy, st)
        nenner = (dx * dx + dy * dy)**1.5
        with np.errstate(divide="ignore", invalid="ignore"):
            k = np.where(nenner > 1e-12, (dx * ddy - dy * ddx) / nenner, 0.0)
        return st, k

    # ------------------------------------------------------------- Umformungen

    def gespiegelt(self) -> "Profil":
        """Spiegelt das Profil an der Sehne.

        Ein Abtriebsfluegel ist ein umgedrehtes Auftriebsprofil - die
        Katalogprofile sind alle fuer Auftrieb gezeichnet. Ohne Spiegelung
        erzeugt ein E423 am Fahrzeug Auftrieb statt Abtrieb.

        Die Punktreihenfolge wird mit umgekehrt: Nach dem Spiegeln ist die
        fruehere Oberseite die Unterseite, und die Selig-Reihenfolge - von der
        Hinterkante ueber oben zur Nase und unten zurueck - muss erhalten
        bleiben, sonst kehren sich Dicke und Woelbung im Vorzeichen um.
        """
        punkte = self.punkte.copy()
        punkte[:, 1] *= -1.0
        return Profil(punkte[::-1], name=f"{self.name} (gespiegelt)",
                      herkunft=self.herkunft)

    def repanelisiert(self, n_je_seite: int = 40) -> "Profil":
        """Neue Punktverteilung mit Kosinus-Clustering je Seite."""
        x = kosinus(n_je_seite)
        yo, yu = self._seiten_auf(x)
        punkte = np.vstack([
            np.column_stack([x, yo])[::-1],
            np.column_stack([x, yu])[1:],
        ])
        return Profil(punkte, name=self.name, herkunft=self.herkunft)

    def nach_cst(self, ordnung: int = 9) -> tuple[np.ndarray, np.ndarray, float]:
        """Passt CST-Koeffizienten an das Profil an.

        Gibt (oben, unten, hinterkante_dicke) zurueck. Die Hinterkantendicke
        wird vorher abgezogen, damit sie nicht in die Koeffizienten wandert.

        Genauigkeit des Rundlaufs Profil -> CST -> Profil, gemessen als echter
        geometrischer Abstand an NACA 4412 bei 250 mm Sehne:

            Ordnung  5   126 um
            Ordnung  7    67 um
            Ordnung  9    37 um      <- Vorgabe
            Ordnung 11    28 um

        Zum Vergleich: Creos Modellgenauigkeit liegt bei 10 um. CST ist damit
        NICHT genau genug, um ein vorhandenes Profil verlustfrei zu ersetzen -
        und das ist auch nicht sein Zweck. Der Weg vom Katalogprofil nach Creo
        laeuft direkt ueber die Punkte und beruehrt CST nie. Gebraucht wird die
        Darstellung erst in M3, wo Formen AUS CST erzeugt und optimiert werden;
        dann gibt es kein Original, gegen das ein Fehler entstehen koennte.

        Der Restfehler sitzt im ersten Promille der Sehne, wo die Kontur fast
        senkrecht steht.
        """
        dz = self.hinterkante_dicke
        ergebnis = []
        for seite, vorzeichen in ((self.oben(), +1.0), (self.unten(), -1.0)):
            x, y = seite[:, 0], seite[:, 1] - seite[:, 0] * vorzeichen * dz / 2.0
            gueltig = x > 1e-9
            A = _cst_matrix(x[gueltig], ordnung)
            loesung = lsq_linear(A, y[gueltig])
            ergebnis.append(loesung.x)
        return ergebnis[0], ergebnis[1], dz

    def skaliert(self, sehne_mm: float) -> np.ndarray:
        """Punkte in Millimetern bei gegebener Sehnenlaenge."""
        return self.punkte * float(sehne_mm)

    def angestellt(self, winkel_grad: float, sehne_mm: float = 1.0,
                   drehpunkt: float = 0.25) -> np.ndarray:
        """Um den Drehpunkt gedrehte Punkte, in Millimetern.

        Positiver Winkel = Nase nach oben, negativer = Nase nach unten. Fuer
        Abtrieb sind die Winkel also negativ. Der Drehpunkt liegt
        standardmaessig bei einem Viertel der Sehne, weil sich dort das Moment
        am wenigsten aendert.

        ACHTUNG, hier steckte ein Vorzeichenfehler: Eine gewoehnliche
        mathematische Drehung um +a hebt die HINTERKANTE (sie liegt bei
        x > Drehpunkt) und senkt die Nase - also genau andersherum als
        beschrieben. Gemessen fuer das E423 bei 250 mm Sehne und -8 Grad: Die
        Nase lag 8,7 mm UEBER der Hinterkante statt darunter.

        Aufgefallen ist es erst durch das Panelverfahren: Die Aerodynamik
        rechnet dieselbe Zahl als Anstellwinkel, und dort bedeutet -8 Grad
        eindeutig mehr Abtrieb. Geometrie und Aerodynamik liefen also
        gegeneinander - gerechnet wurde ein Abtriebsfluegel, exportiert nach
        Creo ein nach oben gedrehter. Deshalb wird hier mit dem NEGATIVEN
        Winkel gedreht.
        """
        p = self.punkte.copy()
        p[:, 0] -= drehpunkt
        a = math.radians(-winkel_grad)
        c, s = math.cos(a), math.sin(a)
        gedreht = np.column_stack([p[:, 0] * c - p[:, 1] * s,
                                   p[:, 0] * s + p[:, 1] * c])
        gedreht[:, 0] += drehpunkt
        return gedreht * float(sehne_mm)

    # -------------------------------------------------------------- Pruefungen

    def laminatzonen(self, fertigung, sehne_mm: float, n: int = 2001) -> list[Zone]:
        """Teilt die Sehne nach dem moeglichen Laminataufbau auf.

        Eine Fluegelschale ist nicht ueberall gleich gebaut. Nach vorne und nach
        hinten laeuft das Profil zusammen; irgendwann passt kein Kern mehr
        hinein, und ganz aussen passt nicht einmal mehr eine Schale. Genau so
        wird das Bauteil auch laminiert - der Kern wird eingelegt, wo Platz ist,
        und weggelassen, wo es eng wird.

        Drei Zonen, von der Dicke her unterschieden:
          sandwich       Dicke >= 2 Haeute + Kern
          schale         Dicke >= 2 Haeute
          vollmaterial   alles darunter
        """
        x, d = self.dickenverlauf(n)
        dicke_mm = d * float(sehne_mm)

        def art(t: float) -> str:
            if fertigung.kern > 0 and t >= fertigung.dicke_sandwich:
                return "sandwich"
            if t >= fertigung.dicke_schale:
                return "schale"
            return "vollmaterial"

        arten = [art(t) for t in dicke_mm]
        zonen: list[Zone] = []
        beginn = 0
        for i in range(1, len(arten) + 1):
            if i == len(arten) or arten[i] != arten[beginn]:
                zonen.append(Zone(arten[beginn], float(x[beginn]),
                                  float(x[min(i, len(x) - 1)])))
                beginn = i
        return zonen

    def pruefe_fertigung(self, fertigung, sehne_mm: float) -> list[Befund]:
        """Prueft das Profil gegen Reglement und Fertigungsgrenzen.

        Alle Werte werden in Millimeter bei der gegebenen Sehne umgerechnet -
        das Reglement nennt absolute Masse, keine Sehnenanteile. Ein Profil,
        das bei 250 mm Sehne durchgeht, kann bei 120 mm durchfallen.
        """
        befunde: list[Befund] = []

        # --- Hinterkante ------------------------------------------------
        if fertigung.hinterkante_durch_verklebung:
            # Das aerodynamische Profil darf spitz auslaufen. Was zaehlt, ist
            # die gebaute Kante aus zwei Haeuten plus Klebespalt.
            gebaut = fertigung.hinterkante_gebaut
            befunde.append(Befund(
                "Hinterkante gebaut", gebaut >= fertigung.hinterkante_min - 1e-9,
                gebaut, fertigung.hinterkante_min, regel="T 2.4.1", stufe="hinweis",
                hinweis=f"Ergibt sich aus 2 x {fertigung.wandstaerke:g} mm Haut "
                        f"+ {fertigung.klebespalt:g} mm Kleber. Liegt unter dem "
                        f"Mass, das ein 1-mm-Radius geometrisch braucht - bei "
                        f"strenger Messung im Scrutineering ist das die "
                        f"Angriffsflaeche. Dickere Haut oder Klebespalt hilft."))

            # Ab wo ist das Profil zu duenn fuer eine Schale? Dahinter ist das
            # Bauteil Vollmaterial. Gesucht wird von HINTEN: an der Nase ist die
            # Dicke ebenfalls null, ein Vorwaertssuchen findet also immer x = 0.
            zonen = self.laminatzonen(fertigung, sehne_mm)
            hinten = [z for z in zonen if z.art == "vollmaterial" and z.bis > 0.5]
            voll_ab = hinten[0].von if hinten else 1.0
            befunde.append(Befund(
                "Vollmaterial ab", voll_ab >= fertigung.verklebung_beginn_max - 1e-9,
                voll_ab * 100.0, fertigung.verklebung_beginn_max * 100.0,
                einheit="% Sehne",
                hinweis=f"Hinter dieser Stelle ist das Profil duenner als die "
                        f"{fertigung.dicke_schale:g} mm, die zwei Haeute brauchen. "
                        f"Je frueher das beginnt, desto schwerer wird der Fluegel. "
                        f"Duennere Haut oder ein dickeres Profil verschiebt die "
                        f"Stelle nach hinten."))

            # Lohnt sich der Kern ueberhaupt?
            if fertigung.kern > 0:
                anteil = sum(z.laenge for z in zonen if z.art == "sandwich")
                befunde.append(Befund(
                    "Sandwichanteil", anteil >= 0.30, anteil * 100.0, 30.0,
                    einheit="% Sehne", stufe="hinweis",
                    hinweis=f"Ein {fertigung.kern:g} mm dicker Kern passt nur auf "
                            f"diesem Teil der Sehne hinein. Bei wenig Anteil lohnt "
                            f"der Aufwand kaum - duennerer Kern oder ganz weglassen."))

        else:
            hk = self.hinterkante_dicke * sehne_mm
            befunde.append(Befund(
                "Hinterkantendicke", hk >= fertigung.hinterkante_min - 1e-9,
                hk, fertigung.hinterkante_min, regel="T 2.4.1",
                hinweis="Hinterkante aufdicken oder Sehne vergroessern. Unter "
                        "2 mm ist der geforderte 1-mm-Radius nicht darstellbar."))

        # --- Nase --------------------------------------------------------
        nr = self.nasenradius() * sehne_mm
        befunde.append(Befund(
            "Nasenradius", nr >= fertigung.nasenradius_min - 1e-9,
            nr, fertigung.nasenradius_min, regel="T 2.4.1",
            hinweis="Nase abrunden. Vorwaertsgerichtete Kanten brauchen 3 mm."))

        return befunde

    def punktzahl(self, sehne_mm: float, toleranz_mm: float = 0.005) -> int | None:
        """Kleinste Punktzahl je Seite, mit der Creo die Kontur trifft.

        Nutzt die in M0 verifizierte Nachbildung des Creo-Splines. Damit wird
        die Punktzahl gerechnet statt geschaetzt.

        Gemessen wird gegen die GLATTE Kontur, nicht gegen den Polygonzug der
        Quellpunkte. Ein erster Versuch verglich mit linear interpolierten
        Katalogdaten - dagegen kann kein Spline gewinnen, weil der Polygonzug
        an jedem der 72 Stuetzpunkte einen Knick hat. Die Suche lief dann bis
        zur Obergrenze und meldete "keine Loesung", obwohl die Kurve laengst
        genau genug war.
        """
        o = self.oben() * float(sehne_mm)

        def kontur(n: int) -> np.ndarray:
            x = kosinus(n) * float(sehne_mm)
            return np.column_stack([x, _werte_auf(o, x)])

        return punktzahl_fuer_toleranz(kontur, toleranz_mm)

    def punktzahl_umlauf(self, sehne_mm: float,
                         toleranz_mm: float = 0.005) -> int | None:
        """Punktzahl je Seite fuer den GESCHLOSSENEN Umlauf.

        Braucht mehr Punkte als `punktzahl`, weil die geschlossene Kurve an
        der Hinterkante keinen Kurvenwechsel als Knick benutzen kann - der
        Knick muss durch dichte Stuetzpunkte erzwungen werden. Deshalb eine
        eigene Rechnung und keine Schaetzung mit einem Aufschlag.
        """
        def umlauf(n: int) -> np.ndarray:
            return self.repanelisiert(n).punkte[:-1] * float(sehne_mm)

        return punktzahl_fuer_umlauf(umlauf, toleranz_mm)

    def __str__(self) -> str:
        return (f"{self.name}  ({len(self.punkte)} Punkte, {self.herkunft})\n"
                f"  max. Dicke     {self.max_dicke*100:6.2f} % bei "
                f"{self.max_dicke_bei*100:.1f} % Sehne\n"
                f"  max. Woelbung  {self.max_woelbung*100:6.2f} %\n"
                f"  Nasenradius    {self.nasenradius()*100:6.3f} % Sehne\n"
                f"  Hinterkante    {self.hinterkante_dicke*100:6.3f} % Sehne")


KATALOG = Path(__file__).resolve().parents[2] / "profile" / "katalog"


def katalogprofile() -> list[str]:
    """Namen der verfuegbaren Katalogdateien, alphabetisch."""
    return sorted(d.name for d in KATALOG.glob("*.dat"))


_KATALOGNOTIZEN: dict | None = None


def katalognotizen() -> dict:
    """Die Notizen aus profile/katalog.yaml, einmal gelesen.

    Fehlt die Datei oder ein Eintrag, ist das kein Fehler: Ein neu abgelegtes
    .dat soll auch ohne Notiz auswaehlbar sein. Dann steht eben nichts dabei.
    """
    global _KATALOGNOTIZEN
    if _KATALOGNOTIZEN is None:
        import yaml
        pfad = KATALOG.parent / "katalog.yaml"
        try:
            _KATALOGNOTIZEN = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
        except FileNotFoundError:
            _KATALOGNOTIZEN = {}
    return _KATALOGNOTIZEN


def katalognotiz(datei: str) -> dict:
    """Notiz zu einer Katalogdatei; leeres Wortverzeichnis, wenn keine da ist."""
    return katalognotizen().get(datei, {})


def katalogoptionen() -> list[dict]:
    """Auswahlliste fuer die Oberflaeche: Klarname und Eignung statt Dateiname.

    "e423.dat" sagt niemandem etwas, "Eppler E423 - Hauptelement" schon. Der
    Wert bleibt der Dateiname, damit sich am Spec nichts aendert.
    """
    optionen = []
    for datei in katalogprofile():
        notiz = katalognotiz(datei)
        name = notiz.get("name", datei.replace(".dat", "").upper())
        eignung = notiz.get("eignung")
        optionen.append({"label": f"{name} - {eignung}" if eignung else name,
                         "value": datei})
    # Nach dem angezeigten Namen sortieren, nicht nach dem Dateinamen. Sonst
    # stuende "Wortmann FX 63-137" zwischen den Epplers und den Goettingern,
    # weil die Datei fx63137.dat heisst - die Liste sieht dann durcheinander
    # aus, obwohl nichts fehlt.
    return sorted(optionen, key=lambda o: o["label"].lower())


def profil_fuer(element) -> Profil:
    """Das wirksame Profil eines Elements, Spiegelung eingeschlossen.

    Eine Stelle fuer alle Aufrufer - Oberflaeche, Export und Report duerfen
    nicht jeder fuer sich entscheiden, ob gespiegelt wird.
    """
    profil = aus_quelle(element.profil)
    # Katalogprofile sind fuer Auftrieb gezeichnet. Fuer Abtrieb - den
    # Normalfall am Rennwagen - werden sie gespiegelt.
    richtung = getattr(element, "wirkrichtung", "abtrieb")
    richtung = getattr(richtung, "value", richtung)
    return profil.gespiegelt() if richtung == "abtrieb" else profil


def aus_quelle(quelle) -> Profil:
    """Baut ein Profil aus der Angabe im Spec.

    Die drei Profilquellen des Datenmodells landen hier an einer Stelle
    zusammen, damit Oberflaeche, Kommandozeile und Reportgenerator denselben
    Weg nehmen und nicht jede fuer sich raten muss.
    """
    art = getattr(quelle, "art", None)
    if art == "datei":
        pfad = Path(quelle.datei)
        if not pfad.is_absolute() and not pfad.exists():
            pfad = KATALOG / quelle.datei
        return Profil.aus_dat(pfad)
    if art == "naca":
        return Profil.aus_naca(quelle.woelbung, quelle.woelbungslage, quelle.dicke)
    if art == "cst":
        return Profil.aus_cst(quelle.oben, quelle.unten, quelle.hinterkante_dicke)
    raise ValueError(f"Unbekannte Profilquelle: {art!r}")


def _werte_auf(seite: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Wertet eine Profilseite formerhaltend an den Stellen x aus.

    Die Auswertestellen werden auf den tatsaechlichen Bereich der Seite
    geklemmt. Nach der Normierung reicht eine Seite naemlich nicht immer exakt
    von 0 bis 1 - die Nase kann bei 1e-6 beginnen, die Hinterkante bei
    0.999998 enden. Ohne Klemmung liefert PCHIP dort NaN, und der Fehler
    breitet sich still in Dicke, Woelbung und Toleranzrechnung aus.

    Der ueberbrueckte Bereich liegt im Bereich von Mikrometern und ist damit
    weit unter jeder Fertigungs- oder Modelltoleranz.
    """
    xs = np.clip(np.asarray(x, dtype=float), seite[0, 0], seite[-1, 0])
    return PchipInterpolator(seite[:, 0], seite[:, 1], extrapolate=False)(xs)


def _monoton(seite: np.ndarray) -> np.ndarray:
    """Macht eine Profilseite streng steigend in x.

    Direkt an der Nase laeuft die echte Kontur ein kurzes Stueck rueckwaerts -
    die Oberseite eines gewoelbten Profils beginnt unterhalb der Nase und
    kriecht erst nach vorne. Fuer alles, was die Seite als Funktion y(x)
    braucht - Dickenverlauf, Woelbung, Repanelisierung, CST-Fit - ist das
    unbrauchbar, weil np.interp monotone Stuetzstellen verlangt und sonst
    stillschweigend Unsinn liefert.

    Betroffen sind nur wenige Punkte im ersten Promille der Sehne.
    """
    x = np.maximum.accumulate(seite[:, 0])
    behalten = np.r_[True, np.diff(x) > 1e-12]
    return np.column_stack([x[behalten], seite[behalten, 1]])


def _normiere(p: np.ndarray) -> np.ndarray:
    """Klassische Sehnennormierung: Nase in den Ursprung, Hinterkante bei (1, 0).

    Die Sehne laeuft vom Nasenpunkt zum Mittelpunkt der Hinterkante. Das Profil
    wird verschoben, gedreht und skaliert, bis diese Linie auf der x-Achse
    liegt. Danach liegt x sicher in [0, 1] - Voraussetzung fuer die
    CST-Darstellung, die ausserhalb nicht definiert ist.

    Der Nasenpunkt wird als der Punkt mit dem groessten Abstand zur Hinterkante
    bestimmt, nicht als der mit dem kleinsten x. Bei gewoelbten Profilen liegt
    der vorderste Punkt naemlich wegen des senkrechten Dickenauftrags leicht
    daneben, und eine Normierung auf min(x) staucht mehrere Nasenpunkte auf
    dieselbe Stelle. Genau daran ist ein frueherer Versuch gescheitert: CST
    erzwingt y(0) = 0, die gestauchten Punkte hatten aber y bis 0.0037.
    """
    p = np.asarray(p, dtype=float)
    hinterkante = 0.5 * (p[0] + p[-1])
    i_nase = int(np.argmax(np.linalg.norm(p - hinterkante, axis=1)))
    nase = p[i_nase]

    v = hinterkante - nase
    sehne = float(np.linalg.norm(v))
    if sehne <= 0:
        raise ValueError("Sehnenlaenge ist null - ist die Punktreihenfolge richtig?")

    winkel = -math.atan2(v[1], v[0])
    c, si = math.cos(winkel), math.sin(winkel)
    q = p - nase
    q = np.column_stack([q[:, 0] * c - q[:, 1] * si,
                         q[:, 0] * si + q[:, 1] * c]) / sehne
    q[:, 0] = np.clip(q[:, 0], 0.0, 1.0)   # gegen Rundungsreste
    return q
