"""
Das Projekt: Laden, Speichern, Sperren.

Der gesamte Zustand von Aero Studio steckt in einer YAML-Datei. Die Oberflaeche
haelt nichts eigenes - sie liest das Spec, stellt es dar und schreibt
Aenderungen hinein. Drei Dinge folgen daraus:

  Oberflaeche und Kommandozeile sind automatisch gleichwertig.
  Jeder Designstand ist eine diffbare Textdatei im Git.
  Rueckgaengig ist ein Sprung zur vorherigen Version, kein eigener Mechanismus.

Der Hash ueber den Inhalt wandert spaeter als Creo-Parameter AERO_SPEC_HASH ins
CAD-Modell. Damit ist jedes Bauteil eindeutig einem Designstand zugeordnet -
die Rueckverfolgbarkeit, die im Engineering-Design-Event gefragt wird.
"""

from __future__ import annotations

import hashlib
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .modell import Element, Fertigung, ProfilAusDatei


class Meta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = "Unbenanntes Aeropaket"
    fahrzeug: str = "RSP27"
    regelstand: str = "2026_v1.1"
    bearbeiter: str = ""
    geaendert: str = ""


class ExportEinstellungen(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ordner: str = "export"
    toleranz_mm: float = Field(default=0.005, gt=0.0)
    punktzahl_manuell: Optional[int] = Field(
        default=None, gt=2,
        description="Ueberschreibt die berechnete Punktzahl. Normalerweise "
                    "leer lassen - die Rechnung ist besser als jede Schaetzung.")


class AeroSpec(BaseModel):
    """Der vollstaendige Zustand eines Aeropakets."""

    model_config = ConfigDict(extra="forbid")

    meta: Meta = Field(default_factory=Meta)
    fertigung: Fertigung = Field(default_factory=Fertigung)
    elemente: list[Element] = Field(default_factory=list)
    export: ExportEinstellungen = Field(default_factory=ExportEinstellungen)

    # ------------------------------------------------------------ Erzeugen

    @staticmethod
    def beispiel() -> "AeroSpec":
        """Ein lauffaehiger Startpunkt, damit die Oberflaeche nie leer ist."""
        return AeroSpec(
            meta=Meta(name="Frontfluegel Hauptelement", fahrzeug="RSP27"),
            fertigung=Fertigung(wandstaerke=0.6, kern=3.0),
            elemente=[Element(id="FW_E1",
                              profil=ProfilAusDatei(datei="e423.dat"),
                              sehne=250.0, anstellwinkel=-4.0)],
        )

    # -------------------------------------------------------------- Ablage

    @staticmethod
    def laden(pfad: str | Path) -> "AeroSpec":
        text = Path(pfad).read_text(encoding="utf-8")
        return AeroSpec.model_validate(yaml.safe_load(text) or {})

    def speichern(self, pfad: str | Path, bearbeiter: str = "",
                  historie: bool = True) -> Path:
        """Schreibt das Spec und legt die bisherige Fassung in die Historie.

        `historie=False` schreibt ohne Sicherung - gedacht fuer Stapellaeufe
        wie das DoE aus M8, wo fuenfhundert Varianten nacheinander entstehen
        und jede einen Historieneintrag erzeugen wuerde.
        """
        pfad = Path(pfad)
        if historie and pfad.is_file():
            # Nur sichern, wenn sich wirklich etwas aendert. Sonst stuenden
            # nach einem Nachmittag dreissig identische Eintraege in der
            # Liste, und der gesuchte Stand von vorhin laege ganz unten.
            # Die Pruefung gehoert hierher und nicht in _in_historie: Nur
            # hier ist der NEUE Inhalt bekannt.
            try:
                unveraendert = AeroSpec.laden(pfad).hash() == self.hash()
            except Exception:
                unveraendert = False      # kaputte Datei erst recht sichern
            if not unveraendert:
                _in_historie(pfad)

        self.meta.geaendert = datetime.now().strftime("%Y-%m-%d %H:%M")
        if bearbeiter:
            self.meta.bearbeiter = bearbeiter
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text(self.als_yaml(), encoding="utf-8")
        return pfad

    def als_yaml(self) -> str:
        return yaml.safe_dump(self.model_dump(mode="json"),
                              allow_unicode=True, sort_keys=False, width=100)

    # ---------------------------------------------------------------- Hash

    def hash(self) -> str:
        """Inhaltshash ueber alles, was die Geometrie bestimmt.

        Der Zeitstempel und der Bearbeiter bleiben aussen vor - sonst waere
        jedes Speichern ein neuer Stand, auch wenn sich nichts geaendert hat.
        """
        daten = self.model_dump(mode="json")
        daten["meta"].pop("geaendert", None)
        daten["meta"].pop("bearbeiter", None)
        roh = yaml.safe_dump(daten, sort_keys=True).encode("utf-8")
        return hashlib.sha1(roh).hexdigest()[:12]


# -------------------------------------------------------------- Historie
#
# Das Konzept sagt seit M1: "Rueckgaengig ist ein Sprung zur vorherigen
# Version, kein eigener Mechanismus." Das stimmt - aber nur, wenn es die
# vorherige Version noch gibt. Bis zum 24.09.2026 ueberschrieb `speichern`
# die Datei, und damit war das Versprechen leer.
#
# Warum nicht einfach auf Git verweisen: Das Team arbeitet im Werkzeug, nicht
# in der Konsole. Wer einen Nachmittag lang Flapwinkel probiert, committet
# nicht nach jedem Reglerzug - und genau dieser Stand von vor zwanzig
# Minuten ist der, den man zurueckhaben will. Git bleibt fuer die Staende,
# die jemand bewusst festhaelt.

HISTORIENORDNER = ".historie"
HISTORIE_MAX = 50


def historienordner(pfad: str | Path) -> Path:
    """Wo die alten Fassungen eines Specs liegen."""
    pfad = Path(pfad)
    return pfad.parent / HISTORIENORDNER / pfad.stem


def _in_historie(pfad: Path) -> Optional[Path]:
    """Legt die aktuelle Fassung der Datei als Stand ab.

    Unveraendert Gespeichertes erzeugt KEINEN neuen Stand: Sonst waere die
    Historie nach einem Nachmittag voller identischer Eintraege, und der
    gesuchte Stand von vorhin laege dreissig Zeilen tiefer.
    """
    try:
        alt = AeroSpec.laden(pfad)
    except Exception:
        # Eine kaputte Datei ist erst recht sicherungswuerdig - dann eben
        # ohne Hash und ohne Dopplungspruefung.
        alt, kennung = None, "unlesbar"
    else:
        kennung = alt.hash()

    ordner = historienordner(pfad)
    ordner.mkdir(parents=True, exist_ok=True)

    if alt is not None:
        juengster = _staende(ordner)[:1]
        if juengster and juengster[0].name.endswith(f"_{kennung}.yaml"):
            return None

    # Millisekunden, nicht Sekunden: Zwei Sicherungen in derselben Sekunde
    # sind beim Klicken durchaus moeglich, und dann entschiede die
    # alphabetische Sortierung nach dem HASH, welcher Stand als neuerer
    # gilt - also der Zufall.
    stempel = f"{datetime.now():%Y-%m-%dT%H-%M-%S-%f}"[:-3]
    ziel = ordner / f"{stempel}_{kennung}.yaml"
    ziel.write_text(pfad.read_text(encoding="utf-8"), encoding="utf-8")

    # Aeltestes wegwerfen, damit der Ordner nicht unbegrenzt waechst.
    for zuviel in _staende(ordner)[HISTORIE_MAX:]:
        zuviel.unlink(missing_ok=True)
    return ziel


def _staende(ordner: Path) -> list[Path]:
    """Alle Staende, neuester zuerst. Der Dateiname sortiert nach Zeit."""
    if not ordner.is_dir():
        return []
    return sorted(ordner.glob("*.yaml"), key=lambda p: p.name, reverse=True)


class Stand(BaseModel):
    """Ein Eintrag der Historie, wie ihn die Oberflaeche anzeigt."""

    model_config = ConfigDict(extra="forbid")

    datei: str
    zeitpunkt: str
    kennung: str
    name: str = ""

    @property
    def lesbar(self) -> str:
        """Der Zeitpunkt so, wie ihn jemand vorliest: 24.09.2026 14:32."""
        for form in ("%Y-%m-%dT%H-%M-%S-%f", "%Y-%m-%dT%H-%M-%S"):
            try:
                wann = datetime.strptime(self.zeitpunkt, form)
                break
            except ValueError:
                continue
        else:
            return self.zeitpunkt
        return wann.strftime("%d.%m.%Y %H:%M")


def historie(pfad: str | Path) -> list[Stand]:
    """Die verfuegbaren Staende eines Specs, neuester zuerst."""
    eintraege = []
    for datei in _staende(historienordner(pfad)):
        stamm = datei.stem
        zeit, _, kennung = stamm.rpartition("_")
        try:
            name = AeroSpec.laden(datei).meta.name
        except Exception:
            name = ""
        eintraege.append(Stand(datei=str(datei), zeitpunkt=zeit,
                               kennung=kennung, name=name))
    return eintraege


def zurueck(pfad: str | Path, stand: str | Path) -> AeroSpec:
    """Holt einen Stand zurueck und macht ihn zur aktuellen Fassung.

    Die bisherige Fassung wandert dabei selbst in die Historie - ein
    Rueckgaengig laesst sich also wieder rueckgaengig machen. Ohne das waere
    ein Fehlgriff in der Liste endgueltig, und genau davor hat man Angst,
    wenn man den Knopf zum ersten Mal drueckt.
    """
    pfad, stand = Path(pfad), Path(stand)
    if not stand.is_file():
        raise FileNotFoundError(f"Diesen Stand gibt es nicht mehr: {stand.name}")

    geholt = AeroSpec.laden(stand)
    if pfad.is_file():
        _in_historie(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(stand.read_text(encoding="utf-8"), encoding="utf-8")
    return geholt


# --------------------------------------------------------------- Sperre

class SperreBelegt(RuntimeError):
    """Wird geworfen, wenn jemand anders das Spec schon bearbeitet."""


@contextmanager
def sperre(pfad: str | Path):
    """Sichert, dass nur einer dasselbe Spec bearbeitet.

    Der Dash-Server ist schnell auch vom Nachbarrechner erreichbar. Ohne Sperre
    schreiben dann zwei Leute in dieselbe Datei, und der letzte gewinnt
    stillschweigend. Lieber eine klare Absage als ein verlorener Nachmittag.

    Ansehen darf jeder, aendern einer.
    """
    pfad = Path(pfad)
    datei = pfad.with_suffix(pfad.suffix + ".lock")
    try:
        fd = os.open(datei, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            inhaber = datei.read_text(encoding="utf-8").strip()
        except OSError:
            inhaber = "unbekannt"
        raise SperreBelegt(
            f"'{pfad.name}' wird bereits bearbeitet von: {inhaber}.\n"
            f"Wenn das nicht stimmt - etwa nach einem Absturz - kann die Datei "
            f"'{datei.name}' gefahrlos geloescht werden.") from None

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"{os.environ.get('USERNAME', 'unbekannt')} "
                    f"auf {os.environ.get('COMPUTERNAME', '?')} "
                    f"seit {datetime.now():%Y-%m-%d %H:%M}")
        yield
    finally:
        datei.unlink(missing_ok=True)
