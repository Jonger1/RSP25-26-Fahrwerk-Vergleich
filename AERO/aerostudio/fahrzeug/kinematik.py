"""
Leser für die RSP-Kinematikexporte.

Beide Formate, die euer Kinematikprogramm ausgibt, werden unterstützt:

  .txt    zwei Zeilen der Form   groesse [einheit]: [wert, wert, ...]
          Die erste Zeile ist die Abszisse, die zweite die Ordinate.

  .html   Plotly-Export. Die Kurven stecken als
          var traceN = { x: [...], y: [...], name: '...' } im Skript,
          die Achsenbeschriftungen im layout.

Der HTML-Weg ist nötig, weil es Textexporte nur für die Hubbewegung gibt.
Wanken und Lenken liegen ausschließlich als HTML vor - und genau die braucht
der Regelvalidator, weil T 8.2 die Einhaltung "with any suspension setup"
verlangt, nicht nur in der Konstruktionslage.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Kurve:
    """Eine Kennlinie: Abszisse, Ordinate, Namen und Einheiten."""

    name: str
    x_name: str
    x_einheit: str
    x: list[float]
    y_name: str
    y_einheit: str
    y: list[float]
    quelle: Path = field(default=None, repr=False)

    @property
    def spanne_x(self) -> tuple[float, float]:
        return (min(self.x), max(self.x))

    @property
    def spanne_y(self) -> tuple[float, float]:
        return (min(self.y), max(self.y))

    def __str__(self) -> str:
        xa, xe = self.spanne_x
        ya, ye = self.spanne_y
        return (f"{self.y_name} [{self.y_einheit}] "
                f"{ya:+.3f} .. {ye:+.3f}  über  "
                f"{self.x_name} [{self.x_einheit}] {xa:+.3f} .. {xe:+.3f}")


# ------------------------------------------------------------------ Textformat

_ZEILE = re.compile(r"^\s*(?P<name>.+?)\s*\[(?P<einheit>[^\]]*)\]\s*:\s*\[(?P<werte>.*)\]\s*$")


def lies_txt(pfad: str | Path) -> Kurve:
    """Liest einen Textexport. Erwartet genau zwei Datenzeilen."""
    pfad = Path(pfad)
    zeilen = [z for z in pfad.read_text(encoding="utf-8", errors="ignore").splitlines() if z.strip()]

    treffer = []
    for z in zeilen:
        m = _ZEILE.match(z)
        if m:
            werte = [float(w) for w in m.group("werte").split(",") if w.strip()]
            treffer.append((m.group("name"), m.group("einheit"), werte))

    if len(treffer) < 2:
        raise ValueError(f"{pfad.name}: erwartet zwei Datenzeilen, gefunden {len(treffer)}.")

    (xn, xe, xv), (yn, ye, yv) = treffer[0], treffer[1]
    if len(xv) != len(yv):
        raise ValueError(f"{pfad.name}: {len(xv)} Abszissen- zu {len(yv)} Ordinatenwerten.")

    return Kurve(name=pfad.stem, x_name=xn, x_einheit=xe, x=xv,
                 y_name=yn, y_einheit=ye, y=yv, quelle=pfad)


# ------------------------------------------------------------------ HTML-Format

_TRACE = re.compile(
    r"var\s+trace\d+\s*=\s*\{.*?x:\s*\[(?P<x>.*?)\].*?y:\s*\[(?P<y>.*?)\].*?"
    r"name:\s*'(?P<name>[^']*)'",
    re.S)
_ACHSE = re.compile(r"(?P<achse>[xy])axis:\s*\{.*?title:\s*'(?P<titel>[^']*)'", re.S)


def _zahlen(roh: str) -> list[float]:
    """Die Werte stehen als Zeichenketten in Anführungszeichen im Plotly-Export."""
    return [float(t) for t in re.findall(r'"?(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"?', roh)]


def _zerlege_titel(titel: str) -> tuple[str, str]:
    """Trennt 'Vehicle Roll Angle [°]' in Name und Einheit."""
    m = re.match(r"^(?P<name>.*?)\s*\[(?P<einheit>[^\]]*)\]\s*$", titel)
    if m:
        return m.group("name").strip(), m.group("einheit").strip()
    return titel.strip(), ""


def lies_html(pfad: str | Path) -> list[Kurve]:
    """Liest alle Kurven eines Plotly-Exports."""
    pfad = Path(pfad)
    t = pfad.read_text(encoding="utf-8", errors="ignore")

    achsen = {m.group("achse"): _zerlege_titel(m.group("titel")) for m in _ACHSE.finditer(t)}
    xn, xe = achsen.get("x", ("", ""))
    yn, ye = achsen.get("y", ("", ""))

    kurven = []
    for m in _TRACE.finditer(t):
        x, y = _zahlen(m.group("x")), _zahlen(m.group("y"))
        if len(x) != len(y) or not x:
            continue
        kurven.append(Kurve(name=m.group("name"), x_name=xn, x_einheit=xe, x=x,
                            y_name=yn or m.group("name"), y_einheit=ye, y=y, quelle=pfad))
    return kurven


def lies(pfad: str | Path) -> list[Kurve]:
    """Liest eine Datei beliebigen der beiden Formate."""
    pfad = Path(pfad)
    if pfad.suffix.lower() == ".txt":
        return [lies_txt(pfad)]
    if pfad.suffix.lower() in (".html", ".htm"):
        return lies_html(pfad)
    raise ValueError(f"Unbekanntes Format: {pfad.name}")


# ------------------------------------------------------------------- Envelope

@dataclass
class Envelope:
    """Der Fahrzustandsbereich, über den der Regelvalidator prüfen muss.

    T 8.2 verlangt die Einhaltung aller Grenzen "with any suspension setup with
    or without a driver". Deshalb genügt die Konstruktionslage nicht - es sind
    die Extremwerte dieser Größen, die zählen.
    """

    radhub_min: float | None = None       # mm, Radaufstandspunkt vertikal
    radhub_max: float | None = None
    wankwinkel_min: float | None = None   # Grad
    wankwinkel_max: float | None = None
    spur_min: float | None = None         # mm
    spur_max: float | None = None
    quellen: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        def z(a, b, e):
            return "nicht gefunden" if a is None else f"{a:+.3f} .. {b:+.3f} {e}"
        return ("\n".join([
            f"  Radhub      {z(self.radhub_min, self.radhub_max, 'mm')}",
            f"  Wankwinkel  {z(self.wankwinkel_min, self.wankwinkel_max, 'Grad')}",
            f"  Spurweite   {z(self.spur_min, self.spur_max, 'mm')}",
        ]))


def sammle_envelope(ordner: str | Path, achse: str = "Front") -> Envelope:
    """Durchsucht einen Exportordner rekursiv und bildet den Fahrzustandsbereich.

    `achse` ist "Front" oder "Rear" und filtert nach dem Dateinamen, weil die
    Exporte beide Achsen im selben Baum ablegen.
    """
    ordner = Path(ordner)
    env = Envelope()

    def erweitere(feld_min, feld_max, werte):
        a, b = min(werte), max(werte)
        return (a if feld_min is None else min(feld_min, a),
                b if feld_max is None else max(feld_max, b))

    # Nach ORDNER filtern, nicht nach Dateiname: In plotsFront liegen einzelne
    # Dateien mit "Rear Axle" im Namen und umgekehrt. Wer nach dem Dateinamen
    # filtert, vermischt beide Achsen - und bekommt fuer hinten die Werte von
    # vorne, ohne dass es auffaellt.
    ordner_name = f"plots{achse.capitalize()}"
    hat_ordnerstruktur = any(p.is_dir() and p.name.lower() == ordner_name.lower()
                             for p in ordner.rglob("plots*"))

    for datei in sorted(ordner.rglob("*")):
        if datei.suffix.lower() not in (".txt", ".html", ".htm"):
            continue
        if hat_ordnerstruktur:
            teile = [t.lower() for t in datei.parts]
            if ordner_name.lower() not in teile:
                continue
            # innerhalb des Achsordners zusaetzlich fremde Achse aussortieren
            fremde = "rear" if achse.lower() == "front" else "front"
            if fremde in datei.name.lower():
                continue
        elif achse.lower() not in datei.name.lower():
            continue
        try:
            kurven = lies(datei)
        except Exception:
            continue

        for k in kurven:
            beschriftungen = f"{k.x_name} {k.y_name}".lower()

            if "contactpatchverticalmovement" in k.x_name.replace(" ", "").lower():
                env.radhub_min, env.radhub_max = erweitere(env.radhub_min, env.radhub_max, k.x)
            if "contact patch z-movement" in k.y_name.lower():
                env.radhub_min, env.radhub_max = erweitere(env.radhub_min, env.radhub_max, k.y)

            if "roll angle" in k.x_name.lower():
                env.wankwinkel_min, env.wankwinkel_max = erweitere(
                    env.wankwinkel_min, env.wankwinkel_max, k.x)

            if "vehicletrack" in k.y_name.replace(" ", "").lower() or "vehicle track" in beschriftungen:
                if k.y_einheit.lower() in ("mm", ""):
                    env.spur_min, env.spur_max = erweitere(env.spur_min, env.spur_max, k.y)

            env.quellen.append(str(datei.relative_to(ordner)))

    return env
