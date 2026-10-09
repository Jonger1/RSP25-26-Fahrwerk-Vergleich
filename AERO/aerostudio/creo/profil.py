"""
Das Versionsprofil lesen - die Adapterschicht zwischen Werkzeug und Creo.

M0 Aufgabe 6 verlangt die Struktur `creo/profiles/` mit `creo8.yaml`. Die
Datei gab es seither, nur hat kein Anwendungscode sie gelesen: Die
Achsabbildung stand zusaetzlich als `STANDARD_FRAME` in formate/ibl.py, der
Befund zu Kommentarzeilen nur als Notiz. Damit war die Adapterschicht eine
Absichtserklaerung. Dieses Modul macht sie zu Code.

**Warum das mehr ist als Aufraeumen.** Die Versionsstrategie im
Meilensteinplan steht und faellt damit, dass eine neue Creo-Version *nur*
eine neue Profildatei kostet. Solange dieselbe Aussage an zwei Stellen steht,
kostet sie zwei Aenderungen an verschiedenen Orten - und beim naechsten Mal
findet jemand nur eine davon. Genau dieser Fehler ist dem Projekt bei der
Paketliste schon einmal passiert.

**Ehrlicher Fallback statt Raten.** Regel 4 der Versionsstrategie: Ist die
Creo-Version unbekannt, wird nicht geraten. Hier heisst das: Fehlt die
Profildatei oder ist sie kaputt, liefert dieses Modul die im Code
hinterlegten Vorgaben und sagt ueber `profil().vollstaendig` und
`profil().maengel`, dass es das getan hat. Es faellt nie stillschweigend auf
etwas Erfundenes zurueck.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

PROFILORDNER = Path(__file__).resolve().parent / "profiles"

# Wird genommen, wenn die Profildatei fehlt oder unlesbar ist. Bewusst
# identisch zur Angabe in creo8.yaml - test_creo_profil.py haelt beide
# zusammen, damit sie nicht auseinanderlaufen koennen.
VORGABE_FRAME = {"creo_x": "+x", "creo_y": "+z", "creo_z": "-y"}

# Werte in der Profildatei, die keine Antwort sind, sondern eine offene Frage.
# Zwei Sorten, und die Unterscheidung ist der ganze Punkt:
#
#   JETZT_OFFEN  blockiert die Abnahme des laufenden Meilensteins.
#   VERTAGT      ist bewusst einem spaeteren Meilenstein zugeordnet und darf
#                den laufenden nicht aufhalten. "OFFEN_BIS_M5" ist eine
#                getroffene Entscheidung, keine Nachlaessigkeit.
#
# Ohne diese Trennung waere M0 nie abzuschliessen: In der Datei stehen seit
# jeher Eintraege, die erst M4 und M5 beantworten koennen.
JETZT_OFFEN = {"AUSFUELLEN", "OFFEN"}
VERTAGT = {"UNGEPRUEFT", "ENTFAELLT"}


def _art(wert) -> str | None:
    """"jetzt", "vertagt" oder None, wenn es eine richtige Antwort ist."""
    if not isinstance(wert, str):
        return None
    text = wert.strip().upper()
    if text in JETZT_OFFEN:
        return "jetzt"
    if text in VERTAGT or text.startswith("OFFEN_BIS_"):
        return "vertagt"
    return None


@dataclass
class Creoprofil:
    """Ein gelesenes Versionsprofil, mit ehrlicher Auskunft ueber Luecken."""

    id: str
    daten: dict
    quelle: Path | None
    maengel: list[str] = field(default_factory=list)

    @property
    def vollstaendig(self) -> bool:
        """Wurde die Datei gelesen, oder sind das die Vorgaben aus dem Code?"""
        return self.quelle is not None and not self.maengel

    # ------------------------------------------------------------- Zugriffe

    def _pfad(self, *schluessel, vorgabe=None):
        knoten = self.daten
        for s in schluessel:
            if not isinstance(knoten, dict) or s not in knoten:
                return vorgabe
            knoten = knoten[s]
        return knoten

    @property
    def frame(self) -> dict[str, str]:
        """Achsabbildung Werkzeug -> Creo, die einzige Wahrheit dafuer."""
        gelesen = self._pfad("export", "frame_map")
        if not isinstance(gelesen, dict):
            return dict(VORGABE_FRAME)
        fehlend = [s for s in VORGABE_FRAME if s not in gelesen]
        if fehlend:
            return dict(VORGABE_FRAME)
        return {s: str(gelesen[s]) for s in VORGABE_FRAME}

    # Die drei Stellen, an denen eine Kommentarzeile stehen kann. Der
    # Exporter schreibt "vor_kopf"; die beiden anderen sind Rueckfallebenen,
    # falls Creo genau diese Stelle nicht mag.
    KOMMENTARORTE = ("ibl_kommentar_vor_kopf", "ibl_kommentar_nach_kopf",
                     "ibl_kommentar_zwischen_sektionen")

    @property
    def kommentare_erlaubt(self) -> bool:
        """Darf eine .ibl "!"-Kommentarzeilen im Kopf tragen?

        ABGELEITET aus den drei Einzelbefunden, nicht getrennt gepflegt: Was
        sich ausrechnen laesst, soll niemand eintippen - ein vierter Eintrag
        waere nur eine weitere Stelle, an der jemand ein `false` vergisst.

        Solange die Befunde offen sind, wird geschrieben. Das ist der Stand,
        auf dem das Werkzeug seit M1 laeuft, und ein Fehlschlag faellt beim
        Import sofort auf - anders als eine Spiegelung, die man der Form
        nicht ansieht. Sobald in creo8.yaml `ibl_kommentar_vor_kopf: false`
        steht, hoert der Exporter von selbst damit auf, ohne dass eine Zeile
        Code geaendert werden muss.
        """
        # Der Exporter schreibt vor den Kopf - nur dieser Befund entscheidet.
        wert = self._pfad("befunde", "ibl_kommentar_vor_kopf")
        if isinstance(wert, bool):
            return wert
        return True

    @property
    def kommentarbefund_offen(self) -> bool:
        """Ist auch nur einer der drei Kommentarbefunde noch ungeprueft?"""
        return any(not isinstance(self._pfad("befunde", ort), bool)
                   for ort in self.KOMMENTARORTE)

    def kommentarorte(self) -> dict[str, bool | None]:
        """Die drei Befunde einzeln - True, False oder None fuer ungeprueft."""
        return {ort: (w if isinstance(w := self._pfad("befunde", ort), bool)
                      else None)
                for ort in self.KOMMENTARORTE}

    def offene_punkte(self, art: str = "jetzt") -> list[tuple[str, str]]:
        """Eintraege, die noch auf eine Antwort warten, mit Pfadangabe.

        art  "jetzt"   blockiert die Abnahme des laufenden Meilensteins
             "vertagt" bewusst einem spaeteren Meilenstein zugeordnet

        Grundlage der M0-Abnahme: Die Checkliste im Pruefprotokoll wird von
        Hand gepflegt und veraltet damit - sie stand am 21.09. noch auf einem
        Stand, den die Profildatei laengst ueberholt hatte. Diese Liste kann
        das nicht, weil sie die Datei selbst liest.
        """
        gefunden: list[tuple[str, str]] = []

        def durchgehen(knoten, pfad: str) -> None:
            if isinstance(knoten, dict):
                for schluessel, wert in knoten.items():
                    durchgehen(wert, f"{pfad}.{schluessel}" if pfad else schluessel)
            elif _art(knoten) == art:
                gefunden.append((pfad, str(knoten).strip()))

        durchgehen(self.daten, "")
        return gefunden


def _lade(pfad: Path) -> Creoprofil:
    maengel: list[str] = []
    try:
        daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        return Creoprofil(id=pfad.stem, daten={}, quelle=None,
                          maengel=[f"Profildatei {pfad.name} fehlt"])
    except Exception as fehler:
        return Creoprofil(id=pfad.stem, daten={}, quelle=None,
                          maengel=[f"Profildatei {pfad.name} unlesbar: {fehler}"])

    if not isinstance(daten, dict):
        return Creoprofil(id=pfad.stem, daten={}, quelle=None,
                          maengel=[f"Profildatei {pfad.name} enthaelt kein Abbild"])

    frame = (daten.get("export") or {}).get("frame_map")
    if not isinstance(frame, dict) or any(s not in frame for s in VORGABE_FRAME):
        maengel.append("export.frame_map fehlt oder ist unvollstaendig - "
                       "es gilt die Vorgabe aus dem Code")

    return Creoprofil(id=pfad.stem, daten=daten, quelle=pfad, maengel=maengel)


@lru_cache(maxsize=None)
def profil(name: str = "creo8") -> Creoprofil:
    """Laedt ein Versionsprofil. Ergebnis wird gehalten, die Datei ist statisch."""
    return _lade(PROFILORDNER / f"{name}.yaml")


def profile() -> list[str]:
    """Alle vorhandenen Versionsprofile, nach Name."""
    return sorted(p.stem for p in PROFILORDNER.glob("*.yaml"))
