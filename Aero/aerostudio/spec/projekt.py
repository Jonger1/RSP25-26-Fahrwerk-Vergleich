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

    def speichern(self, pfad: str | Path, bearbeiter: str = "") -> Path:
        pfad = Path(pfad)
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
